from pathlib import Path
from datetime import datetime, timezone
import csv
import hashlib
import os
import shutil
import subprocess
import sys
import uuid


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

INTERIM_DIR = (
    PROJECT_ROOT
    / "data"
    / "interim"
)

PROCESSED_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
)

VALIDATION_SCRIPT = (
    PROJECT_ROOT
    / "src"
    / "validate_interim_data.py"
)

PROMOTION_LOG = (
    PROJECT_ROOT
    / "logs"
    / "processed_promotion_manifest.csv"
)


# ============================================================
# DATASET CONTRACT
# ============================================================

DATASETS = [
    {
        "dataset": "users",
        "source": "users_cleaned.csv",
        "target": "users.csv",
        "expected_rows": 2_000,
    },
    {
        "dataset": "cards",
        "source": "cards_cleaned.csv",
        "target": "cards.csv",
        "expected_rows": 6_146,
    },
    {
        "dataset": "transactions",
        "source": "transactions_cleaned.csv",
        "target": "transactions.csv",
        "expected_rows": 13_305_915,
    },
    {
        "dataset": "mcc_codes",
        "source": "mcc_codes_cleaned.csv",
        "target": "mcc_codes.csv",
        "expected_rows": 109,
    },
    {
        "dataset": "fraud_labels",
        "source": "fraud_labels_cleaned.csv",
        "target": "fraud_labels.csv",
        "expected_rows": 8_914_963,
    },
]


# ============================================================
# HELPERS
# ============================================================

def print_section(title):
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def sha256_file(
    path,
    chunk_size=8 * 1024 * 1024,
):
    """
    Calculate SHA-256 without loading the whole file into memory.
    """

    digest = hashlib.sha256()

    with open(path, "rb") as file:

        while True:

            chunk = file.read(chunk_size)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def count_csv_rows(path):
    """
    Count CSV data rows efficiently.

    This assumes the CSV files produced by our pipeline
    contain one physical line per record.
    """

    newline_count = 0
    last_byte = None

    with open(path, "rb") as file:

        while True:

            block = file.read(
                8 * 1024 * 1024
            )

            if not block:
                break

            newline_count += (
                block.count(b"\n")
            )

            last_byte = block[-1:]

    if last_byte is None:
        return 0

    physical_lines = newline_count

    if last_byte != b"\n":
        physical_lines += 1

    # Remove header.
    return max(
        physical_lines - 1,
        0
    )


def write_manifest(
    rows,
):
    PROMOTION_LOG.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    file_exists = (
        PROMOTION_LOG.exists()
    )

    fieldnames = [
        "run_id",
        "timestamp_utc",
        "dataset",
        "source_file",
        "processed_file",
        "expected_rows",
        "source_rows",
        "processed_rows",
        "source_size_bytes",
        "processed_size_bytes",
        "source_sha256",
        "processed_sha256",
        "status",
        "overall_status",
    ]

    with open(
        PROMOTION_LOG,
        "a",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames
        )

        if not file_exists:
            writer.writeheader()

        writer.writerows(
            rows
        )


# ============================================================
# PHASE 1
# RUN INDEPENDENT VALIDATION AGAIN
# ============================================================

def run_validation():
    print_section(
        "STEP 1: REVALIDATE INTERIM DATA"
    )

    if not VALIDATION_SCRIPT.exists():
        raise FileNotFoundError(
            f"Validation script not found: "
            f"{VALIDATION_SCRIPT}"
        )

    print(
        "Running Phase 8 validation immediately "
        "before promotion..."
    )

    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATION_SCRIPT),
        ],
        cwd=PROJECT_ROOT,
    )

    if result.returncode != 0:

        raise RuntimeError(
            "Interim validation failed. "
            "Processed promotion has been blocked."
        )

    print()
    print(
        "Interim validation passed."
    )


# ============================================================
# PHASE 2
# CHECK SOURCE FILES
# ============================================================

def validate_sources():
    print_section(
        "STEP 2: VERIFY INTERIM SOURCE FILES"
    )

    source_information = {}

    for item in DATASETS:

        source_path = (
            INTERIM_DIR
            / item["source"]
        )

        if not source_path.exists():

            raise FileNotFoundError(
                f"Missing validated interim file: "
                f"{source_path}"
            )

        source_rows = count_csv_rows(
            source_path
        )

        if (
            source_rows
            != item["expected_rows"]
        ):

            raise RuntimeError(
                f"{item['dataset']} row-count "
                f"reconciliation failed. "
                f"Expected "
                f"{item['expected_rows']:,}, "
                f"found {source_rows:,}."
            )

        source_hash = sha256_file(
            source_path
        )

        source_size = (
            source_path.stat().st_size
        )

        source_information[
            item["dataset"]
        ] = {
            "path": source_path,
            "rows": source_rows,
            "sha256": source_hash,
            "size": source_size,
        }

        print(
            f"{item['dataset']}: "
            f"{source_rows:,} rows "
            f"PASS"
        )

    return source_information


# ============================================================
# PHASE 3
# STAGE BYTE-FOR-BYTE COPIES
# ============================================================

def stage_files(
    source_information,
    run_id,
):
    print_section(
        "STEP 3: STAGE PROCESSED SNAPSHOT"
    )

    PROCESSED_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    staging_dir = (
        PROCESSED_DIR
        / f".promotion_{run_id}"
    )

    if staging_dir.exists():
        shutil.rmtree(
            staging_dir
        )

    staging_dir.mkdir(
        parents=True,
        exist_ok=False
    )

    staged_information = {}

    try:

        for item in DATASETS:

            dataset = item[
                "dataset"
            ]

            source = (
                source_information[
                    dataset
                ]["path"]
            )

            staged = (
                staging_dir
                / item["target"]
            )

            print(
                f"Copying {dataset}..."
            )

            shutil.copy2(
                source,
                staged
            )

            staged_hash = (
                sha256_file(
                    staged
                )
            )

            staged_rows = (
                count_csv_rows(
                    staged
                )
            )

            staged_size = (
                staged.stat().st_size
            )

            expected_hash = (
                source_information[
                    dataset
                ]["sha256"]
            )

            expected_rows = (
                source_information[
                    dataset
                ]["rows"]
            )

            expected_size = (
                source_information[
                    dataset
                ]["size"]
            )

            if (
                staged_hash
                != expected_hash
            ):
                raise RuntimeError(
                    f"{dataset} SHA-256 "
                    f"verification failed."
                )

            if (
                staged_rows
                != expected_rows
            ):
                raise RuntimeError(
                    f"{dataset} staged row "
                    f"count verification failed."
                )

            if (
                staged_size
                != expected_size
            ):
                raise RuntimeError(
                    f"{dataset} staged file-size "
                    f"verification failed."
                )

            staged_information[
                dataset
            ] = {
                "path": staged,
                "rows": staged_rows,
                "sha256": staged_hash,
                "size": staged_size,
            }

            print(
                f"{dataset}: staged PASS"
            )

        return (
            staging_dir,
            staged_information
        )

    except Exception:

        if staging_dir.exists():
            shutil.rmtree(
                staging_dir
            )

        raise


# ============================================================
# PHASE 4
# PUBLISH PROCESSED FILES
# ============================================================

def publish_files(
    staging_dir,
    source_information,
):
    print_section(
        "STEP 4: PUBLISH PROCESSED SNAPSHOT"
    )

    processed_information = {}

    for item in DATASETS:

        dataset = item[
            "dataset"
        ]

        staged_path = (
            staging_dir
            / item["target"]
        )

        final_path = (
            PROCESSED_DIR
            / item["target"]
        )

        os.replace(
            staged_path,
            final_path
        )

        final_hash = (
            sha256_file(
                final_path
            )
        )

        final_rows = (
            count_csv_rows(
                final_path
            )
        )

        final_size = (
            final_path.stat().st_size
        )

        expected_hash = (
            source_information[
                dataset
            ]["sha256"]
        )

        expected_rows = (
            source_information[
                dataset
            ]["rows"]
        )

        expected_size = (
            source_information[
                dataset
            ]["size"]
        )

        if final_hash != expected_hash:

            raise RuntimeError(
                f"{dataset} final SHA-256 "
                f"verification failed."
            )

        if final_rows != expected_rows:

            raise RuntimeError(
                f"{dataset} final row-count "
                f"verification failed."
            )

        if final_size != expected_size:

            raise RuntimeError(
                f"{dataset} final file-size "
                f"verification failed."
            )

        processed_information[
            dataset
        ] = {
            "path": final_path,
            "rows": final_rows,
            "sha256": final_hash,
            "size": final_size,
        }

        print(
            f"{dataset}: published PASS"
        )

    if staging_dir.exists():
        shutil.rmtree(
            staging_dir
        )

    return processed_information


# ============================================================
# PHASE 5
# WRITE AUDIT MANIFEST
# ============================================================

def create_manifest(
    run_id,
    source_information,
    processed_information,
):
    print_section(
        "STEP 5: WRITE PROMOTION MANIFEST"
    )

    timestamp = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    rows = []

    for item in DATASETS:

        dataset = item[
            "dataset"
        ]

        source = (
            source_information[
                dataset
            ]
        )

        processed = (
            processed_information[
                dataset
            ]
        )

        passed = (
            source["rows"]
            == processed["rows"]
            == item["expected_rows"]
            and
            source["sha256"]
            == processed["sha256"]
            and
            source["size"]
            == processed["size"]
        )

        rows.append(
            {
                "run_id": run_id,
                "timestamp_utc": timestamp,
                "dataset": dataset,
                "source_file":
                    str(source["path"]),
                "processed_file":
                    str(processed["path"]),
                "expected_rows":
                    item["expected_rows"],
                "source_rows":
                    source["rows"],
                "processed_rows":
                    processed["rows"],
                "source_size_bytes":
                    source["size"],
                "processed_size_bytes":
                    processed["size"],
                "source_sha256":
                    source["sha256"],
                "processed_sha256":
                    processed["sha256"],
                "status":
                    "PASS"
                    if passed
                    else "FAIL",
                "overall_status":
                    "PASS",
            }
        )

    write_manifest(
        rows
    )

    print(
        f"Manifest written to: "
        f"{PROMOTION_LOG}"
    )


# ============================================================
# FINAL REPORT
# ============================================================

def print_final_report(
    run_id,
    processed_information,
):
    print_section(
        "PROCESSED DATA PROMOTION COMPLETE"
    )

    for item in DATASETS:

        dataset = item[
            "dataset"
        ]

        info = (
            processed_information[
                dataset
            ]
        )

        print(
            f"{dataset:<15} "
            f"{info['rows']:>12,} rows  "
            f"PASS"
        )

    print()

    print(
        f"Promotion run ID: "
        f"{run_id}"
    )

    print()

    print(
        "PROCESSED PROMOTION STATUS: PASS"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    run_id = str(
        uuid.uuid4()
    )

    try:

        print("=" * 70)
        print(
            "VALIDATED INTERIM → PROCESSED PROMOTION"
        )
        print("=" * 70)

        print()
        print(
            "No cleaning, filtering or feature "
            "engineering will occur during promotion."
        )

        # ----------------------------------------------------
        # Re-run Phase 8 validation first
        # ----------------------------------------------------

        run_validation()

        # ----------------------------------------------------
        # Verify validated source files
        # ----------------------------------------------------

        source_information = (
            validate_sources()
        )

        # ----------------------------------------------------
        # Stage byte-identical copies
        # ----------------------------------------------------

        (
            staging_dir,
            staged_information,
        ) = stage_files(
            source_information,
            run_id
        )

        # staged_information is intentionally produced
        # as part of the verification process.
        _ = staged_information

        # ----------------------------------------------------
        # Publish
        # ----------------------------------------------------

        processed_information = (
            publish_files(
                staging_dir,
                source_information
            )
        )

        # ----------------------------------------------------
        # Audit
        # ----------------------------------------------------

        create_manifest(
            run_id,
            source_information,
            processed_information
        )

        print_final_report(
            run_id,
            processed_information
        )

    except Exception as error:

        print()
        print("=" * 70)
        print(
            "PROCESSED PROMOTION STATUS: FAIL"
        )
        print("=" * 70)

        print(
            f"Error: {error}"
        )

        sys.exit(1)


if __name__ == "__main__":
    main()