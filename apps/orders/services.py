from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils.translation import gettext_lazy as _

from apps.catalog.models import Product
from apps.orders.models import Cart, CartItem, Order, OrderItem, OrderStatus


class CheckoutService:
    """
    Сервис оформления заказов и управления жизненным циклом заказа.
    """

    @classmethod
    def _check_idempotency(cls, user, idempotency_key: str | None) -> Order | None:
        if not idempotency_key:
            return None

        existing_order = Order.objects.filter(
            idempotency_key=idempotency_key,
            user=user,
        ).first()
        if existing_order:
            return existing_order

        if Order.objects.filter(idempotency_key=idempotency_key).exists():
            raise ValidationError(
                _("Заказ с указанным ключом идемпотентности уже зарегистрирован.")
            )
        return None

    @classmethod
    def _validate_items_and_stock(
        cls,
        cart_items: list[CartItem],
        locked_products: dict[int, Product],
    ) -> None:
        for item in cart_items:
            product = locked_products.get(item.product_id)
            if not product:
                raise ValidationError(
                    _("Товар '%(name)s' больше недоступен.") % {"name": item.product.name}
                )
            if not product.is_active:
                raise ValidationError(
                    _("Товар '%(name)s' снят с продажи.") % {"name": product.name}
                )
            if product.stock < item.quantity:
                raise ValidationError(
                    _(
                        "Недостаточно товара '%(name)s' на складе. "
                        "Доступно: %(stock)d, запрошено: %(quantity)d."
                    )
                    % {
                        "name": product.name,
                        "stock": product.stock,
                        "quantity": item.quantity,
                    }
                )

    @classmethod
    def create_order_from_cart(
        cls,
        user,
        shipping_address: str,
        idempotency_key: str | None = None,
    ) -> Order:
        """
        Оформить заказ на основе текущей корзины пользователя с блокировкой остатков
        и поддержкой идемпотентности.
        """
        with transaction.atomic():
            # 1. Проверка ключа идемпотентности
            existing = cls._check_idempotency(user, idempotency_key)
            if existing:
                return existing

            # 2. Получение корзины пользователя
            cart = Cart.objects.filter(user=user).first()
            if not cart or not cart.items.exists():
                raise ValidationError(_("Корзина пуста. Невозможно оформить заказ."))

            cart_items = list(cart.items.select_related("product").all())
            if not cart_items:
                raise ValidationError(_("Корзина пуста. Невозможно оформить заказ."))

            # 3. Блокировка строк остатков (select_for_update против Race Condition)
            product_ids = [item.product_id for item in cart_items]
            locked_products = {
                p.id: p for p in Product.objects.select_for_update().filter(id__in=product_ids)
            }

            # 4. Валидация остатков
            cls._validate_items_and_stock(cart_items, locked_products)

            # 5. Подсчет итоговой суммы
            total_amount = sum(
                (locked_products[item.product_id].price * item.quantity for item in cart_items),
                start=Decimal("0.00"),
            )

            # 6. Создание заказа
            order = Order.objects.create(
                user=user,
                status=OrderStatus.PENDING,
                total_amount=total_amount,
                shipping_address=shipping_address.strip(),
                idempotency_key=idempotency_key,
            )

            # 7. Создание позиций заказа (OrderItem)
            order_items = [
                OrderItem(
                    order=order,
                    product=locked_products[item.product_id],
                    price=locked_products[item.product_id].price,
                    quantity=item.quantity,
                )
                for item in cart_items
            ]
            OrderItem.objects.bulk_create(order_items)

            # 8. Списание остатков на складе
            for item in cart_items:
                Product.objects.filter(id=item.product_id).update(stock=F("stock") - item.quantity)

            # 9. Очистка корзины
            cart.items.all().delete()

            # 10. Фоновые задачи Celery после фиксации транзакции в БД
            order_id = order.id
            from apps.orders.tasks import (
                generate_order_receipt_task,
                send_order_confirmation_email_task,
            )

            transaction.on_commit(lambda: send_order_confirmation_email_task.delay(order_id))
            transaction.on_commit(lambda: generate_order_receipt_task.delay(order_id))

            return order

    @staticmethod
    def cancel_order(order: Order, user=None) -> Order:
        """
        Отмена заказа с возвратом списанных остатков товаров на склад.
        """
        if user and order.user != user:
            is_staff = getattr(user, "is_staff", False)
            user_role = getattr(user, "role", "")
            if not (is_staff or user_role in ("manager", "admin")):
                raise ValidationError(_("У вас нет прав для отмены этого заказа."))

        if not order.can_cancel:
            raise ValidationError(
                _("Заказ в текущем статусе '%(status)s' не может быть отменен.")
                % {"status": order.get_status_display()}
            )

        with transaction.atomic():
            order_items = list(order.items.select_related("product").all())
            for item in order_items:
                Product.objects.filter(id=item.product_id).update(stock=F("stock") + item.quantity)

            order.status = OrderStatus.CANCELLED
            order.save(update_fields=["status", "updated_at"])

        return order


class CartService:
    """
    Сервис для работы с корзиной пользователя (добавление, обновление, удаление товаров).
    """

    @staticmethod
    def get_or_create_cart(user=None, session_key: str | None = None) -> Cart:
        """
        Получить или создать корзину для авторизованного пользователя или сессии.
        """
        if user and user.is_authenticated:
            cart, _ = Cart.objects.get_or_create(user=user)
            return cart
        if session_key:
            cart, _ = Cart.objects.get_or_create(session_key=session_key, user__isnull=True)
            return cart
        raise ValidationError(_("Не указан пользователь или ключ сессии."))

    @staticmethod
    def add_to_cart(cart: Cart, product: Product, quantity: int = 1) -> CartItem:
        """
        Добавить товар в корзину или увеличить количество существующего.
        """
        if quantity <= 0:
            raise ValidationError(_("Количество должно быть положительным числом."))

        if not product.is_active:
            raise ValidationError(_("Товар '%(name)s' недоступен.") % {"name": product.name})

        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={"quantity": quantity},
        )

        if not created:
            new_quantity = cart_item.quantity + quantity
            if new_quantity > product.stock:
                raise ValidationError(
                    _(
                        "Недостаточно товара на складе. Доступно: %(stock)d, "
                        "в корзине будет: %(quantity)d."
                    )
                    % {"stock": product.stock, "quantity": new_quantity}
                )
            cart_item.quantity = new_quantity
            cart_item.save(update_fields=["quantity", "updated_at"])
        else:
            if quantity > product.stock:
                cart_item.delete()
                raise ValidationError(
                    _(
                        "Недостаточно товара на складе. Доступно: %(stock)d, "
                        "запрошено: %(quantity)d."
                    )
                    % {"stock": product.stock, "quantity": quantity}
                )

        return cart_item

    @staticmethod
    def update_quantity(cart: Cart, product_id: int, quantity: int) -> CartItem:
        """
        Установить точное количество товара в корзине.
        """
        if quantity <= 0:
            raise ValidationError(_("Количество должно быть больше нуля."))

        cart_item = CartItem.objects.filter(cart=cart, product_id=product_id).first()
        if not cart_item:
            raise ValidationError(_("Товар не найден в корзине."))

        product = cart_item.product
        if not product.is_active:
            raise ValidationError(_("Товар недоступен."))

        if quantity > product.stock:
            raise ValidationError(
                _("Недостаточно товара на складе. Доступно: %(stock)d, запрошено: %(quantity)d.")
                % {"stock": product.stock, "quantity": quantity}
            )

        cart_item.quantity = quantity
        cart_item.save(update_fields=["quantity", "updated_at"])
        return cart_item

    @staticmethod
    def remove_from_cart(cart: Cart, product_id: int) -> None:
        """
        Удалить товар из корзины.
        """
        CartItem.objects.filter(cart=cart, product_id=product_id).delete()
