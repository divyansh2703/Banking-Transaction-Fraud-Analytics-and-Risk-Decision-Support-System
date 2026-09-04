USE financial_transaction_analytics;


-- ============================================================
-- RE-RUN SAFETY
-- ============================================================

TRUNCATE TABLE fraud_labels;
TRUNCATE TABLE transactions;
TRUNCATE TABLE cards;
TRUNCATE TABLE mcc_codes;
TRUNCATE TABLE customers;


-- ============================================================
-- 1. CUSTOMERS
-- ============================================================

LOAD DATA LOCAL INFILE
'/Users/divyanshdoshi/Documents/GitHub/financial_transaction_analytics_platform/data/processed/users.csv'

INTO TABLE customers

CHARACTER SET utf8mb4

FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'

LINES TERMINATED BY '\n'

IGNORE 1 LINES

(
    client_id,
    current_age,
    retirement_age,
    birth_year,
    birth_month,
    gender,
    address,
    latitude,
    longitude,
    per_capita_income,
    yearly_income,
    total_debt,
    credit_score,
    num_credit_cards
);


SELECT
    'customers' AS table_name,
    COUNT(*) AS row_count
FROM customers;


-- ============================================================
-- 2. CARDS
-- ============================================================

LOAD DATA LOCAL INFILE
'/Users/divyanshdoshi/Documents/GitHub/financial_transaction_analytics_platform/data/processed/cards.csv'

INTO TABLE cards

CHARACTER SET utf8mb4

FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'

LINES TERMINATED BY '\n'

IGNORE 1 LINES

(
    card_id,
    client_id,
    card_brand,
    card_type,
    expires,
    has_chip,
    num_cards_issued,
    credit_limit,
    acct_open_date,
    year_pin_last_changed,
    @card_on_dark_web
)

SET
    card_on_dark_web =
        TRIM(
            TRAILING '\r'
            FROM @card_on_dark_web
        );


SELECT
    'cards' AS table_name,
    COUNT(*) AS row_count
FROM cards;


-- ============================================================
-- 3. MCC CODES
-- ============================================================

LOAD DATA LOCAL INFILE
'/Users/divyanshdoshi/Documents/GitHub/financial_transaction_analytics_platform/data/processed/mcc_codes.csv'

INTO TABLE mcc_codes

CHARACTER SET utf8mb4

FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'

LINES TERMINATED BY '\n'

IGNORE 1 LINES

(
    mcc,
    @mcc_description
)

SET
    mcc_description =
        TRIM(
            TRAILING '\r'
            FROM @mcc_description
        );


SELECT
    'mcc_codes' AS table_name,
    COUNT(*) AS row_count
FROM mcc_codes;


-- ============================================================
-- 4. TRANSACTIONS
-- ============================================================

LOAD DATA LOCAL INFILE
'/Users/divyanshdoshi/Documents/GitHub/financial_transaction_analytics_platform/data/processed/transactions.csv'

INTO TABLE transactions

CHARACTER SET utf8mb4

FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'

LINES TERMINATED BY '\n'

IGNORE 1 LINES

(
    @transaction_id,
    @transaction_date,
    @client_id,
    @card_id,
    @amount,
    @use_chip,
    @merchant_id,
    @merchant_city,
    @merchant_state,
    @zip,
    @mcc,
    @errors,
    @before_open_flag,
    @after_expiry_flag,
    @channel_location_flag
)

SET

    transaction_id =
        CAST(
            @transaction_id
            AS UNSIGNED
        ),

    transaction_datetime =
        STR_TO_DATE(
            @transaction_date,
            '%Y-%m-%d %H:%i:%s'
        ),

    client_id =
        CAST(
            @client_id
            AS UNSIGNED
        ),

    card_id =
        CAST(
            @card_id
            AS UNSIGNED
        ),

    amount =
        CAST(
            @amount
            AS DECIMAL(14,2)
        ),

    use_chip =
        @use_chip,

    merchant_id =
        CAST(
            @merchant_id
            AS SIGNED
        ),

    merchant_city =
        @merchant_city,

    merchant_state =
        NULLIF(
            @merchant_state,
            ''
        ),

    zip =
        NULLIF(
            @zip,
            ''
        ),

    mcc =
        @mcc,

    errors =
        NULLIF(
            @errors,
            ''
        ),

    transaction_before_card_open_flag =
        CAST(
            @before_open_flag
            AS UNSIGNED
        ),

    transaction_after_card_expiry_flag =
        CAST(
            @after_expiry_flag
            AS UNSIGNED
        ),

    channel_location_inconsistency_flag =
        CAST(
            TRIM(
                TRAILING '\r'
                FROM @channel_location_flag
            )
            AS UNSIGNED
        );


SELECT
    'transactions' AS table_name,
    COUNT(*) AS row_count
FROM transactions;


-- ============================================================
-- 5. FRAUD LABELS
-- ============================================================

LOAD DATA LOCAL INFILE
'/Users/divyanshdoshi/Documents/GitHub/financial_transaction_analytics_platform/data/processed/fraud_labels.csv'

INTO TABLE fraud_labels

CHARACTER SET utf8mb4

FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'

LINES TERMINATED BY '\n'

IGNORE 1 LINES

(
    transaction_id,
    @fraud_label
)

SET
    fraud_label =
        TRIM(
            TRAILING '\r'
            FROM @fraud_label
        );


SELECT
    'fraud_labels' AS table_name,
    COUNT(*) AS row_count
FROM fraud_labels;