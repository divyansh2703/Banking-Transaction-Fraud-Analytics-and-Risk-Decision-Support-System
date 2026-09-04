USE financial_transaction_analytics;


-- ============================================================
-- BQR004
-- FRAUD REVIEW PRIORITISATION
--
-- BASELINE B:
-- Rank labelled transactions by absolute transaction amount.
--
-- Evaluation population:
-- 2018 validation period only.
-- ============================================================


WITH validation_population AS (

    SELECT
        t.transaction_id,
        t.transaction_datetime,
        ABS(t.amount) AS absolute_amount,

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


-- ============================================================
-- Rank every validation transaction.
--
-- transaction_id is used as a deterministic tie breaker when
-- two transactions have the same absolute amount.
-- ============================================================

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

        SUM(fraud_flag) OVER ()
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


-- ============================================================
-- Review capacity scenarios
-- ============================================================

review_thresholds AS (

    SELECT 0.01 AS review_rate

    UNION ALL

    SELECT 0.05

    UNION ALL

    SELECT 0.10

    UNION ALL

    SELECT 0.20
),


scenario_results AS (

    SELECT

        rt.review_rate,

        CEIL(
            MAX(r.total_transactions)
            * rt.review_rate
        ) AS review_transactions,

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
                WHEN r.risk_rank
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

                    AND r.fraud_flag = 1

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

                    AND r.fraud_flag = 1

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
    ) AS target_review_rate_pct,

    selected_transactions,

    total_transactions,


    ROUND(
        100.0
        * selected_transactions
        / total_transactions,
        4
    ) AS actual_review_rate_pct,


    captured_fraud_transactions,

    total_fraud_transactions,


    ROUND(
        100.0
        * captured_fraud_transactions
        / total_fraud_transactions,
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
        * captured_fraud_value
        / total_fraud_value,
        4
    ) AS fraud_value_capture_pct,


    ROUND(
        100.0
        * captured_fraud_transactions
        / selected_transactions,
        4
    ) AS precision_pct,


    ROUND(
        (
            captured_fraud_transactions
            / selected_transactions
        )
        /
        (
            total_fraud_transactions
            / total_transactions
        ),
        4
    ) AS lift,


    ROUND(
        100.0
        * (
            1
            -
            selected_transactions
            / total_transactions
        ),
        4
    ) AS workload_reduction_pct

FROM scenario_results

ORDER BY
    review_rate;