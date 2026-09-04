USE financial_transaction_analytics;


-- ============================================================
-- BQR004B
-- SIGNAL STABILITY BEFORE MULTI-SIGNAL PRIORITISATION
--
-- PURPOSE
-- Compare fraud relationships between:
--
--   Development: 2010-01-01 to 2017-12-31
--   Validation:  2018-01-01 to 2018-12-31
--
-- Signals:
--   1. Channel
--   2. Error presence
--   3. Absolute transaction amount bands
--   4. MCC
--
-- IMPORTANT
-- 2019 is excluded completely from this analysis.
--
-- Fraud is a rare event, therefore fraud rates are calculated
-- using explicit high-precision SUM / COUNT expressions.
-- ============================================================



-- ============================================================
-- 1. DEVELOPMENT VS VALIDATION BASELINE
-- ============================================================

WITH period_summary AS (

    SELECT

        CASE
            WHEN t.transaction_datetime <
                 '2018-01-01 00:00:00'
            THEN 'Development 2010-2017'

            ELSE 'Validation 2018'
        END AS period,

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

    WHERE
        t.transaction_datetime >=
            '2010-01-01 00:00:00'

        AND t.transaction_datetime <
            '2019-01-01 00:00:00'

    GROUP BY
        CASE
            WHEN t.transaction_datetime <
                 '2018-01-01 00:00:00'
            THEN 'Development 2010-2017'

            ELSE 'Validation 2018'
        END
)

SELECT
    period,

    labelled_transactions,

    fraud_transactions,

    ROUND(
        100.0
        *
        CAST(
            fraud_transactions
            AS DECIMAL(30,12)
        )
        /
        NULLIF(
            labelled_transactions,
            0
        ),
        6
    ) AS fraud_rate_pct

FROM period_summary

ORDER BY period;



-- ============================================================
-- 2. CHANNEL STABILITY
-- ============================================================

WITH base AS (

    SELECT

        CASE
            WHEN t.transaction_datetime <
                 '2018-01-01 00:00:00'
            THEN 'DEV'

            ELSE 'VAL'
        END AS period,

        t.use_chip,

        CASE
            WHEN f.fraud_label = 'Yes'
            THEN 1
            ELSE 0
        END AS fraud_flag

    FROM fraud_labels f

    JOIN transactions t
        ON t.transaction_id =
           f.transaction_id

    WHERE
        t.transaction_datetime >=
            '2010-01-01 00:00:00'

        AND t.transaction_datetime <
            '2019-01-01 00:00:00'
),

period_prevalence AS (

    SELECT
        period,

        CAST(
            SUM(fraud_flag)
            AS DECIMAL(30,12)
        )
        /
        NULLIF(
            CAST(
                COUNT(*)
                AS DECIMAL(30,12)
            ),
            0
        ) AS period_fraud_rate

    FROM base

    GROUP BY period
),

channel_rates AS (

    SELECT
        period,

        use_chip,

        COUNT(*) AS labelled_transactions,

        SUM(fraud_flag) AS fraud_transactions,

        CAST(
            SUM(fraud_flag)
            AS DECIMAL(30,12)
        )
        /
        NULLIF(
            CAST(
                COUNT(*)
                AS DECIMAL(30,12)
            ),
            0
        ) AS fraud_rate

    FROM base

    GROUP BY
        period,
        use_chip
),

combined AS (

    SELECT
        c.use_chip,

        MAX(
            CASE
                WHEN c.period = 'DEV'
                THEN c.labelled_transactions
            END
        ) AS development_transactions,

        MAX(
            CASE
                WHEN c.period = 'DEV'
                THEN c.fraud_transactions
            END
        ) AS development_fraud,

        MAX(
            CASE
                WHEN c.period = 'DEV'
                THEN c.fraud_rate
            END
        ) AS development_rate,

        MAX(
            CASE
                WHEN c.period = 'DEV'
                THEN
                    c.fraud_rate
                    /
                    NULLIF(
                        p.period_fraud_rate,
                        0
                    )
            END
        ) AS development_lift,

        MAX(
            CASE
                WHEN c.period = 'VAL'
                THEN c.labelled_transactions
            END
        ) AS validation_transactions,

        MAX(
            CASE
                WHEN c.period = 'VAL'
                THEN c.fraud_transactions
            END
        ) AS validation_fraud,

        MAX(
            CASE
                WHEN c.period = 'VAL'
                THEN c.fraud_rate
            END
        ) AS validation_rate,

        MAX(
            CASE
                WHEN c.period = 'VAL'
                THEN
                    c.fraud_rate
                    /
                    NULLIF(
                        p.period_fraud_rate,
                        0
                    )
            END
        ) AS validation_lift

    FROM channel_rates c

    JOIN period_prevalence p
        ON c.period = p.period

    GROUP BY
        c.use_chip
)

SELECT
    use_chip,

    development_transactions,

    development_fraud,

    ROUND(
        development_rate * 100,
        6
    ) AS development_fraud_rate_pct,

    ROUND(
        development_lift,
        4
    ) AS development_lift,

    validation_transactions,

    validation_fraud,

    ROUND(
        validation_rate * 100,
        6
    ) AS validation_fraud_rate_pct,

    ROUND(
        validation_lift,
        4
    ) AS validation_lift,

    CASE
        WHEN development_lift > 1
             AND validation_lift > 1
        THEN 'ABOVE_BASELINE_BOTH'

        WHEN development_lift < 1
             AND validation_lift < 1
        THEN 'BELOW_BASELINE_BOTH'

        ELSE 'DIRECTION_CHANGED'
    END AS stability_direction

FROM combined

ORDER BY
    validation_lift DESC;



-- ============================================================
-- 3. ERROR PRESENCE STABILITY
-- ============================================================

WITH base AS (

    SELECT

        CASE
            WHEN t.transaction_datetime <
                 '2018-01-01 00:00:00'
            THEN 'DEV'

            ELSE 'VAL'
        END AS period,

        CASE
            WHEN t.errors IS NOT NULL
            THEN 'Error Present'

            ELSE 'No Error'
        END AS error_status,

        CASE
            WHEN f.fraud_label = 'Yes'
            THEN 1
            ELSE 0
        END AS fraud_flag

    FROM fraud_labels f

    JOIN transactions t
        ON t.transaction_id =
           f.transaction_id

    WHERE
        t.transaction_datetime >=
            '2010-01-01 00:00:00'

        AND t.transaction_datetime <
            '2019-01-01 00:00:00'
),

period_prevalence AS (

    SELECT
        period,

        CAST(
            SUM(fraud_flag)
            AS DECIMAL(30,12)
        )
        /
        NULLIF(
            CAST(
                COUNT(*)
                AS DECIMAL(30,12)
            ),
            0
        ) AS period_fraud_rate

    FROM base

    GROUP BY period
),

error_rates AS (

    SELECT
        period,

        error_status,

        COUNT(*) AS labelled_transactions,

        SUM(fraud_flag) AS fraud_transactions,

        CAST(
            SUM(fraud_flag)
            AS DECIMAL(30,12)
        )
        /
        NULLIF(
            CAST(
                COUNT(*)
                AS DECIMAL(30,12)
            ),
            0
        ) AS fraud_rate

    FROM base

    GROUP BY
        period,
        error_status
),

combined AS (

    SELECT
        e.error_status,

        MAX(
            CASE
                WHEN e.period = 'DEV'
                THEN e.labelled_transactions
            END
        ) AS development_transactions,

        MAX(
            CASE
                WHEN e.period = 'DEV'
                THEN e.fraud_transactions
            END
        ) AS development_fraud,

        MAX(
            CASE
                WHEN e.period = 'DEV'
                THEN e.fraud_rate
            END
        ) AS development_rate,

        MAX(
            CASE
                WHEN e.period = 'DEV'
                THEN
                    e.fraud_rate
                    /
                    NULLIF(
                        p.period_fraud_rate,
                        0
                    )
            END
        ) AS development_lift,

        MAX(
            CASE
                WHEN e.period = 'VAL'
                THEN e.labelled_transactions
            END
        ) AS validation_transactions,

        MAX(
            CASE
                WHEN e.period = 'VAL'
                THEN e.fraud_transactions
            END
        ) AS validation_fraud,

        MAX(
            CASE
                WHEN e.period = 'VAL'
                THEN e.fraud_rate
            END
        ) AS validation_rate,

        MAX(
            CASE
                WHEN e.period = 'VAL'
                THEN
                    e.fraud_rate
                    /
                    NULLIF(
                        p.period_fraud_rate,
                        0
                    )
            END
        ) AS validation_lift

    FROM error_rates e

    JOIN period_prevalence p
        ON e.period = p.period

    GROUP BY
        e.error_status
)

SELECT
    error_status,

    development_transactions,

    development_fraud,

    ROUND(
        development_rate * 100,
        6
    ) AS development_fraud_rate_pct,

    ROUND(
        development_lift,
        4
    ) AS development_lift,

    validation_transactions,

    validation_fraud,

    ROUND(
        validation_rate * 100,
        6
    ) AS validation_fraud_rate_pct,

    ROUND(
        validation_lift,
        4
    ) AS validation_lift,

    CASE
        WHEN development_lift > 1
             AND validation_lift > 1
        THEN 'ABOVE_BASELINE_BOTH'

        WHEN development_lift < 1
             AND validation_lift < 1
        THEN 'BELOW_BASELINE_BOTH'

        ELSE 'DIRECTION_CHANGED'
    END AS stability_direction

FROM combined

ORDER BY
    validation_lift DESC;



-- ============================================================
-- 4. ABSOLUTE AMOUNT BAND STABILITY
--
-- Fixed interpretable bands.
--
-- These thresholds are not optimised using validation data.
-- ============================================================

WITH base AS (

    SELECT

        CASE
            WHEN t.transaction_datetime <
                 '2018-01-01 00:00:00'
            THEN 'DEV'

            ELSE 'VAL'
        END AS period,

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
            WHEN f.fraud_label = 'Yes'
            THEN 1
            ELSE 0
        END AS fraud_flag

    FROM fraud_labels f

    JOIN transactions t
        ON t.transaction_id =
           f.transaction_id

    WHERE
        t.transaction_datetime >=
            '2010-01-01 00:00:00'

        AND t.transaction_datetime <
            '2019-01-01 00:00:00'
),

period_prevalence AS (

    SELECT
        period,

        CAST(
            SUM(fraud_flag)
            AS DECIMAL(30,12)
        )
        /
        NULLIF(
            CAST(
                COUNT(*)
                AS DECIMAL(30,12)
            ),
            0
        ) AS period_fraud_rate

    FROM base

    GROUP BY period
),

amount_rates AS (

    SELECT
        period,

        amount_band,

        COUNT(*) AS labelled_transactions,

        SUM(fraud_flag) AS fraud_transactions,

        CAST(
            SUM(fraud_flag)
            AS DECIMAL(30,12)
        )
        /
        NULLIF(
            CAST(
                COUNT(*)
                AS DECIMAL(30,12)
            ),
            0
        ) AS fraud_rate

    FROM base

    GROUP BY
        period,
        amount_band
),

combined AS (

    SELECT
        a.amount_band,

        MAX(
            CASE
                WHEN a.period = 'DEV'
                THEN a.labelled_transactions
            END
        ) AS development_transactions,

        MAX(
            CASE
                WHEN a.period = 'DEV'
                THEN a.fraud_transactions
            END
        ) AS development_fraud,

        MAX(
            CASE
                WHEN a.period = 'DEV'
                THEN a.fraud_rate
            END
        ) AS development_rate,

        MAX(
            CASE
                WHEN a.period = 'DEV'
                THEN
                    a.fraud_rate
                    /
                    NULLIF(
                        p.period_fraud_rate,
                        0
                    )
            END
        ) AS development_lift,

        MAX(
            CASE
                WHEN a.period = 'VAL'
                THEN a.labelled_transactions
            END
        ) AS validation_transactions,

        MAX(
            CASE
                WHEN a.period = 'VAL'
                THEN a.fraud_transactions
            END
        ) AS validation_fraud,

        MAX(
            CASE
                WHEN a.period = 'VAL'
                THEN a.fraud_rate
            END
        ) AS validation_rate,

        MAX(
            CASE
                WHEN a.period = 'VAL'
                THEN
                    a.fraud_rate
                    /
                    NULLIF(
                        p.period_fraud_rate,
                        0
                    )
            END
        ) AS validation_lift

    FROM amount_rates a

    JOIN period_prevalence p
        ON a.period = p.period

    GROUP BY
        a.amount_band
)

SELECT
    amount_band,

    development_transactions,

    development_fraud,

    ROUND(
        development_rate * 100,
        6
    ) AS development_fraud_rate_pct,

    ROUND(
        development_lift,
        4
    ) AS development_lift,

    validation_transactions,

    validation_fraud,

    ROUND(
        validation_rate * 100,
        6
    ) AS validation_fraud_rate_pct,

    ROUND(
        validation_lift,
        4
    ) AS validation_lift,

    CASE
        WHEN development_lift > 1
             AND validation_lift > 1
        THEN 'ABOVE_BASELINE_BOTH'

        WHEN development_lift < 1
             AND validation_lift < 1
        THEN 'BELOW_BASELINE_BOTH'

        ELSE 'DIRECTION_CHANGED'
    END AS stability_direction

FROM combined

ORDER BY
    amount_band;



-- ============================================================
-- 5. MCC STABILITY
--
-- Population controls reduce the chance that tiny categories
-- dominate the stability review.
--
-- Eligibility:
--
-- Development labelled transactions >= 10,000
-- Validation labelled transactions  >= 1,000
-- ============================================================

WITH base AS (

    SELECT

        CASE
            WHEN t.transaction_datetime <
                 '2018-01-01 00:00:00'
            THEN 'DEV'

            ELSE 'VAL'
        END AS period,

        t.mcc,

        CASE
            WHEN f.fraud_label = 'Yes'
            THEN 1
            ELSE 0
        END AS fraud_flag

    FROM fraud_labels f

    JOIN transactions t
        ON t.transaction_id =
           f.transaction_id

    WHERE
        t.transaction_datetime >=
            '2010-01-01 00:00:00'

        AND t.transaction_datetime <
            '2019-01-01 00:00:00'
),

period_prevalence AS (

    SELECT
        period,

        CAST(
            SUM(fraud_flag)
            AS DECIMAL(30,12)
        )
        /
        NULLIF(
            CAST(
                COUNT(*)
                AS DECIMAL(30,12)
            ),
            0
        ) AS period_fraud_rate

    FROM base

    GROUP BY period
),

mcc_rates AS (

    SELECT
        period,

        mcc,

        COUNT(*) AS labelled_transactions,

        SUM(fraud_flag) AS fraud_transactions,

        CAST(
            SUM(fraud_flag)
            AS DECIMAL(30,12)
        )
        /
        NULLIF(
            CAST(
                COUNT(*)
                AS DECIMAL(30,12)
            ),
            0
        ) AS fraud_rate

    FROM base

    GROUP BY
        period,
        mcc
),

combined AS (

    SELECT
        m.mcc,

        MAX(
            CASE
                WHEN m.period = 'DEV'
                THEN m.labelled_transactions
            END
        ) AS development_transactions,

        MAX(
            CASE
                WHEN m.period = 'DEV'
                THEN m.fraud_transactions
            END
        ) AS development_fraud,

        MAX(
            CASE
                WHEN m.period = 'DEV'
                THEN m.fraud_rate
            END
        ) AS development_rate,

        MAX(
            CASE
                WHEN m.period = 'DEV'
                THEN
                    m.fraud_rate
                    /
                    NULLIF(
                        p.period_fraud_rate,
                        0
                    )
            END
        ) AS development_lift,

        MAX(
            CASE
                WHEN m.period = 'VAL'
                THEN m.labelled_transactions
            END
        ) AS validation_transactions,

        MAX(
            CASE
                WHEN m.period = 'VAL'
                THEN m.fraud_transactions
            END
        ) AS validation_fraud,

        MAX(
            CASE
                WHEN m.period = 'VAL'
                THEN m.fraud_rate
            END
        ) AS validation_rate,

        MAX(
            CASE
                WHEN m.period = 'VAL'
                THEN
                    m.fraud_rate
                    /
                    NULLIF(
                        p.period_fraud_rate,
                        0
                    )
            END
        ) AS validation_lift

    FROM mcc_rates m

    JOIN period_prevalence p
        ON m.period = p.period

    GROUP BY
        m.mcc
)

SELECT
    c.mcc,

    ref.mcc_description,

    c.development_transactions,

    c.development_fraud,

    ROUND(
        c.development_rate * 100,
        6
    ) AS development_fraud_rate_pct,

    ROUND(
        c.development_lift,
        4
    ) AS development_lift,

    c.validation_transactions,

    c.validation_fraud,

    ROUND(
        c.validation_rate * 100,
        6
    ) AS validation_fraud_rate_pct,

    ROUND(
        c.validation_lift,
        4
    ) AS validation_lift,

    ROUND(
        c.validation_lift
        -
        c.development_lift,
        4
    ) AS lift_change,

    CASE
        WHEN c.development_lift > 1
             AND c.validation_lift > 1
        THEN 'ABOVE_BASELINE_BOTH'

        WHEN c.development_lift < 1
             AND c.validation_lift < 1
        THEN 'BELOW_BASELINE_BOTH'

        ELSE 'DIRECTION_CHANGED'
    END AS stability_direction

FROM combined c

JOIN mcc_codes ref
    ON c.mcc = ref.mcc

WHERE
    c.development_transactions >= 10000

    AND c.validation_transactions >= 1000

ORDER BY
    c.development_lift DESC

LIMIT 25;