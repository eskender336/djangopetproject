from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class Category(models.Model):
    """
    Категория товаров с поддержкой иерархической вложенности (дерево категорий).
    """

    name = models.CharField(
        _("Название"),
        max_length=255,
    )
    slug = models.SlugField(
        _("Slug"),
        max_length=255,
        unique=True,
        db_index=True,
        help_text=_("Уникальный URL-идентификатор категории."),
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        verbose_name=_("Родительская категория"),
    )
    is_active = models.BooleanField(
        _("Активна"),
        default=True,
        help_text=_("Отображать категорию в каталоге."),
    )
    created_at = models.DateTimeField(
        _("Дата создания"),
        auto_now_add=True,
    )

    class Meta:
        verbose_name = _("Категория")
        verbose_name_plural = _("Категории")
        ordering = ["name"]

    def __str__(self) -> str:
        if self.parent:
            return f"{self.parent} -> {self.name}"
        return self.name


class Tag(models.Model):
    """
    Тег для гибкой группировки и фильтрации товаров.
    """

    name = models.CharField(
        _("Название"),
        max_length=100,
    )
    slug = models.SlugField(
        _("Slug"),
        max_length=100,
        unique=True,
        db_index=True,
        help_text=_("Уникальный URL-идентификатор тега."),
    )

    class Meta:
        verbose_name = _("Тег")
        verbose_name_plural = _("Теги")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Product(models.Model):
    """
    Основная модель товара каталога.
    """

    name = models.CharField(
        _("Название"),
        max_length=255,
    )
    slug = models.SlugField(
        _("Slug"),
        max_length=255,
        unique=True,
        db_index=True,
        help_text=_("Уникальный URL-идентификатор товара."),
    )
    sku = models.CharField(
        _("Артикул (SKU)"),
        max_length=100,
        unique=True,
        db_index=True,
        help_text=_("Уникальный складской номер товара."),
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name=_("Категория"),
    )
    tags = models.ManyToManyField(
        Tag,
        blank=True,
        related_name="products",
        verbose_name=_("Теги"),
    )
    description = models.TextField(
        _("Описание"),
        blank=True,
    )
    price = models.DecimalField(
        _("Цена"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    stock = models.PositiveIntegerField(
        _("Остаток на складе"),
        default=0,
    )
    is_active = models.BooleanField(
        _("Активен"),
        default=True,
        help_text=_("Доступен ли товар для покупки и отображения в каталоге."),
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
        verbose_name = _("Товар")
        verbose_name_plural = _("Товары")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["category", "price"], name="catalog_prod_cat_price_idx"),
            models.Index(fields=["created_at"], name="catalog_prod_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.sku})"

    @property
    def in_stock(self) -> bool:
        return self.stock > 0


class ProductImage(models.Model):
    """
    Изображение товара с возможностью назначения главного фото.
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name=_("Товар"),
    )
    image = models.ImageField(
        _("Изображение"),
        upload_to="catalog/products/%Y/%m/",
        max_length=500,
    )
    is_main = models.BooleanField(
        _("Главное изображение"),
        default=False,
    )
    created_at = models.DateTimeField(
        _("Дата загрузки"),
        auto_now_add=True,
    )

    class Meta:
        verbose_name = _("Изображение товара")
        verbose_name_plural = _("Изображения товаров")
        ordering = ["-is_main", "-created_at"]

    def __str__(self) -> str:
        return f"Изображение для {self.product.name}"
