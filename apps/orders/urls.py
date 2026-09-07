from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.orders.views import CartViewSet, OrderViewSet
from apps.orders.webhooks import payment_webhook_view

app_name = "orders"

router = DefaultRouter()
router.register("cart", CartViewSet, basename="cart")
router.register("orders", OrderViewSet, basename="order")

urlpatterns = [
    path("webhooks/payment/", payment_webhook_view, name="payment_webhook"),
    path("", include(router.urls)),
]
