from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from apps.orders.models import Cart, Order
from apps.orders.serializers import (
    CartItemAddSerializer,
    CartItemUpdateSerializer,
    CartSerializer,
    CheckoutSerializer,
    OrderSerializer,
)
from apps.orders.services import CartService, CheckoutService


@extend_schema_view(
    list=extend_schema(
        summary="Получить текущую корзину пользователя",
        description="Возвращает состав корзины текущего пользователя со всеми позициями.",
        responses={200: CartSerializer},
        tags=["Cart"],
    ),
)
class CartViewSet(viewsets.ViewSet):
    """
    Управление текущей корзиной покупок авторизованного пользователя.
    """

    permission_classes = [permissions.IsAuthenticated]

    def _get_cart(self) -> Cart:
        cart, _ = Cart.objects.prefetch_related("items__product").get_or_create(
            user=self.request.user
        )
        return cart

    def list(self, request, *args, **kwargs):
        """
        Просмотр корзины текущего пользователя.
        """
        cart = self._get_cart()
        serializer = CartSerializer(cart)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Добавить товар в корзину",
        description="Добавляет товар в корзину или увеличивает его количество, если он уже есть.",
        request=CartItemAddSerializer,
        responses={
            201: CartSerializer,
            400: OpenApiResponse(description="Ошибка валидации или нехватка остатков"),
        },
        tags=["Cart"],
    )
    @action(detail=False, methods=["post"], url_path="items")
    def add_item(self, request):
        serializer = CartItemAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        product = serializer.validated_data["product_id"]
        quantity = serializer.validated_data["quantity"]
        cart = self._get_cart()

        try:
            CartService.add_to_cart(cart=cart, product=product, quantity=quantity)
        except DjangoValidationError as exc:
            raise DRFValidationError(detail=exc.messages) from exc

        # Перезагружаем корзину с предзагрузкой связей для корректного ответа
        cart = Cart.objects.prefetch_related("items__product").get(id=cart.id)
        return Response(CartSerializer(cart).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Изменить количество или удалить товар из корзины",
        description=(
            "PUT / PATCH: Устанавливает новое количество для конкретного товара в корзине.\n"
            "DELETE: Удаляет указанный товар из корзины текущего пользователя."
        ),
        request=CartItemUpdateSerializer,
        responses={
            200: CartSerializer,
            400: OpenApiResponse(description="Ошибка валидации или товар не найден"),
        },
        tags=["Cart"],
    )
    @action(
        detail=False,
        methods=["put", "patch", "delete"],
        url_path=r"items/(?P<product_id>\d+)",
    )
    def manage_item(self, request, product_id=None):
        cart = self._get_cart()

        if request.method == "DELETE":
            CartService.remove_from_cart(cart=cart, product_id=int(product_id))
            cart = Cart.objects.prefetch_related("items__product").get(id=cart.id)
            return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)

        serializer = CartItemUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        quantity = serializer.validated_data["quantity"]

        try:
            CartService.update_quantity(cart=cart, product_id=int(product_id), quantity=quantity)
        except DjangoValidationError as exc:
            raise DRFValidationError(detail=exc.messages) from exc

        cart = Cart.objects.prefetch_related("items__product").get(id=cart.id)
        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Очистить корзину",
        description="Удаляет все позиции из корзины текущего пользователя.",
        responses={200: CartSerializer},
        tags=["Cart"],
    )
    @action(detail=False, methods=["post"], url_path="clear")
    def clear(self, request):
        cart = self._get_cart()
        cart.clear()
        cart = Cart.objects.prefetch_related("items__product").get(id=cart.id)
        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(
        summary="Список заказов",
        description="Возвращает историю заказов текущего пользователя (или всех для персонала).",
        tags=["Orders"],
    ),
    retrieve=extend_schema(
        summary="Детальная информация о заказе",
        description="Возвращает подробности заказа с позициями и статусом.",
        tags=["Orders"],
    ),
)
class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Просмотр истории заказов, оформление (checkout) и отмена заказов.
    """

    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ["status"]
    search_fields = ["idempotency_key", "shipping_address", "items__product__name"]
    ordering_fields = ["created_at", "total_amount", "status"]
    ordering = ["-created_at"]

    def get_queryset(self):
        user = self.request.user
        queryset = Order.objects.select_related("user").prefetch_related("items__product")
        if getattr(user, "is_staff", False) or getattr(user, "role", "") in ("manager", "admin"):
            return queryset
        return queryset.filter(user=user)

    @extend_schema(
        summary="Оформить заказ из корзины (Checkout)",
        description=(
            "Создает заказ на основе текущей корзины пользователя с безопасным списанием "
            "остатков (select_for_update) и защитой от повторных запросов (idempotency_key)."
        ),
        request=CheckoutSerializer,
        responses={
            201: OrderSerializer,
            400: OpenApiResponse(
                description="Ошибка валидации данных, остатков или пустая корзина"
            ),
        },
        tags=["Orders"],
    )
    @action(detail=False, methods=["post"], url_path="checkout")
    def checkout(self, request):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        shipping_address = serializer.validated_data["shipping_address"]
        idempotency_key = serializer.validated_data.get("idempotency_key")

        try:
            order = CheckoutService.create_order_from_cart(
                user=request.user,
                shipping_address=shipping_address,
                idempotency_key=idempotency_key,
            )
        except DjangoValidationError as exc:
            raise DRFValidationError(detail=exc.messages) from exc

        order = (
            Order.objects.select_related("user").prefetch_related("items__product").get(id=order.id)
        )
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Отменить заказ",
        description="Отменяет заказ и возвращает остатки товаров на склад.",
        request=None,
        responses={
            200: OrderSerializer,
            400: OpenApiResponse(description="Заказ не может быть отменен"),
        },
        tags=["Orders"],
    )
    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        order = self.get_object()

        try:
            cancelled_order = CheckoutService.cancel_order(order=order, user=request.user)
        except DjangoValidationError as exc:
            raise DRFValidationError(detail=exc.messages) from exc

        cancelled_order = (
            Order.objects.select_related("user")
            .prefetch_related("items__product")
            .get(id=cancelled_order.id)
        )
        return Response(OrderSerializer(cancelled_order).data, status=status.HTTP_200_OK)
