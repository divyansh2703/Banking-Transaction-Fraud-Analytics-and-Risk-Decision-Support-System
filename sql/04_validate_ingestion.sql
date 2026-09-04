USE financial_transaction_analytics;


-- ============================================================
-- PHASE 12 SQL INGESTION VALIDATION
-- ============================================================


-- ============================================================
-- 1. ROW COUNTS
-- ============================================================

SELECT
    'customers' AS dataset,
    COUNT(*) AS actual_rows,
    2000 AS expected_rows,
    CASE
        WHEN COUNT(*) = 2000
        THEN 'PASS'
        ELSE 'FAIL'
    END AS status
FROM customers

UNION ALL

SELECT
    'cards',
    COUNT(*),
    6146,
    CASE
        WHEN COUNT(*) = 6146
        THEN 'PASS'
        ELSE 'FAIL'
    END
FROM cards

UNION ALL

SELECT
    'transactions',
    COUNT(*),
    13305915,
    CASE
        WHEN COUNT(*) = 13305915
        THEN 'PASS'
        ELSE 'FAIL'
    END
FROM transactions

UNION ALL

SELECT
    'mcc_codes',
    COUNT(*),
    109,
    CASE
        WHEN COUNT(*) = 109
        THEN 'PASS'
        ELSE 'FAIL'
    END
FROM mcc_codes

UNION ALL

SELECT
    'fraud_labels',
    COUNT(*),
    8914963,
    CASE
        WHEN COUNT(*) = 8914963
        THEN 'PASS'
        ELSE 'FAIL'
    END
FROM fraud_labels;


-- ============================================================
-- 2. FRAUD LABEL RECONCILIATION
-- ============================================================

SELECT
    fraud_label,
    COUNT(*) AS transaction_count
FROM fraud_labels
GROUP BY fraud_label
ORDER BY fraud_label;


-- Expected:
-- No   8,901,631
-- Yes     13,332


-- ============================================================
-- 3. TRANSACTION CUSTOMER INTEGRITY
-- ============================================================

SELECT
    COUNT(*) AS missing_customer_references,
    CASE
        WHEN COUNT(*) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END AS status

FROM transactions t

LEFT JOIN customers c
    ON t.client_id = c.client_id

WHERE c.client_id IS NULL;


-- ============================================================
-- 4. CARD CUSTOMER INTEGRITY
-- ============================================================

SELECT
    COUNT(*) AS missing_customer_references,
    CASE
        WHEN COUNT(*) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END AS status

FROM cards ca

LEFT JOIN customers c
    ON ca.client_id = c.client_id

WHERE c.client_id IS NULL;


-- ============================================================
-- 5. TRANSACTION CARD INTEGRITY
-- ============================================================

SELECT
    COUNT(*) AS missing_card_references,
    CASE
        WHEN COUNT(*) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END AS status

FROM transactions t

LEFT JOIN cards ca
    ON t.card_id = ca.card_id

WHERE ca.card_id IS NULL;


-- ============================================================
-- 6. TRANSACTION MCC INTEGRITY
-- ============================================================

SELECT
    COUNT(*) AS unknown_mcc_references,
    CASE
        WHEN COUNT(*) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END AS status

FROM transactions t

LEFT JOIN mcc_codes m
    ON t.mcc = m.mcc

WHERE m.mcc IS NULL;


-- ============================================================
-- 7. FRAUD TRANSACTION INTEGRITY
-- ============================================================

SELECT
    COUNT(*) AS fraud_labels_without_transaction,
    CASE
        WHEN COUNT(*) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END AS status

FROM fraud_labels f

LEFT JOIN transactions t
    ON f.transaction_id =
       t.transaction_id

WHERE t.transaction_id IS NULL;


-- ============================================================
-- 8. TRANSACTION DATE RANGE
-- ============================================================

SELECT
    MIN(transaction_datetime)
        AS minimum_transaction_datetime,

    MAX(transaction_datetime)
        AS maximum_transaction_datetime

FROM transactions;


-- Expected:
-- 2010-01-01 00:01:00
-- 2019-10-31 23:59:00


-- ============================================================
-- 9. TRANSACTION CHANNEL RECONCILIATION
-- ============================================================

SELECT
    use_chip,
    COUNT(*) AS transaction_count

FROM transactions

GROUP BY use_chip

ORDER BY transaction_count DESC;


-- Expected:
--
-- Swipe Transaction   6,967,185
-- Chip Transaction    4,780,818
-- Online Transaction  1,557,912


-- ============================================================
-- 10. AMOUNT SIGN RECONCILIATION
-- ============================================================

SELECT

    SUM(
        CASE
            WHEN amount > 0
            THEN 1
            ELSE 0
        END
    ) AS positive_transactions,

    SUM(
        CASE
            WHEN amount < 0
            THEN 1
            ELSE 0
        END
    ) AS negative_transactions,

    SUM(
        CASE
            WHEN amount = 0
            THEN 1
            ELSE 0
        END
    ) AS zero_transactions

FROM transactions;


-- Expected:
--
-- Positive  12,635,227
-- Negative     660,049
-- Zero          10,639


-- ============================================================
-- 11. DATA QUALITY FLAG RECONCILIATION
-- ============================================================

SELECT

    SUM(
        transaction_before_card_open_flag
    ) AS before_open_count,

    SUM(
        transaction_after_card_expiry_flag
    ) AS after_expiry_count,

    SUM(
        channel_location_inconsistency_flag
    ) AS channel_location_inconsistency_count

FROM transactions;


-- Expected:
--
-- Before card open     309
-- After expiry          83
-- Channel/location   5,788