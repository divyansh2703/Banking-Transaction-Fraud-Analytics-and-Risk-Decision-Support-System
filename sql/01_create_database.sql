-- ============================================================
-- PHASE 12
-- FINANCIAL TRANSACTION ANALYTICS DATABASE
-- ============================================================

CREATE DATABASE IF NOT EXISTS financial_transaction_analytics
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;

USE financial_transaction_analytics;

SELECT
    DATABASE() AS active_database;