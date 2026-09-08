# Banking Transaction Fraud Analytics and Risk Decision Support

An independent banking analytics project that turns customer, card, merchant and transaction records into a traceable foundation for fraud investigation prioritisation. The committed work covers ingestion, cleaning, independent validation, exploratory analysis, MySQL analytical views and reporting exports. Predictive models and stakeholder dashboards remain future work.

## The question

Which transaction groups deserve further investigation, and how can review capacity be compared without treating missing fraud labels as legitimate transactions?

## Tools and methods

Python, pandas, MySQL, SQL, Data validation, Fraud analytics, Excel reporting.

## Work in this repository

1. Built separate ingestion, cleaning and validation components for customers, cards, transactions, merchant categories and fraud labels.
2. Checked identifier uniqueness, reference integrity, card ownership, monetary transformations and lifecycle flags using an independent validator.
3. Developed MySQL tables, analytical views and business question queries covering transaction concentration, operational errors, fraud concentration, label coverage and review prioritisation.
4. Added temporal signal stability and multiple signal baseline queries to examine whether candidate review rules remain useful across periods.
5. Created a Python exporter and SQL reporting layer for Excel summaries without loading the full transaction population into a worksheet.

## Evidence and scope

| Measure | Recorded value |
| --- | --- |
| Transaction records | 13,305,915 |
| Customers | 2,000 |
| Cards | 6,146 |
| Merchant category codes | 109 |
| Available fraud labels | 8,914,963 |
| Fraud labelled transactions | 13,332 |
| Transactions without labels | 4,390,952 |
| Recorded interim validation | 56 passed; 0 failed |

## Repository guide

| File or folder | Purpose |
| --- | --- |
| [config/source_contracts.json](https://github.com/divyansh2703/Banking-Transaction-Fraud-Analytics-and-Risk-Decision-Support-System/blob/main/config/source_contracts.json) | Expected source structure |
| [src/validate_interim_data.py](https://github.com/divyansh2703/Banking-Transaction-Fraud-Analytics-and-Risk-Decision-Support-System/blob/main/src/validate_interim_data.py) | Independent validation logic |
| [logs/interim_validation_report.csv](https://github.com/divyansh2703/Banking-Transaction-Fraud-Analytics-and-Risk-Decision-Support-System/blob/main/logs/interim_validation_report.csv) | Recorded validation evidence |
| [reports/eda/phase_10_10_fraud/fraud_prevalence.csv](https://github.com/divyansh2703/Banking-Transaction-Fraud-Analytics-and-Risk-Decision-Support-System/blob/main/reports/eda/phase_10_10_fraud/fraud_prevalence.csv) | Observed label counts |
| [reports/eda/phase_10_10_fraud/fraud_channel_summary.csv](https://github.com/divyansh2703/Banking-Transaction-Fraud-Analytics-and-Risk-Decision-Support-System/blob/main/reports/eda/phase_10_10_fraud/fraud_channel_summary.csv) | Channel comparison |
| [sql/06_create_analytical_views.sql](https://github.com/divyansh2703/Banking-Transaction-Fraud-Analytics-and-Risk-Decision-Support-System/blob/main/sql/06_create_analytical_views.sql) | Reusable analytical layer |
| [sql/business_questions/bq04c_multisignal_baseline.sql](https://github.com/divyansh2703/Banking-Transaction-Fraud-Analytics-and-Risk-Decision-Support-System/blob/main/sql/business_questions/bq04c_multisignal_baseline.sql) | Candidate baseline analysis |
| [sql/reporting/01_excel_reporting_exports.sql](https://github.com/divyansh2703/Banking-Transaction-Fraud-Analytics-and-Risk-Decision-Support-System/blob/main/sql/reporting/01_excel_reporting_exports.sql) | Reporting SQL |
| [src/export_excel_reporting.py](https://github.com/divyansh2703/Banking-Transaction-Fraud-Analytics-and-Risk-Decision-Support-System/blob/main/src/export_excel_reporting.py) | Excel reporting exporter |
| [excel/Financial_Transaction_Risk_Analysis.xlsx](https://github.com/divyansh2703/Banking-Transaction-Fraud-Analytics-and-Risk-Decision-Support-System/blob/main/excel/Financial_Transaction_Risk_Analysis.xlsx) | Committed Excel workbook |

## Getting started

Use a dedicated Python environment. `requirements.txt` currently lists pandas and ijson; the full notebook and reporting workflow needs additional imports, including the MySQL connector used by the exporter. Obtain the authorised raw files separately and use the filenames in `config/source_contracts.json`. The full raw and processed transaction datasets are not committed.

Run the cleaning stages before `src/validate_interim_data.py`, then review and execute SQL files 01 through 07 in order against a local MySQL database. Inspect database names, local data paths and the load settings before execution. The reporting exporter prompts for the MySQL password and can be run from the repository root after its SQL dependencies exist:

```bash
python src/export_excel_reporting.py
```

The historical validation evidence is committed. A fresh execution of the complete pipeline was not performed for this documentation update.

## Current limitations

1. Missing fraud labels represent unknown outcomes. They must not be filled as nonfraud for supervised evaluation.
2. The saved channel summary contains 8,779 fraud labelled online transactions, 3,176 chip transactions and 1,377 swipe transactions. These are observed associations, not proof that a payment channel causes fraud.
3. The original data publisher, exact release, licence, currency and synthetic status still need explicit documentation.
4. The SQL scripts are committed implementations. Their presence alone does not establish completed query results or operational impact.
5. There is no committed final fraud model, validated financial saving, measured workload reduction or completed Tableau dashboard supporting those claims.

## Next steps

1. Document source provenance and a complete reproducible environment.
2. Publish reviewed SQL result tables and complete the Excel analysis.
3. Evaluate predictive models only after defining the decision time, eligible labels and a defensible baseline.

## Authors and reuse

Divyansh Doshi.

Documentation reviewed against the public repository on 7 September 2026. Counts are taken from the named saved artifacts or directly inspected CSVs; this review did not rerun model training or validate a complete deployment. No source code licence was found in the reviewed project tree. Data and third party material may have separate terms.
