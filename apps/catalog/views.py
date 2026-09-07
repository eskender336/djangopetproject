from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.catalog.filters import ProductFilter
from apps.catalog.models import Category, Product, Tag
from apps.catalog.permissions import IsAdminOrManagerOrReadOnly
from apps.catalog.serializers import (
    CategorySerializer,
    ProductDetailSerializer,
    ProductListSerializer,
    ProductWriteSerializer,
    TagSerializer,
)
from apps.catalog.services import CatalogCacheService
from apps.users.models import UserRole


@extend_schema_view(
    list=extend_schema(summary="Список категорий", tags=["Categories"]),
    retrieve=extend_schema(summary="Детальная информация о категории", tags=["Categories"]),
)
class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Эндпоинт для просмотра списка и детальной информации о категориях товаров.
    """

    queryset = Category.objects.select_related("parent").all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["parent", "is_active"]
    search_fields = ["name", "slug"]
    ordering_fields = ["name", "created_at"]
    ordering = ["name"]


@extend_schema_view(
    list=extend_schema(summary="Список тегов", tags=["Tags"]),
    retrieve=extend_schema(summary="Детальная информация о теге", tags=["Tags"]),
)
class TagViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Эндпоинт для просмотра списка и информации о тегах.
    """

    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "slug"]
    ordering_fields = ["name"]
    ordering = ["name"]


@extend_schema_view(
    list=extend_schema(summary="Список товаров", tags=["Products"]),
    retrieve=extend_schema(summary="Детальная информация о товаре", tags=["Products"]),
    create=extend_schema(summary="Создать новый товар (Менеджер/Админ)", tags=["Products"]),
    update=extend_schema(summary="Обновить товар (Менеджер/Админ)", tags=["Products"]),
    partial_update=extend_schema(
        summary="Частично обновить товар (Менеджер/Админ)", tags=["Products"]
    ),
    destroy=extend_schema(summary="Удалить товар (Менеджер/Админ)", tags=["Products"]),
)
class ProductViewSet(viewsets.ModelViewSet):
    """
    Эндпоинт для работы с товарами.
    Предоставляет оптимизированный список, детальный просмотр и управление товарами.
    """

    queryset = Product.objects.select_related("category").prefetch_related("tags", "images")
    permission_classes = [IsAdminOrManagerOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ProductFilter
    search_fields = ["name", "description", "sku"]
    ordering_fields = ["price", "created_at", "name", "stock"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = Product.objects.select_related("category").prefetch_related("tags", "images")
        user = self.request.user

        # Для неавторизованных пользователей и обычных покупателей показываем только активные товары
        is_privileged = user.is_authenticated and (
            user.is_staff
            or user.is_superuser
            or getattr(user, "role", None) in (UserRole.ADMIN, UserRole.MANAGER)
        )
        if not is_privileged:
            qs = qs.filter(is_active=True, category__is_active=True)

        return qs

    def get_serializer_class(self):
        if self.action in ("list", "popular"):
            return ProductListSerializer
        if self.action in ("create", "update", "partial_update"):
            return ProductWriteSerializer
        return ProductDetailSerializer

    @extend_schema(
        summary="Список популярных товаров (кэшируется в Redis)",
        description="Возвращает закэшированный в Redis список популярных товаров.",
        responses={200: ProductListSerializer(many=True)},
        tags=["Products"],
    )
    @action(
        detail=False, methods=["get"], url_path="popular", permission_classes=[permissions.AllowAny]
    )
    def popular(self, request):
        try:
            limit = int(request.query_params.get("limit", 10))
            limit = max(1, min(limit, 100))
        except (TypeError, ValueError):
            limit = 10
        data = CatalogCacheService.get_popular_products(limit=limit)
        return Response(data, status=status.HTTP_200_OK)
