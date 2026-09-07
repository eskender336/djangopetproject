import logging
from typing import Any

from django.core.cache import cache

from apps.catalog.models import Product
from apps.catalog.serializers import ProductListSerializer

logger = logging.getLogger(__name__)


class CatalogCacheService:
    """
    Сервис кэширования данных каталога в Redis.
    """

    POPULAR_PRODUCTS_CACHE_KEY = "catalog:popular_products"
    POPULAR_PRODUCTS_CACHE_TIMEOUT = 3600  # 1 час

    @classmethod
    def get_cache_key(cls, limit: int = 10) -> str:
        return f"{cls.POPULAR_PRODUCTS_CACHE_KEY}:{limit}"

    @classmethod
    def get_popular_products(
        cls, limit: int = 10, force_refresh: bool = False
    ) -> list[dict[str, Any]]:
        """
        Получение списка популярных товаров из кэша Redis или из БД с сохранением в кэш.
        """
        cache_key = cls.get_cache_key(limit)

        if not force_refresh:
            cached_data = cache.get(cache_key)
            if cached_data is not None:
                logger.debug("Hit кэша для популярных товаров (ключ: %s)", cache_key)
                return cached_data

        logger.debug("Miss кэша для популярных товаров (ключ: %s), загрузка из БД", cache_key)
        products = (
            Product.objects.filter(is_active=True, category__is_active=True)
            .select_related("category")
            .prefetch_related("tags", "images")
            .order_by("-stock", "-created_at")[:limit]
        )

        serializer = ProductListSerializer(products, many=True)
        data = serializer.data

        cache.set(cache_key, data, timeout=cls.POPULAR_PRODUCTS_CACHE_TIMEOUT)
        return data

    @classmethod
    def invalidate_popular_products_cache(cls) -> None:
        """
        Инвалидация кэша популярных товаров в Redis при изменении каталога.
        """
        keys_to_delete = [
            cls.POPULAR_PRODUCTS_CACHE_KEY,
            *(cls.get_cache_key(limit) for limit in (5, 10, 20, 50, 100)),
        ]
        cache.delete_many(keys_to_delete)
        logger.info("Кэш популярных товаров инвалидирован (ключи: %s)", keys_to_delete)
