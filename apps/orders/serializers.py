from rest_framework import serializers

from apps.catalog.models import Product
from apps.orders.models import Cart, CartItem, Order, OrderItem


class CartProductShortSerializer(serializers.ModelSerializer):
    """
    Краткая информация о товаре для элементов корзины и позиций заказа.
    """

    class Meta:
        model = Product
        fields = ("id", "name", "slug", "sku", "price", "stock", "in_stock")
        read_only_fields = fields


class CartItemSerializer(serializers.ModelSerializer):
    """
    Сериализатор элемента корзины с подсчетом стоимости позиции.
    """

    product = CartProductShortSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True),
        source="product",
        write_only=True,
    )
    total_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = CartItem
        fields = (
            "id",
            "product",
            "product_id",
            "quantity",
            "total_price",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "total_price", "created_at", "updated_at")

    def validate_quantity(self, value: int) -> int:
        if value < 1:
            raise serializers.ValidationError("Количество товара должно быть не менее 1.")
        return value


class CartItemAddSerializer(serializers.Serializer):
    """
    Сериализатор добавления товара в корзину.
    """

    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True),
    )
    quantity = serializers.IntegerField(
        default=1,
        min_value=1,
    )

    def validate(self, attrs):
        product = attrs["product_id"]
        quantity = attrs["quantity"]
        if quantity > product.stock:
            raise serializers.ValidationError(
                {"quantity": f"На складе доступно только {product.stock} шт."}
            )
        return attrs


class CartItemUpdateSerializer(serializers.Serializer):
    """
    Сериализатор изменения количества товара в корзине.
    """

    quantity = serializers.IntegerField(
        min_value=1,
        required=True,
    )


class CartSerializer(serializers.ModelSerializer):
    """
    Сериализатор корзины пользователя с вычисляемой суммарной стоимостью.
    """

    items = CartItemSerializer(many=True, read_only=True)
    total_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )
    total_items_count = serializers.IntegerField(read_only=True)
    is_empty = serializers.BooleanField(read_only=True)

    class Meta:
        model = Cart
        fields = (
            "id",
            "items",
            "total_items_count",
            "total_price",
            "is_empty",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class OrderItemSerializer(serializers.ModelSerializer):
    """
    Сериализатор позиции оформленного заказа.
    """

    product = CartProductShortSerializer(read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    total_price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = OrderItem
        fields = (
            "id",
            "product",
            "product_name",
            "price",
            "quantity",
            "total_price",
            "created_at",
        )
        read_only_fields = fields


class OrderSerializer(serializers.ModelSerializer):
    """
    Сериализатор оформленного заказа.
    """

    items = OrderItemSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    can_cancel = serializers.BooleanField(read_only=True)

    class Meta:
        model = Order
        fields = (
            "id",
            "user",
            "user_email",
            "status",
            "status_display",
            "total_amount",
            "shipping_address",
            "idempotency_key",
            "items",
            "can_cancel",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "user",
            "user_email",
            "status",
            "status_display",
            "total_amount",
            "can_cancel",
            "created_at",
            "updated_at",
        )


class CheckoutSerializer(serializers.Serializer):
    """
    Сериализатор параметров оформления заказа из корзины.
    """

    shipping_address = serializers.CharField(
        max_length=1000,
        min_length=5,
        required=True,
        error_messages={
            "required": "Адрес доставки обязателен для оформления заказа.",
            "blank": "Адрес доставки не может быть пустым.",
        },
    )
    idempotency_key = serializers.CharField(
        max_length=255,
        required=False,
        allow_null=True,
        allow_blank=True,
        default=None,
    )

    def validate_shipping_address(self, value: str) -> str:
        value = value.strip()
        if len(value) < 5:
            raise serializers.ValidationError("Адрес доставки слишком короткий.")
        return value
