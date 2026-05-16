# Отчёт по реализации брокера сообщений PyBroker

## Базовая функциональность

| Требование | Файлы | Реализация |
|---|---|---|
| Pub/Sub паттерн | `pybroker/server/topic.py` | TopicManager — fan-out доставка всем подписчикам, поддержка wildcard подписок (`logs.*`) |
| Очереди FIFO/LIFO | `pybroker/server/queue.py` | MessageQueue — heap-очередь с переключением порядка через `queue_type`, round-robin потребителей |
| Публикация в топики/очереди | `pybroker/server/broker.py` | `_publish_to_topic()`, `_publish_to_queue()` — маршрутизация по префиксу `/topic/` и `/queue/` |
| Подписка на топики/очереди | `pybroker/server/broker.py` | `_on_subscribe()` — регистрация в TopicManager или QueueManager с учётом ack-режима |
| Множественные подписчики | `pybroker/server/topic.py`, `queue.py` | Топики: доставка всем. Очереди: round-robin с `_consumer_index` |

## Персистентность

| Требование | Файлы | Реализация |
|---|---|---|
| Сохранение на диск | `pybroker/server/storage.py` | SQLite с WAL-режимом, таблицы `queues` и `messages` |
| Восстановление после перезапуска | `pybroker/server/broker.py` → `restore()` | Сброс IN_FLIGHT→READY, загрузка всех очередей и сообщений в память |
| Гарантия доставки | `pybroker/server/queue.py` | At-least-once: двухфазная доставка (READY→IN_FLIGHT→ACK), visibility timeout 30с, автоматический redelivery |

## Клиентская библиотека

| Файл | Реализация |
|---|---|
| `pybroker/client/client.py` | Асинхронный SDK: `publish()`, `subscribe()`, `ack()`, `nack()`, `unsubscribe()`. Context manager. Фоновый listener. Callback-модель обработки сообщений |

## Протокол взаимодействия

| Файл | Реализация |
|---|---|
| `pybroker/server/protocol.py` | STOMP 1.2 поверх TCP. Парсинг/сборка фреймов, escape-последовательности, content-length, защита от превышения размера (1 МБ) |

## Документация

| Файл | Содержание |
|---|---|
| `README.md` | Описание проекта, цели, требования, ссылки на документацию |
| `docs/architecture.md` | Архитектурная схема, слои, взаимодействие модулей |
| `docs/data-structures.md` | Формат сообщений, STOMP-протокол, схема БД |
| `docs/tech-stack.md` | Выбранные технологии и обоснование |
| `docs/implementation-plan.md` | Последовательность разработки |

## Docker

| Файл | Реализация |
|---|---|
| `Dockerfile` | Python 3.12-slim, установка зависимостей, порты 9090+8080 |
| `docker-compose.yml` | Брокер + publisher + 2 subscriber |

## Дополнительный функционал

### Приоритеты сообщений
- **Файл:** `pybroker/server/queue.py`, `pybroker/common/models.py`
- **Как:** Заголовок `priority: N`, сортировка через min-heap по `-priority`

### TTL
- **Файл:** `pybroker/common/models.py`, `pybroker/server/queue.py`, `broker.py`
- **Как:** Заголовок `x-ttl: секунды`, фоновый `_expiry_loop()` каждую секунду удаляет истёкшие

### Dead Letter Queue
- **Файл:** `pybroker/server/broker.py` → `_move_to_dlq()`, `_handle_failed_delivery()`
- **Как:** После `max_deliveries` (5) неудачных попыток → автоматическое перемещение в `<queue>.DLQ` с метаданными (причина, счётчик, оригинальная очередь)

### Метрики
- **Файл:** `pybroker/server/metrics.py`
- **Как:** Счётчики published/delivered/acked/nacked/timeouts, логирование каждые 30с

### Web UI мониторинга
- **Файлы:** `pybroker/server/web.py`, `pybroker/server/static/index.html`
- **Как:** aiohttp-сервер на порту 8080, REST API `/api/state`, SPA-дашборд с авторефрешем. Показывает: метрики, подключения, топики, очереди в реальном времени

### STOMP 1.2 (стандартный протокол)
- **Файл:** `pybroker/server/protocol.py`
- **Как:** Полная реализация STOMP 1.2 — CONNECT, SEND, SUBSCRIBE, UNSUBSCRIBE, ACK, NACK, DISCONNECT, RECEIPT

### Тестовая среда для демо
- **Файлы:** `demo/order_service.py`, `demo/notification_service.py`, `demo/analytics_service.py`
- **Как:** 3 FastAPI микросервиса (publisher + 2 subscriber), каждый с веб-интерфейсом. Сценарий: создание заказов → уведомления (pub/sub) + обработка (queue). Docker Compose для запуска всего стека: `demo/docker-compose.yml`

## Запуск демо

```bash
cd demo
docker-compose up --build
```

| Сервис | URL | Описание |
|---|---|---|
| Broker Dashboard | http://localhost:8080 | Мониторинг брокера |
| Order Service | http://localhost:8001 | Создание заказов (publisher) |
| Notification Service | http://localhost:8002 | Уведомления (subscriber, pub/sub) |
| Analytics Service | http://localhost:8003 | Аналитика (subscriber, pub/sub + queue) |
