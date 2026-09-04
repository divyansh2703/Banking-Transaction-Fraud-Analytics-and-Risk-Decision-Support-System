USE financial_transaction_analytics;


-- ============================================================
-- PHASE 12.7
-- REUSABLE ANALYTICAL VIEWS
--
-- PURPOSE
--
-- Provide a controlled analytical layer above the certified
-- base tables for:
--
--   Tableau
--   Excel
--   SQL reporting
--   Later analytical feature engineering
--
-- IMPORTANT
--
-- These are descriptive/context views.
--
-- They are NOT automatically leakage-safe model features.
-- Historical predictive features will be engineered separately.
-- ============================================================



-- ============================================================
-- CLEAN UP EXISTING VIEWS
-- ============================================================

DROP VIEW IF EXISTS vw_2018_amount_baseline_kpis;

DROP VIEW IF EXISTS vw_channel_operational_risk_summary;

DROP VIEW IF EXISTS vw_mcc_risk_summary;

DROP VIEW IF EXISTS vw_merchant_risk_summary;

DROP VIEW IF EXISTS vw_customer_portfolio_summary;

DROP VIEW IF EXISTS vw_labelled_transaction_context;

DROP VIEW IF EXISTS vw_transaction_context;



-- ============================================================
-- VIEW 1
-- TRANSACTION CONTEXT
--
-- Grain:
-- One row per transaction.
--
-- Expected rows:
-- 13,305,915
--
-- Adds:
--   absolute transaction amount
--   amount sign
--   time fields
--   MCC description
--   selected card context
--   operational error flag
--
-- Does NOT add fraud labels.
-- ============================================================

CREATE VIEW vw_transaction_context AS

SELECT

    t.transaction_id,

    t.transaction_datetime,

    DATE(
        t.transaction_datetime
    ) AS transaction_date,

    YEAR(
        t.transaction_datetime
    ) AS transaction_year,

    MONTH(
        t.transaction_datetime
    ) AS transaction_month,

    t.client_id,

    t.card_id,

    t.amount,

    ABS(
        t.amount
    ) AS absolute_amount,


    CASE

        WHEN t.amount > 0
        THEN 'Positive'

        WHEN t.amount < 0
        THEN 'Negative'

        ELSE 'Zero'

    END AS amount_sign,


    t.use_chip,

    t.merchant_id,

    t.merchant_city,

    t.merchant_state,

    t.zip,

    t.mcc,

    m.mcc_description,

    t.errors,


    CASE
        WHEN t.errors IS NOT NULL
        THEN 1
        ELSE 0
    END AS error_flag,


    t.transaction_before_card_open_flag,

    t.transaction_after_card_expiry_flag,

    t.channel_location_inconsistency_flag,


    c.card_brand,

    c.card_type,

    c.has_chip,

    c.credit_limit,

    c.num_cards_issued,

    c.acct_open_date,

    c.expires


FROM transactions t

JOIN cards c
    ON t.card_id =
       c.card_id

JOIN mcc_codes m
    ON t.mcc =
       m.mcc;



-- ============================================================
-- VIEW 2
-- LABELLED TRANSACTION CONTEXT
--
-- Grain:
-- One row per supplied fraud label.
--
-- Expected rows:
-- 8,914,963
--
-- IMPORTANT:
-- Unlabelled transactions are excluded.
--
-- This view must never interpret missing labels as non-fraud.
-- ============================================================

CREATE VIEW vw_labelled_transaction_context AS

SELECT

    v.*,

    f.fraud_label,


    CASE
        WHEN f.fraud_label = 'Yes'
        THEN 1
        ELSE 0
    END AS fraud_flag


FROM vw_transaction_context v

JOIN fraud_labels f
    ON v.transaction_id =
       f.transaction_id;



-- ============================================================
-- VIEW 3
-- CUSTOMER PORTFOLIO SUMMARY
--
-- Grain:
-- One row per customer.
--
-- Expected rows:
-- 2,000
--
-- Includes customers with no observed transactions.
--
-- NOTE:
-- Customer financial profile fields are descriptive source
-- attributes and are NOT automatically approved as historical
-- model features.
-- ============================================================

CREATE VIEW vw_customer_portfolio_summary AS

SELECT

    cu.client_id,

    cu.current_age,

    cu.retirement_age,

    cu.gender,

    cu.per_capita_income,

    cu.yearly_income,

    cu.total_debt,

    cu.credit_score,

    cu.num_credit_cards
        AS source_num_credit_cards,


    COUNT(
        t.transaction_id
    ) AS transaction_count,


    COUNT(
        DISTINCT t.card_id
    ) AS observed_transaction_cards,


    COUNT(
        DISTINCT t.merchant_id
    ) AS distinct_merchants,


    COUNT(
        DISTINCT t.mcc
    ) AS distinct_mccs,


    ROUND(
        COALESCE(
            SUM(
                ABS(t.amount)
            ),
            0
        ),
        2
    ) AS absolute_transaction_value,


    ROUND(
        COALESCE(
            AVG(
                ABS(t.amount)
            ),
            0
        ),
        2
    ) AS average_absolute_amount,


    MIN(
        t.transaction_datetime
    ) AS first_transaction_datetime,


    MAX(
        t.transaction_datetime
    ) AS last_transaction_datetime,


    SUM(

        CASE
            WHEN t.errors IS NOT NULL
            THEN 1
            ELSE 0
        END

    ) AS error_transactions,


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

        NULLIF(
            COUNT(
                t.transaction_id
            ),
            0
        ),

        4

    ) AS error_rate_pct,


    COUNT(
        f.transaction_id
    ) AS labelled_transactions,


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

        NULLIF(
            COUNT(
                f.transaction_id
            ),
            0
        ),

        6

    ) AS labelled_fraud_rate_pct


FROM customers cu

LEFT JOIN transactions t
    ON cu.client_id =
       t.client_id

LEFT JOIN fraud_labels f
    ON t.transaction_id =
       f.transaction_id


GROUP BY

    cu.client_id,

    cu.current_age,

    cu.retirement_age,

    cu.gender,

    cu.per_capita_income,

    cu.yearly_income,

    cu.total_debt,

    cu.credit_score,

    cu.num_credit_cards;



-- ============================================================
-- VIEW 4
-- MERCHANT RISK SUMMARY
--
-- Grain:
-- One row per observed merchant.
--
-- Expected rows:
-- 74,831
--
-- Fraud rates use only labelled transactions.
-- ============================================================

CREATE VIEW vw_merchant_risk_summary AS

SELECT

    t.merchant_id,


    COUNT(*)
        AS transaction_count,


    COUNT(
        DISTINCT t.client_id
    ) AS distinct_customers,


    COUNT(
        DISTINCT t.mcc
    ) AS distinct_mccs,


    ROUND(
        SUM(
            ABS(t.amount)
        ),
        2
    ) AS absolute_transaction_value,


    ROUND(
        AVG(
            ABS(t.amount)
        ),
        2
    ) AS average_absolute_amount,


    SUM(

        CASE
            WHEN t.errors IS NOT NULL
            THEN 1
            ELSE 0
        END

    ) AS error_transactions,


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

        4

    ) AS error_rate_pct,


    COUNT(
        f.transaction_id
    ) AS labelled_transactions,


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

        NULLIF(
            COUNT(
                f.transaction_id
            ),
            0
        ),

        6

    ) AS labelled_fraud_rate_pct,


    ROUND(

        SUM(
            CASE
                WHEN f.fraud_label = 'Yes'
                THEN ABS(t.amount)
                ELSE 0
            END
        ),

        2

    ) AS confirmed_fraud_transaction_value


FROM transactions t

LEFT JOIN fraud_labels f
    ON t.transaction_id =
       f.transaction_id


GROUP BY
    t.merchant_id;



-- ============================================================
-- VIEW 5
-- MCC RISK SUMMARY
--
-- Grain:
-- One row per MCC.
--
-- Expected rows:
-- 109
--
-- Combines:
--   transaction activity
--   value exposure
--   operational errors
--   supplied fraud-label evidence
-- ============================================================

CREATE VIEW vw_mcc_risk_summary AS

SELECT

    t.mcc,

    m.mcc_description,


    COUNT(*)
        AS transaction_count,


    COUNT(
        DISTINCT t.merchant_id
    ) AS distinct_merchants,


    ROUND(
        SUM(
            ABS(t.amount)
        ),
        2
    ) AS absolute_transaction_value,


    ROUND(
        AVG(
            ABS(t.amount)
        ),
        2
    ) AS average_absolute_amount,


    SUM(

        CASE
            WHEN t.errors IS NOT NULL
            THEN 1
            ELSE 0
        END

    ) AS error_transactions,


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

        4

    ) AS error_rate_pct,


    COUNT(
        f.transaction_id
    ) AS labelled_transactions,


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

        NULLIF(
            COUNT(
                f.transaction_id
            ),
            0
        ),

        6

    ) AS labelled_fraud_rate_pct,


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

        NULLIF(
            SUM(
                SUM(
                    CASE
                        WHEN f.fraud_label = 'Yes'
                        THEN 1
                        ELSE 0
                    END
                )
            ) OVER (),
            0
        ),

        4

    ) AS share_of_confirmed_fraud_pct


FROM transactions t

JOIN mcc_codes m
    ON t.mcc =
       m.mcc

LEFT JOIN fraud_labels f
    ON t.transaction_id =
       f.transaction_id


GROUP BY

    t.mcc,

    m.mcc_description;



-- ============================================================
-- VIEW 6
-- CHANNEL OPERATIONAL AND RISK SUMMARY
--
-- Grain:
-- One row per transaction channel.
--
-- Expected rows:
-- 3
--
-- Useful for Tableau and operational reporting.
-- ============================================================

CREATE VIEW vw_channel_operational_risk_summary AS

SELECT

    t.use_chip
        AS transaction_channel,


    COUNT(*)
        AS transaction_count,


    SUM(

        CASE
            WHEN t.errors IS NOT NULL
            THEN 1
            ELSE 0
        END

    ) AS error_transactions,


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

        4

    ) AS error_rate_pct,


    COUNT(
        f.transaction_id
    ) AS labelled_transactions,


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

        NULLIF(
            COUNT(
                f.transaction_id
            ),
            0
        ),

        6

    ) AS labelled_fraud_rate_pct,


    ROUND(
        SUM(
            ABS(t.amount)
        ),
        2
    ) AS absolute_transaction_value,


    ROUND(

        SUM(
            CASE
                WHEN f.fraud_label = 'Yes'
                THEN ABS(t.amount)
                ELSE 0
            END
        ),

        2

    ) AS confirmed_fraud_transaction_value


FROM transactions t

LEFT JOIN fraud_labels f
    ON t.transaction_id =
       f.transaction_id


GROUP BY
    t.use_chip;



-- ============================================================
-- VIEW 7
-- 2018 AMOUNT-ONLY VALIDATION BASELINE KPI VIEW
--
-- Grain:
-- One row per review-capacity scenario.
--
-- Expected rows:
-- 4
--
-- Review capacities:
--   1%
--   5%
--   10%
--   20%
--
-- This freezes the selected transparent baseline for reporting.
--
-- 2019 is NOT used.
-- ============================================================

CREATE VIEW vw_2018_amount_baseline_kpis AS

WITH validation_population AS (

    SELECT

        t.transaction_id,

        ABS(
            t.amount
        ) AS absolute_amount,


        CASE
            WHEN f.fraud_label = 'Yes'
            THEN 1
            ELSE 0
        END AS fraud_flag


    FROM transactions t

    JOIN fraud_labels f
        ON t.transaction_id =
           f.transaction_id


    WHERE
        t.transaction_datetime >=
            '2018-01-01 00:00:00'

        AND t.transaction_datetime <
            '2019-01-01 00:00:00'
),


ranked_transactions AS (

    SELECT

        transaction_id,

        absolute_amount,

        fraud_flag,


        ROW_NUMBER() OVER (

            ORDER BY
                absolute_amount DESC,
                transaction_id ASC

        ) AS risk_rank,


        COUNT(*) OVER ()
            AS total_transactions,


        SUM(
            fraud_flag
        ) OVER ()
            AS total_fraud_transactions,


        SUM(

            CASE
                WHEN fraud_flag = 1
                THEN absolute_amount
                ELSE 0
            END

        ) OVER ()
            AS total_fraud_value


    FROM validation_population
),


review_thresholds AS (

    SELECT
        CAST(
            0.01
            AS DECIMAL(5,4)
        ) AS review_rate

    UNION ALL

    SELECT
        CAST(
            0.05
            AS DECIMAL(5,4)
        )

    UNION ALL

    SELECT
        CAST(
            0.10
            AS DECIMAL(5,4)
        )

    UNION ALL

    SELECT
        CAST(
            0.20
            AS DECIMAL(5,4)
        )
),


scenario_results AS (

    SELECT

        rt.review_rate,


        MAX(
            r.total_transactions
        ) AS total_transactions,


        MAX(
            r.total_fraud_transactions
        ) AS total_fraud_transactions,


        MAX(
            r.total_fraud_value
        ) AS total_fraud_value,


        SUM(

            CASE
                WHEN
                    r.risk_rank
                    <= CEIL(
                        r.total_transactions
                        * rt.review_rate
                    )

                THEN 1
                ELSE 0
            END

        ) AS selected_transactions,


        SUM(

            CASE
                WHEN
                    r.risk_rank
                    <= CEIL(
                        r.total_transactions
                        * rt.review_rate
                    )

                    AND
                    r.fraud_flag = 1

                THEN 1
                ELSE 0
            END

        ) AS captured_fraud_transactions,


        SUM(

            CASE
                WHEN
                    r.risk_rank
                    <= CEIL(
                        r.total_transactions
                        * rt.review_rate
                    )

                    AND
                    r.fraud_flag = 1

                THEN r.absolute_amount
                ELSE 0
            END

        ) AS captured_fraud_value


    FROM ranked_transactions r

    CROSS JOIN review_thresholds rt


    GROUP BY
        rt.review_rate
)


SELECT

    ROUND(
        review_rate * 100,
        2
    ) AS review_rate_pct,


    selected_transactions,


    total_transactions,


    captured_fraud_transactions,


    total_fraud_transactions,


    ROUND(

        100.0
        *
        captured_fraud_transactions
        /
        total_fraud_transactions,

        4

    ) AS fraud_case_capture_pct,


    ROUND(
        captured_fraud_value,
        2
    ) AS captured_fraud_value,


    ROUND(
        total_fraud_value,
        2
    ) AS total_fraud_value,


    ROUND(

        100.0
        *
        captured_fraud_value
        /
        total_fraud_value,

        4

    ) AS fraud_value_capture_pct,


    ROUND(

        100.0
        *
        captured_fraud_transactions
        /
        selected_transactions,

        4

    ) AS precision_pct,


    ROUND(

        (
            CAST(
                captured_fraud_transactions
                AS DECIMAL(30,12)
            )
            /
            selected_transactions
        )

        /

        (
            CAST(
                total_fraud_transactions
                AS DECIMAL(30,12)
            )
            /
            total_transactions
        ),

        4

    ) AS lift,


    ROUND(

        100.0
        *
        (
            1
            -
            CAST(
                selected_transactions
                AS DECIMAL(30,12)
            )
            /
            total_transactions
        ),

        4

    ) AS workload_reduction_pct


FROM scenario_results;