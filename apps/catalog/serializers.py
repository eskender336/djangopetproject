from decimal import Decimal

from django.utils.text import slugify
from rest_framework import serializers

from apps.catalog.models import Category, Product, ProductImage, Tag

CYRILLIC_TO_LATIN = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "yo",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


def transliterate(text: str) -> str:
    """
    Транслитерация кириллицы в латиницу для генерации URL slug.
    """
    return "".join(CYRILLIC_TO_LATIN.get(c, c) for c in text.lower())


class CategorySerializer(serializers.ModelSerializer):
    """
    Сериализатор категорий каталога.
    """

    parent_name = serializers.CharField(source="parent.name", read_only=True, default=None)

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
            "parent",
            "parent_name",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class TagSerializer(serializers.ModelSerializer):
    """
    Сериализатор тегов.
    """

    class Meta:
        model = Tag
        fields = [
            "id",
            "name",
            "slug",
        ]
        read_only_fields = ["id"]


class ProductImageSerializer(serializers.ModelSerializer):
    """
    Сериализатор изображений товаров.
    """

    class Meta:
        model = ProductImage
        fields = [
            "id",
            "product",
            "image",
            "is_main",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class ProductListSerializer(serializers.ModelSerializer):
    """
    Оптимизированный сериализатор товара для списков.
    """

    category_name = serializers.CharField(source="category.name", read_only=True)
    in_stock = serializers.BooleanField(read_only=True)
    main_image = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "sku",
            "category",
            "category_name",
            "price",
            "stock",
            "in_stock",
            "is_active",
            "main_image",
            "created_at",
        ]
        read_only_fields = fields

    def get_main_image(self, obj: Product) -> str | None:
        """
        Возвращает URL главного изображения или первого доступного,
        используя уже предзагруженный prefetch_related('images').
        """
        images = getattr(obj, "prefetched_images", None)
        if images is None:
            images = list(obj.images.all())

        if not images:
            return None

        main_img = next((img for img in images if img.is_main), images[0])
        if not main_img.image:
            return None

        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(main_img.image.url)
        return main_img.image.url


class ProductDetailSerializer(serializers.ModelSerializer):
    """
    Детальный сериализатор товара с вложенными объектами категории, тегов и изображений.
    """

    category = CategorySerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    in_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "sku",
            "category",
            "tags",
            "images",
            "description",
            "price",
            "stock",
            "in_stock",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ProductWriteSerializer(serializers.ModelSerializer):
    """
    Сериализатор создания и редактирования товара для менеджеров и администраторов.
    """

    slug = serializers.SlugField(required=False, allow_blank=True)
    tags = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Tag.objects.all(),
        required=False,
    )

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "sku",
            "category",
            "tags",
            "description",
            "price",
            "stock",
            "is_active",
        ]
        read_only_fields = ["id"]

    def validate_price(self, value: Decimal) -> Decimal:
        if value < Decimal("0.00"):
            raise serializers.ValidationError("Цена не может быть отрицательной.")
        return value

    def validate_stock(self, value: int) -> int:
        if value < 0:
            raise serializers.ValidationError("Остаток на складе не может быть отрицательным.")
        return value

    def validate(self, attrs: dict) -> dict:
        # Автоматическая генерация slug при отсутствии
        name = attrs.get("name")
        slug = attrs.get("slug")
        if not slug and name:
            latin_name = transliterate(name)
            base_slug = slugify(latin_name) or slugify(name, allow_unicode=True) or "product"
            candidate_slug = base_slug
            counter = 1
            qs = Product.objects.all()
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            while qs.filter(slug=candidate_slug).exists():
                candidate_slug = f"{base_slug}-{counter}"
                counter += 1
            attrs["slug"] = candidate_slug
        return attrs
