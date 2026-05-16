-- ПОДГОТОВКА
UPDATE accounts SET balance = 500.00 WHERE owner = 'Иванов';

-- ТЕРМИНАЛ 1
BEGIN;
SELECT balance FROM accounts WHERE owner = 'Иванов';

UPDATE accounts SET balance = 200.00 WHERE owner = 'Иванов';
COMMIT;

-- ТЕРМИНАЛ 2 (выполнить между SELECT и UPDATE в Терминале 1)
BEGIN;
SELECT balance FROM accounts WHERE owner = 'Иванов';

UPDATE accounts SET balance = 800.00 WHERE owner = 'Иванов';
COMMIT;

-- ПРОВЕРКА
SELECT * FROM accounts WHERE owner = 'Иванов';
