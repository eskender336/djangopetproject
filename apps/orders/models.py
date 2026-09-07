from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class Cart(models.Model):
    """
    Корзина покупок пользователя или гостевой сессии.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="cart",
        verbose_name=_("Пользователь"),
    )
    session_key = models.CharField(
        _("Ключ сессии"),
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
    )
    created_at = models.DateTimeField(
        _("Дата создания"),
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        _("Дата обновления"),
        auto_now=True,
    )

    class Meta:
        verbose_name = _("Корзина")
        verbose_name_plural = _("Корзины")
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        if self.user:
            return f"Корзина пользователя {self.user}"
        return f"Анонимная корзина ({self.session_key})"

    @property
    def total_price(self) -> Decimal:
        """
        Подсчет суммарной стоимости всех позиций в корзине.
        """
        return sum(
            (item.total_price for item in self.items.all()),
            start=Decimal("0.00"),
        )

    @property
    def total_items_count(self) -> int:
        """
        Подсчет общего количества единиц товаров в корзине.
        """
        return sum(item.quantity for item in self.items.all())

    @property
    def is_empty(self) -> bool:
        """
        Проверка, пуста ли корзина.
        """
        return not self.items.exists()

    def clear(self) -> None:
        """
        Очистить все позиции в корзине.
        """
        self.items.all().delete()


class CartItem(models.Model):
    """
    Элемент (позиция товара) в корзине.
    """

    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Корзина"),
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="cart_items",
        verbose_name=_("Товар"),
    )
    quantity = models.PositiveIntegerField(
        _("Количество"),
        default=1,
        validators=[MinValueValidator(1)],
    )
    created_at = models.DateTimeField(
        _("Дата добавления"),
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        _("Дата обновления"),
        auto_now=True,
    )

    class Meta:
        verbose_name = _("Элемент корзины")
        verbose_name_plural = _("Элементы корзины")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "product"],
                name="unique_cart_product",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product.name} x {self.quantity}"

    @property
    def total_price(self) -> Decimal:
        """
        Стоимость позиции (цена товара * количество).
        """
        return self.product.price * self.quantity


class OrderStatus(models.TextChoices):
    PENDING = "pending", _("В ожидании")
    PAID = "paid", _("Оплачен")
    SHIPPED = "shipped", _("Отправлен")
    DELIVERED = "delivered", _("Доставлен")
    CANCELLED = "cancelled", _("Отменен")


class Order(models.Model):
    """
    Модель оформленного заказа.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="orders",
        verbose_name=_("Пользователь"),
    )
    status = models.CharField(
        _("Статус заказа"),
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING,
        db_index=True,
    )
    total_amount = models.DecimalField(
        _("Итоговая сумма"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    shipping_address = models.TextField(
        _("Адрес доставки"),
    )
    idempotency_key = models.CharField(
        _("Ключ идемпотентности"),
        max_length=255,
        null=True,
        blank=True,
        unique=True,
        db_index=True,
    )
    created_at = models.DateTimeField(
        _("Дата создания"),
        auto_now_add=True,
        db_index=True,
    )
    updated_at = models.DateTimeField(
        _("Дата обновления"),
        auto_now=True,
    )

    class Meta:
        verbose_name = _("Заказ")
        verbose_name_plural = _("Заказы")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"], name="orders_order_user_status_idx"),
            models.Index(fields=["created_at"], name="orders_order_created_idx"),
        ]

    def __str__(self) -> str:
        return f"Заказ #{self.id} от {self.user} ({self.get_status_display()})"

    @property
    def can_cancel(self) -> bool:
        """
        Возможность отмены заказа покупателем.
        """
        return self.status in (OrderStatus.PENDING, OrderStatus.PAID)


class OrderItem(models.Model):
    """
    Позиция (товар) внутри оформленного заказа.
    """

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Заказ"),
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="order_items",
        verbose_name=_("Товар"),
    )
    price = models.DecimalField(
        _("Цена за единицу"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    quantity = models.PositiveIntegerField(
        _("Количество"),
        default=1,
        validators=[MinValueValidator(1)],
    )
    created_at = models.DateTimeField(
        _("Дата добавления"),
        auto_now_add=True,
    )

    class Meta:
        verbose_name = _("Позиция заказа")
        verbose_name_plural = _("Позиции заказа")
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.product.name} ({self.quantity} шт.)"

    @property
    def total_price(self) -> Decimal:
        """
        Стоимость позиции (цена фиксации * количество).
        """
        return self.price * self.quantity
