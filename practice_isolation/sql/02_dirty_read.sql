-- ТЕРМИНАЛ 1
UPDATE accounts SET balance = 500.00 WHERE owner = 'Иванов';

BEGIN;
UPDATE accounts SET balance = balance - 300 WHERE owner = 'Иванов';
-- НЕ коммитим, ждём чтение из Терминала 2

ROLLBACK;

-- ТЕРМИНАЛ 2
BEGIN;
SELECT balance FROM accounts WHERE owner = 'Иванов';
COMMIT;

-- ПРОВЕРКА
SELECT * FROM accounts WHERE owner = 'Иванов';
