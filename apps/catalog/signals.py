import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.catalog.models import Category, Product
from apps.catalog.services import CatalogCacheService

logger = logging.getLogger(__name__)


@receiver([post_save, post_delete], sender=Product)
def product_cache_invalidation_handler(sender, instance, **kwargs):
    """
    Инвалидация кэша каталога при создании, обновлении или удалении товара.
    """
    logger.debug("Инвалидация кэша из-за изменения товара #%s (%s)", instance.id, instance.name)
    CatalogCacheService.invalidate_popular_products_cache()


@receiver([post_save, post_delete], sender=Category)
def category_cache_invalidation_handler(sender, instance, **kwargs):
    """
    Инвалидация кэша каталога при изменении или удалении категории.
    """
    logger.debug("Инвалидация кэша из-за изменения категории #%s (%s)", instance.id, instance.name)
    CatalogCacheService.invalidate_popular_products_cache()
