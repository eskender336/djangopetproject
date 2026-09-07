import django_filters
from django.db.models import QuerySet

from apps.catalog.models import Product, Tag


class ProductFilter(django_filters.FilterSet):
    """
    Фильтр для каталога товаров: по цене (диапазон), slug категории,
    наличию на складе и тегам.
    """

    price_min = django_filters.NumberFilter(
        field_name="price",
        lookup_expr="gte",
        label="Минимальная цена",
    )
    price_max = django_filters.NumberFilter(
        field_name="price",
        lookup_expr="lte",
        label="Максимальная цена",
    )
    category_slug = django_filters.CharFilter(
        field_name="category__slug",
        lookup_expr="exact",
        label="Slug категории",
    )
    in_stock = django_filters.BooleanFilter(
        method="filter_in_stock",
        label="В наличии (true/false)",
    )
    tags = django_filters.ModelMultipleChoiceFilter(
        field_name="tags__slug",
        to_field_name="slug",
        queryset=Tag.objects.all(),
        label="Slug тегов (можно передавать несколько)",
    )

    class Meta:
        model = Product
        fields = [
            "category",
            "category_slug",
            "price_min",
            "price_max",
            "in_stock",
            "tags",
            "is_active",
        ]

    def filter_in_stock(self, queryset: QuerySet, name: str, value: bool | None) -> QuerySet:
        if value is None:
            return queryset
        if value:
            return queryset.filter(stock__gt=0)
        return queryset.filter(stock=0)
