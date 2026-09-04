USE financial_transaction_analytics;


-- ============================================================
-- EXCEL REPORTING EXPORTS
-- ============================================================


-- ============================================================
-- 1. REVIEW CAPACITY
-- ============================================================

SELECT *
FROM vw_2018_amount_baseline_kpis
ORDER BY review_rate_pct;



-- ============================================================
-- 2. CHANNEL ANALYSIS
-- ============================================================

SELECT *
FROM vw_channel_operational_risk_summary
ORDER BY transaction_count DESC;



-- ============================================================
-- 3. MCC ANALYSIS
-- ============================================================

SELECT *
FROM vw_mcc_risk_summary
ORDER BY fraud_transactions DESC;



-- ============================================================
-- 4. MERCHANT ANALYSIS
--
-- Restrict output to useful monitoring population rather
-- than exporting all 74,831 merchants into Excel initially.
-- ============================================================

SELECT
    merchant_id,
    transaction_count,
    distinct_customers,
    distinct_mccs,
    absolute_transaction_value,
    average_absolute_amount,
    error_transactions,
    error_rate_pct,
    labelled_transactions,
    fraud_transactions,
    labelled_fraud_rate_pct,
    confirmed_fraud_transaction_value

FROM vw_merchant_risk_summary

WHERE labelled_transactions >= 1000

ORDER BY fraud_transactions DESC

LIMIT 500;



-- ============================================================
-- 5. CUSTOMER SUMMARY
--
-- Keep only business-relevant columns.
-- ============================================================

SELECT
    client_id,
    current_age,
    gender,
    yearly_income,
    total_debt,
    credit_score,
    source_num_credit_cards,
    transaction_count,
    observed_transaction_cards,
    distinct_merchants,
    distinct_mccs,
    absolute_transaction_value,
    average_absolute_amount,
    error_transactions,
    error_rate_pct,
    labelled_transactions,
    fraud_transactions,
    labelled_fraud_rate_pct

FROM vw_customer_portfolio_summary

ORDER BY transaction_count DESC;