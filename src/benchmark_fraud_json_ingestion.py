from pathlib import Path
from time import perf_counter
import json
import tracemalloc


PROJECT_ROOT = Path(__file__).resolve().parents[1]

FRAUD_FILE = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "train_fraud_labels.json"
)


def main():

    if not FRAUD_FILE.exists():
        raise FileNotFoundError(
            f"Fraud label file not found: {FRAUD_FILE}"
        )

    # File size on disk
    file_size_bytes = FRAUD_FILE.stat().st_size
    file_size_mb = file_size_bytes / (1024 ** 2)

    print(f"File size: {file_size_mb:.6f} MB")

    # Begin measuring Python allocations
    tracemalloc.start()

    start_time = perf_counter()

    with open(FRAUD_FILE, "r", encoding="utf-8") as file:
        fraud_data = json.load(file)

    elapsed_seconds = perf_counter() - start_time

    current_memory_bytes, peak_memory_bytes = (
        tracemalloc.get_traced_memory()
    )

    tracemalloc.stop()

    current_memory_mb = current_memory_bytes / (1024 ** 2)
    peak_memory_mb = peak_memory_bytes / (1024 ** 2)

    # Structural checks
    top_level_keys = list(fraud_data.keys())

    if "target" not in fraud_data:
        raise KeyError(
            "Expected top-level key 'target' was not found."
        )

    if not isinstance(fraud_data["target"], dict):
        raise TypeError(
            "'target' exists but is not a dictionary."
        )

    fraud_labels = fraud_data["target"]
    label_count = len(fraud_labels)

    print(f"Top-level keys: {top_level_keys}")
    print(f"Number of top-level keys: {len(top_level_keys):,}")
    print(f"Number of labels inside target: {label_count:,}")
    print(f"Load time: {elapsed_seconds:.6f} seconds")
    print(
        f"Current traced memory after load: "
        f"{current_memory_mb:.6f} MB"
    )
    print(
        f"Peak traced memory during load: "
        f"{peak_memory_mb:.6f} MB"
    )

    if file_size_mb > 0:
        memory_to_file_ratio = peak_memory_mb / file_size_mb

        print(
            f"Peak-memory-to-file-size ratio: "
            f"{memory_to_file_ratio:.6f}x"
        )


if __name__ == "__main__":
    main()