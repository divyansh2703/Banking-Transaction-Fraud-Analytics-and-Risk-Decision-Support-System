USE financial_transaction_analytics;


-- ============================================================
-- PHASE 12.3
-- WORKLOAD-DRIVEN ANALYTICAL INDEXES
-- ============================================================


-- ============================================================
-- TRANSACTIONS
--
-- Composite indexes are intentionally ordered with the
-- business entity first and transaction time second.
--
-- This supports both:
--   WHERE client_id = ...
-- and:
--   WHERE client_id = ... AND transaction_datetime < ...
--
-- which will become important for historical behaviour.
-- ============================================================

ALTER TABLE transactions

    ADD INDEX idx_tx_client_datetime
        (
            client_id,
            transaction_datetime
        ),

    ADD INDEX idx_tx_card_datetime
        (
            card_id,
            transaction_datetime
        ),

    ADD INDEX idx_tx_merchant_datetime
        (
            merchant_id,
            transaction_datetime
        ),

    ADD INDEX idx_tx_mcc
        (
            mcc
        ),

    ADD INDEX idx_tx_datetime
        (
            transaction_datetime
        );


-- ============================================================
-- CARDS
--
-- card_id is already the primary key.
-- client_id requires an index for customer portfolio joins.
-- ============================================================

ALTER TABLE cards

    ADD INDEX idx_cards_client_id
        (
            client_id
        );


-- ============================================================
-- FRAUD LABELS
--
-- transaction_id is already the primary key.
--
-- Fraud Yes is extremely rare, so leading with fraud_label
-- allows selective access to confirmed fraud transactions.
-- ============================================================

ALTER TABLE fraud_labels

    ADD INDEX idx_fraud_label_transaction
        (
            fraud_label,
            transaction_id
        );


-- ============================================================
-- UPDATE OPTIMIZER STATISTICS
-- ============================================================

ANALYZE TABLE
    transactions,
    cards,
    fraud_labels;


-- ============================================================
-- INDEX REVIEW
-- ============================================================

SHOW INDEX FROM transactions;

SHOW INDEX FROM cards;

SHOW INDEX FROM fraud_labels;