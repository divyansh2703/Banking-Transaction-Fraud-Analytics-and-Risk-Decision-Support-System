from pathlib import Path
from datetime import datetime, timezone
import hashlib
import time

import pandas as pd


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

RAW_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "transactions_data.csv"
)

INTERIM_PATH = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "transactions_cleaned.csv"
)

PROCESSED_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "transactions.csv"
)

PROMOTION_MANIFEST_PATH = (
    PROJECT_ROOT
    / "logs"
    / "processed_promotion_manifest.csv"
)

OUTPUT_REPORT_PATH = (
    PROJECT_ROOT
    / "logs"
    / "transaction_file_inspection.csv"
)


EXPECTED_ROWS = 13_305_915
EXPECTED_CUSTOMERS = 1_219
EXPECTED_CARDS = 4_071

EXPECTED_FIRST_DATE = pd.Timestamp(
    "2010-01-01 00:01:00"
)

EXPECTED_LAST_DATE = pd.Timestamp(
    "2019-10-31 23:59:00"
)

CHUNK_SIZE = 100_000


# ============================================================
# FILE DEFINITIONS
# ============================================================

FILES = {
    "raw": {
        "path": RAW_PATH,
        "id_column": "id",
    },
    "interim": {
        "path": INTERIM_PATH,
        "id_column": "transaction_id",
    },
    "processed": {
        "path": PROCESSED_PATH,
        "id_column": "transaction_id",
    },
}


# ============================================================
# HELPERS
# ============================================================

def print_section(title):
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def sha256_file(
    path,
    block_size=8 * 1024 * 1024
):
    """
    Calculate the SHA-256 hash of the complete file
    without loading the complete file into memory.
    """

    digest = hashlib.sha256()

    with open(path, "rb") as file:

        while True:

            block = file.read(block_size)

            if not block:
                break

            digest.update(block)

    return digest.hexdigest()


def format_bytes(size_bytes):
    return (
        f"{size_bytes:,} bytes "
        f"({size_bytes / (1024 ** 3):.4f} GiB)"
    )


def canonical_core_hash_update(
    digest,
    chunk,
    id_column
):
    """
    Build a content fingerprint based only on the
    transaction identity fields shared by raw,
    interim and processed datasets.

    This is intentionally different from the full-file
    SHA-256.

    It lets us test whether raw and cleaned files contain
    the same ordered transaction population even though
    their complete CSV bytes differ after cleaning.
    """

    core = chunk[
        [
            id_column,
            "date",
            "client_id",
            "card_id",
        ]
    ].copy()

    core = core.rename(
        columns={
            id_column: "transaction_id"
        }
    )

    # Normalize ID representations.
    for column in [
        "transaction_id",
        "client_id",
        "card_id",
    ]:
        core[column] = (
            pd.to_numeric(
                core[column],
                errors="raise"
            )
            .astype("int64")
            .astype(str)
        )

    # Normalize dates to one representation.
    core["date"] = (
        pd.to_datetime(
            core["date"],
            format="%Y-%m-%d %H:%M:%S",
            errors="raise"
        )
        .dt.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )

    lines = (
        core[
            [
                "transaction_id",
                "date",
                "client_id",
                "card_id",
            ]
        ]
        .astype(str)
        .agg("|".join, axis=1)
    )

    payload = (
        "\n".join(lines)
        + "\n"
    ).encode("utf-8")

    digest.update(payload)


# ============================================================
# INSPECT ONE TRANSACTION FILE
# ============================================================

def inspect_transaction_file(
    label,
    path,
    id_column
):
    print_section(
        f"INSPECTING {label.upper()} TRANSACTION FILE"
    )

    if not path.exists():

        print(
            f"FILE NOT FOUND: {path}"
        )

        return {
            "layer": label,
            "path": str(path),
            "exists": False,
            "status": "FAIL",
        }

    print(
        f"Path: {path}"
    )

    size_bytes = (
        path.stat().st_size
    )

    print(
        f"File size: "
        f"{format_bytes(size_bytes)}"
    )

    print()
    print(
        "Calculating full-file SHA-256..."
    )

    full_sha256 = sha256_file(
        path
    )

    print(
        f"SHA-256: {full_sha256}"
    )


    # --------------------------------------------------------
    # Read header only
    # --------------------------------------------------------

    header = pd.read_csv(
        path,
        nrows=0
    )

    columns = list(
        header.columns
    )

    print()
    print(
        f"Columns ({len(columns)}):"
    )

    for column in columns:
        print(
            f"  {column}"
        )


    required_columns = {
        id_column,
        "date",
        "client_id",
        "card_id",
    }

    missing_required = (
        required_columns
        - set(columns)
    )

    if missing_required:

        raise ValueError(
            f"{label}: missing required columns: "
            f"{sorted(missing_required)}"
        )


    # --------------------------------------------------------
    # Stream through the file
    # --------------------------------------------------------

    total_rows = 0

    min_date = None
    max_date = None

    min_transaction_id = None
    max_transaction_id = None

    unique_customers = set()
    unique_cards = set()

    canonical_digest = (
        hashlib.sha256()
    )

    first_transaction_id = None
    first_transaction_date = None

    last_transaction_id = None
    last_transaction_date = None

    start_time = time.perf_counter()


    reader = pd.read_csv(
        path,
        usecols=[
            id_column,
            "date",
            "client_id",
            "card_id",
        ],
        dtype={
            id_column: "string",
            "client_id": "string",
            "card_id": "string",
            "date": "string",
        },
        chunksize=CHUNK_SIZE
    )


    for chunk_number, chunk in enumerate(
        reader,
        start=1
    ):

        row_count = len(chunk)

        total_rows += row_count


        # ----------------------------------------------------
        # Parse dates
        # ----------------------------------------------------

        parsed_dates = pd.to_datetime(
            chunk["date"],
            format="%Y-%m-%d %H:%M:%S",
            errors="raise"
        )


        chunk_min_date = (
            parsed_dates.min()
        )

        chunk_max_date = (
            parsed_dates.max()
        )


        if min_date is None:
            min_date = chunk_min_date
        else:
            min_date = min(
                min_date,
                chunk_min_date
            )


        if max_date is None:
            max_date = chunk_max_date
        else:
            max_date = max(
                max_date,
                chunk_max_date
            )


        # ----------------------------------------------------
        # Transaction ID range
        # ----------------------------------------------------

        ids_numeric = pd.to_numeric(
            chunk[id_column],
            errors="raise"
        ).astype("int64")


        chunk_min_id = (
            ids_numeric.min()
        )

        chunk_max_id = (
            ids_numeric.max()
        )


        if min_transaction_id is None:

            min_transaction_id = int(
                chunk_min_id
            )

        else:

            min_transaction_id = min(
                min_transaction_id,
                int(chunk_min_id)
            )


        if max_transaction_id is None:

            max_transaction_id = int(
                chunk_max_id
            )

        else:

            max_transaction_id = max(
                max_transaction_id,
                int(chunk_max_id)
            )


        # ----------------------------------------------------
        # First and last physical rows
        # ----------------------------------------------------

        if first_transaction_id is None:

            first_transaction_id = (
                str(
                    chunk.iloc[0][
                        id_column
                    ]
                )
            )

            first_transaction_date = (
                str(
                    chunk.iloc[0][
                        "date"
                    ]
                )
            )


        last_transaction_id = (
            str(
                chunk.iloc[-1][
                    id_column
                ]
            )
        )

        last_transaction_date = (
            str(
                chunk.iloc[-1][
                    "date"
                ]
            )
        )


        # ----------------------------------------------------
        # Customers and cards
        # ----------------------------------------------------

        unique_customers.update(
            pd.to_numeric(
                chunk["client_id"],
                errors="raise"
            )
            .astype("int64")
            .tolist()
        )

        unique_cards.update(
            pd.to_numeric(
                chunk["card_id"],
                errors="raise"
            )
            .astype("int64")
            .tolist()
        )


        # ----------------------------------------------------
        # Canonical core transaction fingerprint
        # ----------------------------------------------------

        canonical_core_hash_update(
            canonical_digest,
            chunk,
            id_column
        )


        if (
            chunk_number % 20 == 0
            or row_count < CHUNK_SIZE
        ):

            print(
                f"Processed "
                f"{total_rows:,} rows"
            )


    elapsed_seconds = (
        time.perf_counter()
        - start_time
    )

    canonical_hash = (
        canonical_digest.hexdigest()
    )


    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------

    row_count_match = (
        total_rows
        == EXPECTED_ROWS
    )

    customer_count_match = (
        len(unique_customers)
        == EXPECTED_CUSTOMERS
    )

    card_count_match = (
        len(unique_cards)
        == EXPECTED_CARDS
    )

    first_date_match = (
        min_date
        == EXPECTED_FIRST_DATE
    )

    last_date_match = (
        max_date
        == EXPECTED_LAST_DATE
    )


    all_population_checks_pass = all(
        [
            row_count_match,
            customer_count_match,
            card_count_match,
            first_date_match,
            last_date_match,
        ]
    )


    # --------------------------------------------------------
    # Output
    # --------------------------------------------------------

    print()
    print(
        f"Rows: "
        f"{total_rows:,}"
    )

    print(
        f"Unique customers: "
        f"{len(unique_customers):,}"
    )

    print(
        f"Unique cards: "
        f"{len(unique_cards):,}"
    )

    print(
        f"Minimum transaction ID: "
        f"{min_transaction_id}"
    )

    print(
        f"Maximum transaction ID: "
        f"{max_transaction_id}"
    )

    print(
        f"Minimum transaction date: "
        f"{min_date}"
    )

    print(
        f"Maximum transaction date: "
        f"{max_date}"
    )

    print()
    print(
        f"First physical row: "
        f"{first_transaction_id} | "
        f"{first_transaction_date}"
    )

    print(
        f"Last physical row: "
        f"{last_transaction_id} | "
        f"{last_transaction_date}"
    )

    print()
    print(
        "Canonical transaction-core SHA-256:"
    )

    print(
        canonical_hash
    )

    print()
    print(
        f"Inspection time: "
        f"{elapsed_seconds:.2f} seconds"
    )

    print()
    print(
        "Population checks:"
    )

    print(
        f"  Expected rows: "
        f"{row_count_match}"
    )

    print(
        f"  Expected customers: "
        f"{customer_count_match}"
    )

    print(
        f"  Expected cards: "
        f"{card_count_match}"
    )

    print(
        f"  Expected first date: "
        f"{first_date_match}"
    )

    print(
        f"  Expected last date: "
        f"{last_date_match}"
    )

    print(
        f"  Overall population check: "
        f"{'PASS' if all_population_checks_pass else 'FAIL'}"
    )


    return {
        "layer": label,
        "path": str(path),
        "exists": True,
        "file_size_bytes": size_bytes,
        "full_file_sha256": full_sha256,
        "canonical_core_sha256": canonical_hash,
        "row_count": total_rows,
        "unique_customers": len(
            unique_customers
        ),
        "unique_cards": len(
            unique_cards
        ),
        "min_transaction_id":
            min_transaction_id,
        "max_transaction_id":
            max_transaction_id,
        "min_date":
            str(min_date),
        "max_date":
            str(max_date),
        "first_physical_transaction_id":
            first_transaction_id,
        "first_physical_transaction_date":
            first_transaction_date,
        "last_physical_transaction_id":
            last_transaction_id,
        "last_physical_transaction_date":
            last_transaction_date,
        "row_count_match":
            row_count_match,
        "customer_count_match":
            customer_count_match,
        "card_count_match":
            card_count_match,
        "first_date_match":
            first_date_match,
        "last_date_match":
            last_date_match,
        "population_status":
            (
                "PASS"
                if all_population_checks_pass
                else "FAIL"
            ),
    }


# ============================================================
# READ THE PROMOTION MANIFEST
# ============================================================

def inspect_manifest():
    print_section(
        "PROMOTION MANIFEST CHECK"
    )

    if not PROMOTION_MANIFEST_PATH.exists():

        print(
            "Promotion manifest does not exist."
        )

        return None


    manifest = pd.read_csv(
        PROMOTION_MANIFEST_PATH
    )


    transaction_rows = manifest[
        manifest["dataset"]
        == "transactions"
    ].copy()


    if transaction_rows.empty:

        print(
            "No transaction promotion record "
            "was found in the manifest."
        )

        return None


    # Latest transaction promotion entry.
    latest = (
        transaction_rows.iloc[-1]
    )


    print(
        f"Promotion run ID: "
        f"{latest['run_id']}"
    )

    print(
        f"Expected rows: "
        f"{int(latest['expected_rows']):,}"
    )

    print(
        f"Source rows: "
        f"{int(latest['source_rows']):,}"
    )

    print(
        f"Processed rows: "
        f"{int(latest['processed_rows']):,}"
    )

    print(
        "Manifest source SHA-256:"
    )

    print(
        latest["source_sha256"]
    )

    print(
        "Manifest processed SHA-256:"
    )

    print(
        latest["processed_sha256"]
    )

    print(
        f"Manifest status: "
        f"{latest['status']}"
    )

    print(
        f"Manifest overall status: "
        f"{latest['overall_status']}"
    )


    return {
        "run_id":
            latest["run_id"],
        "expected_rows":
            int(
                latest["expected_rows"]
            ),
        "source_rows":
            int(
                latest["source_rows"]
            ),
        "processed_rows":
            int(
                latest["processed_rows"]
            ),
        "source_sha256":
            latest["source_sha256"],
        "processed_sha256":
            latest[
                "processed_sha256"
            ],
        "status":
            latest["status"],
        "overall_status":
            latest[
                "overall_status"
            ],
    }


# ============================================================
# COMPARE ALL THREE FILES
# ============================================================

def compare_results(
    results,
    manifest_info
):
    print_section(
        "CROSS-LAYER COMPARISON"
    )

    result_map = {
        result["layer"]: result
        for result in results
        if result.get(
            "exists",
            False
        )
    }


    required_layers = {
        "raw",
        "interim",
        "processed",
    }


    if (
        set(result_map.keys())
        != required_layers
    ):

        print(
            "FAIL: One or more transaction files "
            "are missing."
        )

        return False


    raw = result_map["raw"]
    interim = result_map["interim"]
    processed = result_map["processed"]


    # --------------------------------------------------------
    # Raw → Interim
    # --------------------------------------------------------

    print(
        "RAW → INTERIM"
    )

    raw_interim_rows_match = (
        raw["row_count"]
        == interim["row_count"]
    )

    raw_interim_core_match = (
        raw["canonical_core_sha256"]
        == interim[
            "canonical_core_sha256"
        ]
    )

    print(
        f"  Row counts equal: "
        f"{raw_interim_rows_match}"
    )

    print(
        f"  Canonical core population equal: "
        f"{raw_interim_core_match}"
    )


    # --------------------------------------------------------
    # Interim → Processed
    # --------------------------------------------------------

    print()
    print(
        "INTERIM → PROCESSED"
    )

    interim_processed_rows_match = (
        interim["row_count"]
        == processed["row_count"]
    )

    interim_processed_file_hash_match = (
        interim["full_file_sha256"]
        == processed[
            "full_file_sha256"
        ]
    )

    interim_processed_core_match = (
        interim["canonical_core_sha256"]
        == processed[
            "canonical_core_sha256"
        ]
    )


    print(
        f"  Row counts equal: "
        f"{interim_processed_rows_match}"
    )

    print(
        f"  Full-file SHA-256 equal: "
        f"{interim_processed_file_hash_match}"
    )

    print(
        f"  Canonical core population equal: "
        f"{interim_processed_core_match}"
    )


    # --------------------------------------------------------
    # Manifest → Processed
    # --------------------------------------------------------

    manifest_match = None

    if manifest_info is not None:

        print()
        print(
            "PROMOTION MANIFEST → PROCESSED"
        )

        manifest_match = (
            processed[
                "full_file_sha256"
            ]
            == manifest_info[
                "processed_sha256"
            ]
        )

        print(
            f"  Processed hash matches manifest: "
            f"{manifest_match}"
        )


    # --------------------------------------------------------
    # Final result
    # --------------------------------------------------------

    all_population_pass = all(
        result[
            "population_status"
        ] == "PASS"
        for result in results
        if result.get(
            "exists",
            False
        )
    )


    final_pass = all(
        [
            all_population_pass,
            raw_interim_rows_match,
            raw_interim_core_match,
            interim_processed_rows_match,
            interim_processed_file_hash_match,
            interim_processed_core_match,
            (
                manifest_match
                if manifest_match is not None
                else True
            ),
        ]
    )


    print()
    print("=" * 80)

    if final_pass:

        print(
            "LOCAL TRANSACTION PIPELINE STATUS: PASS"
        )

        print()
        print(
            "Raw transaction population is preserved "
            "in interim."
        )

        print(
            "Processed transactions are an exact "
            "byte-for-byte copy of validated interim."
        )

        if manifest_info is not None:

            print(
                "Processed transactions also match "
                "the promotion manifest."
            )

    else:

        print(
            "LOCAL TRANSACTION PIPELINE STATUS: FAIL"
        )

        print()
        print(
            "Do not continue EDA until the failing "
            "comparison is investigated."
        )

    print("=" * 80)


    return final_pass


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 80)
    print(
        "TRANSACTION FILE INTEGRITY INSPECTION"
    )
    print("=" * 80)

    print(
        f"Run timestamp UTC: "
        f"{datetime.now(timezone.utc).isoformat()}"
    )

    print()
    print(
        "This script is READ ONLY."
    )

    print(
        "It will not modify raw, interim or "
        "processed transaction data."
    )


    results = []


    for label, config in FILES.items():

        result = inspect_transaction_file(
            label=label,
            path=config["path"],
            id_column=config[
                "id_column"
            ],
        )

        results.append(
            result
        )


    # --------------------------------------------------------
    # Save inspection report
    # --------------------------------------------------------

    report = pd.DataFrame(
        results
    )

    OUTPUT_REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    report.to_csv(
        OUTPUT_REPORT_PATH,
        index=False
    )


    print_section(
        "INSPECTION REPORT SAVED"
    )

    print(
        OUTPUT_REPORT_PATH
    )


    # --------------------------------------------------------
    # Promotion manifest
    # --------------------------------------------------------

    manifest_info = (
        inspect_manifest()
    )


    # --------------------------------------------------------
    # Cross-layer comparison
    # --------------------------------------------------------

    final_pass = compare_results(
        results,
        manifest_info
    )


    # --------------------------------------------------------
    # Compact final table
    # --------------------------------------------------------

    print_section(
        "FINAL FILE SUMMARY"
    )

    display_columns = [
        "layer",
        "exists",
        "file_size_bytes",
        "row_count",
        "unique_customers",
        "unique_cards",
        "min_date",
        "max_date",
        "population_status",
    ]

    available_columns = [
        column
        for column
        in display_columns
        if column in report.columns
    ]

    print(
        report[
            available_columns
        ].to_string(
            index=False
        )
    )


    print()

    if final_pass:

        print(
            "SAFE LOCAL BASELINE: YES"
        )

    else:

        print(
            "SAFE LOCAL BASELINE: NO"
        )


if __name__ == "__main__":
    main()