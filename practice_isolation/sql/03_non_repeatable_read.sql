-- ПОДГОТОВКА
UPDATE accounts SET balance = 500.00 WHERE owner = 'Иванов';
UPDATE accounts SET balance = 1000.00 WHERE owner = 'Петров';
UPDATE accounts SET balance = 750.00 WHERE owner = 'Сидоров';

-- ТЕРМИНАЛ 1
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
SELECT SUM(balance) AS total FROM accounts;

SELECT SUM(balance) AS total FROM accounts;
COMMIT;

-- ТЕРМИНАЛ 2 (выполнить между двумя SELECT в Терминале 1)
BEGIN;
UPDATE accounts SET balance = balance + 300 WHERE owner = 'Иванов';
COMMIT;

-- ПРОВЕРКА
SELECT * FROM accounts;
