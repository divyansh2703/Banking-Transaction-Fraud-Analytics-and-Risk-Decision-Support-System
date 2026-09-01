from pathlib import Path
from time import perf_counter
import tracemalloc

import ijson


PROJECT_ROOT = Path(__file__).resolve().parents[1]

FRAUD_FILE = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "train_fraud_labels.json"
)

EXPECTED_LABELS = 8_914_963


def main():

    if not FRAUD_FILE.exists():
        raise FileNotFoundError(
            f"Fraud label file not found: {FRAUD_FILE}"
        )

    file_size_bytes = FRAUD_FILE.stat().st_size
    file_size_mb = file_size_bytes / (1024 ** 2)

    print(f"File size: {file_size_mb:.6f} MB")

    tracemalloc.start()

    start_time = perf_counter()

    label_count = 0
    yes_count = 0
    no_count = 0
    unexpected_labels = 0

    with open(FRAUD_FILE, "rb") as file:

        for transaction_id, label in ijson.kvitems(
            file,
            "target"
        ):

            label_count += 1

            if label == "Yes":
                yes_count += 1

            elif label == "No":
                no_count += 1

            else:
                unexpected_labels += 1

    elapsed_seconds = perf_counter() - start_time

    current_memory_bytes, peak_memory_bytes = (
        tracemalloc.get_traced_memory()
    )

    tracemalloc.stop()

    current_memory_mb = current_memory_bytes / (1024 ** 2)
    peak_memory_mb = peak_memory_bytes / (1024 ** 2)

    reconciliation_passed = (
        label_count == EXPECTED_LABELS
    )

    print(f"Labels processed: {label_count:,}")
    print(f"Yes labels: {yes_count:,}")
    print(f"No labels: {no_count:,}")
    print(f"Unexpected labels: {unexpected_labels:,}")

    print(
        f"Reconciliation passed: "
        f"{reconciliation_passed}"
    )

    print(
        f"Elapsed time: "
        f"{elapsed_seconds:.6f} seconds"
    )

    print(
        f"Current traced memory: "
        f"{current_memory_mb:.6f} MB"
    )

    print(
        f"Peak traced memory: "
        f"{peak_memory_mb:.6f} MB"
    )

    if file_size_mb > 0:

        memory_to_file_ratio = (
            peak_memory_mb / file_size_mb
        )

        print(
            f"Peak-memory-to-file-size ratio: "
            f"{memory_to_file_ratio:.6f}x"
        )


if __name__ == "__main__":
    main()