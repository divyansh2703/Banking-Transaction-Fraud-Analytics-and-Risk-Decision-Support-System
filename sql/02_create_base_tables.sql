USE financial_transaction_analytics;


-- ============================================================
-- CUSTOMERS
-- Source: data/processed/users.csv
-- Grain: one row per customer
-- ============================================================

DROP TABLE IF EXISTS customers;

CREATE TABLE customers (

    client_id INT UNSIGNED NOT NULL,

    current_age TINYINT UNSIGNED NOT NULL,
    retirement_age TINYINT UNSIGNED NOT NULL,

    birth_year SMALLINT UNSIGNED NOT NULL,
    birth_month TINYINT UNSIGNED NOT NULL,

    gender VARCHAR(16) NOT NULL,
    address VARCHAR(255) NOT NULL,

    latitude DECIMAL(9,6) NOT NULL,
    longitude DECIMAL(9,6) NOT NULL,

    per_capita_income DECIMAL(14,2) NOT NULL,
    yearly_income DECIMAL(14,2) NOT NULL,
    total_debt DECIMAL(14,2) NOT NULL,

    credit_score SMALLINT UNSIGNED NOT NULL,
    num_credit_cards TINYINT UNSIGNED NOT NULL,

    PRIMARY KEY (client_id),

    CONSTRAINT chk_customer_birth_month
        CHECK (
            birth_month BETWEEN 1 AND 12
        )

) ENGINE = InnoDB;


-- ============================================================
-- CARDS
-- Source: data/processed/cards.csv
-- Grain: one row per card
-- ============================================================

DROP TABLE IF EXISTS cards;

CREATE TABLE cards (

    card_id INT UNSIGNED NOT NULL,
    client_id INT UNSIGNED NOT NULL,

    card_brand VARCHAR(32) NOT NULL,
    card_type VARCHAR(32) NOT NULL,

    -- Month precision intentionally preserved.
    expires CHAR(7) NOT NULL,

    has_chip CHAR(3) NOT NULL,

    num_cards_issued TINYINT UNSIGNED NOT NULL,

    credit_limit DECIMAL(14,2) NOT NULL,

    -- Month precision intentionally preserved.
    acct_open_date CHAR(7) NOT NULL,

    year_pin_last_changed SMALLINT UNSIGNED NOT NULL,

    card_on_dark_web CHAR(3) NOT NULL,

    PRIMARY KEY (card_id),

    CONSTRAINT chk_card_has_chip
        CHECK (
            has_chip IN ('YES', 'NO')
        ),

    CONSTRAINT chk_card_dark_web
        CHECK (
            card_on_dark_web IN ('Yes', 'No')
        )

) ENGINE = InnoDB;


-- ============================================================
-- MCC REFERENCE
-- Source: data/processed/mcc_codes.csv
-- Grain: one row per MCC
-- ============================================================

DROP TABLE IF EXISTS mcc_codes;

CREATE TABLE mcc_codes (

    mcc CHAR(4) NOT NULL,

    mcc_description VARCHAR(255) NOT NULL,

    PRIMARY KEY (mcc)

) ENGINE = InnoDB;


-- ============================================================
-- TRANSACTIONS
-- Source: data/processed/transactions.csv
-- Grain: one row per transaction
-- ============================================================

DROP TABLE IF EXISTS transactions;

CREATE TABLE transactions (

    transaction_id BIGINT UNSIGNED NOT NULL,

    transaction_datetime DATETIME NOT NULL,

    client_id INT UNSIGNED NOT NULL,
    card_id INT UNSIGNED NOT NULL,

    amount DECIMAL(14,2) NOT NULL,

    use_chip VARCHAR(32) NOT NULL,

    merchant_id BIGINT NOT NULL,

    merchant_city VARCHAR(128) NOT NULL,

    merchant_state VARCHAR(128) NULL,

    -- Stored as text intentionally.
    zip VARCHAR(32) NULL,

    -- MCC is a categorical code, not a numerical measure.
    mcc CHAR(4) NOT NULL,

    errors VARCHAR(255) NULL,

    transaction_before_card_open_flag TINYINT UNSIGNED NOT NULL,

    transaction_after_card_expiry_flag TINYINT UNSIGNED NOT NULL,

    channel_location_inconsistency_flag TINYINT UNSIGNED NOT NULL,

    PRIMARY KEY (transaction_id),

    CONSTRAINT chk_before_open_flag
        CHECK (
            transaction_before_card_open_flag
            IN (0, 1)
        ),

    CONSTRAINT chk_after_expiry_flag
        CHECK (
            transaction_after_card_expiry_flag
            IN (0, 1)
        ),

    CONSTRAINT chk_channel_location_flag
        CHECK (
            channel_location_inconsistency_flag
            IN (0, 1)
        )

) ENGINE = InnoDB;


-- ============================================================
-- FRAUD LABELS
-- Source: data/processed/fraud_labels.csv
-- Grain: one row per labelled transaction
--
-- Not every transaction has a supplied fraud label.
-- ============================================================

DROP TABLE IF EXISTS fraud_labels;

CREATE TABLE fraud_labels (

    transaction_id BIGINT UNSIGNED NOT NULL,

    fraud_label CHAR(3) NOT NULL,

    PRIMARY KEY (transaction_id),

    CONSTRAINT chk_fraud_label
        CHECK (
            fraud_label IN ('Yes', 'No')
        )

) ENGINE = InnoDB;


-- ============================================================
-- TABLE CREATION CHECK
-- ============================================================

SHOW TABLES;