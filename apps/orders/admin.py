from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from apps.orders.models import Cart, CartItem, Order, OrderItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    fields = ("product", "quantity", "get_item_price", "get_total_price", "created_at")
    readonly_fields = ("get_item_price", "get_total_price", "created_at")

    @admin.display(description=_("Цена за ед."))
    def get_item_price(self, obj):
        return f"{obj.product.price} руб." if obj.product else "-"

    @admin.display(description=_("Сумма"))
    def get_total_price(self, obj):
        return f"{obj.total_price} руб." if obj.product else "-"


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "session_key",
        "get_items_count",
        "get_total_price",
        "created_at",
        "updated_at",
    )
    list_select_related = ("user",)
    search_fields = ("user__email", "session_key")
    readonly_fields = ("created_at", "updated_at", "get_total_price")
    inlines = [CartItemInline]

    @admin.display(description=_("Кол-во товаров"))
    def get_items_count(self, obj):
        return obj.total_items_count

    @admin.display(description=_("Итоговая сумма"))
    def get_total_price(self, obj):
        return f"{obj.total_price} руб."


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = ("product", "price", "quantity", "get_total_price", "created_at")
    readonly_fields = ("price", "get_total_price", "created_at")

    @admin.display(description=_("Сумма"))
    def get_total_price(self, obj):
        return f"{obj.total_price} руб."


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "status",
        "total_amount",
        "idempotency_key",
        "created_at",
        "updated_at",
    )
    list_filter = ("status", "created_at")
    list_select_related = ("user",)
    search_fields = ("user__email", "idempotency_key", "shipping_address")
    readonly_fields = ("created_at", "updated_at", "idempotency_key")
    ordering = ("-created_at",)
    inlines = [OrderItemInline]

    fieldsets = (
        (None, {"fields": ("user", "status", "total_amount")}),
        (_("Доставка"), {"fields": ("shipping_address",)}),
        (_("Служебная информация"), {"fields": ("idempotency_key", "created_at", "updated_at")}),
    )
