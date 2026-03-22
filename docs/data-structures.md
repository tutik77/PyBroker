# Структуры данных

## Сообщение (Message)

Центральная сущность брокера. Формат единый для топиков и очередей.

```python
@dataclass
class Message:
    id: str                    # UUID4, уникальный идентификатор
    destination: str           # /topic/name или /queue/name
    body: bytes                # Полезная нагрузка (непрозрачна для брокера)
    headers: dict[str, str]    # Заголовки из STOMP-фрейма
    timestamp: float           # Unix timestamp создания
```

## Протокол: STOMP 1.2

STOMP (Simple Text Oriented Messaging Protocol) — текстовый протокол поверх TCP. Спецификация — 15 страниц.

### Формат фрейма

```
COMMAND\n
header1:value1\n
header2:value2\n
\n
body\0
```

- Первая строка — команда
- Заголовки — `ключ:значение`, по одному на строку
- Пустая строка отделяет заголовки от тела
- Тело завершается нулевым байтом `\0`
- Если есть заголовок `content-length`, тело читается по длине (позволяет передавать `\0` внутри тела)

### Адресация (destinations)

Тип доставки определяется префиксом `destination`:

| Префикс | Тип | Поведение |
|----------|-----|-----------|
| `/topic/` | Pub/Sub | Сообщение всем подписчикам |
| `/queue/` | Очередь | Сообщение одному потребителю |

Примеры: `/topic/logs.error`, `/topic/events.*`, `/queue/tasks`, `/queue/emails`

### Клиентские фреймы

**CONNECT** — установка соединения:
```
CONNECT
accept-version:1.2
host:localhost

\0
```

**SEND** — отправить сообщение в топик или очередь:
```
SEND
destination:/topic/logs.error
content-type:text/plain
receipt:msg-1

disk full\0
```

```
SEND
destination:/queue/tasks
content-type:application/json

{"job": "resize_image"}\0
```

**SUBSCRIBE** — подписаться на топик или очередь:
```
SUBSCRIBE
destination:/topic/logs.*
id:sub-0
ack:auto

\0
```

```
SUBSCRIBE
destination:/queue/tasks
id:sub-1
ack:client
x-queue-type:LIFO

\0
```

- `id` — уникальный идентификатор подписки (нужен для UNSUBSCRIBE)
- `ack:auto` — для топиков (подтверждение не требуется)
- `ack:client` — для очередей (требуется явный ACK)
- `x-queue-type` — кастомный заголовок, задаёт тип очереди при первом обращении (FIFO по умолчанию)

**UNSUBSCRIBE** — отписаться:
```
UNSUBSCRIBE
id:sub-0

\0
```

**ACK** — подтвердить обработку сообщения:
```
ACK
id:msg-uuid-xxx

\0
```

**NACK** — отклонить сообщение (вернуть в очередь):
```
NACK
id:msg-uuid-xxx

\0
```

**DISCONNECT** — корректное закрытие:
```
DISCONNECT
receipt:disconnect-1

\0
```

### Серверные фреймы

**CONNECTED** — ответ на CONNECT:
```
CONNECTED
version:1.2
server:PyBroker/1.0

\0
```

**MESSAGE** — доставка сообщения подписчику:
```
MESSAGE
destination:/topic/logs.error
message-id:uuid-xxx
subscription:sub-0
content-type:text/plain

disk full\0
```

**RECEIPT** — подтверждение обработки фрейма с `receipt`:
```
RECEIPT
receipt-id:msg-1

\0
```

**ERROR** — ошибка:
```
ERROR
message:Queue not found

Queue 'tasks' does not exist\0
```

### Пример полного диалога

```
CLIENT:  CONNECT
         accept-version:1.2
         host:localhost
         \0

SERVER:  CONNECTED
         version:1.2
         server:PyBroker/1.0
         \0

CLIENT:  SUBSCRIBE
         destination:/topic/logs.*
         id:sub-0
         ack:auto
         \0

CLIENT:  SEND
         destination:/topic/logs.error
         content-type:text/plain
         \0

SERVER:  MESSAGE                          ← push подписчику
         destination:/topic/logs.error
         message-id:a1b2c3d4
         subscription:sub-0

         disk full\0

CLIENT:  SUBSCRIBE
         destination:/queue/tasks
         id:sub-1
         ack:client
         \0

(другой клиент отправляет в очередь)

SERVER:  MESSAGE                          ← push потребителю
         destination:/queue/tasks
         message-id:e5f6g7h8
         subscription:sub-1

         {"job": "resize"}\0

CLIENT:  ACK
         id:e5f6g7h8
         \0

CLIENT:  DISCONNECT
         receipt:bye
         \0

SERVER:  RECEIPT
         receipt-id:bye
         \0
```

## Топик (Topic)

```python
class Topic:
    name: str                           # Имя, напр. "logs.error"
    subscribers: set[Connection]        # Множество подписчиков
```

**Паттерн-матчинг** для wildcard-подписок:
- `logs.*` → матчит `logs.error`, `logs.info` (один уровень вложенности)
- Реализация: разделение по `.`, сегмент `*` матчит любой один сегмент

**Хранение подписок в брокере:**
```python
# Точные подписки — O(1) lookup
subscriptions: dict[str, set[Connection]]

# Wildcard-подписки — проверяются при каждом SEND
wildcard_subscriptions: list[tuple[str, Connection]]
```

## Очередь (Queue)

```python
class Queue:
    name: str                                        # Имя очереди
    queue_type: str = "FIFO"                         # FIFO или LIFO
    messages: collections.deque[Message]             # Ожидающие доставки (READY)
    in_flight: dict[str, tuple[Message, float, int]] # msg_id → (msg, время_выдачи, попытка)
    consumers: list[Connection]                      # Привязанные потребители
    consumer_index: int = 0                          # Индекс для round-robin
    visibility_timeout: float = 30.0                 # Секунд до повторной доставки
```

- **FIFO:** `messages.popleft()` — первый пришёл, первый вышел
- **LIFO:** `messages.pop()` — последний пришёл, первый вышел (стек)

### Состояния сообщения в очереди

```
                              ack()
┌─────────┐   consume()   ┌───────────┐   ──────────►  удалено
│  READY  │──────────────►│ IN_FLIGHT │
└─────────┘               └───────────┘
     ▲                         │
     │     timeout / nack()    │
     └─────────────────────────┘
         (повторная доставка)
```

## Схема базы данных (SQLite)

```sql
-- Сообщения очередей (pub/sub не персистится)
CREATE TABLE messages (
    id          TEXT PRIMARY KEY,
    queue_name  TEXT NOT NULL,
    body        BLOB NOT NULL,
    headers     TEXT NOT NULL DEFAULT '{}',  -- JSON
    status      TEXT NOT NULL DEFAULT 'READY',  -- READY | IN_FLIGHT
    created_at  REAL NOT NULL,                  -- Unix timestamp
    locked_at   REAL,                           -- когда выдано потребителю
    delivery_count INTEGER NOT NULL DEFAULT 0,

    CONSTRAINT valid_status CHECK (status IN ('READY', 'IN_FLIGHT'))
);

-- Индексы для быстрых запросов
CREATE INDEX idx_messages_queue_status ON messages(queue_name, status, created_at);
CREATE INDEX idx_messages_locked_at ON messages(locked_at) WHERE status = 'IN_FLIGHT';

-- Метаданные очередей
CREATE TABLE queues (
    name                TEXT PRIMARY KEY,
    queue_type          TEXT NOT NULL DEFAULT 'FIFO',  -- FIFO | LIFO
    visibility_timeout  REAL NOT NULL DEFAULT 30.0,
    created_at          REAL NOT NULL
);
```

### Ключевые SQL-операции

```sql
-- Получить следующее сообщение (FIFO — ORDER BY created_at ASC, LIFO — DESC)
UPDATE messages
SET status = 'IN_FLIGHT', locked_at = ?, delivery_count = delivery_count + 1
WHERE id = (
    SELECT id FROM messages
    WHERE queue_name = ? AND status = 'READY'
    ORDER BY created_at ASC  -- или DESC для LIFO
    LIMIT 1
)
RETURNING *;

-- Подтвердить (ACK)
DELETE FROM messages WHERE id = ? AND status = 'IN_FLIGHT';

-- Вернуть просроченные IN_FLIGHT в READY
UPDATE messages
SET status = 'READY', locked_at = NULL
WHERE status = 'IN_FLIGHT'
  AND locked_at + ? < ?;
```

## Внутренние структуры брокера

```python
class Broker:
    topics: dict[str, Topic]          # Имя → объект топика
    queues: dict[str, Queue]          # Имя → объект очереди
    connections: dict[str, Connection] # ID соединения → объект
    storage: Storage                   # Слой персистентности
```

Все структуры живут в памяти одного потока `asyncio`. Диск используется только для персистентности очередей — при старте данные загружаются из SQLite обратно в `deque`.
