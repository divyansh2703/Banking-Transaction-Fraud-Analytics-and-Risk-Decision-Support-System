USE financial_transaction_analytics;


-- ============================================================
-- FRAUD LABEL TEMPORAL COVERAGE
-- Purpose:
-- Understand whether labels are distributed consistently
-- across the transaction observation period before defining
-- temporal development / holdout periods.
-- ============================================================


-- ============================================================
-- 1. LABELLED DATE RANGE
-- ============================================================

SELECT
    MIN(t.transaction_datetime)
        AS first_labelled_transaction,

    MAX(t.transaction_datetime)
        AS last_labelled_transaction,

    COUNT(*) AS labelled_transactions,

    SUM(
        f.fraud_label = 'Yes'
    ) AS fraud_transactions

FROM fraud_labels f

JOIN transactions t
    ON t.transaction_id =
       f.transaction_id;


-- ============================================================
-- 2. LABEL COVERAGE BY YEAR
-- ============================================================

WITH transaction_years AS (

    SELECT
        YEAR(transaction_datetime) AS transaction_year,
        COUNT(*) AS total_transactions

    FROM transactions

    GROUP BY
        YEAR(transaction_datetime)
),

label_years AS (

    SELECT
        YEAR(t.transaction_datetime)
            AS transaction_year,

        COUNT(*) AS labelled_transactions,

        SUM(
            f.fraud_label = 'Yes'
        ) AS fraud_transactions

    FROM fraud_labels f

    JOIN transactions t
        ON t.transaction_id =
           f.transaction_id

    GROUP BY
        YEAR(t.transaction_datetime)
)

SELECT
    ty.transaction_year,

    ty.total_transactions,

    COALESCE(
        ly.labelled_transactions,
        0
    ) AS labelled_transactions,

    ROUND(
        100.0
        *
        COALESCE(
            ly.labelled_transactions,
            0
        )
        /
        ty.total_transactions,
        4
    ) AS label_coverage_pct,

    COALESCE(
        ly.fraud_transactions,
        0
    ) AS fraud_transactions,

    ROUND(
        100.0
        *
        COALESCE(
            ly.fraud_transactions,
            0
        )
        /
        NULLIF(
            ly.labelled_transactions,
            0
        ),
        6
    ) AS fraud_rate_pct

FROM transaction_years ty

LEFT JOIN label_years ly
    ON ty.transaction_year =
       ly.transaction_year

ORDER BY
    ty.transaction_year;


-- ============================================================
-- 3. MONTHLY LABEL COVERAGE
-- Focus on later years where potential holdout data exists.
-- ============================================================

WITH transaction_months AS (

    SELECT
        DATE_FORMAT(
            transaction_datetime,
            '%Y-%m'
        ) AS transaction_month,

        COUNT(*) AS total_transactions

    FROM transactions

    GROUP BY
        DATE_FORMAT(
            transaction_datetime,
            '%Y-%m'
        )
),

label_months AS (

    SELECT
        DATE_FORMAT(
            t.transaction_datetime,
            '%Y-%m'
        ) AS transaction_month,

        COUNT(*) AS labelled_transactions,

        SUM(
            f.fraud_label = 'Yes'
        ) AS fraud_transactions

    FROM fraud_labels f

    JOIN transactions t
        ON t.transaction_id =
           f.transaction_id

    GROUP BY
        DATE_FORMAT(
            t.transaction_datetime,
            '%Y-%m'
        )
)

SELECT
    tm.transaction_month,

    tm.total_transactions,

    COALESCE(
        lm.labelled_transactions,
        0
    ) AS labelled_transactions,

    ROUND(
        100.0
        *
        COALESCE(
            lm.labelled_transactions,
            0
        )
        /
        tm.total_transactions,
        4
    ) AS label_coverage_pct,

    COALESCE(
        lm.fraud_transactions,
        0
    ) AS fraud_transactions,

    ROUND(
        100.0
        *
        COALESCE(
            lm.fraud_transactions,
            0
        )
        /
        NULLIF(
            lm.labelled_transactions,
            0
        ),
        6
    ) AS fraud_rate_pct

FROM transaction_months tm

LEFT JOIN label_months lm
    ON tm.transaction_month =
       lm.transaction_month

WHERE tm.transaction_month >= '2017-01'

ORDER BY
    tm.transaction_month;