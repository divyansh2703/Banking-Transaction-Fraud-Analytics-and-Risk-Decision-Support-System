USE financial_transaction_analytics;


-- ============================================================
-- BQR001
-- TRANSACTION ACTIVITY AND VALUE CONCENTRATION
-- ============================================================


-- ============================================================
-- 1. CUSTOMER LEVEL ACTIVITY
-- ============================================================

WITH customer_activity AS (

    SELECT
        client_id,

        COUNT(*) AS transaction_count,

        ROUND(
            SUM(ABS(amount)),
            2
        ) AS absolute_transaction_value,

        ROUND(
            AVG(ABS(amount)),
            2
        ) AS average_absolute_transaction_value

    FROM transactions

    GROUP BY client_id
)

SELECT
    client_id,
    transaction_count,
    absolute_transaction_value,
    average_absolute_transaction_value

FROM customer_activity

ORDER BY transaction_count DESC

LIMIT 20;

-- ============================================================
-- 2. CUSTOMER CONCENTRATION
-- ============================================================

WITH customer_activity AS (

    SELECT
        client_id,
        COUNT(*) AS transaction_count

    FROM transactions

    GROUP BY client_id
),

ranked_customers AS (

    SELECT
        client_id,
        transaction_count,

        ROW_NUMBER() OVER (
            ORDER BY transaction_count DESC
        ) AS customer_rank,

        COUNT(*) OVER () AS total_customers,

        SUM(transaction_count) OVER ()
            AS total_transactions

    FROM customer_activity
)

SELECT

    ROUND(
        100.0
        *
        SUM(
            CASE
                WHEN customer_rank
                     <= FLOOR(
                         total_customers * 0.10
                     )
                THEN transaction_count
                ELSE 0
            END
        )
        /
        MAX(total_transactions),
        4
    ) AS top_10_percent_transaction_share,

    ROUND(
        100.0
        *
        SUM(
            CASE
                WHEN customer_rank
                     <= FLOOR(
                         total_customers * 0.20
                     )
                THEN transaction_count
                ELSE 0
            END
        )
        /
        MAX(total_transactions),
        4
    ) AS top_20_percent_transaction_share

FROM ranked_customers;

-- ============================================================
-- 3. MERCHANT CONCENTRATION
-- ============================================================

WITH merchant_activity AS (

    SELECT
        merchant_id,
        COUNT(*) AS transaction_count

    FROM transactions

    GROUP BY merchant_id
),

ranked_merchants AS (

    SELECT
        merchant_id,
        transaction_count,

        ROW_NUMBER() OVER (
            ORDER BY transaction_count DESC
        ) AS merchant_rank,

        COUNT(*) OVER ()
            AS total_merchants,

        SUM(transaction_count) OVER ()
            AS total_transactions

    FROM merchant_activity
)

SELECT

    MAX(total_merchants)
        AS distinct_merchants,

    ROUND(
        100.0
        *
        SUM(
            CASE
                WHEN merchant_rank
                     <= FLOOR(
                         total_merchants * 0.01
                     )
                THEN transaction_count
                ELSE 0
            END
        )
        /
        MAX(total_transactions),
        4
    ) AS top_1_percent_transaction_share,

    ROUND(
        100.0
        *
        SUM(
            CASE
                WHEN merchant_rank
                     <= FLOOR(
                         total_merchants * 0.05
                     )
                THEN transaction_count
                ELSE 0
            END
        )
        /
        MAX(total_transactions),
        4
    ) AS top_5_percent_transaction_share,

    ROUND(
        100.0
        *
        SUM(
            CASE
                WHEN merchant_rank
                     <= FLOOR(
                         total_merchants * 0.10
                     )
                THEN transaction_count
                ELSE 0
            END
        )
        /
        MAX(total_transactions),
        4
    ) AS top_10_percent_transaction_share

FROM ranked_merchants;
-- ============================================================
-- 4. MCC TRANSACTION COUNT VS TRANSACTION VALUE
-- ============================================================

WITH mcc_activity AS (

    SELECT
        t.mcc,

        COUNT(*) AS transaction_count,

        SUM(
            ABS(t.amount)
        ) AS absolute_transaction_value

    FROM transactions t

    GROUP BY t.mcc
),

portfolio_totals AS (

    SELECT
        SUM(transaction_count)
            AS total_transactions,

        SUM(absolute_transaction_value)
            AS total_absolute_value

    FROM mcc_activity
)

SELECT
    a.mcc,
    m.mcc_description,

    a.transaction_count,

    ROUND(
        100.0
        * a.transaction_count
        / p.total_transactions,
        4
    ) AS transaction_share_pct,

    ROUND(
        a.absolute_transaction_value,
        2
    ) AS absolute_transaction_value,

    ROUND(
        100.0
        * a.absolute_transaction_value
        / p.total_absolute_value,
        4
    ) AS absolute_value_share_pct,

    ROUND(
        (
            a.absolute_transaction_value
            / p.total_absolute_value
        )
        /
        (
            a.transaction_count
            / p.total_transactions
        ),
        4
    ) AS value_to_frequency_index

FROM mcc_activity a

JOIN mcc_codes m
    ON a.mcc = m.mcc

CROSS JOIN portfolio_totals p

ORDER BY a.transaction_count DESC

LIMIT 15;
