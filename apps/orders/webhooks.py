import asyncio
import json
import logging
from typing import Any

from asgiref.sync import sync_to_async
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from apps.orders.models import Order, OrderStatus
from apps.orders.services import CheckoutService

logger = logging.getLogger(__name__)


@csrf_exempt
async def payment_webhook_view(request: HttpRequest) -> JsonResponse:
    """
    Асинхронный эндпоинт для обработки внешних вебхуков от платежных систем.
    Поддерживает события успешной оплаты (payment.succeeded) и сбоя (payment.failed).
    """
    if request.method != "POST":
        return JsonResponse(
            {"error": "Метод не поддерживается. Разрешен только POST."},
            status=405,
        )

    try:
        payload: dict[str, Any] = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.warning("Некорректный JSON в теле запроса вебхука")
        return JsonResponse({"error": "Некорректный формат JSON."}, status=400)

    order_id = payload.get("order_id")
    event = payload.get("event") or payload.get("status")

    if not order_id or not event:
        return JsonResponse(
            {"error": "Поля 'order_id' и 'event' обязательны."},
            status=400,
        )

    try:
        order_id = int(order_id)
    except (TypeError, ValueError):
        return JsonResponse({"error": "'order_id' должен быть числом."}, status=400)

    # Симуляция асинхронной верификации подписи платежного провайдера (async I/O)
    await asyncio.sleep(0.01)

    logger.info("Обработка вебхука: order_id=%s, event=%s", order_id, event)

    # Асинхронное получение заказа через нативный Async ORM Django
    order = await Order.objects.filter(id=order_id).afirst()
    if not order:
        logger.warning("Заказ #%s для вебхука не найден в базе данных", order_id)
        return JsonResponse(
            {"error": f"Заказ #{order_id} не найден."},
            status=404,
        )

    if event in ("payment.succeeded", "payment.paid", "success", "paid"):
        if order.status == OrderStatus.PENDING:
            order.status = OrderStatus.PAID
            await order.asave(update_fields=["status", "updated_at"])
            message = f"Статус заказа #{order_id} успешно обновлен на PAID."
        else:
            message = f"Заказ #{order_id} уже имеет статус {order.status}."

        logger.info(message)
        return JsonResponse(
            {
                "status": "success",
                "message": message,
                "order_id": order.id,
                "order_status": order.status,
            },
            status=200,
        )

    if event in ("payment.failed", "payment.cancelled", "failed", "cancelled"):
        if order.can_cancel:
            # Отмена заказа с возвратом остатков на склад через sync_to_async
            await sync_to_async(CheckoutService.cancel_order)(order=order)
            # Перезагружаем заказ для актуального статуса
            await order.arefresh_from_db()
            message = f"Заказ #{order_id} отменен, остатки возвращены на склад."
        else:
            message = f"Заказ #{order_id} не может быть отменен (текущий статус: {order.status})."

        logger.info(message)
        return JsonResponse(
            {
                "status": "success",
                "message": message,
                "order_id": order.id,
                "order_status": order.status,
            },
            status=200,
        )

    logger.warning("Получено неподдерживаемое событие вебхука: %s", event)
    return JsonResponse(
        {"error": f"Неподдерживаемое событие '{event}'."},
        status=400,
    )
