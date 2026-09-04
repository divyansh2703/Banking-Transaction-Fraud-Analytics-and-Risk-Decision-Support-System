USE financial_transaction_analytics;


-- ============================================================
-- PHASE 12.7
-- ANALYTICAL VIEW VALIDATION
-- ============================================================



-- ============================================================
-- 1. VIEW INVENTORY
-- ============================================================

SELECT

    TABLE_NAME,

    TABLE_TYPE

FROM information_schema.TABLES

WHERE
    TABLE_SCHEMA =
        'financial_transaction_analytics'

    AND TABLE_TYPE = 'VIEW'

ORDER BY
    TABLE_NAME;



-- ============================================================
-- 2. ROW-LEVEL TRANSACTION VIEW
-- ============================================================

SELECT

    COUNT(*)
        AS transaction_context_rows

FROM vw_transaction_context;


-- Expected:
-- 13,305,915



-- ============================================================
-- 3. LABELLED TRANSACTION VIEW
-- ============================================================

SELECT

    COUNT(*)
        AS labelled_context_rows,

    SUM(
        fraud_flag
    ) AS fraud_transactions

FROM vw_labelled_transaction_context;


-- Expected:
--
-- labelled_context_rows = 8,914,963
-- fraud_transactions    = 13,332



-- ============================================================
-- 4. LABEL DISTRIBUTION
-- ============================================================

SELECT

    fraud_label,

    COUNT(*)
        AS transaction_count

FROM vw_labelled_transaction_context

GROUP BY
    fraud_label

ORDER BY
    fraud_label;


-- Expected:
--
-- No  = 8,901,631
-- Yes =    13,332



-- ============================================================
-- 5. CUSTOMER SUMMARY RECONCILIATION
-- ============================================================

SELECT

    COUNT(*)
        AS customers,

    SUM(
        CASE
            WHEN transaction_count > 0
            THEN 1
            ELSE 0
        END
    ) AS transaction_active_customers,

    SUM(
        CASE
            WHEN transaction_count = 0
            THEN 1
            ELSE 0
        END
    ) AS customers_without_transactions

FROM vw_customer_portfolio_summary;


-- Expected:
--
-- customers                     = 2,000
-- transaction_active_customers  = 1,219
-- customers_without_transactions = 781



-- ============================================================
-- 6. MERCHANT SUMMARY RECONCILIATION
-- ============================================================

SELECT

    COUNT(*)
        AS merchants,

    SUM(
        transaction_count
    ) AS transaction_count

FROM vw_merchant_risk_summary;


-- Expected:
--
-- merchants         = 74,831
-- transaction_count = 13,305,915



-- ============================================================
-- 7. MCC SUMMARY RECONCILIATION
-- ============================================================

SELECT

    COUNT(*)
        AS mcc_count,

    SUM(
        transaction_count
    ) AS transaction_count,

    SUM(
        fraud_transactions
    ) AS fraud_transactions

FROM vw_mcc_risk_summary;


-- Expected:
--
-- mcc_count         = 109
-- transaction_count = 13,305,915
-- fraud_transactions = 13,332



-- ============================================================
-- 8. CHANNEL SUMMARY
-- ============================================================

SELECT *

FROM vw_channel_operational_risk_summary

ORDER BY
    transaction_count DESC;


-- Expected transaction populations:
--
-- Swipe  = 6,967,185
-- Chip   = 4,780,818
-- Online = 1,557,912



-- ============================================================
-- 9. SELECTED AMOUNT BASELINE
-- ============================================================

SELECT *

FROM vw_2018_amount_baseline_kpis

ORDER BY
    review_rate_pct;


-- Expected 10% benchmark:
--
-- selected_transactions      = 93,460
-- fraud_case_capture_pct     = 24.3708
-- fraud_value_capture_pct    = 73.0661
-- precision_pct              = 0.4248
-- lift                       = 2.4371
-- workload_reduction_pct     = 90.0000



-- ============================================================
-- 10. VIEW DEFINITIONS PRESENT
-- ============================================================

SELECT

    COUNT(*)
        AS analytical_view_count

FROM information_schema.VIEWS

WHERE
    TABLE_SCHEMA =
        'financial_transaction_analytics'

    AND TABLE_NAME IN (

        'vw_transaction_context',

        'vw_labelled_transaction_context',

        'vw_customer_portfolio_summary',

        'vw_merchant_risk_summary',

        'vw_mcc_risk_summary',

        'vw_channel_operational_risk_summary',

        'vw_2018_amount_baseline_kpis'
    );


-- Expected:
-- 7