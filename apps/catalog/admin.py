from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.catalog.models import Category, Product, ProductImage, Tag


class ProductImageInline(admin.TabularInline):
    """
    Инлайн-редактирование изображений товара на странице товара.
    """

    model = ProductImage
    extra = 1
    fields = ("image", "image_preview", "is_main", "created_at")
    readonly_fields = ("image_preview", "created_at")

    def image_preview(self, obj: ProductImage):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height: 60px; max-width: 60px; border-radius: 4px;" />',
                obj.image.url,
            )
        return "-"

    image_preview.short_description = _("Превью")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "parent", "is_active", "created_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    list_select_related = ("parent",)
    ordering = ("name",)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "sku",
        "category",
        "price",
        "stock",
        "in_stock_display",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active", "category", "created_at")
    search_fields = ("name", "sku", "description")
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ("tags",)
    list_select_related = ("category",)
    inlines = [ProductImageInline]
    ordering = ("-created_at",)

    @admin.display(boolean=True, description=_("В наличии"))
    def in_stock_display(self, obj: Product) -> bool:
        return obj.in_stock


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "image_preview", "is_main", "created_at")
    list_filter = ("is_main", "created_at")
    search_fields = ("product__name", "product__sku")
    list_select_related = ("product",)
    ordering = ("-created_at",)

    def image_preview(self, obj: ProductImage):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height: 50px; max-width: 50px; border-radius: 4px;" />',
                obj.image.url,
            )
        return "-"

    image_preview.short_description = _("Превью")
