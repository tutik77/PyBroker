# PyBroker — Брокер сообщений на Python

## О проекте

PyBroker — учебный брокер сообщений с протоколом **STOMP 1.2**, реализующий паттерны **Pub/Sub** и **Message Queue** с персистентностью, гарантией доставки at-least-once и клиентским SDK.

Брокер обеспечивает асинхронную коммуникацию между микросервисами через топики (fan-out всем подписчикам) и очереди (доставка одному из потребителей).

## Возможности

### Базовые
- **STOMP 1.2** — стандартный текстовый протокол обмена сообщениями
- **Pub/Sub** — публикация в топики (`/topic/...`), подписка с wildcard-паттернами (`logs.*`)
- **Очереди сообщений** — FIFO и LIFO очереди (`/queue/...`) с конкурирующими потребителями
- **Персистентность** — сохранение сообщений очередей в SQLite, восстановление после перезапуска
- **Гарантия доставки** — at-least-once с подтверждениями (ACK) и таймаутами
- **Клиентский SDK** — асинхронная Python-библиотека с удобным API

### Дополнительные (планируются)
- Приоритеты сообщений
- TTL (Time To Live)
- Dead Letter Queue
- Метрики (Prometheus)
- Web UI мониторинга

## Быстрый старт

### Запуск брокера

```bash
python -m pybroker.server --host 0.0.0.0 --port 9090
```

### Использование SDK

```python
from pybroker.client import BrokerClient

async with BrokerClient("localhost", 9090) as client:
    # Pub/Sub
    await client.subscribe("/topic/events.*", callback=on_event)
    await client.publish("/topic/events.user", b'{"action": "login"}')

    # Очереди
    await client.send("/queue/tasks", b'{"job": "process"}')
    msg = await client.receive("/queue/tasks")
    await client.ack(msg.id)
```

### Тестирование через telnet

STOMP — текстовый протокол, можно подключиться через telnet:
```
$ telnet localhost 9090
CONNECT
accept-version:1.2
host:localhost

^@
```

### Docker

```bash
docker-compose up -d
```

## Структура проекта

```
broker/
├── pybroker/
│   ├── server/              # Серверная часть брокера
│   │   ├── __init__.py
│   │   ├── __main__.py      # Точка входа (python -m pybroker.server)
│   │   ├── broker.py        # Ядро: маршрутизация по destination
│   │   ├── server.py        # TCP-сервер (asyncio.start_server)
│   │   ├── connection.py    # Обработка клиентского соединения
│   │   ├── protocol.py      # Парсинг и сборка STOMP-фреймов
│   │   ├── topic.py         # Pub/Sub: топики и подписки
│   │   ├── queue.py         # Очереди с ACK/NACK
│   │   └── storage.py       # Персистентность (SQLite + WAL)
│   ├── client/              # Клиентский SDK
│   │   ├── __init__.py
│   │   └── client.py        # Асинхронный клиент
│   └── common/              # Общие модули
│       ├── __init__.py
│       └── models.py        # Общие типы (Message, StompFrame)
├── examples/                # Тестовые микросервисы
│   ├── publisher.py         # Публикатор (1 шт.)
│   ├── subscriber_a.py      # Подписчик A
│   └── subscriber_b.py      # Подписчик B
├── tests/
├── docs/
│   ├── architecture.md      # Архитектурная схема
│   ├── data-structures.md   # Структуры данных и протокол STOMP
│   ├── tech-stack.md        # Технический стек
│   └── implementation-plan.md # План реализации
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## Документация

| Документ | Описание |
|----------|----------|
| [Архитектура](docs/architecture.md) | Схема системы, модули и их взаимодействие |
| [Структуры данных](docs/data-structures.md) | Формат сообщений, STOMP-протокол, схема БД |
| [Технический стек](docs/tech-stack.md) | Выбранные технологии и обоснование |
| [План реализации](docs/implementation-plan.md) | Последовательность разработки |

## Лицензия

Учебный проект, ТРПО.
