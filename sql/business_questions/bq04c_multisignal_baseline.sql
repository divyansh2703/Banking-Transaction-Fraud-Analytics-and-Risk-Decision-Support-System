USE financial_transaction_analytics;


-- ============================================================
-- BQR004C
-- TRANSPARENT MULTI-SIGNAL FRAUD PRIORITISATION BASELINE
--
-- DEVELOPMENT:
--   2010-01-01 to 2017-12-31
--
-- VALIDATION:
--   2018-01-01 to 2018-12-31
--
-- 2019 IS NOT USED.
--
-- BASELINE B
--   Absolute transaction amount only
--
-- BASELINE C
--   Development-derived amount lift
--   x
--   Development-derived error lift
--
-- IMPORTANT
-- combined_risk_index is a ranking score.
-- It is NOT a calibrated fraud probability.
-- ============================================================



-- ============================================================
-- 0. CLEAN UP TEMPORARY TABLES
-- ============================================================

DROP TEMPORARY TABLE IF EXISTS dev_signal_cells;

DROP TEMPORARY TABLE IF EXISTS dev_amount_lift;

DROP TEMPORARY TABLE IF EXISTS dev_error_lift;

DROP TEMPORARY TABLE IF EXISTS validation_scored;

DROP TEMPORARY TABLE IF EXISTS all_rankings;



-- ============================================================
-- 1. DEVELOPMENT SIGNAL CELLS
--
-- Creates the 12 possible combinations of:
--
-- amount band x error status
-- ============================================================

CREATE TEMPORARY TABLE dev_signal_cells AS

SELECT

    CASE
        WHEN ABS(t.amount) < 25
        THEN '01 | < 25'

        WHEN ABS(t.amount) < 50
        THEN '02 | 25 - <50'

        WHEN ABS(t.amount) < 100
        THEN '03 | 50 - <100'

        WHEN ABS(t.amount) < 250
        THEN '04 | 100 - <250'

        WHEN ABS(t.amount) < 500
        THEN '05 | 250 - <500'

        ELSE '06 | >=500'
    END AS amount_band,


    CASE
        WHEN t.errors IS NOT NULL
        THEN 'Error Present'

        ELSE 'No Error'
    END AS error_status,


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
    ON t.transaction_id = f.transaction_id


WHERE
    t.transaction_datetime >=
        '2010-01-01 00:00:00'

    AND t.transaction_datetime <
        '2018-01-01 00:00:00'


GROUP BY

    CASE
        WHEN ABS(t.amount) < 25
        THEN '01 | < 25'

        WHEN ABS(t.amount) < 50
        THEN '02 | 25 - <50'

        WHEN ABS(t.amount) < 100
        THEN '03 | 50 - <100'

        WHEN ABS(t.amount) < 250
        THEN '04 | 100 - <250'

        WHEN ABS(t.amount) < 500
        THEN '05 | 250 - <500'

        ELSE '06 | >=500'
    END,


    CASE
        WHEN t.errors IS NOT NULL
        THEN 'Error Present'

        ELSE 'No Error'
    END;



-- ============================================================
-- 2. DEVELOPMENT PORTFOLIO PREVALENCE
-- ============================================================

SET @development_transactions = (

    SELECT
        SUM(labelled_transactions)

    FROM dev_signal_cells
);


SET @development_fraud = (

    SELECT
        SUM(fraud_transactions)

    FROM dev_signal_cells
);


SET @development_fraud_rate = (

    CAST(
        @development_fraud
        AS DECIMAL(30,12)
    )

    /

    NULLIF(
        CAST(
            @development_transactions
            AS DECIMAL(30,12)
        ),
        0
    )
);



-- ============================================================
-- 3. DEVELOPMENT RECONCILIATION
-- ============================================================

SELECT

    @development_transactions
        AS development_transactions,

    @development_fraud
        AS development_fraud,

    ROUND(
        @development_fraud_rate * 100,
        6
    ) AS development_fraud_rate_pct;


-- Expected:
--
-- development_transactions = 7,203,025
-- development_fraud        = 10,343
-- fraud_rate_pct           = 0.143592



-- ============================================================
-- 4. DEVELOPMENT AMOUNT LIFT
-- ============================================================

CREATE TEMPORARY TABLE dev_amount_lift AS

SELECT

    amount_band,

    SUM(
        labelled_transactions
    ) AS labelled_transactions,

    SUM(
        fraud_transactions
    ) AS fraud_transactions,


    CAST(
        SUM(fraud_transactions)
        AS DECIMAL(30,12)
    )

    /

    NULLIF(
        CAST(
            SUM(labelled_transactions)
            AS DECIMAL(30,12)
        ),
        0
    ) AS development_fraud_rate,


    (
        CAST(
            SUM(fraud_transactions)
            AS DECIMAL(30,12)
        )

        /

        NULLIF(
            CAST(
                SUM(labelled_transactions)
                AS DECIMAL(30,12)
            ),
            0
        )
    )

    /

    NULLIF(
        @development_fraud_rate,
        0
    ) AS development_lift


FROM dev_signal_cells

GROUP BY
    amount_band;



-- ============================================================
-- 5. AUDIT AMOUNT WEIGHTS
-- ============================================================

SELECT

    amount_band,

    labelled_transactions,

    fraud_transactions,

    ROUND(
        development_fraud_rate * 100,
        6
    ) AS development_fraud_rate_pct,

    ROUND(
        development_lift,
        4
    ) AS development_lift

FROM dev_amount_lift

ORDER BY
    amount_band;



-- ============================================================
-- 6. DEVELOPMENT ERROR LIFT
-- ============================================================

CREATE TEMPORARY TABLE dev_error_lift AS

SELECT

    error_status,

    SUM(
        labelled_transactions
    ) AS labelled_transactions,

    SUM(
        fraud_transactions
    ) AS fraud_transactions,


    CAST(
        SUM(fraud_transactions)
        AS DECIMAL(30,12)
    )

    /

    NULLIF(
        CAST(
            SUM(labelled_transactions)
            AS DECIMAL(30,12)
        ),
        0
    ) AS development_fraud_rate,


    (
        CAST(
            SUM(fraud_transactions)
            AS DECIMAL(30,12)
        )

        /

        NULLIF(
            CAST(
                SUM(labelled_transactions)
                AS DECIMAL(30,12)
            ),
            0
        )
    )

    /

    NULLIF(
        @development_fraud_rate,
        0
    ) AS development_lift


FROM dev_signal_cells

GROUP BY
    error_status;



-- ============================================================
-- 7. AUDIT ERROR WEIGHTS
-- ============================================================

SELECT

    error_status,

    labelled_transactions,

    fraud_transactions,

    ROUND(
        development_fraud_rate * 100,
        6
    ) AS development_fraud_rate_pct,

    ROUND(
        development_lift,
        4
    ) AS development_lift

FROM dev_error_lift

ORDER BY
    development_lift DESC;



-- ============================================================
-- 8. MATERIALISE SCORED 2018 VALIDATION POPULATION
--
-- This is deliberately materialised into a temporary table.
--
-- This prevents MySQL ERROR 1137:
-- "Can't reopen table"
-- ============================================================

CREATE TEMPORARY TABLE validation_scored AS

SELECT

    t.transaction_id,

    ABS(t.amount)
        AS absolute_amount,


    CASE
        WHEN ABS(t.amount) < 25
        THEN '01 | < 25'

        WHEN ABS(t.amount) < 50
        THEN '02 | 25 - <50'

        WHEN ABS(t.amount) < 100
        THEN '03 | 50 - <100'

        WHEN ABS(t.amount) < 250
        THEN '04 | 100 - <250'

        WHEN ABS(t.amount) < 500
        THEN '05 | 250 - <500'

        ELSE '06 | >=500'
    END AS amount_band,


    CASE
        WHEN t.errors IS NOT NULL
        THEN 'Error Present'

        ELSE 'No Error'
    END AS error_status,


    CASE
        WHEN f.fraud_label = 'Yes'
        THEN 1
        ELSE 0
    END AS fraud_flag,


    a.development_lift
        AS amount_lift,


    e.development_lift
        AS error_lift,


    (
        a.development_lift
        *
        e.development_lift
    ) AS combined_risk_index


FROM transactions t

JOIN fraud_labels f
    ON t.transaction_id =
       f.transaction_id

JOIN dev_amount_lift a

    ON
        CASE
            WHEN ABS(t.amount) < 25
            THEN '01 | < 25'

            WHEN ABS(t.amount) < 50
            THEN '02 | 25 - <50'

            WHEN ABS(t.amount) < 100
            THEN '03 | 50 - <100'

            WHEN ABS(t.amount) < 250
            THEN '04 | 100 - <250'

            WHEN ABS(t.amount) < 500
            THEN '05 | 250 - <500'

            ELSE '06 | >=500'
        END
        =
        a.amount_band

JOIN dev_error_lift e

    ON
        CASE
            WHEN t.errors IS NOT NULL
            THEN 'Error Present'

            ELSE 'No Error'
        END
        =
        e.error_status


WHERE
    t.transaction_datetime >=
        '2018-01-01 00:00:00'

    AND t.transaction_datetime <
        '2019-01-01 00:00:00';



-- ============================================================
-- 9. VALIDATION RECONCILIATION
-- ============================================================

SELECT

    COUNT(*)
        AS validation_transactions,

    SUM(fraud_flag)
        AS validation_fraud_transactions,

    ROUND(
        100.0
        *
        CAST(
            SUM(fraud_flag)
            AS DECIMAL(30,12)
        )
        /
        NULLIF(
            COUNT(*),
            0
        ),
        6
    ) AS validation_fraud_rate_pct

FROM validation_scored;


-- Expected:
--
-- validation_transactions       = 934,599
-- validation_fraud_transactions = 1,629
-- validation_fraud_rate_pct     = 0.174299



-- ============================================================
-- 10. CREATE COMBINED RANKING TABLE
--
-- The two methods are inserted separately.
--
-- This is the key fix for MySQL ERROR 1137.
-- ============================================================

CREATE TEMPORARY TABLE all_rankings (

    method
        VARCHAR(64) NOT NULL,

    transaction_id
        BIGINT UNSIGNED NOT NULL,

    absolute_amount
        DECIMAL(14,2) NOT NULL,

    fraud_flag
        TINYINT NOT NULL,

    risk_rank
        BIGINT UNSIGNED NOT NULL,

    total_transactions
        BIGINT UNSIGNED NOT NULL,

    total_fraud_transactions
        BIGINT UNSIGNED NOT NULL,

    total_fraud_value
        DECIMAL(30,2) NOT NULL
);



-- ============================================================
-- 11. BASELINE B
-- AMOUNT ONLY
-- ============================================================

INSERT INTO all_rankings (

    method,

    transaction_id,

    absolute_amount,

    fraud_flag,

    risk_rank,

    total_transactions,

    total_fraud_transactions,

    total_fraud_value
)

SELECT

    'Baseline B | Amount Only'
        AS method,

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


FROM validation_scored;



-- ============================================================
-- 12. BASELINE C
-- AMOUNT + ERROR
-- ============================================================

INSERT INTO all_rankings (

    method,

    transaction_id,

    absolute_amount,

    fraud_flag,

    risk_rank,

    total_transactions,

    total_fraud_transactions,

    total_fraud_value
)

SELECT

    'Baseline C | Amount + Error'
        AS method,

    transaction_id,

    absolute_amount,

    fraud_flag,


    ROW_NUMBER() OVER (

        ORDER BY
            combined_risk_index DESC,

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


FROM validation_scored;



-- ============================================================
-- 13. RANKING RECONCILIATION
--
-- Both methods MUST contain exactly the same 2018 population.
-- ============================================================

SELECT

    method,

    COUNT(*)
        AS ranked_transactions,

    SUM(fraud_flag)
        AS fraud_transactions,

    ROUND(
        SUM(
            CASE
                WHEN fraud_flag = 1
                THEN absolute_amount

                ELSE 0
            END
        ),
        2
    ) AS total_fraud_value

FROM all_rankings

GROUP BY
    method

ORDER BY
    method;


-- Expected per method:
--
-- ranked_transactions = 934,599
-- fraud_transactions  = 1,629
-- total_fraud_value   = 151,107.98



-- ============================================================
-- 14. REVIEW CAPACITY EVALUATION
-- ============================================================

WITH review_thresholds AS (

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

        r.method,

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


    FROM all_rankings r

    CROSS JOIN review_thresholds rt


    GROUP BY

        r.method,

        rt.review_rate
)



-- ============================================================
-- 15. FINAL BASELINE COMPARISON
-- ============================================================

SELECT

    method,


    ROUND(
        review_rate * 100,
        2
    ) AS target_review_rate_pct,


    selected_transactions,


    total_transactions,


    ROUND(
        100.0
        *
        selected_transactions
        /
        total_transactions,
        4
    ) AS actual_review_rate_pct,


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
            NULLIF(
                selected_transactions,
                0
            )
        )

        /

        (
            CAST(
                total_fraud_transactions
                AS DECIMAL(30,12)
            )
            /
            NULLIF(
                total_transactions,
                0
            )
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


FROM scenario_results


ORDER BY

    review_rate,

    method;