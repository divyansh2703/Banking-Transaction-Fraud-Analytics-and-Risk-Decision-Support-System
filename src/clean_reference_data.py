from pathlib import Path
from time import perf_counter
import argparse
import csv
import json
import sys

import ijson


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_MCC_FILE = (
    PROJECT_ROOT / "data" / "raw" / "mcc_codes.json"
)

DEFAULT_FRAUD_FILE = (
    PROJECT_ROOT / "data" / "raw" / "train_fraud_labels.json"
)

INTERIM_DIR = PROJECT_ROOT / "data" / "interim"

DEFAULT_MCC_OUTPUT = (
    INTERIM_DIR / "mcc_codes_cleaned.csv"
)

DEFAULT_FRAUD_OUTPUT = (
    INTERIM_DIR / "fraud_labels_cleaned.csv"
)


# ============================================================
# EXPECTED SOURCE RESULTS
# ============================================================

EXPECTED_MCC_RECORDS = 109

EXPECTED_FRAUD_LABELS = 8_914_963
EXPECTED_YES_LABELS = 13_332
EXPECTED_NO_LABELS = 8_901_631

ALLOWED_FRAUD_LABELS = {
    "Yes",
    "No",
}


# ============================================================
# GENERAL VALIDATION
# ============================================================

def validate_file_exists(file_path, description):
    if not file_path.exists():
        raise FileNotFoundError(
            f"{description} not found: {file_path}"
        )


def remove_existing_temp_file(temp_file):
    """
    Prevent accidental reuse of an incomplete temporary file
    from a previous failed run.
    """

    if temp_file.exists():
        temp_file.unlink()


# ============================================================
# MCC CLEANING
# ============================================================

def clean_mcc_codes(
    mcc_file,
    output_file
):
    """
    Transform the MCC JSON mapping:

        "5812": "Eating Places and Restaurants"

    into an analytical CSV:

        mcc,mcc_description
        5812,Eating Places and Restaurants

    MCC remains a string/category code.
    """

    print("Cleaning mcc_codes.json...")

    start = perf_counter()

    with open(
        mcc_file,
        "r",
        encoding="utf-8"
    ) as file:
        data = json.load(file)

    # --------------------------------------------------------
    # Validate JSON structure
    # --------------------------------------------------------

    if not isinstance(data, dict):
        raise TypeError(
            "mcc_codes.json must contain a JSON key-value mapping."
        )

    records_read = len(data)

    if records_read != EXPECTED_MCC_RECORDS:
        raise ValueError(
            "MCC record reconciliation failed. "
            f"Expected {EXPECTED_MCC_RECORDS:,}, "
            f"found {records_read:,}."
        )

    cleaned_rows = []

    for raw_mcc, description in data.items():

        mcc = str(raw_mcc).strip()

        # MCC should be exactly four numeric characters.
        if not (
            len(mcc) == 4
            and mcc.isdigit()
        ):
            raise ValueError(
                f"Invalid MCC format detected: {raw_mcc}"
            )

        if description is None:
            raise ValueError(
                f"MCC {mcc} has a missing description."
            )

        description = str(description).strip()

        if description == "":
            raise ValueError(
                f"MCC {mcc} has a blank description."
            )

        cleaned_rows.append(
            {
                "mcc": mcc,
                "mcc_description": description,
            }
        )

    # --------------------------------------------------------
    # Validate MCC uniqueness
    # --------------------------------------------------------

    mcc_values = [
        row["mcc"]
        for row in cleaned_rows
    ]

    unique_mcc_count = len(set(mcc_values))

    if unique_mcc_count != records_read:
        raise ValueError(
            "Duplicate MCC values detected."
        )

    # --------------------------------------------------------
    # Write using temporary file first
    # --------------------------------------------------------

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    temp_file = output_file.with_suffix(
        output_file.suffix + ".tmp"
    )

    remove_existing_temp_file(
        temp_file
    )

    with open(
        temp_file,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=[
                "mcc",
                "mcc_description",
            ]
        )

        writer.writeheader()

        writer.writerows(
            cleaned_rows
        )

    # Only replace final output after validation succeeds.
    temp_file.replace(
        output_file
    )

    elapsed = perf_counter() - start

    return {
        "records_read": records_read,
        "records_written": len(cleaned_rows),
        "unique_mcc": unique_mcc_count,
        "elapsed": elapsed,
    }


# ============================================================
# FRAUD LABEL CLEANING
# ============================================================

def clean_fraud_labels(
    fraud_file,
    output_file
):
    """
    Stream the fraud-label JSON without loading the entire
    8.9M-record mapping into memory.

    Raw structure:

        {
            "target": {
                "10649266": "No",
                ...
            }
        }

    Output:

        transaction_id,fraud_label
        10649266,No
        ...
    """

    print("Cleaning train_fraud_labels.json using streaming...")

    start = perf_counter()

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    temp_file = output_file.with_suffix(
        output_file.suffix + ".tmp"
    )

    remove_existing_temp_file(
        temp_file
    )

    records_read = 0
    records_written = 0

    yes_count = 0
    no_count = 0

    invalid_transaction_ids = 0
    unexpected_labels = 0

    try:

        with open(
            fraud_file,
            "rb"
        ) as source_file, open(
            temp_file,
            "w",
            newline="",
            encoding="utf-8"
        ) as output:

            writer = csv.writer(
                output
            )

            writer.writerow(
                [
                    "transaction_id",
                    "fraud_label",
                ]
            )

            # ------------------------------------------------
            # Incrementally parse everything under "target"
            # ------------------------------------------------

            for transaction_id, label in ijson.kvitems(
                source_file,
                "target"
            ):

                records_read += 1

                transaction_id = str(
                    transaction_id
                ).strip()

                # --------------------------------------------
                # Transaction ID validation
                # --------------------------------------------

                if not transaction_id.isdigit():
                    invalid_transaction_ids += 1
                    continue

                # --------------------------------------------
                # Label validation
                # --------------------------------------------

                if label not in ALLOWED_FRAUD_LABELS:
                    unexpected_labels += 1
                    continue

                if label == "Yes":
                    yes_count += 1

                elif label == "No":
                    no_count += 1

                # --------------------------------------------
                # Write directly to disk
                # --------------------------------------------

                writer.writerow(
                    [
                        transaction_id,
                        label,
                    ]
                )

                records_written += 1

        # ====================================================
        # FINAL FRAUD RECONCILIATION
        # ====================================================

        problems = []

        if records_read != EXPECTED_FRAUD_LABELS:
            problems.append(
                "Fraud label input reconciliation failed: "
                f"expected {EXPECTED_FRAUD_LABELS:,}, "
                f"read {records_read:,}"
            )

        if records_written != EXPECTED_FRAUD_LABELS:
            problems.append(
                "Fraud label output reconciliation failed: "
                f"expected {EXPECTED_FRAUD_LABELS:,}, "
                f"wrote {records_written:,}"
            )

        if invalid_transaction_ids != 0:
            problems.append(
                f"Invalid transaction IDs: "
                f"{invalid_transaction_ids:,}"
            )

        if unexpected_labels != 0:
            problems.append(
                f"Unexpected fraud labels: "
                f"{unexpected_labels:,}"
            )

        if yes_count != EXPECTED_YES_LABELS:
            problems.append(
                "Yes-label reconciliation failed: "
                f"expected {EXPECTED_YES_LABELS:,}, "
                f"found {yes_count:,}"
            )

        if no_count != EXPECTED_NO_LABELS:
            problems.append(
                "No-label reconciliation failed: "
                f"expected {EXPECTED_NO_LABELS:,}, "
                f"found {no_count:,}"
            )

        if (
            yes_count
            + no_count
            + unexpected_labels
            != records_read
        ):
            problems.append(
                "Fraud label category reconciliation failed."
            )

        if problems:
            raise ValueError(
                "\n".join(problems)
            )

        # ----------------------------------------------------
        # Only publish final output if everything passed
        # ----------------------------------------------------

        temp_file.replace(
            output_file
        )

    except Exception:

        # Do not leave a partial file that could later
        # be mistaken for valid processed data.
        if temp_file.exists():
            temp_file.unlink()

        raise

    elapsed = perf_counter() - start

    return {
        "records_read": records_read,
        "records_written": records_written,
        "yes_count": yes_count,
        "no_count": no_count,
        "unexpected_labels": unexpected_labels,
        "invalid_transaction_ids": invalid_transaction_ids,
        "elapsed": elapsed,
    }


# ============================================================
# REPORTING
# ============================================================

def print_mcc_report(
    metrics,
    output_file
):

    print()
    print("=" * 70)
    print("MCC CLEANING VALIDATION")
    print("=" * 70)

    print(
        f"Records read: "
        f"{metrics['records_read']:,}"
    )

    print(
        f"Records written: "
        f"{metrics['records_written']:,}"
    )

    print(
        f"Unique MCC values: "
        f"{metrics['unique_mcc']:,}"
    )

    print(
        "Invalid MCC values: 0"
    )

    print(
        "Missing/blank descriptions: 0"
    )

    print(
        f"Output file: {output_file}"
    )

    print(
        f"Processing time: "
        f"{metrics['elapsed']:.6f} seconds"
    )


def print_fraud_report(
    metrics,
    output_file
):

    print()
    print("=" * 70)
    print("FRAUD LABEL CLEANING VALIDATION")
    print("=" * 70)

    print()
    print("A. RECORD RECONCILIATION")

    print(
        f"Labels read: "
        f"{metrics['records_read']:,}"
    )

    print(
        f"Labels written: "
        f"{metrics['records_written']:,}"
    )

    print(
        f"Difference: "
        f"{metrics['records_read'] - metrics['records_written']:,}"
    )

    print()
    print("B. IDENTIFIER VALIDATION")

    print(
        f"Invalid transaction IDs: "
        f"{metrics['invalid_transaction_ids']:,}"
    )

    print()
    print("C. LABEL VALIDATION")

    print(
        f"Yes labels: "
        f"{metrics['yes_count']:,}"
    )

    print(
        f"No labels: "
        f"{metrics['no_count']:,}"
    )

    print(
        f"Unexpected labels: "
        f"{metrics['unexpected_labels']:,}"
    )

    print()
    print(
        f"Output file: {output_file}"
    )

    print(
        f"Processing time: "
        f"{metrics['elapsed']:.6f} seconds"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Clean MCC reference data and fraud labels."
        )
    )

    parser.add_argument(
        "--mcc",
        type=Path,
        default=DEFAULT_MCC_FILE,
        help="Path to mcc_codes.json"
    )

    parser.add_argument(
        "--fraud",
        type=Path,
        default=DEFAULT_FRAUD_FILE,
        help="Path to train_fraud_labels.json"
    )

    parser.add_argument(
        "--mcc-output",
        type=Path,
        default=DEFAULT_MCC_OUTPUT,
        help="Output path for mcc_codes_cleaned.csv"
    )

    parser.add_argument(
        "--fraud-output",
        type=Path,
        default=DEFAULT_FRAUD_OUTPUT,
        help="Output path for fraud_labels_cleaned.csv"
    )

    args = parser.parse_args()

    mcc_file = args.mcc.resolve()
    fraud_file = args.fraud.resolve()

    mcc_output = args.mcc_output.resolve()
    fraud_output = args.fraud_output.resolve()

    try:

        print("=" * 70)
        print("REFERENCE DATA CLEANING PIPELINE")
        print("=" * 70)
        print()

        validate_file_exists(
            mcc_file,
            "MCC source file"
        )

        validate_file_exists(
            fraud_file,
            "Fraud-label source file"
        )

        # ====================================================
        # MCC
        # ====================================================

        mcc_metrics = clean_mcc_codes(
            mcc_file,
            mcc_output
        )

        print_mcc_report(
            mcc_metrics,
            mcc_output
        )

        # ====================================================
        # FRAUD LABELS
        # ====================================================

        fraud_metrics = clean_fraud_labels(
            fraud_file,
            fraud_output
        )

        print_fraud_report(
            fraud_metrics,
            fraud_output
        )

        print()
        print("=" * 70)
        print("REFERENCE DATA CLEANING PIPELINE STATUS: PASS")
        print("=" * 70)

    except Exception as error:

        print()
        print("=" * 70)
        print("REFERENCE DATA CLEANING PIPELINE STATUS: FAIL")
        print("=" * 70)

        print(
            f"Error: {error}"
        )

        sys.exit(1)


if __name__ == "__main__":
    main()