# E-Commerce Backend Engine & Order Processing Platform

[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.1-092E20?style=for-the-badge&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Django REST Framework](https://img.shields.io/badge/DRF-3.15-A30000?style=for-the-badge&logo=django&logoColor=white)](https://www.django-rest-framework.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?style=for-the-badge&logo=redis&logoColor=white)](https://redis.io/)
[![Celery](https://img.shields.io/badge/Celery-5.4-37814A?style=for-the-badge&logo=celery&logoColor=white)](https://docs.celeryq.dev/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Ruff](https://img.shields.io/badge/Code%20Style-Ruff-261230?style=for-the-badge&logo=ruff&logoColor=white)](https://astral.sh/ruff)
[![Tests](https://img.shields.io/badge/Tests-Pytest%20(71%20passed)-success?style=for-the-badge&logo=pytest&logoColor=white)](https://pytest.org/)

Высоконагруженный, транзакционно-безопасный бэкенд интернет-магазина и платформа обработки заказов. Проект спроектирован с учетом требований Enterprise-разработки: строгая защита от состояний гонки (Race Condition), многоуровневая оптимизация ORM-запросов (исключение проблемы $N+1$), распределенная очередь фоновых задач (Celery), периодический сборщик просроченных заказов (Celery Beat), реактивное кэширование в Redis, асинхронная обработка внешних вебхуков платежных шлюзов и автоматизированный CI/CD пайплайн.

---

## 📑 Содержание

- [Архитектура системы](#-архитектура-системы)
- [Используемый стек технологий](#-используемый-стек-технологий)
- [Быстрый старт](#-быстрый-старт)
  - [Запуск через Docker Compose (Рекомендуется)](#1-запуск-через-docker-compose-рекомендуется)
  - [Локальный запуск для разработки](#2-локальный-запуск-для-разработки)
- [Обзор API и документация](#-обзор-api-и-документация)
  - [Интерактивная документация](#интерактивная-документация)
  - [Основные эндпоинты платформы](#основные-эндпоинты-платформы)
- [Решенные инженерные сценарии и подготовка к собеседованиям](#-решенные-инженерные-сценарии-и-подготовка-к-собеседованиям)
  - [1. Защита от Race Condition при списании остатков](#1-борьба-с-race-condition-состояние-гонки-при-покупке-товаров)
  - [2. Ликвидация проблемы $N+1$ запросов в Django ORM](#2-решение-проблемы-n1-запросов-в-orm)
  - [3. Отказоустойчивость фоновых задач (Celery + Redis)](#3-надежность-фоновых-задач-celery--redis)
  - [4. Периодические задачи и автоматический возврат остатков (Celery Beat)](#4-периодические-задачи-celery-beat-автоотмена-заказов)
  - [5. Стратегия кэширования и инвалидация в Redis](#5-кэширование-в-redis-и-реактивная-инвалидация)
  - [6. Асинхронный Python и нативный Async ORM](#6-асинхронный-python-async-def-async-orm-event-loop)
  - [7. Базы данных, составные индексы и изоляция транзакций](#7-базы-данных-и-sql-оптимизация)
  - [8. Безопасность, JWT и ключ идемпотентности](#8-rest-api-безопасность-и-идемпотентность)
- [Тестирование и контроль качества](#-тестирование-и-контроль-качества)
- [CI/CD пайплайн (GitHub Actions)](#-cicd-пайплайн-github-actions)

---

## 🏗 Архитектура системы

Ниже представлена высокоуровневая архитектурная схема платформы, демонстрирующая разделение синхронных HTTP-потоков, асинхронных вебхуков, кэширования и распределенной обработки фоновых задач:

```mermaid
flowchart TB
    subgraph Clients["Клиентский уровень"]
        SPA["Frontend / Web App"]
        Mobile["Mobile Client"]
        PaymentGateway["Payment Gateway (Stripe/YooKassa)"]
    end

    subgraph Entrypoint["API Gateway & Reverse Proxy"]
        Nginx["Nginx / Traefik (HTTPS / Load Balancer)"]
    end

    subgraph Application["Django Application Server (ASGI / WSGI)"]
        AuthView["JWT Auth / Users API"]
        CatalogView["Catalog ViewSet (Cached Read / Filter)"]
        OrderView["Orders / Checkout ViewSet (Atomic Transaction)"]
        AsyncWebhook["Async Payment Webhook Handler (Event Loop)"]
    end

    subgraph Storage["Уровень постоянного хранения (Data Layer)"]
        Postgres[(PostgreSQL 16\nPrimary Database\nRow-Level Locking / B-Tree Indexes)]
    end

    subgraph CacheAndBroker["Кэш и Брокер сообщений"]
        RedisCache[("Redis 7 (DB 1)\nCatalog Cache & Signals Invalidation")]
        RedisBroker[("Redis 7 (DB 0)\nCelery Message Broker & Result Backend")]
    end

    subgraph DistributedWorkers["Распределенные фоновые воркеры"]
        CeleryWorker["Celery Worker Nodes\n- Order Confirmation Email\n- Receipt & PDF Generation"]
        CeleryBeat["Celery Beat Scheduler\n- Cancel Expired Unpaid Orders (Every 5m)"]
    end

    SPA -->|HTTP/REST| Nginx
    Mobile -->|HTTP/REST| Nginx
    PaymentGateway -->|Async HTTP POST Webhook| Nginx

    Nginx -->|/api/auth/, /api/users/| AuthView
    Nginx -->|/api/catalog/| CatalogView
    Nginx -->|/api/orders/| OrderView
    Nginx -->|/api/orders/webhooks/| AsyncWebhook

    CatalogView <-->|Cache Hit / Cache Miss| RedisCache
    CatalogView -->|Read Fallback| Postgres

    AuthView --> Postgres
    OrderView -->|SELECT FOR UPDATE / Atomic Commit| Postgres
    AsyncWebhook -->|Native Async ORM (afirst, asave)| Postgres

    OrderView -.->|transaction.on_commit(delay)| RedisBroker
    CeleryBeat -.->|Schedule Periodic Tasks| RedisBroker
    RedisBroker -->|Consume Tasks| CeleryWorker
    CeleryWorker -->|Update Status / Read Data| Postgres
```

---

## 🛠 Используемый стек технологий

| Компонент | Технология | Обоснование выбора |
| :--- | :--- | :--- |
| **Язык разработки** | `Python 3.12 / 3.11` | Высокая производительность, современные аннотации типов, улучшенный Asyncio Event Loop. |
| **Веб-фреймворк** | `Django 5.1` | Зрелая экосистема, надежный ORM с поддержкой `select_for_update()`, нативных `async` методов, миграций и сигналов. |
| **API Фреймворк** | `Django REST Framework 3.15` | Полнофункциональная сериализация, валидация, встроенная фильтрация и пагинация. |
| **База данных** | `PostgreSQL 16` | ACID-транзакции, пессимистические блокировки строк (`FOR UPDATE`), составные B-Tree индексы, строгие ограничения целостности. |
| **Кэш / In-Memory Store** | `Redis 7` | Субмиллисекундный доступ к горячим данным каталога, поддержка атомарных операций и TTL. |
| **Очередь задач** | `Celery 5.4` | Асинхронное выполнение ресурсоемких операций (отправка email, чеки) без блокировки клиентских потоков. |
| **Планировщик задач** | `Celery Beat` | Периодический мониторинг состояния системы (регулярная очистка и возврат просроченных остатков). |
| **Документация OpenAPI** | `drf-spectacular` | Автоматическая генерация спецификации OpenAPI 3.0, поддержка интерактивных Swagger UI и ReDoc. |
| **Аутентификация** | `djangorestframework-simplejwt` | Защищенная авторизация через JWT с ротацией refresh-токенов и блэклистом. |
| **Контейнеризация** | `Docker & Docker Compose` | Декларативное описание инфраструктуры, изолированные сервисы с Healthcheck. |
| **Тестирование & Линтинг** | `pytest`, `factory-boy`, `faker`, `ruff` | 71 модульный и интеграционный тест, быстрая валидация стиля и статический анализ кода. |

---

## 🚀 Быстрый старт

### 1. Запуск через Docker Compose (Рекомендуется)

Все сервисы (Django Web API, PostgreSQL 16, Redis 7, Celery Worker, Celery Beat) оркестрируются через единый конфигурационный файл `docker-compose.yml` с настроенными проверками доступности (`healthcheck`).

1. **Клонируйте репозиторий:**
   ```bash
   git clone https://github.com/your-username/djangopetproject.git
   cd djangopetproject
   ```

2. **Создайте файл переменных окружения:**
   ```bash
   cp .env.example .env
   ```

3. **Соберите и запустите контейнеры:**
   ```bash
   docker compose up --build -d
   ```

4. **Примените миграции базы данных и создайте суперпользователя:**
   ```bash
   docker compose exec web python manage.py migrate
   docker compose exec web python manage.py createsuperuser
   ```

5. **Сервис готов к работе:**
   - Swagger UI: [http://localhost:8000/api/docs/](http://localhost:8000/api/docs/)
   - Панель администратора: [http://localhost:8000/admin/](http://localhost:8000/admin/)

---

### 2. Локальный запуск для разработки

1. **Создайте и активируйте виртуальное окружение:**
   ```bash
   python -m venv .venv
   # Windows (PowerShell):
   .venv\Scripts\Activate.ps1
   # Linux / macOS:
   source .venv/bin/activate
   ```

2. **Установите зависимости:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **Настройте `.env`:**
   ```bash
   cp .env.example .env
   ```
   *(При локальной разработке без PostgreSQL проект автоматически переключается на SQLite).*

4. **Примените миграции:**
   ```bash
   python manage.py migrate
   ```

5. **Запустите сервер разработки:**
   ```bash
   python manage.py runserver 127.0.0.1:8000
   ```

6. **Запустите Celery Worker и Celery Beat (в отдельных терминалах при наличии Redis):**
   ```bash
   # Терминал 1 (Worker):
   celery -A config worker --loglevel=info

   # Терминал 2 (Beat):
   celery -A config beat --loglevel=info
   ```

---

## 📖 Обзор API и документация

### Интерактивная документация

| Документация | URL | Описание |
| :--- | :--- | :--- |
| **Swagger UI** | [`/api/docs/`](http://localhost:8000/api/docs/) | Интерактивное тестирование эндпоинтов, просмотр схем запросов и ответов. |
| **ReDoc** | [`/api/redoc/`](http://localhost:8000/api/redoc/) | Структурированная документация API в стиле ReDoc. |
| **OpenAPI JSON Schema** | [`/api/schema/`](http://localhost:8000/api/schema/) | Сырая спецификация схемы OpenAPI 3.0. |
| **Django Admin** | [`/admin/`](http://localhost:8000/admin/) | Панель администрирования каталога, пользователей и заказов. |

### Основные эндпоинты платформы

```text
├── Authentication & Users
│   ├── POST   /api/auth/token/              # Получение JWT пары токенов (access + refresh)
│   ├── POST   /api/auth/token/refresh/      # Ротация access-токена с выдачей нового refresh
│   ├── POST   /api/users/register/          # Регистрация нового покупателя
│   └── GET/PUT /api/users/profile/          # Просмотр и редактирование профиля пользователя
│
├── Product Catalog
│   ├── GET    /api/catalog/categories/      # Иерархическое дерево категорий
│   ├── GET    /api/catalog/tags/            # Список тегов товаров
│   ├── GET    /api/catalog/products/        # Каталог товаров (фильтрация по цене, остатку, тегам)
│   ├── GET    /api/catalog/products/{id}/   # Детальная карточка товара
│   ├── GET    /api/catalog/products/popular/# Горячий топ товаров (кэшируется в Redis)
│   └── POST/PUT /api/catalog/products/      # Управление товарами (только Manager / Admin)
│
├── Cart & Order Management
│   ├── GET    /api/orders/cart/             # Просмотр текущей корзины пользователя
│   ├── POST   /api/orders/cart/items/       # Добавление позиции в корзину
│   ├── PUT/DEL /api/orders/cart/items/{id}/ # Обновление количества или удаление товара из корзины
│   ├── POST   /api/orders/cart/clear/       # Полная очистка корзины
│   ├── GET    /api/orders/orders/           # История заказов текущего пользователя
│   ├── POST   /api/orders/orders/checkout/  # Атомарное оформление заказа с Idempotency-Key
│   └── POST   /api/orders/orders/{id}/cancel/# Отмена заказа с возвратом остатков на склад
│
└── Webhooks & Integrations
    └── POST   /api/orders/webhooks/payment/ # Асинхронная обработка событий оплаты (Async ORM)
```

---

## 🧠 Решенные инженерные сценарии и подготовка к собеседованиям

Раздел содержит детальный разбор ключевых архитектурных и инженерных решений, реализованных в кодовой базе проекта. Он служит практическим справочником для технических интервью на позицию **Middle+/Senior Python/Django Backend Developer**.

---

### 1. Борьба с Race Condition (состояние гонки при покупке товаров)

#### 🔴 Проблема
В интернет-магазинах с высокой конкурентностью запросов (flash-распродажи, ограниченный тираж) возникает классическая проблема параллельного доступа — **Lost Update (потерянное обновление)** или **Overbooking (продажа товара в минус)**:
1. На складе остался ровно 1 ноутбук (`stock = 1`).
2. Одновременно приходят 2 клиента и нажимают кнопку «Оформить заказ».
3. Поток А считывает `stock = 1` (валидация пройдена).
4. Поток Б считывает `stock = 1` (валидация пройдена).
5. Поток А списывает 1 шт., устанавливая `stock = 0`.
6. Поток Б списывает 1 шт., устанавливая `stock = -1` (или перезаписывает остаток некорректным значением). В итоге оформлено два заказа на один физический товар.

#### 🟢 Архитектурное решение в проекте
Решение реализовано в [`CheckoutService.create_order_from_cart`](file:///c:/Users/Администратор/Documents/djangopetproject/apps/orders/services.py#L65-L144):
- **Пессимистическая блокировка строк на уровне СУБД (Row-level Locking)**: вызов `Product.objects.select_for_update().filter(id__in=product_ids)` внутри блока `transaction.atomic()`.
- **SQL трансляция**: PostgreSQL выполняет запрос `SELECT ... FROM catalog_product WHERE id IN (...) FOR UPDATE`. Строки блокируются до завершения (COMMIT или ROLLBACK) текущей транзакции. Все конкурирующие транзакции встают в очередь ожидания освобождения блокировки.
- **Атомарный F-выражение апдейт**: `Product.objects.filter(id=item.product_id).update(stock=F("stock") - item.quantity)` выполняет списание напрямую на стороне PostgreSQL (`UPDATE catalog_product SET stock = stock - quantity`), гарантируя вычисление остатка на уровне базы данных.

```python
with transaction.atomic():
    # Блокировка строк продуктов от изменений параллельными транзакциями
    product_ids = [item.product_id for item in cart_items]
    locked_products = {
        p.id: p for p in Product.objects.select_for_update().filter(id__in=product_ids)
    }

    # Валидация актуальных остатков внутри транзакции
    cls._validate_items_and_stock(cart_items, locked_products)

    # Создание заказа и позиций
    order = Order.objects.create(...)
    OrderItem.objects.bulk_create(...)

    # Атомарное списание остатков через F-expression
    for item in cart_items:
        Product.objects.filter(id=item.product_id).update(stock=F("stock") - item.quantity)
```

---

### 2. Решение проблемы $N+1$ запросов в ORM

#### 🔴 Проблема
При рендере списка товаров или заказов с вложенными связями (категории, теги, изображения, позиции заказа) обращение к атрибутам связанных моделей приводит к выполнению отдельного SQL-запроса на каждую строку: для $N$ записей генерируется $1 + N$ (или $1 + 2N$) запросов к базе данных, вызывая деградацию производительности и перегрузку пула соединений СУБД.

#### 🟢 Архитектурное решение в проекте
В кодовой базе проекта реализована дифференцированная оптимизация связей в зависимости от их кардинальности:
1. **`select_related` (SQL `INNER JOIN` / `LEFT OUTER JOIN`)** — для связей типа `ForeignKey` и `OneToOne`:
   - При выборке товаров: `Product.objects.select_related("category")`.
   - При выборке категорий с родителями: `Category.objects.select_related("parent")`.
   - При выборке заказов: `Order.objects.select_related("user")`.
2. **`prefetch_related` (отдельный оптимизированный запрос `WHERE id IN (...)`)** — для связей типа `ManyToManyField` и обратных `ForeignKey`:
   - При выборке товаров с тегами и фото: `Product.objects.prefetch_related("tags", "images")`.
   - При выборке заказов с элементами и их товарами: `Order.objects.prefetch_related("items__product")`.
   - При выборке корзины: `Cart.objects.prefetch_related("items__product")`.

```python
# Было (N+1 проблема): 1 запрос на товары + 50 запросов на категории + 50 на теги + 50 на фото = 151 SQL запрос!
# Стало: ровно 3 высокоэффективных запроса:
queryset = Product.objects.select_related("category").prefetch_related("tags", "images")
```

---

### 3. Надежность фоновых задач (Celery + Redis)

#### 🔴 Проблемы интеграции очередей
1. **Database-Worker Race Condition (Phantom Records)**: если отправить задачу в Celery (`task.delay(order_id)`) *до* завершения транзакции в БД, воркер может мгновенно подхватить задачу из Redis до того, как PostgreSQL закоммитит транзакцию. Воркер упадет с ошибкой `Order.DoesNotExist`.
2. **Временные сбои внешних API (Transient Failures)**: сетевые задержки и таймауты SMTP-сервера или внешнего сервиса генерации чеков могут приводить к потере сообщений.
3. **Thundering Herd при ретраях**: если все упавшие воркеры повторяют попытку ровно через фиксированные 60 секунд, они одновременно перегружают упавший сервис.

#### 🟢 Архитектурное решение в проекте
В файле [`apps/orders/tasks.py`](file:///c:/Users/Администратор/Documents/djangopetproject/apps/orders/tasks.py) и [`apps/orders/services.py`](file:///c:/Users/Администратор/Documents/djangopetproject/apps/orders/services.py):
- **Гарантированный запуск через `transaction.on_commit`**: Celery-задачи диспетчеризуются исключительно после успешного коммита транзакции в БД:
  ```python
  transaction.on_commit(lambda: send_order_confirmation_email_task.delay(order_id))
  transaction.on_commit(lambda: generate_order_receipt_task.delay(order_id))
  ```
- **Экспоненциальная задержка с джиттером (Exponential Backoff + Jitter)**: параметры `autoretry_for=(Exception,)`, `retry_backoff=True` и `retry_jitter=True` автоматически увеличивают интервал между попытками и добавляют случайный шум, устраняя эффект лавины повторных запросов.
- **Идемпотентность выполнения**: задачи безопасно обрабатывают повторные вызовы без дублирования побочных эффектов.

---

### 4. Периодические задачи (Celery Beat): автоотмена заказов

#### 🔴 Проблема
Пользователи кладут товары в корзину и создают заказ со статусом `PENDING`, списывая товар со склада. Если клиент не оплачивает заказ, остатки на складе оказываются «зависшими», из-за чего магазин теряет реальные продажи.

#### 🟢 Архитектурное решение в проекте
- **Расписание Celery Beat**: в [`config/celery.py`](file:///c:/Users/Администратор/Documents/djangopetproject/config/celery.py) настроена регулярная задача, запускаемая каждые 5 минут (`crontab(minute="*/5")`).
- **Сборщик просроченных заказов**: задача [`cancel_unpaid_expired_orders_task`](file:///c:/Users/Администратор/Documents/djangopetproject/apps/orders/tasks.py#L123-L153) выбирает все заказы `status=OrderStatus.PENDING`, созданные более 30 минут назад (`created_at__lte=now() - 30 min`).
- **Атомарный возврат товаров**: для каждого заказа вызывается `CheckoutService.cancel_order()`, который в атомарной транзакции переводит статус заказа в `CANCELLED` и возвращает товары на склад через `Product.objects.filter(...).update(stock=F("stock") + item.quantity)`.

---

### 5. Кэширование в Redis и реактивная инвалидация

#### 🔴 Проблема
Главная страница интернет-магазина и список популярных товаров генерируют тысячи однотипных тяжелых запросов к базе данных в секунду. Простое кэширование с фиксированным временем жизни (TTL) приводит либо к показу неактуальных цен и остатков (Stale Data), либо к постоянным промахам кэша (Cache Miss).

#### 🟢 Архитектурное решение в проекте
В [`CatalogCacheService`](file:///c:/Users/Администратор/Documents/djangopetproject/apps/catalog/services.py) и [`apps/catalog/signals.py`](file:///c:/Users/Администратор/Documents/djangopetproject/apps/catalog/signals.py):
- **Cache Aside Pattern**: при запросе к эндпоинту `/api/catalog/products/popular/` данные сначала ищутся в Redis по ключу `catalog:popular_products:{limit}`. При промахе данные считываются из PostgreSQL с полной оптимизацией связей, сериализуются и сохраняются в Redis с TTL = 1 час (3600 с).
- **Реактивная инвалидация по сигналам (Event-Driven Invalidation)**: обработчики сигналов Django `post_save` и `post_delete` для моделей `Product` и `Category` мгновенно сбрасывают все ключи кэша каталога через `cache.delete_many(...)` при любом изменении ассортимента, гарантируя 100% консистентность данных.

---

### 6. Асинхронный Python (Async def, Async ORM, Event Loop)

#### 🔴 Проблема
Платежные провайдеры (ЮKassa, Stripe, CloudPayments) отправляют HTTP-уведомления (вебхуки) о результатах транзакций. Классический синхронный WSGI-воркер при обработке вебхука блокирует рабочий поток на время выполнения I/O операций (верификация подписи, валидация, сетевые запросы), что при пиковых нагрузках приводит к исчерпанию пула потоков веб-сервера.

#### 🟢 Архитектурное решение в проекте
В [`apps/orders/webhooks.py`](file:///c:/Users/Администратор/Documents/djangopetproject/apps/orders/webhooks.py):
- **Нативный `async def` эндпоинт**: `payment_webhook_view(request)` выполняется в неблокирующем Event Loop Django ASGI.
- **Django 5 Async ORM**: прямые асинхронные вызовы к СУБД без блокировки потоков:
  - `await Order.objects.filter(id=order_id).afirst()`
  - `await order.asave(update_fields=["status", "updated_at"])`
  - `await order.arefresh_from_db()`
- **Безопасная интеграция синхронных транзакций**: вызов сложной бизнес-логики с возвратом товаров на склад изолирован через мост `await sync_to_async(CheckoutService.cancel_order)(order=order)`.

---

### 7. Базы данных и SQL-оптимизация

#### 🟢 Архитектурное решение в проекте
1. **Составные индексы (Composite B-Tree Indexes)**:
   - В модели `Product`: `Index(fields=["category", "price"])` для ускорения выборки и фильтрации товаров внутри категории по диапазону цен.
   - В модели `Order`: `Index(fields=["user", "status"])` для мгновенной фильтрации заказов конкретного пользователя по их статусу в личном кабинете.
   - Временные индексы: `Index(fields=["created_at"])` для быстрой сортировки хронологических списков и поиска устаревших заказов.
2. **Ограничения целостности на уровне БД**:
   - `UniqueConstraint(fields=["cart", "product"])` в таблице `CartItem` исключает появление дублирующихся строк одного товара в одной корзине.
   - `models.PROTECT` на внешних ключах `category` и `user` предотвращает случайное удаление категорий и учетных записей, к которым привязаны существующие заказы и товары.
3. **Уровни изоляции транзакций**: использование стандартного для PostgreSQL уровня `Read Committed` в сочетании с явным пессимистическим блокированием (`SELECT FOR UPDATE`), что обеспечивает идеальный баланс между максимальной производительностью чтения и строгой сериализуемостью критических операций списания балансов и остатков.

---

### 8. REST API, Безопасность и Идемпотентность

#### 🟢 Архитектурное решение в проекте
1. **Защита от дублирования заказов через `Idempotency-Key`**:
   - Клиент генерирует уникальный UUID и передает его в теле запроса `/api/orders/orders/checkout/` (поле `idempotency_key`).
   - Если из-за сетевого сбоя или повторного клика пользователя запрос отправляется дважды, `CheckoutService._check_idempotency` находит уже созданный заказ и возвращает его без повторного списания денег и уменьшения остатков на складе.
2. **JWT-аутентификация с ротацией**:
   - `ACCESS_TOKEN_LIFETIME = 60 минут`, `REFRESH_TOKEN_LIFETIME = 7 дней`.
   - Включена ротация refresh-токенов (`ROTATE_REFRESH_TOKENS = True`) с помещением использованных токенов в блэклист (`BLACKLIST_AFTER_ROTATION = True`), что защищает от повторного использования перехваченных токенов.
3. **Ролевой контроль доступа (RBAC)**:
   - Кастомный пермишен `IsAdminOrManagerOrReadOnly` разделяет права: чтение доступно всем, модификация каталога разрешена только пользователям с ролями `MANAGER` или `ADMIN`.

---

## 🧪 Тестирование и контроль качества

В проекте настроен всеобъемлющий тестовый комплект на базе `pytest-django`, `factory-boy` и `faker`. Покрыты все критические бизнес-сценарии:

- **71 тест** покрывает модули каталога, корзины, заказов, пользователей, асинхронных вебхуков, Celery-задач и кэширования.
- Изоляция тестовой базы данных с поддержкой быстрой очистки фикстур.
- Тестирование сигналов инвалидации кэша и работы `LocMemCache`.
- Тестирование отложенных триггеров `transaction.on_commit`.

### Запуск тестов локально:

```bash
# Запуск полного набора тестов
pytest

# Запуск с подробным выводом и проверкой покрытия
pytest -v -s
```

### Проверка стиля кода и статический анализ (Ruff):

```bash
# Проверка линтером
ruff check .

# Проверка форматирования
ruff format --check .
```

---

## 🔄 CI/CD пайплайн (GitHub Actions)

В репозитории настроен автоматический пайплайн непрерывной интеграции [`.github/workflows/ci.yml`](file:///.github/workflows/ci.yml), который запускается на каждый `push` и `pull_request` в ветки `main` и `master`:

1. **Job: Lint & Formatting**:
   - Запуск `ruff check .` (проверка соответствия PEP8, обнаружение багов, неиспользуемых импортов).
   - Запуск `ruff format --check .` (проверка форматирования кода).
2. **Job: Test Suite (Matrix Build)**:
   - Тестирование в матрице версий Python (`3.11`, `3.12`).
   - Развертывание служебных контейнеров **PostgreSQL 16** и **Redis 7** в среде GitHub Actions.
   - Прогон полного набора тестов `pytest`.
3. **Job: Docker Build**:
   - Валидация сборки production-ready Docker-образа (`docker build .`).

---

## 📄 Лицензия

Проект распространяется под свободной лицензией **MIT**. Подробная информация находится в файле `LICENSE`.
