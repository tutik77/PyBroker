# Online Store Transactions

Демонстрация трёх SQL-транзакций для упрощённой схемы интернет-магазина: размещение заказа, обновление email клиента и добавление продукта. Реализация на Python 3.12 + SQLAlchemy 2.0 + PostgreSQL.

## Архитектура

```
app/
├── config.py          — настройки (Pydantic Settings)
├── database.py        — фабрика engine и session
├── models.py          — ORM-модели (Customers, Products, Orders, OrderItems)
├── schemas.py         — Pydantic DTO для входа/выхода сервисов
├── exceptions.py      — доменные исключения
├── repositories.py    — доступ к данным
├── unit_of_work.py    — UoW с явными границами транзакций
├── services.py        — три сценария (OrderService, CustomerService, ProductService)
├── bootstrap.py       — сборка зависимостей и ожидание БД
└── main.py            — демо-раннер
```

Каждый сервис открывает `UnitOfWork`, который стартует транзакцию в `__enter__` и выполняет `commit`/`rollback` в `__exit__` — любая ошибка автоматически откатывает все изменения.

## Сценарии

- **Сценарий 1 — размещение заказа** ([app/services.py](app/services.py) → `OrderService.place_order`): блокирует строки Customer и Products через `SELECT ... FOR UPDATE`, создаёт `Orders`, добавляет `OrderItems` с вычисленными `subtotal`, затем обновляет `total_amount` суммой по позициям. Всё в одной транзакции.
- **Сценарий 2 — обновление email** (`CustomerService.update_email`): `SELECT ... FOR UPDATE` по клиенту, проверка уникальности нового email, обновление, `flush`. IntegrityError из unique-констрейнта перехватывается как доменный `DuplicateEmailError`.
- **Сценарий 3 — добавление продукта** (`ProductService.add_product`): проверка уникальности имени + вставка. Unique-констрейнт в БД гарантирует консистентность даже при конкурентной вставке.

## Запуск через Docker

```bash
docker compose up --build
```

Контейнер `store-db` поднимает Postgres 16; `store-app` дожидается health-check БД, создаёт схему и прогоняет все три сценария.

Для просмотра данных поднимается Adminer на <http://localhost:8080>. Логин:
- System: **PostgreSQL**
- Server: **db**
- Username / Password / Database: **store** / **store** / **store**

## Локальный запуск

```bash
python -m venv .venv
source .venv/bin/activate   # на Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python -m app.main
```

Для локального запуска поднимите Postgres (например, `docker compose up db`) и убедитесь, что переменные в `.env` указывают на него.
