from __future__ import annotations

import csv
import getpass
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

import pymysql


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_DIR = PROJECT_ROOT / "excel" / "data_exports"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_DATABASE = os.getenv(
    "MYSQL_DATABASE",
    "financial_transaction_analytics",
)


# ============================================================
# CONTROLLED REPORTING EXPORTS
# ============================================================

EXPORTS = {

    "review_capacity.csv": {
        "source": "vw_2018_amount_baseline_kpis",
        "expected_rows": 4,
        "query": """
            SELECT
                review_rate_pct,
                selected_transactions,
                total_transactions,
                captured_fraud_transactions,
                total_fraud_transactions,
                fraud_case_capture_pct,
                captured_fraud_value,
                total_fraud_value,
                fraud_value_capture_pct,
                precision_pct,
                lift,
                workload_reduction_pct

            FROM vw_2018_amount_baseline_kpis

            ORDER BY review_rate_pct;
        """,
    },


    "channel_analysis.csv": {
        "source": "vw_channel_operational_risk_summary",
        "expected_rows": 3,
        "query": """
            SELECT
                transaction_channel,
                transaction_count,
                error_transactions,
                error_rate_pct,
                labelled_transactions,
                fraud_transactions,
                labelled_fraud_rate_pct,
                absolute_transaction_value,
                confirmed_fraud_transaction_value

            FROM vw_channel_operational_risk_summary

            ORDER BY transaction_count DESC;
        """,
    },


    "mcc_analysis.csv": {
        "source": "vw_mcc_risk_summary",
        "expected_rows": 109,
        "query": """
            SELECT
                mcc,
                mcc_description,
                transaction_count,
                distinct_merchants,
                absolute_transaction_value,
                average_absolute_amount,
                error_transactions,
                error_rate_pct,
                labelled_transactions,
                fraud_transactions,
                labelled_fraud_rate_pct,
                share_of_confirmed_fraud_pct

            FROM vw_mcc_risk_summary

            ORDER BY fraud_transactions DESC;
        """,
    },


    "merchant_analysis.csv": {
        "source": "vw_merchant_risk_summary",
        "expected_rows": None,
        "query": """
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
        """,
    },


    "customer_summary.csv": {
        "source": "vw_customer_portfolio_summary",
        "expected_rows": 2000,
        "query": """
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
        """,
    },
}


# ============================================================
# HELPERS
# ============================================================

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


def export_query(
    connection,
    filename: str,
    query: str,
) -> tuple[int, int]:

    output_path = OUTPUT_DIR / filename

    with connection.cursor() as cursor:

        cursor.execute(query)

        column_names = [
            column[0]
            for column in cursor.description
        ]

        rows = cursor.fetchall()

    # utf-8-sig is deliberate:
    # Excel recognises UTF-8 reliably when the BOM is present.
    with output_path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:

        writer = csv.writer(file)

        writer.writerow(column_names)

        writer.writerows(rows)

    return len(rows), len(column_names)


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    print("=" * 65)
    print("EXCEL REPORTING EXPORT")
    print("=" * 65)

    password = getpass.getpass(
        f"MySQL password for {MYSQL_USER}: "
    )

    connection = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=password,
        database=MYSQL_DATABASE,
        charset="utf8mb4",
        autocommit=True,
    )

    manifest_rows = []

    export_timestamp = datetime.now(
        timezone.utc
    ).isoformat()

    try:

        for filename, config in EXPORTS.items():

            print(f"\nExporting: {filename}")

            row_count, column_count = export_query(
                connection=connection,
                filename=filename,
                query=config["query"],
            )

            expected_rows = config["expected_rows"]

            if expected_rows is None:
                validation_status = "PASS"
            elif row_count == expected_rows:
                validation_status = "PASS"
            else:
                validation_status = "FAIL"

            output_path = OUTPUT_DIR / filename

            file_hash = sha256_file(
                output_path
            )

            manifest_rows.append(
                {
                    "filename": filename,
                    "source": config["source"],
                    "row_count": row_count,
                    "column_count": column_count,
                    "expected_rows": (
                        expected_rows
                        if expected_rows is not None
                        else ""
                    ),
                    "validation_status": validation_status,
                    "exported_at_utc": export_timestamp,
                    "sha256": file_hash,
                }
            )

            print(
                f"Rows: {row_count:,} | "
                f"Columns: {column_count} | "
                f"Status: {validation_status}"
            )

            if validation_status != "PASS":
                raise ValueError(
                    f"{filename} failed row-count validation. "
                    f"Expected {expected_rows:,}, "
                    f"found {row_count:,}."
                )

    finally:

        connection.close()


    # ========================================================
    # EXPORT MANIFEST
    # ========================================================

    manifest_path = (
        OUTPUT_DIR
        / "export_manifest.csv"
    )

    manifest_columns = [
        "filename",
        "source",
        "row_count",
        "column_count",
        "expected_rows",
        "validation_status",
        "exported_at_utc",
        "sha256",
    ]

    with manifest_path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=manifest_columns,
        )

        writer.writeheader()

        writer.writerows(
            manifest_rows
        )


    # ========================================================
    # FINAL SUMMARY
    # ========================================================

    print("\n" + "=" * 65)
    print("EXPORT COMPLETE")
    print("=" * 65)

    for row in manifest_rows:

        print(
            f"{row['filename']:<25} "
            f"{row['row_count']:>8,} rows "
            f"{row['validation_status']}"
        )

    print(
        f"\nManifest: "
        f"{manifest_path.relative_to(PROJECT_ROOT)}"
    )


if __name__ == "__main__":
    main()