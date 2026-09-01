from pathlib import Path
from time import perf_counter

import pandas as pd


# --------------------------------------------------
# Configuration
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]

TRANSACTION_FILE = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "transactions_data.csv"
)

EXPECTED_ROWS = 13_305_915

CHUNK_SIZES = [
    100_000,
    250_000,
    500_000,
    1_000_000,
]


# --------------------------------------------------
# Benchmark function
# --------------------------------------------------

def benchmark_chunk_size(file_path: Path, chunk_size: int) -> dict:
    start_time = perf_counter()

    total_rows = 0
    chunk_count = 0
    max_chunk_memory_bytes = 0

    for chunk in pd.read_csv(
        file_path,
        chunksize=chunk_size,
        on_bad_lines="error"
    ):
        chunk_count += 1

        rows_in_chunk = len(chunk)
        total_rows += rows_in_chunk

        chunk_memory_bytes = chunk.memory_usage(
            deep=True
        ).sum()

        if chunk_memory_bytes > max_chunk_memory_bytes:
            max_chunk_memory_bytes = chunk_memory_bytes

    elapsed_seconds = perf_counter() - start_time

    reconciliation_passed = total_rows == EXPECTED_ROWS

    max_chunk_memory_mb = (
        max_chunk_memory_bytes / (1024 ** 2)
    )

    return {
        "chunk_size": chunk_size,
        "chunks_processed": chunk_count,
        "rows_read": total_rows,
        "elapsed_seconds": elapsed_seconds,
        "max_chunk_memory_mb": max_chunk_memory_mb,
        "reconciliation_passed": reconciliation_passed,
    }


# --------------------------------------------------
# Run benchmarks
# --------------------------------------------------

def main():
    if not TRANSACTION_FILE.exists():
        raise FileNotFoundError(
            f"Transaction file not found: {TRANSACTION_FILE}"
        )

    results = []

    for chunk_size in CHUNK_SIZES:
        print(f"\nTesting chunk size: {chunk_size:,}")

        result = benchmark_chunk_size(
            TRANSACTION_FILE,
            chunk_size
        )

        results.append(result)

        print(
            f"Rows read: "
            f"{result['rows_read']:,}"
        )

        print(
            f"Chunks processed: "
            f"{result['chunks_processed']:,}"
        )

        print(
            f"Elapsed time: "
            f"{result['elapsed_seconds']:.6f} seconds"
        )

        print(
            f"Maximum chunk memory: "
            f"{result['max_chunk_memory_mb']:.6f} MB"
        )

        print(
            f"Reconciliation passed: "
            f"{result['reconciliation_passed']}"
        )

    results_df = pd.DataFrame(results)

    print("\nFINAL BENCHMARK RESULTS")
    print(results_df.to_string(index=False))


if __name__ == "__main__":
    main()