USE financial_transaction_analytics;


-- ============================================================
-- BQR003
-- FRAUD CONCENTRATION IN LABELLED TRANSACTIONS
-- ============================================================


-- ============================================================
-- 1. OVERALL FRAUD PREVALENCE
-- ============================================================

SELECT

    COUNT(*) AS labelled_transactions,

    SUM(
        CASE
            WHEN fraud_label = 'Yes'
            THEN 1
            ELSE 0
        END
    ) AS fraud_transactions,

    ROUND(
        100.0
        *
        SUM(
            CASE
                WHEN fraud_label = 'Yes'
                THEN 1
                ELSE 0
            END
        )
        /
        COUNT(*),
        6
    ) AS fraud_rate_pct

FROM fraud_labels;


-- ============================================================
-- 2. FRAUD BY CHANNEL
-- ============================================================

SELECT

    t.use_chip,

    COUNT(*) AS labelled_transactions,

    SUM(
        CASE
            WHEN f.fraud_label = 'Yes'
            THEN 1
            ELSE 0
        END
    ) AS fraud_transactions,

    ROUND(
        100.0
        *
        SUM(
            CASE
                WHEN f.fraud_label = 'Yes'
                THEN 1
                ELSE 0
            END
        )
        /
        COUNT(*),
        6
    ) AS fraud_rate_pct

FROM fraud_labels f

JOIN transactions t
    ON t.transaction_id =
       f.transaction_id

GROUP BY t.use_chip

ORDER BY fraud_rate_pct DESC;


-- ============================================================
-- 3. FRAUD AMOUNT PROFILE
-- ============================================================

SELECT

    f.fraud_label,

    COUNT(*) AS transaction_count,

    ROUND(
        AVG(
            ABS(t.amount)
        ),
        2
    ) AS mean_absolute_amount,

    ROUND(
        MIN(
            ABS(t.amount)
        ),
        2
    ) AS min_absolute_amount,

    ROUND(
        MAX(
            ABS(t.amount)
        ),
        2
    ) AS max_absolute_amount

FROM fraud_labels f

JOIN transactions t
    ON t.transaction_id =
       f.transaction_id

GROUP BY f.fraud_label

ORDER BY f.fraud_label;


-- ============================================================
-- 4. FRAUD BY MCC
-- ============================================================

WITH fraud_by_mcc AS (

    SELECT

        t.mcc,

        COUNT(*) AS labelled_transactions,

        SUM(
            CASE
                WHEN f.fraud_label = 'Yes'
                THEN 1
                ELSE 0
            END
        ) AS fraud_transactions

    FROM fraud_labels f

    JOIN transactions t
        ON t.transaction_id =
           f.transaction_id

    GROUP BY t.mcc
)

SELECT

    a.mcc,

    m.mcc_description,

    a.labelled_transactions,

    a.fraud_transactions,

    ROUND(
        100.0
        * a.fraud_transactions
        / a.labelled_transactions,
        6
    ) AS fraud_rate_pct,

    ROUND(
        100.0
        * a.fraud_transactions
        /
        SUM(
            a.fraud_transactions
        ) OVER (),
        4
    ) AS share_of_all_fraud_pct

FROM fraud_by_mcc a

JOIN mcc_codes m
    ON a.mcc = m.mcc

ORDER BY a.fraud_transactions DESC

LIMIT 15;


-- ============================================================
-- 5. FRAUD BY MERCHANT
--
-- Minimum labelled population avoids tiny merchants
-- dominating a rate ranking.
-- ============================================================

WITH fraud_by_merchant AS (

    SELECT

        t.merchant_id,

        COUNT(*) AS labelled_transactions,

        SUM(
            CASE
                WHEN f.fraud_label = 'Yes'
                THEN 1
                ELSE 0
            END
        ) AS fraud_transactions

    FROM fraud_labels f

    JOIN transactions t
        ON t.transaction_id =
           f.transaction_id

    GROUP BY t.merchant_id
)

SELECT

    merchant_id,

    labelled_transactions,

    fraud_transactions,

    ROUND(
        100.0
        * fraud_transactions
        / labelled_transactions,
        6
    ) AS fraud_rate_pct

FROM fraud_by_merchant

WHERE labelled_transactions >= 1000

ORDER BY fraud_transactions DESC

LIMIT 15;


-- ============================================================
-- 6. ERRORS VS FRAUD
-- ============================================================

SELECT

    f.fraud_label,

    COUNT(*) AS labelled_transactions,

    SUM(
        CASE
            WHEN t.errors IS NOT NULL
            THEN 1
            ELSE 0
        END
    ) AS transactions_with_error,

    ROUND(
        100.0
        *
        SUM(
            CASE
                WHEN t.errors IS NOT NULL
                THEN 1
                ELSE 0
            END
        )
        /
        COUNT(*),
        6
    ) AS error_rate_pct

FROM fraud_labels f

JOIN transactions t
    ON t.transaction_id =
       f.transaction_id

GROUP BY f.fraud_label

ORDER BY f.fraud_label;