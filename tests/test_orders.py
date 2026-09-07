from decimal import Decimal

import pytest
from django.contrib.admin.sites import site
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from rest_framework import status

from apps.catalog.models import Category, Product
from apps.orders.admin import CartAdmin, CartItemInline, OrderAdmin, OrderItemInline
from apps.orders.models import Cart, CartItem, Order, OrderItem, OrderStatus
from apps.orders.services import CartService, CheckoutService
from apps.users.models import User, UserRole


@pytest.fixture
def test_category(db):
    return Category.objects.create(name="Электроника", slug="electronics")


@pytest.fixture
def product_a(db, test_category):
    return Product.objects.create(
        name="Смартфон Alpha",
        slug="smartphone-alpha",
        sku="SKU-ALP-001",
        category=test_category,
        price=Decimal("50000.00"),
        stock=10,
        is_active=True,
    )


@pytest.fixture
def product_b(db, test_category):
    return Product.objects.create(
        name="Наушники Beta",
        slug="headphones-beta",
        sku="SKU-BET-002",
        category=test_category,
        price=Decimal("10000.00"),
        stock=5,
        is_active=True,
    )


@pytest.fixture
def another_user(db):
    return User.objects.create_user(
        email="another@example.com",
        password="Password123!",
        first_name="Сергей",
        last_name="Кузнецов",
        role=UserRole.CUSTOMER,
    )


@pytest.fixture
def manager_user(db):
    return User.objects.create_user(
        email="manager_orders@example.com",
        password="Password123!",
        role=UserRole.MANAGER,
    )


@pytest.fixture
def manager_client(api_client, manager_user):
    api_client.force_authenticate(user=manager_user)
    return api_client


# ==============================================================================
# Model Tests
# ==============================================================================


@pytest.mark.django_db
class TestOrdersModels:
    def test_cart_creation_and_properties(self, test_user, product_a, product_b):
        cart = Cart.objects.create(user=test_user)
        assert cart.is_empty is True
        assert cart.total_items_count == 0
        assert cart.total_price == Decimal("0.00")
        assert "Корзина пользователя" in str(cart)

        # Добавляем позиции
        CartItem.objects.create(cart=cart, product=product_a, quantity=2)
        CartItem.objects.create(cart=cart, product=product_b, quantity=1)

        cart.refresh_from_db()
        assert cart.is_empty is False
        assert cart.total_items_count == 3
        assert cart.total_price == Decimal("110000.00")  # (50000*2) + (10000*1)

        cart.clear()
        assert cart.items.count() == 0
        assert cart.is_empty is True

    def test_cart_item_unique_constraint(self, test_user, product_a):
        cart = Cart.objects.create(user=test_user)
        CartItem.objects.create(cart=cart, product=product_a, quantity=1)

        with pytest.raises(IntegrityError):
            CartItem.objects.create(cart=cart, product=product_a, quantity=2)

    def test_order_and_order_item_models(self, test_user, product_a):
        order = Order.objects.create(
            user=test_user,
            status=OrderStatus.PENDING,
            total_amount=Decimal("50000.00"),
            shipping_address="г. Москва, ул. Тверская, д. 1",
            idempotency_key="idemp-key-001",
        )
        assert f"Заказ #{order.id}" in str(order)
        assert order.can_cancel is True

        order_item = OrderItem.objects.create(
            order=order,
            product=product_a,
            price=Decimal("50000.00"),
            quantity=1,
        )
        assert f"{product_a.name} (1 шт.)" in str(order_item)
        assert order_item.total_price == Decimal("50000.00")


# ==============================================================================
# Admin Registration Tests
# ==============================================================================


@pytest.mark.django_db
class TestOrdersAdmin:
    def test_admin_registration(self):
        assert Cart in site._registry
        assert Order in site._registry

        cart_admin = site._registry[Cart]
        assert isinstance(cart_admin, CartAdmin)
        assert CartItemInline in cart_admin.inlines

        order_admin = site._registry[Order]
        assert isinstance(order_admin, OrderAdmin)
        assert OrderItemInline in order_admin.inlines

    def test_cart_and_order_admin_display_helpers(self, test_user, product_a):
        cart = Cart.objects.create(user=test_user)
        item = CartItem.objects.create(cart=cart, product=product_a, quantity=2)

        cart_admin = site._registry[Cart]
        assert cart_admin.get_items_count(cart) == 2
        assert "100000.00" in cart_admin.get_total_price(cart)

        cart_inline = CartItemInline(CartItem, site)
        assert "50000.00" in cart_inline.get_item_price(item)
        assert "100000.00" in cart_inline.get_total_price(item)


# ==============================================================================
# Services Tests (CheckoutService & CartService)
# ==============================================================================


@pytest.mark.django_db
class TestCheckoutService:
    def test_checkout_success(self, test_user, product_a, product_b):
        cart = Cart.objects.create(user=test_user)
        CartItem.objects.create(cart=cart, product=product_a, quantity=2)
        CartItem.objects.create(cart=cart, product=product_b, quantity=1)

        initial_stock_a = product_a.stock
        initial_stock_b = product_b.stock

        order = CheckoutService.create_order_from_cart(
            user=test_user,
            shipping_address="г. Москва, ул. Ленина, д. 10, кв. 5",
            idempotency_key="checkout-test-key-1",
        )

        assert order.user == test_user
        assert order.status == OrderStatus.PENDING
        assert order.total_amount == Decimal("110000.00")
        assert order.shipping_address == "г. Москва, ул. Ленина, д. 10, кв. 5"
        assert order.idempotency_key == "checkout-test-key-1"
        assert order.items.count() == 2

        # Проверка списания остатков на складе
        product_a.refresh_from_db()
        product_b.refresh_from_db()
        assert product_a.stock == initial_stock_a - 2
        assert product_b.stock == initial_stock_b - 1

        # Проверка очистки корзины
        assert cart.items.count() == 0

    def test_checkout_idempotency_prevents_duplicate_deduction(self, test_user, product_a):
        cart = Cart.objects.create(user=test_user)
        CartItem.objects.create(cart=cart, product=product_a, quantity=1)

        key = "unique-idempotency-key-123"
        order1 = CheckoutService.create_order_from_cart(
            user=test_user,
            shipping_address="г. Казань, ул. Баумана, д. 5",
            idempotency_key=key,
        )

        product_a.refresh_from_db()
        stock_after_first = product_a.stock

        # Повторный вызов с тем же ключом
        order2 = CheckoutService.create_order_from_cart(
            user=test_user,
            shipping_address="г. Казань, ул. Баумана, д. 5",
            idempotency_key=key,
        )

        assert order1.id == order2.id
        product_a.refresh_from_db()
        assert product_a.stock == stock_after_first  # Списания повторно не произошло

    def test_checkout_empty_cart_raises_error(self, test_user):
        Cart.objects.create(user=test_user)
        with pytest.raises(ValidationError, match="Корзина пуста"):
            CheckoutService.create_order_from_cart(
                user=test_user,
                shipping_address="г. Москва, ул. Арбат, 1",
            )

    def test_checkout_insufficient_stock_raises_error(self, test_user, product_a):
        cart = Cart.objects.create(user=test_user)
        CartItem.objects.create(cart=cart, product=product_a, quantity=15)  # Available is 10

        with pytest.raises(ValidationError, match="Недостаточно товара"):
            CheckoutService.create_order_from_cart(
                user=test_user,
                shipping_address="г. Москва, ул. Тверская, 1",
            )

        # Остаток не должен измениться
        product_a.refresh_from_db()
        assert product_a.stock == 10

    def test_cancel_order_restores_stock(self, test_user, product_a):
        cart = Cart.objects.create(user=test_user)
        CartItem.objects.create(cart=cart, product=product_a, quantity=3)

        order = CheckoutService.create_order_from_cart(
            user=test_user,
            shipping_address="г. Москва, Ленинский пр-т, 1",
        )
        product_a.refresh_from_db()
        assert product_a.stock == 7

        cancelled = CheckoutService.cancel_order(order=order, user=test_user)
        assert cancelled.status == OrderStatus.CANCELLED

        product_a.refresh_from_db()
        assert product_a.stock == 10  # Остаток возвращен!


@pytest.mark.django_db
class TestCartService:
    def test_add_and_update_and_remove(self, test_user, product_a):
        cart = CartService.get_or_create_cart(user=test_user)

        # Add
        item = CartService.add_to_cart(cart=cart, product=product_a, quantity=2)
        assert item.quantity == 2

        # Increment existing
        item = CartService.add_to_cart(cart=cart, product=product_a, quantity=3)
        assert item.quantity == 5

        # Update
        item = CartService.update_quantity(cart=cart, product_id=product_a.id, quantity=4)
        assert item.quantity == 4

        # Remove
        CartService.remove_from_cart(cart=cart, product_id=product_a.id)
        assert not cart.items.filter(product=product_a).exists()


# ==============================================================================
# DRF API Endpoints Tests (CartViewSet & OrderViewSet)
# ==============================================================================


@pytest.mark.django_db
class TestCartAPI:
    def test_get_cart(self, authenticated_client, test_user, product_a):
        cart = Cart.objects.create(user=test_user)
        CartItem.objects.create(cart=cart, product=product_a, quantity=2)

        url = "/api/orders/cart/"
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["total_items_count"] == 2
        assert response.data["total_price"] == "100000.00"
        assert len(response.data["items"]) == 1

    def test_add_item_to_cart_api(self, authenticated_client, product_a):
        url = "/api/orders/cart/items/"
        payload = {"product_id": product_a.id, "quantity": 3}
        response = authenticated_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["total_items_count"] == 3
        assert response.data["total_price"] == "150000.00"

    def test_update_item_quantity_api(self, authenticated_client, test_user, product_a):
        cart = Cart.objects.create(user=test_user)
        CartItem.objects.create(cart=cart, product=product_a, quantity=1)

        url = f"/api/orders/cart/items/{product_a.id}/"
        payload = {"quantity": 4}
        response = authenticated_client.patch(url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["total_items_count"] == 4
        assert response.data["total_price"] == "200000.00"

    def test_remove_item_from_cart_api(self, authenticated_client, test_user, product_a):
        cart = Cart.objects.create(user=test_user)
        CartItem.objects.create(cart=cart, product=product_a, quantity=1)

        url = f"/api/orders/cart/items/{product_a.id}/"
        response = authenticated_client.delete(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["total_items_count"] == 0

    def test_clear_cart_api(self, authenticated_client, test_user, product_a, product_b):
        cart = Cart.objects.create(user=test_user)
        CartItem.objects.create(cart=cart, product=product_a, quantity=1)
        CartItem.objects.create(cart=cart, product=product_b, quantity=2)

        url = "/api/orders/cart/clear/"
        response = authenticated_client.post(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["total_items_count"] == 0
        assert response.data["is_empty"] is True

    def test_unauthenticated_cart_access_denied(self, api_client):
        url = "/api/orders/cart/"
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestOrderAPI:
    def test_checkout_api_success(self, authenticated_client, test_user, product_a):
        cart = Cart.objects.create(user=test_user)
        CartItem.objects.create(cart=cart, product=product_a, quantity=2)

        url = "/api/orders/orders/checkout/"
        payload = {
            "shipping_address": "г. Санкт-Петербург, Невский пр-т, д. 25, кв. 10",
            "idempotency_key": "api-idemp-key-01",
        }
        response = authenticated_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["status"] == OrderStatus.PENDING
        assert response.data["total_amount"] == "100000.00"
        assert response.data["shipping_address"] == payload["shipping_address"]
        assert len(response.data["items"]) == 1
        assert response.data["items"][0]["quantity"] == 2

        # Повторный запрос с тем же idempotency_key возвращает 201 с тем же заказом
        response_dup = authenticated_client.post(url, payload, format="json")
        assert response_dup.status_code == status.HTTP_201_CREATED
        assert response_dup.data["id"] == response.data["id"]

    def test_checkout_api_validation_error_empty_cart(self, authenticated_client, test_user):
        Cart.objects.create(user=test_user)
        url = "/api/orders/orders/checkout/"
        payload = {"shipping_address": "г. Москва, ул. Новый Арбат, 10"}
        response = authenticated_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_list_and_retrieve_orders_api(self, authenticated_client, test_user, product_a):
        order = Order.objects.create(
            user=test_user,
            status=OrderStatus.PENDING,
            total_amount=Decimal("50000.00"),
            shipping_address="г. Москва, ул. Тверская, 1",
        )
        OrderItem.objects.create(
            order=order, product=product_a, price=Decimal("50000.00"), quantity=1
        )

        # List
        url = "/api/orders/orders/"
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["id"] == order.id

        # Detail
        detail_url = f"/api/orders/orders/{order.id}/"
        response = authenticated_client.get(detail_url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == order.id
        assert len(response.data["items"]) == 1

    def test_cancel_order_api(self, authenticated_client, test_user, product_a):
        order = Order.objects.create(
            user=test_user,
            status=OrderStatus.PENDING,
            total_amount=Decimal("50000.00"),
            shipping_address="г. Москва, ул. Тверская, 1",
        )
        OrderItem.objects.create(
            order=order, product=product_a, price=Decimal("50000.00"), quantity=2
        )
        product_a.stock = 8
        product_a.save()

        url = f"/api/orders/orders/{order.id}/cancel/"
        response = authenticated_client.post(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == OrderStatus.CANCELLED

        product_a.refresh_from_db()
        assert product_a.stock == 10  # 8 + 2 restored
