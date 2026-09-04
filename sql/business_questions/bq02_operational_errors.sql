USE financial_transaction_analytics;


-- ============================================================
-- BQR002
-- OPERATIONAL TRANSACTION ERRORS
-- ============================================================


-- ============================================================
-- 1. OVERALL ERROR RATE
-- ============================================================

SELECT
    COUNT(*) AS total_transactions,

    SUM(
        CASE
            WHEN errors IS NOT NULL
            THEN 1
            ELSE 0
        END
    ) AS transactions_with_error,

    ROUND(
        100.0
        *
        SUM(
            CASE
                WHEN errors IS NOT NULL
                THEN 1
                ELSE 0
            END
        )
        /
        COUNT(*),
        4
    ) AS error_rate_pct

FROM transactions;


-- ============================================================
-- 2. TOP RECORDED ERROR VALUES
-- ============================================================

SELECT
    errors AS error_value,

    COUNT(*) AS transaction_count,

    ROUND(
        100.0
        * COUNT(*)
        /
        SUM(COUNT(*)) OVER (),
        4
    ) AS share_of_error_transactions_pct

FROM transactions

WHERE errors IS NOT NULL

GROUP BY errors

ORDER BY transaction_count DESC

LIMIT 10;


-- ============================================================
-- 3. ERROR RATE BY CHANNEL
-- ============================================================

SELECT
    use_chip,

    COUNT(*) AS transaction_count,

    SUM(
        CASE
            WHEN errors IS NOT NULL
            THEN 1
            ELSE 0
        END
    ) AS transactions_with_error,

    ROUND(
        100.0
        *
        SUM(
            CASE
                WHEN errors IS NOT NULL
                THEN 1
                ELSE 0
            END
        )
        /
        COUNT(*),
        4
    ) AS error_rate_pct

FROM transactions

GROUP BY use_chip

ORDER BY error_rate_pct DESC;


-- ============================================================
-- 4. ERROR CONTRIBUTION BY CHANNEL
-- ============================================================

SELECT
    use_chip,

    SUM(
        CASE
            WHEN errors IS NOT NULL
            THEN 1
            ELSE 0
        END
    ) AS transactions_with_error,

    ROUND(
        100.0
        *
        SUM(
            CASE
                WHEN errors IS NOT NULL
                THEN 1
                ELSE 0
            END
        )
        /
        SUM(
            SUM(
                CASE
                    WHEN errors IS NOT NULL
                    THEN 1
                    ELSE 0
                END
            )
        ) OVER (),
        4
    ) AS share_of_all_errors_pct

FROM transactions

GROUP BY use_chip

ORDER BY transactions_with_error DESC;

