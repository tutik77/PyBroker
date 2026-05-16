-- ПОДГОТОВКА
DELETE FROM orders;
INSERT INTO orders (customer, amount, status) VALUES
    ('Иванов', 100.00, 'NEW'),
    ('Петров', 250.00, 'NEW'),
    ('Сидоров', 300.00, 'DONE');

-- ТЕРМИНАЛ 1
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
SELECT COUNT(*) AS new_orders FROM orders WHERE status = 'NEW';
SELECT * FROM orders WHERE status = 'NEW';

SELECT COUNT(*) AS new_orders FROM orders WHERE status = 'NEW';
SELECT * FROM orders WHERE status = 'NEW';
COMMIT;

-- ТЕРМИНАЛ 2 (выполнить между двумя блоками SELECT в Терминале 1)
BEGIN;
INSERT INTO orders (customer, amount, status) VALUES ('Козлов', 500.00, 'NEW');
COMMIT;

-- ПРОВЕРКА
SELECT * FROM orders;
