from pathlib import Path
from time import perf_counter
import argparse
import sys

import pandas as pd


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_TRANSACTIONS_FILE = (
    PROJECT_ROOT / "data" / "raw" / "transactions_data.csv"
)

DEFAULT_USERS_FILE = (
    PROJECT_ROOT / "data" / "interim" / "users_cleaned.csv"
)

DEFAULT_CARDS_FILE = (
    PROJECT_ROOT / "data" / "interim" / "cards_cleaned.csv"
)

INTERIM_DIR = PROJECT_ROOT / "data" / "interim"

DEFAULT_OUTPUT_FILE = (
    INTERIM_DIR / "transactions_cleaned.csv"
)


# ============================================================
# PIPELINE CONFIGURATION
# ============================================================

CHUNK_SIZE = 100_000

EXPECTED_TRANSACTION_ROWS = 13_305_915

EXPECTED_BEFORE_OPENING = 309
EXPECTED_AFTER_EXPIRY = 83
EXPECTED_CHANNEL_LOCATION_FLAGS = 5_788

EXPECTED_NEGATIVE_AMOUNTS = 660_049
EXPECTED_ZERO_AMOUNTS = 10_639


EXPECTED_TRANSACTION_COLUMNS = [
    "id",
    "date",
    "client_id",
    "card_id",
    "amount",
    "use_chip",
    "merchant_id",
    "merchant_city",
    "merchant_state",
    "zip",
    "mcc",
    "errors",
]


ALLOWED_TRANSACTION_METHODS = {
    "Chip Transaction",
    "Online Transaction",
    "Swipe Transaction",
}


OUTPUT_COLUMNS = [
    "transaction_id",
    "date",
    "client_id",
    "card_id",
    "amount",
    "use_chip",
    "merchant_id",
    "merchant_city",
    "merchant_state",
    "zip",
    "mcc",
    "errors",
    "transaction_before_card_open_flag",
    "transaction_after_card_expiry_flag",
    "channel_location_inconsistency_flag",
]


# ============================================================
# GENERAL VALIDATION
# ============================================================

def validate_file_exists(file_path, description):
    if not file_path.exists():
        raise FileNotFoundError(
            f"{description} not found: {file_path}"
        )


def validate_source_schema(file_path):
    """
    Read only the CSV header and validate expected structure
    before processing 13.3M records.
    """

    header = pd.read_csv(
        file_path,
        nrows=0
    )

    actual_columns = list(header.columns)

    missing = (
        set(EXPECTED_TRANSACTION_COLUMNS)
        - set(actual_columns)
    )

    unexpected = (
        set(actual_columns)
        - set(EXPECTED_TRANSACTION_COLUMNS)
    )

    problems = []

    if missing:
        problems.append(
            f"Missing columns: {sorted(missing)}"
        )

    if unexpected:
        problems.append(
            f"Unexpected columns: {sorted(unexpected)}"
        )

    if problems:
        raise ValueError(
            "Transaction schema validation failed. "
            + "; ".join(problems)
        )


# ============================================================
# REFERENCE DATA
# ============================================================

def load_reference_tables(users_file, cards_file):

    users = pd.read_csv(
        users_file,
        usecols=["client_id"]
    )

    cards = pd.read_csv(
        cards_file,
        dtype={
            "acct_open_date": "string",
            "expires": "string",
        }
    )

    # --------------------------------------------------------
    # Validate users
    # --------------------------------------------------------

    if users["client_id"].isna().any():
        raise ValueError(
            "users_cleaned contains missing client_id values."
        )

    if users["client_id"].duplicated().any():
        raise ValueError(
            "users_cleaned contains duplicate client_id values."
        )

    # --------------------------------------------------------
    # Validate cards
    # --------------------------------------------------------

    if cards["card_id"].isna().any():
        raise ValueError(
            "cards_cleaned contains missing card_id values."
        )

    if cards["card_id"].duplicated().any():
        raise ValueError(
            "cards_cleaned contains duplicate card_id values."
        )

    # --------------------------------------------------------
    # Explicitly parse month-level dates
    # --------------------------------------------------------

    cards["acct_open_parsed"] = pd.to_datetime(
        cards["acct_open_date"],
        format="%Y-%m",
        errors="coerce"
    )

    cards["expires_parsed"] = pd.to_datetime(
        cards["expires"],
        format="%Y-%m",
        errors="coerce"
    )

    invalid_open_dates = (
        cards["acct_open_parsed"].isna().sum()
    )

    invalid_expiry_dates = (
        cards["expires_parsed"].isna().sum()
    )

    if invalid_open_dates > 0:
        raise ValueError(
            f"{invalid_open_dates:,} cleaned card opening "
            f"dates could not be parsed."
        )

    if invalid_expiry_dates > 0:
        raise ValueError(
            f"{invalid_expiry_dates:,} cleaned card expiry "
            f"dates could not be parsed."
        )

    return users, cards


# ============================================================
# AMOUNT CLEANING
# ============================================================

def clean_amount(series):
    """
    Convert raw strings such as:

        $14.57
        $-77.00
        $0.00

    into numeric values.

    Negative and zero values are intentionally preserved.
    """

    original_missing = series.isna()

    cleaned = (
        series
        .astype("string")
        .str.strip()
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
    )

    numeric = pd.to_numeric(
        cleaned,
        errors="coerce"
    )

    newly_unparseable = (
        numeric.isna()
        & ~original_missing
    )

    return numeric, newly_unparseable


# ============================================================
# TRANSACTION CHUNK CLEANING
# ============================================================

def clean_transaction_chunk(
    chunk,
    user_ids,
    card_reference
):

    metrics = {
        "rows": len(chunk),
        "missing_transaction_ids": 0,
        "duplicate_transaction_ids": 0,
        "unparseable_dates": 0,
        "unparseable_amounts": 0,
        "unknown_client_ids": 0,
        "unknown_card_ids": 0,
        "ownership_mismatches": 0,
        "invalid_use_chip": 0,
        "negative_amounts": 0,
        "zero_amounts": 0,
        "before_opening": 0,
        "after_expiry": 0,
        "channel_location_flags": 0,
    }

    # ========================================================
    # IDENTIFIER VALIDATION
    # ========================================================

    metrics["missing_transaction_ids"] = (
        chunk["id"].isna().sum()
    )

    metrics["duplicate_transaction_ids"] = (
        chunk["id"].duplicated().sum()
    )

    if metrics["missing_transaction_ids"] > 0:
        raise ValueError(
            "Missing transaction IDs detected."
        )

    # Note:
    # chunk-level duplicates are checked here.
    # Global transaction-ID uniqueness was already validated
    # during Phase 6 across the complete source.

    # ========================================================
    # CUSTOMER VALIDATION
    # ========================================================

    metrics["unknown_client_ids"] = (
        ~chunk["client_id"].isin(user_ids)
    ).sum()

    if metrics["unknown_client_ids"] > 0:
        raise ValueError(
            f"{metrics['unknown_client_ids']:,} unknown "
            f"customer references detected."
        )

    # ========================================================
    # DATE CLEANING
    # ========================================================

    parsed_dates = pd.to_datetime(
        chunk["date"],
        format="%Y-%m-%d %H:%M:%S",
        errors="coerce"
    )

    metrics["unparseable_dates"] = (
        parsed_dates.isna().sum()
    )

    if metrics["unparseable_dates"] > 0:
        raise ValueError(
            f"{metrics['unparseable_dates']:,} transaction "
            f"dates could not be parsed."
        )

    chunk["date"] = parsed_dates

    # ========================================================
    # AMOUNT CLEANING
    # ========================================================

    amount_numeric, amount_errors = clean_amount(
        chunk["amount"]
    )

    metrics["unparseable_amounts"] = (
        amount_errors.sum()
    )

    if metrics["unparseable_amounts"] > 0:
        raise ValueError(
            f"{metrics['unparseable_amounts']:,} transaction "
            f"amounts could not be parsed."
        )

    chunk["amount"] = amount_numeric

    metrics["negative_amounts"] = (
        chunk["amount"] < 0
    ).sum()

    metrics["zero_amounts"] = (
        chunk["amount"] == 0
    ).sum()

    # ========================================================
    # CHANNEL VALIDITY
    # ========================================================

    invalid_channel = (
        chunk["use_chip"].isna()
        |
        ~chunk["use_chip"].isin(
            ALLOWED_TRANSACTION_METHODS
        )
    )

    metrics["invalid_use_chip"] = (
        invalid_channel.sum()
    )

    if metrics["invalid_use_chip"] > 0:
        raise ValueError(
            f"{metrics['invalid_use_chip']:,} invalid "
            f"use_chip values detected."
        )

    # ========================================================
    # MCC STANDARDISATION
    # ========================================================

    if chunk["mcc"].isna().any():
        raise ValueError(
            "Missing MCC values detected."
        )

    chunk["mcc"] = (
        chunk["mcc"]
        .astype("Int64")
        .astype("string")
        .str.zfill(4)
    )

    # ========================================================
    # ZIP REPRESENTATION
    # ========================================================

    # ZIP is a code rather than a measured number.
    # Reading the column as string preserves the supplied
    # representation and its nulls.
    #
    # No ZIP values are imputed.

    chunk["zip"] = chunk["zip"].astype("string")

    # ========================================================
    # JOIN CARD REFERENCE INFORMATION
    # ========================================================

    chunk = chunk.merge(
        card_reference,
        how="left",
        on="card_id",
        validate="many_to_one"
    )

    metrics["unknown_card_ids"] = (
        chunk["card_client_id"].isna().sum()
    )

    if metrics["unknown_card_ids"] > 0:
        raise ValueError(
            f"{metrics['unknown_card_ids']:,} unknown "
            f"card references detected."
        )

    # ========================================================
    # CARD OWNERSHIP VALIDATION
    # ========================================================

    ownership_mismatch = (
        chunk["client_id"]
        != chunk["card_client_id"]
    )

    metrics["ownership_mismatches"] = (
        ownership_mismatch.sum()
    )

    if metrics["ownership_mismatches"] > 0:
        raise ValueError(
            f"{metrics['ownership_mismatches']:,} "
            f"card/customer ownership mismatches detected."
        )

    # ========================================================
    # CARD LIFECYCLE QUALITY FLAGS
    # ========================================================

    transaction_month = (
        chunk["date"]
        .dt.to_period("M")
    )

    opening_month = (
        chunk["acct_open_parsed"]
        .dt.to_period("M")
    )

    expiry_month = (
        chunk["expires_parsed"]
        .dt.to_period("M")
    )

    before_opening = (
        transaction_month
        < opening_month
    )

    after_expiry = (
        transaction_month
        > expiry_month
    )

    chunk[
        "transaction_before_card_open_flag"
    ] = before_opening.astype("int8")

    chunk[
        "transaction_after_card_expiry_flag"
    ] = after_expiry.astype("int8")

    metrics["before_opening"] = (
        before_opening.sum()
    )

    metrics["after_expiry"] = (
        after_expiry.sum()
    )

    # ========================================================
    # CHANNEL / LOCATION SEMANTIC FLAG
    # ========================================================

    channel_location_inconsistency = (
        chunk["use_chip"].eq(
            "Chip Transaction"
        )
        &
        chunk["merchant_city"]
        .astype("string")
        .str.strip()
        .str.upper()
        .eq("ONLINE")
    )

    chunk[
        "channel_location_inconsistency_flag"
    ] = (
        channel_location_inconsistency
        .astype("int8")
    )

    metrics["channel_location_flags"] = (
        channel_location_inconsistency.sum()
    )

    # ========================================================
    # RENAME TRANSACTION IDENTIFIER
    # ========================================================

    chunk = chunk.rename(
        columns={
            "id": "transaction_id"
        }
    )

    # ========================================================
    # REMOVE TEMPORARY CARD JOIN FIELDS
    # ========================================================

    chunk = chunk.drop(
        columns=[
            "card_client_id",
            "acct_open_parsed",
            "expires_parsed",
        ]
    )

    # ========================================================
    # FINAL COLUMN ORDER
    # ========================================================

    chunk = chunk[
        OUTPUT_COLUMNS
    ]

    return chunk, metrics


# ============================================================
# ACCUMULATED METRICS
# ============================================================

def create_totals():

    return {
        "rows_read": 0,
        "rows_written": 0,
        "chunks_processed": 0,
        "missing_transaction_ids": 0,
        "duplicate_transaction_ids": 0,
        "unparseable_dates": 0,
        "unparseable_amounts": 0,
        "unknown_client_ids": 0,
        "unknown_card_ids": 0,
        "ownership_mismatches": 0,
        "invalid_use_chip": 0,
        "negative_amounts": 0,
        "zero_amounts": 0,
        "before_opening": 0,
        "after_expiry": 0,
        "channel_location_flags": 0,
    }


def update_totals(totals, metrics, rows_written):

    totals["rows_read"] += metrics["rows"]

    totals["rows_written"] += rows_written

    totals["chunks_processed"] += 1

    for key in [
        "missing_transaction_ids",
        "duplicate_transaction_ids",
        "unparseable_dates",
        "unparseable_amounts",
        "unknown_client_ids",
        "unknown_card_ids",
        "ownership_mismatches",
        "invalid_use_chip",
        "negative_amounts",
        "zero_amounts",
        "before_opening",
        "after_expiry",
        "channel_location_flags",
    ]:
        totals[key] += metrics[key]


# ============================================================
# FINAL VALIDATION
# ============================================================

def final_validation(totals):

    problems = []

    if totals["rows_read"] != EXPECTED_TRANSACTION_ROWS:
        problems.append(
            "Input row reconciliation failed: "
            f"expected {EXPECTED_TRANSACTION_ROWS:,}, "
            f"read {totals['rows_read']:,}"
        )

    if totals["rows_written"] != EXPECTED_TRANSACTION_ROWS:
        problems.append(
            "Output row reconciliation failed: "
            f"expected {EXPECTED_TRANSACTION_ROWS:,}, "
            f"wrote {totals['rows_written']:,}"
        )

    if totals["rows_read"] != totals["rows_written"]:
        problems.append(
            "Rows read and rows written do not match."
        )

    if totals["unparseable_dates"] != 0:
        problems.append(
            "Unparseable transaction dates detected."
        )

    if totals["unparseable_amounts"] != 0:
        problems.append(
            "Unparseable transaction amounts detected."
        )

    if totals["unknown_client_ids"] != 0:
        problems.append(
            "Unknown customer references detected."
        )

    if totals["unknown_card_ids"] != 0:
        problems.append(
            "Unknown card references detected."
        )

    if totals["ownership_mismatches"] != 0:
        problems.append(
            "Card/customer ownership mismatches detected."
        )

    if totals["invalid_use_chip"] != 0:
        problems.append(
            "Invalid transaction methods detected."
        )

    # --------------------------------------------------------
    # Reconcile known Phase 6 quality results
    # --------------------------------------------------------

    if totals["before_opening"] != EXPECTED_BEFORE_OPENING:
        problems.append(
            "Before-opening flag reconciliation failed: "
            f"expected {EXPECTED_BEFORE_OPENING:,}, "
            f"found {totals['before_opening']:,}"
        )

    if totals["after_expiry"] != EXPECTED_AFTER_EXPIRY:
        problems.append(
            "After-expiry flag reconciliation failed: "
            f"expected {EXPECTED_AFTER_EXPIRY:,}, "
            f"found {totals['after_expiry']:,}"
        )

    if (
        totals["channel_location_flags"]
        != EXPECTED_CHANNEL_LOCATION_FLAGS
    ):
        problems.append(
            "Channel/location flag reconciliation failed: "
            f"expected "
            f"{EXPECTED_CHANNEL_LOCATION_FLAGS:,}, "
            f"found "
            f"{totals['channel_location_flags']:,}"
        )

    if (
        totals["negative_amounts"]
        != EXPECTED_NEGATIVE_AMOUNTS
    ):
        problems.append(
            "Negative amount reconciliation failed: "
            f"expected {EXPECTED_NEGATIVE_AMOUNTS:,}, "
            f"found {totals['negative_amounts']:,}"
        )

    if totals["zero_amounts"] != EXPECTED_ZERO_AMOUNTS:
        problems.append(
            "Zero amount reconciliation failed: "
            f"expected {EXPECTED_ZERO_AMOUNTS:,}, "
            f"found {totals['zero_amounts']:,}"
        )

    if problems:
        raise ValueError(
            "\n".join(problems)
        )


# ============================================================
# MAIN CLEANING PIPELINE
# ============================================================

def clean_transactions(
    transactions_file,
    users_file,
    cards_file,
    output_file
):

    validate_file_exists(
        transactions_file,
        "Raw transaction file"
    )

    validate_file_exists(
        users_file,
        "Cleaned users file"
    )

    validate_file_exists(
        cards_file,
        "Cleaned cards file"
    )

    validate_source_schema(
        transactions_file
    )

    users, cards = load_reference_tables(
        users_file,
        cards_file
    )

    user_ids = set(
        users["client_id"].tolist()
    )

    card_reference = (
        cards[
            [
                "card_id",
                "client_id",
                "acct_open_parsed",
                "expires_parsed",
            ]
        ]
        .rename(
            columns={
                "client_id": "card_client_id"
            }
        )
    )

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # Prevent accidental append to a previous pipeline run.
    if output_file.exists():
        output_file.unlink()

    totals = create_totals()

    first_chunk = True

    start_time = perf_counter()

    # ========================================================
    # CHUNKED PROCESSING
    # ========================================================

    reader = pd.read_csv(
        transactions_file,
        chunksize=CHUNK_SIZE,
        dtype={
            "zip": "string",
        },
        on_bad_lines="error"
    )

    for chunk_number, chunk in enumerate(
        reader,
        start=1
    ):

        cleaned_chunk, metrics = (
            clean_transaction_chunk(
                chunk,
                user_ids,
                card_reference
            )
        )

        cleaned_chunk.to_csv(
            output_file,
            mode="w" if first_chunk else "a",
            header=first_chunk,
            index=False
        )

        first_chunk = False

        update_totals(
            totals,
            metrics,
            len(cleaned_chunk)
        )

        print(
            f"Processed chunk {chunk_number}: "
            f"{totals['rows_read']:,} rows read, "
            f"{totals['rows_written']:,} rows written"
        )

    elapsed = perf_counter() - start_time

    # ========================================================
    # FINAL RECONCILIATION
    # ========================================================

    final_validation(
        totals
    )

    return totals, elapsed


# ============================================================
# REPORTING
# ============================================================

def print_final_report(
    totals,
    output_file,
    elapsed
):

    print()
    print("=" * 70)
    print("TRANSACTIONS CLEANING VALIDATION")
    print("=" * 70)

    print()
    print("A. RECORD RECONCILIATION")
    print(
        f"Rows read: "
        f"{totals['rows_read']:,}"
    )
    print(
        f"Rows written: "
        f"{totals['rows_written']:,}"
    )
    print(
        f"Difference: "
        f"{totals['rows_read'] - totals['rows_written']:,}"
    )
    print(
        f"Chunks processed: "
        f"{totals['chunks_processed']:,}"
    )

    print()
    print("B. IDENTIFIER AND RELATIONSHIP VALIDATION")
    print(
        f"Missing transaction IDs: "
        f"{totals['missing_transaction_ids']:,}"
    )
    print(
        f"Unknown customer IDs: "
        f"{totals['unknown_client_ids']:,}"
    )
    print(
        f"Unknown card IDs: "
        f"{totals['unknown_card_ids']:,}"
    )
    print(
        f"Card/customer ownership mismatches: "
        f"{totals['ownership_mismatches']:,}"
    )

    print()
    print("C. TRANSFORMATION VALIDATION")
    print(
        f"Unparseable transaction dates: "
        f"{totals['unparseable_dates']:,}"
    )
    print(
        f"Unparseable transaction amounts: "
        f"{totals['unparseable_amounts']:,}"
    )
    print(
        f"Invalid use_chip values: "
        f"{totals['invalid_use_chip']:,}"
    )

    print()
    print("D. AMOUNT RECONCILIATION")
    print(
        f"Negative amounts: "
        f"{totals['negative_amounts']:,}"
    )
    print(
        f"Zero amounts: "
        f"{totals['zero_amounts']:,}"
    )

    print()
    print("E. DATA QUALITY FLAGS")
    print(
        f"Transactions before card opening: "
        f"{totals['before_opening']:,}"
    )
    print(
        f"Transactions after card expiry: "
        f"{totals['after_expiry']:,}"
    )
    print(
        f"Channel/location inconsistency flags: "
        f"{totals['channel_location_flags']:,}"
    )

    print()
    print("=" * 70)
    print("TRANSACTION CLEANING PIPELINE STATUS: PASS")
    print("=" * 70)

    print(
        f"Output file: {output_file}"
    )

    print(
        f"Processing time: {elapsed:.6f} seconds"
    )


# ============================================================
# COMMAND LINE ENTRY POINT
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Clean and standardize the transaction dataset "
            "using chunked processing."
        )
    )

    parser.add_argument(
        "--transactions",
        type=Path,
        default=DEFAULT_TRANSACTIONS_FILE,
        help="Path to transactions_data.csv"
    )

    parser.add_argument(
        "--users",
        type=Path,
        default=DEFAULT_USERS_FILE,
        help="Path to users_cleaned.csv"
    )

    parser.add_argument(
        "--cards",
        type=Path,
        default=DEFAULT_CARDS_FILE,
        help="Path to cards_cleaned.csv"
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_FILE,
        help="Output path for transactions_cleaned.csv"
    )

    args = parser.parse_args()

    try:

        print("=" * 70)
        print("TRANSACTIONS CLEANING PIPELINE")
        print("=" * 70)

        print()
        print(f"Chunk size: {CHUNK_SIZE:,}")
        print(
            f"Expected rows: "
            f"{EXPECTED_TRANSACTION_ROWS:,}"
        )
        print()

        totals, elapsed = clean_transactions(
            transactions_file=args.transactions.resolve(),
            users_file=args.users.resolve(),
            cards_file=args.cards.resolve(),
            output_file=args.output.resolve(),
        )

        print_final_report(
            totals,
            args.output.resolve(),
            elapsed
        )

    except Exception as error:

        print()
        print("=" * 70)
        print("TRANSACTION CLEANING PIPELINE STATUS: FAIL")
        print("=" * 70)

        print(
            f"Error: {error}"
        )

        sys.exit(1)


if __name__ == "__main__":
    main()