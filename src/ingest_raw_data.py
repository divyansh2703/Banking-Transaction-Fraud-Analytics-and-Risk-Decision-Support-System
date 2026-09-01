from pathlib import Path
from datetime import datetime, timezone
from time import perf_counter
import csv
import json
import sys
import uuid

import ijson
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

RAW_DIR = PROJECT_ROOT / "data" / "raw"
CONFIG_FILE = PROJECT_ROOT / "config" / "source_contracts.json"
MANIFEST_FILE = PROJECT_ROOT / "logs" / "ingestion_manifest.csv"


MANIFEST_COLUMNS = [
    "run_id",
    "timestamp_utc",
    "source_file",
    "ingestion_method",
    "file_size_bytes",
    "records_read",
    "expected_records",
    "structure_detected",
    "chunk_size",
    "chunks_processed",
    "processing_seconds",
    "status",
    "overall_run_status",
    "error_message",
]


def load_contracts():
    with open(CONFIG_FILE, "r", encoding="utf-8") as file:
        config = json.load(file)

    return config["sources"]


def validate_columns(actual_columns, expected_columns):
    actual = set(actual_columns)
    expected = set(expected_columns)

    missing = expected - actual
    unexpected = actual - expected

    if missing or unexpected:
        messages = []

        if missing:
            messages.append(
                f"Missing columns: {sorted(missing)}"
            )

        if unexpected:
            messages.append(
                f"Unexpected columns: {sorted(unexpected)}"
            )

        raise ValueError("; ".join(messages))


def validate_record_count(actual, expected):
    if expected is None:
        return

    if actual != expected:
        raise ValueError(
            f"Record reconciliation failed. "
            f"Expected {expected:,}, read {actual:,}."
        )


def create_base_result(contract, file_path):
    return {
        "run_id": None,
        "timestamp_utc": None,
        "source_file": contract["file_name"],
        "ingestion_method": contract["method"],
        "file_size_bytes": (
            file_path.stat().st_size
            if file_path.exists()
            else None
        ),
        "records_read": None,
        "expected_records": contract.get("expected_records"),
        "structure_detected": None,
        "chunk_size": contract.get("chunk_size"),
        "chunks_processed": None,
        "processing_seconds": None,
        "status": "FAIL",
        "overall_run_status": None,
        "error_message": "",
    }


def ingest_csv_full(contract, file_path):
    start = perf_counter()

    df = pd.read_csv(
        file_path,
        on_bad_lines="error"
    )

    actual_columns = list(df.columns)

    validate_columns(
        actual_columns,
        contract["required_columns"]
    )

    records_read = len(df)

    validate_record_count(
        records_read,
        contract.get("expected_records")
    )

    elapsed = perf_counter() - start

    return {
        "records_read": records_read,
        "structure_detected": json.dumps(actual_columns),
        "chunks_processed": 1,
        "processing_seconds": elapsed,
    }


def ingest_csv_chunked(contract, file_path):
    start = perf_counter()

    header = pd.read_csv(
        file_path,
        nrows=0
    )

    actual_columns = list(header.columns)

    validate_columns(
        actual_columns,
        contract["required_columns"]
    )

    total_rows = 0
    chunk_count = 0

    for chunk in pd.read_csv(
        file_path,
        chunksize=contract["chunk_size"],
        on_bad_lines="error"
    ):
        total_rows += len(chunk)
        chunk_count += 1

    validate_record_count(
        total_rows,
        contract.get("expected_records")
    )

    elapsed = perf_counter() - start

    return {
        "records_read": total_rows,
        "structure_detected": json.dumps(actual_columns),
        "chunks_processed": chunk_count,
        "processing_seconds": elapsed,
    }


def ingest_json_mapping(contract, file_path):
    start = perf_counter()

    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise TypeError(
            "Expected JSON mapping but received another structure."
        )

    records_read = len(data)

    validate_record_count(
        records_read,
        contract.get("expected_records")
    )

    elapsed = perf_counter() - start

    return {
        "records_read": records_read,
        "structure_detected": "JSON key-value mapping",
        "chunks_processed": 1,
        "processing_seconds": elapsed,
    }


def ingest_json_stream(contract, file_path):
    start = perf_counter()

    prefix = contract["json_prefix"]

    records_read = 0

    with open(file_path, "rb") as file:
        for _, _ in ijson.kvitems(file, prefix):
            records_read += 1

    validate_record_count(
        records_read,
        contract.get("expected_records")
    )

    elapsed = perf_counter() - start

    return {
        "records_read": records_read,
        "structure_detected": (
            f"Streaming JSON mapping at '{prefix}'"
        ),
        "chunks_processed": None,
        "processing_seconds": elapsed,
    }


def process_source(contract):
    file_path = RAW_DIR / contract["file_name"]

    result = create_base_result(
        contract,
        file_path
    )

    try:
        if not file_path.exists():
            raise FileNotFoundError(
                f"Required source file not found: {file_path}"
            )

        method = contract["method"]

        if method == "csv_full":
            ingestion_result = ingest_csv_full(
                contract,
                file_path
            )

        elif method == "csv_chunked":
            ingestion_result = ingest_csv_chunked(
                contract,
                file_path
            )

        elif method == "json_mapping":
            ingestion_result = ingest_json_mapping(
                contract,
                file_path
            )

        elif method == "json_stream":
            ingestion_result = ingest_json_stream(
                contract,
                file_path
            )

        else:
            raise ValueError(
                f"Unknown ingestion method: {method}"
            )

        result.update(ingestion_result)
        result["status"] = "PASS"

    except Exception as error:
        result["error_message"] = str(error)

    return result


def write_manifest(results):
    MANIFEST_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    file_exists = MANIFEST_FILE.exists()

    with open(
        MANIFEST_FILE,
        "a",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=MANIFEST_COLUMNS
        )

        if not file_exists:
            writer.writeheader()

        writer.writerows(results)


def main():
    contracts = load_contracts()

    run_id = str(uuid.uuid4())

    timestamp = datetime.now(
        timezone.utc
    ).isoformat()

    results = []

    print(f"Run ID: {run_id}")
    print()

    for contract in contracts:
        print(
            f"Processing: "
            f"{contract['file_name']}"
        )

        result = process_source(contract)

        result["run_id"] = run_id
        result["timestamp_utc"] = timestamp

        results.append(result)

        print(
            f"Status: {result['status']}"
        )

        if result["records_read"] is not None:
            print(
                f"Records read: "
                f"{result['records_read']:,}"
            )

        if result["error_message"]:
            print(
                f"Error: "
                f"{result['error_message']}"
            )

        print()

    overall_status = (
        "PASS"
        if all(
            result["status"] == "PASS"
            for result in results
        )
        else "FAIL"
    )

    for result in results:
        result["overall_run_status"] = overall_status

        if result["processing_seconds"] is not None:
            result["processing_seconds"] = (
                f"{result['processing_seconds']:.6f}"
            )

    write_manifest(results)

    print(
        f"OVERALL INGESTION STATUS: "
        f"{overall_status}"
    )

    print(
        f"Manifest written to: "
        f"{MANIFEST_FILE}"
    )

    if overall_status == "FAIL":
        sys.exit(1)


if __name__ == "__main__":
    main()