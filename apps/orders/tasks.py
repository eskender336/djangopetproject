import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from apps.orders.models import Order, OrderStatus
from apps.orders.services import CheckoutService

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
)
def send_order_confirmation_email_task(self, order_id: int) -> dict:
    """
    Фоновая задача отправки email с подтверждением заказа клиенту.
    Поддерживает автоматические повторные попытки (autoretry_for) при сбоях сети/SMTP.
    """
    logger.info("Запуск задачи отправки email подтверждения для заказа #%s", order_id)

    try:
        order = (
            Order.objects.select_related("user").prefetch_related("items__product").get(id=order_id)
        )
    except Order.DoesNotExist as exc:
        logger.error("Заказ #%s не найден при попытке отправки email", order_id)
        raise exc

    recipient_email = order.user.email
    if not recipient_email:
        logger.warning("У пользователя заказа #%s отсутствует email", order_id)
        return {
            "status": "skipped",
            "reason": "no_email",
            "order_id": order_id,
        }

    items_summary = "\n".join(
        f"- {item.product.name}: {item.quantity} шт. x {item.price} руб."
        for item in order.items.all()
    )

    subject = f"Подтверждение заказа #{order.id} в интернет-магазине"
    message = (
        f"Здравствуйте, {order.user.first_name or 'покупатель'}!\n\n"
        f"Ваш заказ #{order.id} успешно оформлен.\n\n"
        f"Состав заказа:\n{items_summary}\n\n"
        f"Итого к оплате: {order.total_amount} руб.\n"
        f"Адрес доставки: {order.shipping_address}\n\n"
        f"Статус заказа: {order.get_status_display()}\n\n"
        f"Спасибо за покупку!"
    )

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@ecommerce.example.com")

    send_mail(
        subject=subject,
        message=message,
        from_email=from_email,
        recipient_list=[recipient_email],
        fail_silently=False,
    )

    logger.info(
        "Email с подтверждением заказа #%s успешно отправлен на %s", order_id, recipient_email
    )
    return {
        "status": "sent",
        "order_id": order_id,
        "recipient": recipient_email,
        "total_amount": str(order.total_amount),
    }


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def generate_order_receipt_task(self, order_id: int) -> dict:
    """
    Фоновая задача генерации чека / квитанции заказа.
    """
    logger.info("Генерация квитанции/чека для заказа #%s", order_id)

    try:
        order = (
            Order.objects.select_related("user").prefetch_related("items__product").get(id=order_id)
        )
    except Order.DoesNotExist as exc:
        logger.error("Заказ #%s не найден для формирования чека", order_id)
        raise exc

    receipt_number = f"REC-{order.id:06d}"
    items_count = order.items.count()

    receipt_data = {
        "status": "generated",
        "order_id": order.id,
        "receipt_number": receipt_number,
        "customer_email": order.user.email,
        "total_amount": str(order.total_amount),
        "items_count": items_count,
        "generated_at": timezone.now().isoformat(),
    }

    logger.info("Квитанция %s для заказа #%s успешно сформирована", receipt_number, order_id)
    return receipt_data


@shared_task
def cancel_unpaid_expired_orders_task() -> dict:
    """
    Периодическая задача Celery Beat для автоматической отмены заказов
    в статусе PENDING старше 30 минут с возвратом остатков на склад.
    """
    logger.info("Запуск периодической проверки просроченных неоплаченных заказов")

    expiration_threshold = timezone.now() - timedelta(minutes=30)
    expired_orders = Order.objects.filter(
        status=OrderStatus.PENDING,
        created_at__lte=expiration_threshold,
    )

    cancelled_order_ids = []
    for order in expired_orders:
        try:
            CheckoutService.cancel_order(order=order)
            cancelled_order_ids.append(order.id)
            logger.info("Заказ #%s успешно отменен из-за истечения срока оплаты", order.id)
        except Exception as exc:
            logger.error("Ошибка при отмене просроченного заказа #%s: %s", order.id, exc)

    result = {
        "status": "success",
        "cancelled_count": len(cancelled_order_ids),
        "cancelled_order_ids": cancelled_order_ids,
    }
    logger.info(
        "Проверка просроченных заказов завершена: отменено %d заказов", len(cancelled_order_ids)
    )
    return result
