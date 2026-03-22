# План реализации

## Общий подход

Инкрементальная разработка — каждый шаг даёт работающую (пусть и неполную) систему, которую можно запустить и проверить. Порядок: от ядра к периферии.

## Этап 2: Базовая функциональность (MVP)

### Шаг 1. Модель сообщения и STOMP-протокол
**Файлы:** `pybroker/common/models.py`, `pybroker/server/protocol.py`

- Dataclass `Message` с полями: id, destination, body, headers, timestamp
- Dataclass `StompFrame` с полями: command, headers, body
- Парсер STOMP-фреймов: чтение из TCP-потока до `\0`, разбор на команду/заголовки/тело
- Сборщик STOMP-фреймов: формирование фрейма из команды, заголовков и тела

**Проверка:** unit-тест — собрать фрейм → распарсить → получить исходные данные.

### Шаг 2. TCP-сервер и соединения
**Файлы:** `pybroker/server/server.py`, `pybroker/server/connection.py`

- `BrokerServer` — запуск `asyncio.start_server(host, port)`
- `Connection` — обёртка над reader/writer, уникальный ID, хранение состояния (подписки)
- Цикл чтения: `while True: frame = await protocol.read_frame(reader)`
- Обработка CONNECT → ответ CONNECTED
- Диспетчеризация STOMP-команд на обработчики

**Проверка:** запустить сервер, подключиться `telnet`, отправить CONNECT — получить CONNECTED.

### Шаг 3. Pub/Sub (in-memory)
**Файлы:** `pybroker/server/topic.py`, `pybroker/server/broker.py`

- `TopicManager` — `dict[str, set[Connection]]` для точных подписок
- Wildcard-подписки: `logs.*` матчит `logs.error`
- SUBSCRIBE с `destination:/topic/...` → добавить подписчика
- SEND с `destination:/topic/...` → fan-out MESSAGE всем подписчикам
- UNSUBSCRIBE → убрать подписчика
- Автоматическая отписка при отключении клиента

**Проверка:** 1 publisher + 2 subscriber, отправить SEND — оба получили MESSAGE.

### Шаг 4. Очереди сообщений (in-memory)
**Файлы:** `pybroker/server/queue.py` (дополнение `broker.py`)

- `QueueManager` — `dict[str, Queue]`
- `Queue` — `deque` для FIFO (`popleft`) и LIFO (`pop`), тип задаётся заголовком `x-queue-type` при первом обращении
- SUBSCRIBE с `destination:/queue/...`, `ack:client` → регистрация потребителя
- SEND с `destination:/queue/...` → добавить в очередь, доставить потребителю
- ACK → удалить сообщение
- NACK → вернуть в очередь
- Round-robin распределение между потребителями
- Двухфазная доставка: `READY → IN_FLIGHT → DONE`
- Visibility timeout: фоновая корутина `check_timeouts()` каждую секунду

**Проверка:** 1 producer + 2 consumer, отправить 10 сообщений — каждый consumer получил ~5.

### Шаг 5. Персистентность
**Файлы:** `pybroker/server/storage.py`

- `Storage` — класс с async-методами: `save_message()`, `delete_message()`, `load_pending()`, `update_status()`
- SQLite с WAL mode через `aiosqlite`
- Создание таблиц `messages` и `queues` при первом запуске
- При старте брокера: `load_pending()` → восстановить `READY` и `IN_FLIGHT` сообщения в memory-очереди

**Проверка:** отправить сообщения → перезапустить брокер → сообщения на месте.

### Шаг 6. Клиентский SDK
**Файлы:** `pybroker/client/client.py`

- `BrokerClient` — async context manager
- Внутри — формирование и парсинг STOMP-фреймов, скрытых от пользователя
- Методы: `connect()`, `close()`, `publish()`, `subscribe()`, `send()`, `ack()`, `nack()`
- Фоновая корутина для приёма push-сообщений MESSAGE (подписки)
- Callback-модель: `await client.subscribe("/topic/logs.*", callback=fn)`
- Обработка разрыва соединения с информативной ошибкой

**Проверка:** переписать тестовые микросервисы на SDK — всё работает через клиентскую библиотеку.

### Шаг 7. Тестовые микросервисы и Docker
**Файлы:** `examples/publisher.py`, `examples/subscriber_a.py`, `examples/subscriber_b.py`, `Dockerfile`, `docker-compose.yml`

- Publisher: отправляет SEND в `/topic/events` + SEND в `/queue/tasks`
- Subscriber A: SUBSCRIBE на `/topic/events`
- Subscriber B: SUBSCRIBE на `/topic/events` + SUBSCRIBE на `/queue/tasks`
- `docker-compose.yml`: 4 сервиса (broker, publisher, subscriber_a, subscriber_b)
- Подробные логи событий в каждом сервисе

**Проверка:** `docker-compose up` — видны логи взаимодействия всех сервисов.

## Этап 3: Дополнительный функционал

*(реализуется после приёмки этапа 2)*

- Приоритетные очереди (кастомный заголовок `priority`, сортировка при dequeue)
- TTL сообщений (заголовок `x-ttl`, фоновая задача `purge_expired`)
- Dead Letter Queue (перенос после N неудачных доставок в отдельную очередь)
- Метрики (внутренние счётчики: опубликовано, доставлено, ACK, NACK, таймауты)

## Этап 4: Финализация

- Prometheus endpoint для метрик
- Web UI мониторинга (опционально)
- Нагрузочное тестирование
- Финальная документация

## Зависимости между шагами

```
Шаг 1 (модели, STOMP-протокол)
  │
  ▼
Шаг 2 (TCP-сервер)
  │
  ├──────────────┐
  ▼              ▼
Шаг 3          Шаг 4
(pub/sub)      (очереди)
  │              │
  └──────┬───────┘
         ▼
       Шаг 5 (персистентность)
         │
         ▼
       Шаг 6 (SDK)
         │
         ▼
       Шаг 7 (Docker + демо)
```

Шаги 3 и 4 могут разрабатываться параллельно, т.к. топики и очереди независимы друг от друга.
