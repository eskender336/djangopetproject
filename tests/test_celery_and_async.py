import asyncio
import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core import mail
from django.core.cache import cache
from django.test import Client, RequestFactory
from django.utils import timezone

from apps.catalog.models import Category, Product
from apps.catalog.services import CatalogCacheService
from apps.orders.models import Cart, CartItem, Order, OrderItem, OrderStatus
from apps.orders.services import CheckoutService
from apps.orders.tasks import (
    cancel_unpaid_expired_orders_task,
    generate_order_receipt_task,
    send_order_confirmation_email_task,
)
from apps.orders.webhooks import payment_webhook_view
from apps.users.models import User, UserRole
from config.celery import app as celery_app


@pytest.fixture
def catalog_category(db):
    return Category.objects.create(name="Тестовая категория", slug="test-category-celery")


@pytest.fixture
def catalog_product(db, catalog_category):
    return Product.objects.create(
        name="Ноутбук Pro",
        slug="laptop-pro",
        sku="SKU-LAP-999",
        category=catalog_category,
        price=Decimal("120000.00"),
        stock=15,
        is_active=True,
    )


@pytest.fixture
def buyer_user(db):
    return User.objects.create_user(
        email="buyer@example.com",
        password="SecurePassword123!",
        first_name="Алексей",
        last_name="Смирнов",
        role=UserRole.CUSTOMER,
    )


@pytest.fixture
def sample_order(db, buyer_user, catalog_product):
    order = Order.objects.create(
        user=buyer_user,
        status=OrderStatus.PENDING,
        total_amount=Decimal("120000.00"),
        shipping_address="г. Екатеринбург, ул. Мира, д. 19",
        idempotency_key="sample-order-celery-1",
    )
    OrderItem.objects.create(
        order=order,
        product=catalog_product,
        price=Decimal("120000.00"),
        quantity=1,
    )
    return order


# ==============================================================================
# 1. Celery Configuration & Beat Schedule Tests
# ==============================================================================


class TestCeleryConfiguration:
    def test_celery_app_initialization(self):
        assert celery_app is not None
        assert celery_app.main == "djangopetproject"

    def test_beat_schedule_contains_cancel_expired_orders_task(self):
        assert "cancel-unpaid-expired-orders-every-5-minutes" in celery_app.conf.beat_schedule
        entry = celery_app.conf.beat_schedule["cancel-unpaid-expired-orders-every-5-minutes"]
        assert entry["task"] == "apps.orders.tasks.cancel_unpaid_expired_orders_task"


# ==============================================================================
# 2. Celery Background Tasks Tests
# ==============================================================================


@pytest.mark.django_db
class TestCeleryTasks:
    def test_send_order_confirmation_email_task_success(self, sample_order):
        mail.outbox.clear()
        result = send_order_confirmation_email_task(sample_order.id)

        assert result["status"] == "sent"
        assert result["order_id"] == sample_order.id
        assert result["recipient"] == sample_order.user.email
        assert result["total_amount"] == "120000.00"

        # Проверка отправленного письма через Django test mail backend
        assert len(mail.outbox) == 1
        sent_email = mail.outbox[0]
        assert f"#{sample_order.id}" in sent_email.subject
        assert sample_order.user.email in sent_email.to
        assert "Ноутбук Pro" in sent_email.body
        assert "120000.00" in sent_email.body
        assert sample_order.shipping_address in sent_email.body

    def test_send_order_confirmation_email_task_no_email(self, sample_order):
        mail.outbox.clear()
        sample_order.user.email = ""
        sample_order.user.save()

        result = send_order_confirmation_email_task(sample_order.id)
        assert result["status"] == "skipped"
        assert result["reason"] == "no_email"
        assert len(mail.outbox) == 0

    def test_send_order_confirmation_email_task_order_not_found(self):
        with pytest.raises(Order.DoesNotExist):
            send_order_confirmation_email_task(999999)

    def test_generate_order_receipt_task_success(self, sample_order):
        result = generate_order_receipt_task(sample_order.id)

        assert result["status"] == "generated"
        assert result["order_id"] == sample_order.id
        assert result["receipt_number"] == f"REC-{sample_order.id:06d}"
        assert result["customer_email"] == sample_order.user.email
        assert result["total_amount"] == "120000.00"
        assert result["items_count"] == 1
        assert "generated_at" in result

    def test_generate_order_receipt_task_order_not_found(self):
        with pytest.raises(Order.DoesNotExist):
            generate_order_receipt_task(999999)

    def test_cancel_unpaid_expired_orders_task(self, buyer_user, catalog_product):
        now = timezone.now()

        # 1. Просроченный заказ в статусе PENDING (40 минут назад) -> ДОЛЖЕН быть отменен
        order_expired = Order.objects.create(
            user=buyer_user,
            status=OrderStatus.PENDING,
            total_amount=Decimal("240000.00"),
            shipping_address="Адрес 1",
        )
        OrderItem.objects.create(
            order=order_expired,
            product=catalog_product,
            price=Decimal("120000.00"),
            quantity=2,
        )
        catalog_product.stock = 13  # 15 - 2
        catalog_product.save()

        Order.objects.filter(id=order_expired.id).update(created_at=now - timedelta(minutes=40))

        # 2. Свежий заказ в статусе PENDING (10 минут назад) -> НЕ должен быть отменен
        order_fresh = Order.objects.create(
            user=buyer_user,
            status=OrderStatus.PENDING,
            total_amount=Decimal("120000.00"),
            shipping_address="Адрес 2",
        )
        Order.objects.filter(id=order_fresh.id).update(created_at=now - timedelta(minutes=10))

        # 3. Оплаченный заказ (50 минут назад) -> НЕ должен быть отменен
        order_paid = Order.objects.create(
            user=buyer_user,
            status=OrderStatus.PAID,
            total_amount=Decimal("120000.00"),
            shipping_address="Адрес 3",
        )
        Order.objects.filter(id=order_paid.id).update(created_at=now - timedelta(minutes=50))

        # Запуск задачи
        task_result = cancel_unpaid_expired_orders_task()

        assert task_result["status"] == "success"
        assert order_expired.id in task_result["cancelled_order_ids"]
        assert order_fresh.id not in task_result["cancelled_order_ids"]
        assert order_paid.id not in task_result["cancelled_order_ids"]

        # Проверка обновления статусов в БД
        order_expired.refresh_from_db()
        order_fresh.refresh_from_db()
        order_paid.refresh_from_db()

        assert order_expired.status == OrderStatus.CANCELLED
        assert order_fresh.status == OrderStatus.PENDING
        assert order_paid.status == OrderStatus.PAID

        # Проверка возврата остатка на склад (было 13, вернулось 2 -> 15)
        catalog_product.refresh_from_db()
        assert catalog_product.stock == 15


# ==============================================================================
# 3. Checkout Celery Dispatch Integration Tests
# ==============================================================================


@pytest.mark.django_db(transaction=True)
class TestCheckoutCeleryIntegration:
    @patch("apps.orders.tasks.generate_order_receipt_task.delay")
    @patch("apps.orders.tasks.send_order_confirmation_email_task.delay")
    def test_checkout_triggers_celery_tasks_via_on_commit(
        self, mock_email_delay, mock_receipt_delay, buyer_user, catalog_product
    ):
        cart = Cart.objects.create(user=buyer_user)
        CartItem.objects.create(cart=cart, product=catalog_product, quantity=1)

        order = CheckoutService.create_order_from_cart(
            user=buyer_user,
            shipping_address="г. Москва, Красная площадь, 1",
            idempotency_key="checkout-celery-test-1",
        )

        assert order.status == OrderStatus.PENDING
        mock_email_delay.assert_called_once_with(order.id)
        mock_receipt_delay.assert_called_once_with(order.id)


# ==============================================================================
# 4. Redis Catalog Caching & Signal Invalidation Tests
# ==============================================================================


@pytest.mark.django_db
class TestCatalogCachingAndSignals:
    def test_get_popular_products_caching(self, catalog_product):
        cache.clear()

        # Первый вызов: заполнение кэша (miss -> set)
        data_first = CatalogCacheService.get_popular_products(limit=5)
        assert len(data_first) >= 1
        assert data_first[0]["id"] == catalog_product.id

        cache_key = CatalogCacheService.get_cache_key(limit=5)
        cached_val = cache.get(cache_key)
        assert cached_val is not None
        assert cached_val == data_first

        # Второй вызов: hit из кэша
        data_cached = CatalogCacheService.get_popular_products(limit=5)
        assert data_cached == data_first

    def test_cache_invalidation_on_product_save_and_delete(self, catalog_category, catalog_product):
        cache.clear()
        CatalogCacheService.get_popular_products(limit=10)
        cache_key = CatalogCacheService.get_cache_key(limit=10)
        assert cache.get(cache_key) is not None

        # Изменение товара должно инвалидировать кэш через post_save
        catalog_product.price = Decimal("135000.00")
        catalog_product.save()
        assert cache.get(cache_key) is None

        # Снова заполняем кэш
        CatalogCacheService.get_popular_products(limit=10)
        assert cache.get(cache_key) is not None

        # Удаление товара должно инвалидировать кэш через post_delete
        catalog_product.delete()
        assert cache.get(cache_key) is None

    def test_cache_invalidation_on_category_save_and_delete(self, catalog_category):
        cache.clear()
        CatalogCacheService.get_popular_products(limit=10)
        cache_key = CatalogCacheService.get_cache_key(limit=10)
        assert cache.get(cache_key) is not None

        # Изменение категории должно инвалидировать кэш
        catalog_category.name = "Обновленная категория"
        catalog_category.save()
        assert cache.get(cache_key) is None

    def test_popular_products_api_endpoint(self, api_client, catalog_product):
        url = "/api/catalog/products/popular/?limit=5"
        response = api_client.get(url)
        assert response.status_code == 200
        assert isinstance(response.data, list)
        assert len(response.data) >= 1
        assert response.data[0]["id"] == catalog_product.id


# ==============================================================================
# 5. Async Payment Webhook Tests
# ==============================================================================


@pytest.mark.django_db(transaction=True)
class TestAsyncPaymentWebhook:
    def test_webhook_payment_succeeded(self, sample_order):
        client = Client()
        payload = {
            "order_id": sample_order.id,
            "event": "payment.succeeded",
        }
        response = client.post(
            "/api/orders/webhooks/payment/",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["order_id"] == sample_order.id
        assert data["order_status"] == OrderStatus.PAID

        sample_order.refresh_from_db()
        assert sample_order.status == OrderStatus.PAID

    def test_webhook_payment_failed_cancels_order_and_restores_stock(
        self, buyer_user, catalog_product
    ):
        order = Order.objects.create(
            user=buyer_user,
            status=OrderStatus.PENDING,
            total_amount=Decimal("240000.00"),
            shipping_address="г. Самара, ул. Лесная, д. 5",
        )
        OrderItem.objects.create(
            order=order,
            product=catalog_product,
            price=Decimal("120000.00"),
            quantity=3,
        )
        catalog_product.stock = 12  # 15 - 3
        catalog_product.save()

        client = Client()
        payload = {
            "order_id": order.id,
            "event": "payment.failed",
        }
        response = client.post(
            "/api/orders/webhooks/payment/",
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["order_status"] == OrderStatus.CANCELLED

        order.refresh_from_db()
        assert order.status == OrderStatus.CANCELLED

        catalog_product.refresh_from_db()
        assert catalog_product.stock == 15  # 12 + 3 restored

    def test_webhook_order_not_found(self):
        client = Client()
        payload = {"order_id": 999999, "event": "payment.succeeded"}
        response = client.post(
            "/api/orders/webhooks/payment/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 404
        assert "не найден" in response.json()["error"]

    def test_webhook_invalid_json(self):
        client = Client()
        response = client.post(
            "/api/orders/webhooks/payment/",
            data="not-a-valid-json",
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "Некорректный формат JSON" in response.json()["error"]

    def test_webhook_missing_fields(self):
        client = Client()
        payload = {"order_id": 1}  # Missing 'event'
        response = client.post(
            "/api/orders/webhooks/payment/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_webhook_method_not_allowed(self):
        client = Client()
        response = client.get("/api/orders/webhooks/payment/")
        assert response.status_code == 405

    def test_webhook_unknown_event(self, sample_order):
        client = Client()
        payload = {"order_id": sample_order.id, "event": "unsupported_event_type"}
        response = client.post(
            "/api/orders/webhooks/payment/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "Неподдерживаемое событие" in response.json()["error"]

    def test_direct_async_view_call(self, sample_order):
        rf = RequestFactory()
        payload = json.dumps({"order_id": sample_order.id, "event": "payment.succeeded"}).encode(
            "utf-8"
        )
        request = rf.post(
            "/api/orders/webhooks/payment/",
            data=payload,
            content_type="application/json",
        )

        response = asyncio.run(payment_webhook_view(request))
        assert response.status_code == 200
        data = json.loads(response.content.decode("utf-8"))
        assert data["order_status"] == OrderStatus.PAID
