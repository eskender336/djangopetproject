from decimal import Decimal

import pytest
from django.contrib.admin.sites import site
from rest_framework import status

from apps.catalog.admin import ProductAdmin, ProductImageAdmin
from apps.catalog.models import Category, Product, ProductImage, Tag
from apps.users.models import User, UserRole


@pytest.fixture
def manager_user(db):
    return User.objects.create_user(
        email="manager@example.com",
        password="Password123!",
        role=UserRole.MANAGER,
    )


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        email="admin@example.com",
        password="Password123!",
        role=UserRole.ADMIN,
        is_staff=True,
    )


@pytest.fixture
def manager_client(api_client, manager_user):
    api_client.force_authenticate(user=manager_user)
    return api_client


@pytest.fixture
def admin_client(api_client, admin_user):
    api_client.force_authenticate(user=admin_user)
    return api_client


@pytest.fixture
def sample_data(db):
    cat_parent = Category.objects.create(name="Электроника", slug="electronics")
    cat_child = Category.objects.create(name="Смартфоны", slug="smartphones", parent=cat_parent)
    cat_inactive = Category.objects.create(name="Архив", slug="archive", is_active=False)

    tag_flagship = Tag.objects.create(name="Флагман", slug="flagship")
    tag_sale = Tag.objects.create(name="Скидка", slug="sale")

    prod1 = Product.objects.create(
        name="Супер Смартфон X",
        slug="super-smartphone-x",
        sku="SKU-001",
        category=cat_child,
        description="Флагманский смартфон нового поколения",
        price=Decimal("99990.00"),
        stock=10,
        is_active=True,
    )
    prod1.tags.add(tag_flagship, tag_sale)

    prod2 = Product.objects.create(
        name="Бюджетный Смартфон Y",
        slug="budget-smartphone-y",
        sku="SKU-002",
        category=cat_child,
        description="Доступный смартфон для базовых задач",
        price=Decimal("19990.00"),
        stock=0,
        is_active=True,
    )
    prod2.tags.add(tag_sale)

    prod_inactive = Product.objects.create(
        name="Скрытый Товар Z",
        slug="hidden-item-z",
        sku="SKU-003",
        category=cat_child,
        description="Неактивный товар",
        price=Decimal("5000.00"),
        stock=5,
        is_active=False,
    )

    ProductImage.objects.create(
        product=prod1,
        image="catalog/products/test1.jpg",
        is_main=True,
    )
    ProductImage.objects.create(
        product=prod1,
        image="catalog/products/test2.jpg",
        is_main=False,
    )

    return {
        "cat_parent": cat_parent,
        "cat_child": cat_child,
        "cat_inactive": cat_inactive,
        "tag_flagship": tag_flagship,
        "tag_sale": tag_sale,
        "prod1": prod1,
        "prod2": prod2,
        "prod_inactive": prod_inactive,
    }


@pytest.mark.django_db
class TestCatalogModels:
    def test_category_string_representation(self, sample_data):
        assert str(sample_data["cat_parent"]) == "Электроника"
        assert str(sample_data["cat_child"]) == "Электроника -> Смартфоны"

    def test_tag_string_representation(self, sample_data):
        assert str(sample_data["tag_flagship"]) == "Флагман"

    def test_product_string_and_in_stock(self, sample_data):
        prod1 = sample_data["prod1"]
        prod2 = sample_data["prod2"]
        assert str(prod1) == "Супер Смартфон X (SKU-001)"
        assert prod1.in_stock is True
        assert prod2.in_stock is False

    def test_product_image_string(self, sample_data):
        image = sample_data["prod1"].images.first()
        assert str(image) == "Изображение для Супер Смартфон X"


@pytest.mark.django_db
class TestCatalogAPI:
    def test_list_categories(self, api_client, sample_data):
        url = "/api/catalog/categories/"
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        results = data["results"] if "results" in data else data
        assert len(results) >= 3

    def test_list_tags(self, api_client, sample_data):
        url = "/api/catalog/tags/"
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        results = data["results"] if "results" in data else data
        assert len(results) >= 2

    def test_list_products_public_only_active(self, api_client, sample_data):
        url = "/api/catalog/products/"
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        results = data["results"] if "results" in data else data
        skus = [p["sku"] for p in results]
        assert "SKU-001" in skus
        assert "SKU-002" in skus
        assert "SKU-003" not in skus

    def test_list_products_manager_sees_inactive(self, manager_client, sample_data):
        url = "/api/catalog/products/"
        response = manager_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        results = data["results"] if "results" in data else data
        skus = [p["sku"] for p in results]
        assert "SKU-003" in skus

    def test_filter_products_by_price(self, api_client, sample_data):
        url = "/api/catalog/products/?price_min=50000"
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        results = data["results"] if "results" in data else data
        skus = [p["sku"] for p in results]
        assert "SKU-001" in skus
        assert "SKU-002" not in skus

    def test_filter_products_in_stock(self, api_client, sample_data):
        url = "/api/catalog/products/?in_stock=true"
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        results = data["results"] if "results" in data else data
        skus = [p["sku"] for p in results]
        assert "SKU-001" in skus
        assert "SKU-002" not in skus

    def test_filter_products_by_tags(self, api_client, sample_data):
        url = "/api/catalog/products/?tags=flagship"
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        results = data["results"] if "results" in data else data
        skus = [p["sku"] for p in results]
        assert "SKU-001" in skus
        assert "SKU-002" not in skus

    def test_filter_products_by_category_slug(self, api_client, sample_data):
        url = "/api/catalog/products/?category_slug=smartphones"
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        results = data["results"] if "results" in data else data
        assert len(results) == 2

    def test_search_products(self, api_client, sample_data):
        url = "/api/catalog/products/?search=Бюджетный"
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        results = data["results"] if "results" in data else data
        assert len(results) == 1
        assert results[0]["sku"] == "SKU-002"

    def test_ordering_products_by_price(self, api_client, sample_data):
        url = "/api/catalog/products/?ordering=price"
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        results = data["results"] if "results" in data else data
        prices = [Decimal(p["price"]) for p in results]
        assert prices == sorted(prices)

    def test_retrieve_product_detail(self, api_client, sample_data):
        prod = sample_data["prod1"]
        url = f"/api/catalog/products/{prod.id}/"
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert data["id"] == prod.id
        assert data["category"]["name"] == "Смартфоны"
        assert len(data["tags"]) == 2
        assert len(data["images"]) == 2
        assert data["in_stock"] is True

    def test_create_product_forbidden_for_anonymous_and_customer(
        self, api_client, authenticated_client, sample_data
    ):
        url = "/api/catalog/products/"
        payload = {
            "name": "Новый Товар",
            "sku": "SKU-NEW",
            "category": sample_data["cat_child"].id,
            "price": "1500.00",
            "stock": 5,
        }
        res1 = api_client.post(url, payload)
        assert res1.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

        res2 = authenticated_client.post(url, payload)
        assert res2.status_code == status.HTTP_403_FORBIDDEN

    def test_create_product_success_for_manager(self, manager_client, sample_data):
        url = "/api/catalog/products/"
        payload = {
            "name": "Планшет Pro",
            "sku": "SKU-TAB-01",
            "category": sample_data["cat_child"].id,
            "tags": [sample_data["tag_flagship"].id],
            "description": "Мощный планшет",
            "price": "45000.00",
            "stock": 8,
            "is_active": True,
        }
        response = manager_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["sku"] == "SKU-TAB-01"
        assert response.data["slug"] == "planshet-pro" or "planshet" in response.data["slug"]
        assert Product.objects.filter(sku="SKU-TAB-01").exists()

    def test_update_product_success_for_admin(self, admin_client, sample_data):
        prod = sample_data["prod1"]
        url = f"/api/catalog/products/{prod.id}/"
        payload = {
            "name": "Супер Смартфон X Updated",
            "price": "89990.00",
            "stock": 15,
        }
        response = admin_client.patch(url, payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Супер Смартфон X Updated"
        prod.refresh_from_db()
        assert prod.price == Decimal("89990.00")
        assert prod.stock == 15

    def test_delete_product_success_for_admin(self, admin_client, sample_data):
        prod = sample_data["prod2"]
        url = f"/api/catalog/products/{prod.id}/"
        response = admin_client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Product.objects.filter(id=prod.id).exists()

    def test_create_product_validation_errors(self, admin_client, sample_data):
        url = "/api/catalog/products/"
        payload = {
            "name": "Некорректный Товар",
            "sku": "SKU-001",
            "category": sample_data["cat_child"].id,
            "price": "-100.00",
            "stock": -5,
        }
        response = admin_client.post(url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "sku" in response.data or "price" in response.data or "stock" in response.data


@pytest.mark.django_db
class TestCatalogAdmin:
    def test_admin_registration(self):
        assert site.is_registered(Category)
        assert site.is_registered(Tag)
        assert site.is_registered(Product)
        assert site.is_registered(ProductImage)

    def test_admin_custom_displays(self, sample_data):
        prod_admin = ProductAdmin(Product, site)
        prod = sample_data["prod1"]
        assert prod_admin.in_stock_display(prod) is True

        img_admin = ProductImageAdmin(ProductImage, site)
        img = prod.images.first()
        preview_html = img_admin.image_preview(img)
        assert "<img" in preview_html
