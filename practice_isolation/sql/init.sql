-- Создание таблицы счетов
CREATE TABLE accounts (
    id SERIAL PRIMARY KEY,
    owner VARCHAR(100) NOT NULL,
    balance DECIMAL(10, 2) NOT NULL DEFAULT 0.00
);

-- Создание таблицы заказов (для phantom read)
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    customer VARCHAR(100) NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'NEW'
);

-- Тестовые данные для счетов
INSERT INTO accounts (owner, balance) VALUES
    ('Иванов', 500.00),
    ('Петров', 1000.00),
    ('Сидоров', 750.00);

-- Тестовые данные для заказов
INSERT INTO orders (customer, amount, status) VALUES
    ('Иванов', 100.00, 'NEW'),
    ('Петров', 250.00, 'NEW'),
    ('Сидоров', 300.00, 'DONE');
