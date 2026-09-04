from pathlib import Path
from collections import defaultdict
import time

import numpy as np
import pandas as pd


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

TRANSACTIONS_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "transactions.csv"
)

FRAUD_LABELS_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "fraud_labels.csv"
)

MCC_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "mcc_codes.csv"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "reports"
    / "eda"
    / "phase_10_10_fraud"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# CERTIFIED EXPECTATIONS
# ============================================================

EXPECTED_TRANSACTIONS = 13_305_915
EXPECTED_LABELS = 8_914_963
EXPECTED_FRAUD_YES = 13_332
EXPECTED_FRAUD_NO = 8_901_631

CHUNK_SIZE = 250_000


# ============================================================
# HELPERS
# ============================================================

def print_section(title):
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def save_table(
    dataframe,
    filename
):
    path = (
        OUTPUT_DIR
        / filename
    )

    dataframe.to_csv(
        path,
        index=False
    )

    print(
        f"Saved: {path}"
    )


# ============================================================
# STEP 1
# VALIDATE INPUT FILES
# ============================================================

print_section(
    "PHASE 10.10: FRAUD-LABELLED TRANSACTION EDA"
)

for path in [
    TRANSACTIONS_PATH,
    FRAUD_LABELS_PATH,
    MCC_PATH,
]:

    if not path.exists():

        raise FileNotFoundError(
            f"Required file not found: {path}"
        )

    print(
        f"Found: {path}"
    )


# ============================================================
# STEP 2
# LOAD FRAUD LABEL LOOKUP
# ============================================================

print_section(
    "STEP 1: LOAD CERTIFIED FRAUD LABELS"
)

start_time = time.perf_counter()

fraud_labels = pd.read_csv(
    FRAUD_LABELS_PATH,
    dtype={
        "transaction_id": "int64",
        "fraud_label": "category",
    }
)


if len(fraud_labels) != EXPECTED_LABELS:

    raise RuntimeError(
        f"Fraud label population mismatch. "
        f"Expected {EXPECTED_LABELS:,}, "
        f"found {len(fraud_labels):,}."
    )


if not fraud_labels[
    "transaction_id"
].is_unique:

    raise RuntimeError(
        "Fraud label transaction IDs "
        "are not unique."
    )


fraud_counts = (
    fraud_labels[
        "fraud_label"
    ]
    .value_counts()
)


actual_yes = int(
    fraud_counts.get(
        "Yes",
        0
    )
)

actual_no = int(
    fraud_counts.get(
        "No",
        0
    )
)


if actual_yes != EXPECTED_FRAUD_YES:

    raise RuntimeError(
        f"Expected {EXPECTED_FRAUD_YES:,} "
        f"Yes labels, found {actual_yes:,}."
    )


if actual_no != EXPECTED_FRAUD_NO:

    raise RuntimeError(
        f"Expected {EXPECTED_FRAUD_NO:,} "
        f"No labels, found {actual_no:,}."
    )


# ------------------------------------------------------------
# Build memory-efficient lookup
# ------------------------------------------------------------

label_lookup = (
    fraud_labels
    .set_index(
        "transaction_id"
    )[
        "fraud_label"
    ]
)


print(
    f"Fraud labels: "
    f"{len(fraud_labels):,}"
)

print(
    f"Yes: "
    f"{actual_yes:,}"
)

print(
    f"No: "
    f"{actual_no:,}"
)

print(
    f"Label load time: "
    f"{time.perf_counter() - start_time:.2f} seconds"
)


# ============================================================
# STEP 3
# LOAD MCC REFERENCE
# ============================================================

print_section(
    "STEP 2: LOAD MCC REFERENCE"
)

mcc_reference = pd.read_csv(
    MCC_PATH,
    dtype={
        "mcc": "string"
    }
)

mcc_reference[
    "mcc"
] = (
    mcc_reference[
        "mcc"
    ]
    .str.zfill(4)
)


if len(mcc_reference) != 109:

    raise RuntimeError(
        f"Expected 109 MCC rows, "
        f"found {len(mcc_reference):,}."
    )


if not mcc_reference[
    "mcc"
].is_unique:

    raise RuntimeError(
        "MCC reference contains "
        "duplicate MCC values."
    )


print(
    "MCC reference: 109 rows PASS"
)


# ============================================================
# STEP 4
# INITIALISE AGGREGATORS
# ============================================================

print_section(
    "STEP 3: STREAM TRANSACTIONS"
)


# ------------------------------------------------------------
# Amount arrays
#
# We keep only the numeric amount values for the labelled
# transactions so exact median / quantiles can be calculated.
# We do NOT retain the full merged transaction table.
# ------------------------------------------------------------

amount_parts = {
    "Yes": [],
    "No": [],
}


# ------------------------------------------------------------
# Fraud prevalence
# ------------------------------------------------------------

prevalence_counts = {
    "Yes": 0,
    "No": 0,
}


# ------------------------------------------------------------
# Channel
# ------------------------------------------------------------

channel_stats = defaultdict(
    lambda: {
        "labelled_transactions": 0,
        "fraud_transactions": 0,
    }
)


# ------------------------------------------------------------
# MCC
# ------------------------------------------------------------

mcc_stats = defaultdict(
    lambda: {
        "labelled_transactions": 0,
        "fraud_transactions": 0,
    }
)


# ------------------------------------------------------------
# Error presence
# ------------------------------------------------------------

error_stats = {
    "Yes": {
        "labelled_transactions": 0,
        "transactions_with_error": 0,
    },
    "No": {
        "labelled_transactions": 0,
        "transactions_with_error": 0,
    },
}


# ------------------------------------------------------------
# Reconciliation
# ------------------------------------------------------------

transaction_rows_scanned = 0
labelled_rows_matched = 0

stream_start = time.perf_counter()


# ============================================================
# STEP 5
# STREAM THROUGH CERTIFIED TRANSACTION FILE
# ============================================================

reader = pd.read_csv(
    TRANSACTIONS_PATH,
    usecols=[
        "transaction_id",
        "amount",
        "use_chip",
        "mcc",
        "errors",
    ],
    dtype={
        "transaction_id": "int64",
        "amount": "float64",
        "use_chip": "string",
        "mcc": "string",
        "errors": "string",
    },
    chunksize=CHUNK_SIZE
)


for chunk_number, chunk in enumerate(
    reader,
    start=1
):

    transaction_rows_scanned += len(
        chunk
    )


    # --------------------------------------------------------
    # Attach fraud label using certified lookup
    # --------------------------------------------------------

    chunk[
        "fraud_label"
    ] = (
        chunk[
            "transaction_id"
        ]
        .map(
            label_lookup
        )
    )


    # --------------------------------------------------------
    # Keep only transactions that actually have labels
    # --------------------------------------------------------

    labelled = chunk[
        chunk[
            "fraud_label"
        ].notna()
    ].copy()


    if labelled.empty:

        continue


    labelled[
        "fraud_label"
    ] = (
        labelled[
            "fraud_label"
        ]
        .astype(str)
    )


    labelled[
        "mcc"
    ] = (
        labelled[
            "mcc"
        ]
        .str.zfill(4)
    )


    labelled[
        "error_present"
    ] = (
        labelled[
            "errors"
        ].notna()
    )


    labelled_rows_matched += len(
        labelled
    )


    # ========================================================
    # A. FRAUD PREVALENCE
    # ========================================================

    chunk_label_counts = (
        labelled[
            "fraud_label"
        ]
        .value_counts()
    )


    for label in [
        "Yes",
        "No",
    ]:

        prevalence_counts[
            label
        ] += int(
            chunk_label_counts.get(
                label,
                0
            )
        )


    # ========================================================
    # B. STORE AMOUNTS FOR EXACT QUANTILES
    # ========================================================

    for label in [
        "Yes",
        "No",
    ]:

        values = (
            labelled.loc[
                labelled[
                    "fraud_label"
                ] == label,
                "amount"
            ]
            .to_numpy(
                dtype=np.float64,
                copy=True
            )
        )

        if len(values) > 0:

            amount_parts[
                label
            ].append(
                values
            )


    # ========================================================
    # C. CHANNEL AGGREGATION
    # ========================================================

    channel_grouped = (
        labelled
        .groupby(
            "use_chip",
            observed=True
        )
        .agg(
            labelled_transactions=(
                "transaction_id",
                "size"
            ),

            fraud_transactions=(
                "fraud_label",
                lambda x:
                    (x == "Yes").sum()
            ),
        )
    )


    for channel, row in (
        channel_grouped.iterrows()
    ):

        channel_stats[
            channel
        ][
            "labelled_transactions"
        ] += int(
            row[
                "labelled_transactions"
            ]
        )

        channel_stats[
            channel
        ][
            "fraud_transactions"
        ] += int(
            row[
                "fraud_transactions"
            ]
        )


    # ========================================================
    # D. MCC AGGREGATION
    # ========================================================

    mcc_grouped = (
        labelled
        .groupby(
            "mcc",
            observed=True
        )
        .agg(
            labelled_transactions=(
                "transaction_id",
                "size"
            ),

            fraud_transactions=(
                "fraud_label",
                lambda x:
                    (x == "Yes").sum()
            ),
        )
    )


    for mcc, row in (
        mcc_grouped.iterrows()
    ):

        mcc_stats[
            mcc
        ][
            "labelled_transactions"
        ] += int(
            row[
                "labelled_transactions"
            ]
        )

        mcc_stats[
            mcc
        ][
            "fraud_transactions"
        ] += int(
            row[
                "fraud_transactions"
            ]
        )


    # ========================================================
    # E. ERROR AGGREGATION
    # ========================================================

    error_grouped = (
        labelled
        .groupby(
            "fraud_label",
            observed=True
        )
        .agg(
            labelled_transactions=(
                "transaction_id",
                "size"
            ),

            transactions_with_error=(
                "error_present",
                "sum"
            ),
        )
    )


    for label, row in (
        error_grouped.iterrows()
    ):

        if label not in error_stats:
            continue

        error_stats[
            label
        ][
            "labelled_transactions"
        ] += int(
            row[
                "labelled_transactions"
            ]
        )

        error_stats[
            label
        ][
            "transactions_with_error"
        ] += int(
            row[
                "transactions_with_error"
            ]
        )


    # --------------------------------------------------------
    # Progress
    # --------------------------------------------------------

    if (
        chunk_number % 10 == 0
        or transaction_rows_scanned
        == EXPECTED_TRANSACTIONS
    ):

        print(
            f"Scanned "
            f"{transaction_rows_scanned:,} "
            f"transactions | "
            f"matched "
            f"{labelled_rows_matched:,} labels"
        )


# ============================================================
# STEP 6
# RECONCILIATION
# ============================================================

print_section(
    "STEP 4: RECONCILIATION"
)


if (
    transaction_rows_scanned
    != EXPECTED_TRANSACTIONS
):

    raise RuntimeError(
        f"Transaction population mismatch. "
        f"Expected {EXPECTED_TRANSACTIONS:,}, "
        f"scanned "
        f"{transaction_rows_scanned:,}."
    )


if (
    labelled_rows_matched
    != EXPECTED_LABELS
):

    raise RuntimeError(
        f"Labelled transaction mismatch. "
        f"Expected {EXPECTED_LABELS:,}, "
        f"matched "
        f"{labelled_rows_matched:,}."
    )


if (
    prevalence_counts["Yes"]
    != EXPECTED_FRAUD_YES
):

    raise RuntimeError(
        "Fraud Yes reconciliation failed."
    )


if (
    prevalence_counts["No"]
    != EXPECTED_FRAUD_NO
):

    raise RuntimeError(
        "Fraud No reconciliation failed."
    )


print(
    f"Transactions scanned: "
    f"{transaction_rows_scanned:,} PASS"
)

print(
    f"Labelled transactions matched: "
    f"{labelled_rows_matched:,} PASS"
)

print(
    f"Fraud Yes: "
    f"{prevalence_counts['Yes']:,} PASS"
)

print(
    f"Fraud No: "
    f"{prevalence_counts['No']:,} PASS"
)

print(
    f"Streaming time: "
    f"{time.perf_counter() - stream_start:.2f} seconds"
)


# ============================================================
# STEP 7
# FRAUD PREVALENCE TABLE
# ============================================================

print_section(
    "OUTPUT 1: FRAUD PREVALENCE"
)


fraud_prevalence = pd.DataFrame(
    [
        {
            "fraud_label": "No",
            "transaction_count":
                prevalence_counts[
                    "No"
                ],
        },
        {
            "fraud_label": "Yes",
            "transaction_count":
                prevalence_counts[
                    "Yes"
                ],
        },
    ]
)


fraud_prevalence[
    "transaction_share"
] = (
    fraud_prevalence[
        "transaction_count"
    ]
    /
    EXPECTED_LABELS
)


print(
    fraud_prevalence.to_string(
        index=False
    )
)


save_table(
    fraud_prevalence,
    "fraud_prevalence.csv"
)


# ============================================================
# STEP 8
# FRAUD AMOUNT SUMMARY
# ============================================================

print_section(
    "OUTPUT 2: FRAUD AMOUNT SUMMARY"
)


amount_summary_rows = []


for label in [
    "No",
    "Yes",
]:

    if not amount_parts[label]:

        raise RuntimeError(
            f"No amount observations "
            f"found for {label}."
        )


    signed_values = np.concatenate(
        amount_parts[
            label
        ]
    )


    absolute_values = np.abs(
        signed_values
    )


    amount_summary_rows.append(
        {
            "fraud_label": label,

            "transaction_count":
                len(
                    signed_values
                ),

            "mean_signed_amount":
                signed_values.mean(),

            "median_signed_amount":
                np.median(
                    signed_values
                ),

            "mean_absolute_amount":
                absolute_values.mean(),

            "median_absolute_amount":
                np.median(
                    absolute_values
                ),

            "p95_absolute_amount":
                np.quantile(
                    absolute_values,
                    0.95
                ),

            "p99_absolute_amount":
                np.quantile(
                    absolute_values,
                    0.99
                ),

            "minimum_signed_amount":
                signed_values.min(),

            "maximum_signed_amount":
                signed_values.max(),
        }
    )


fraud_amount_summary = pd.DataFrame(
    amount_summary_rows
)


print(
    fraud_amount_summary.to_string(
        index=False
    )
)


save_table(
    fraud_amount_summary,
    "fraud_amount_summary.csv"
)


# ============================================================
# STEP 9
# FRAUD BY CHANNEL
# ============================================================

print_section(
    "OUTPUT 3: FRAUD BY CHANNEL"
)


fraud_channel_summary = pd.DataFrame(
    [
        {
            "use_chip": channel,
            **values,
        }

        for channel, values
        in channel_stats.items()
    ]
)


fraud_channel_summary[
    "fraud_rate"
] = (
    fraud_channel_summary[
        "fraud_transactions"
    ]
    /
    fraud_channel_summary[
        "labelled_transactions"
    ]
)


fraud_channel_summary = (
    fraud_channel_summary
    .sort_values(
        "fraud_rate",
        ascending=False
    )
    .reset_index(
        drop=True
    )
)


print(
    fraud_channel_summary.to_string(
        index=False
    )
)


save_table(
    fraud_channel_summary,
    "fraud_channel_summary.csv"
)


# ============================================================
# STEP 10
# FRAUD BY MCC
# ============================================================

print_section(
    "OUTPUT 4: TOP MCCs BY CONFIRMED FRAUD COUNT"
)


fraud_mcc_summary = pd.DataFrame(
    [
        {
            "mcc": mcc,
            **values,
        }

        for mcc, values
        in mcc_stats.items()
    ]
)


fraud_mcc_summary[
    "fraud_rate"
] = (
    fraud_mcc_summary[
        "fraud_transactions"
    ]
    /
    fraud_mcc_summary[
        "labelled_transactions"
    ]
)


fraud_mcc_summary = (
    fraud_mcc_summary
    .merge(
        mcc_reference,
        on="mcc",
        how="left",
        validate="one_to_one"
    )
)


if (
    fraud_mcc_summary[
        "mcc_description"
    ]
    .isna()
    .any()
):

    raise RuntimeError(
        "One or more MCC descriptions "
        "failed to map."
    )


top_fraud_mcc = (
    fraud_mcc_summary
    .nlargest(
        10,
        "fraud_transactions"
    )[
        [
            "mcc",
            "mcc_description",
            "labelled_transactions",
            "fraud_transactions",
            "fraud_rate",
        ]
    ]
    .reset_index(
        drop=True
    )
)


print(
    top_fraud_mcc.to_string(
        index=False
    )
)


save_table(
    fraud_mcc_summary,
    "fraud_mcc_full_summary.csv"
)

save_table(
    top_fraud_mcc,
    "fraud_mcc_top_10.csv"
)


# ============================================================
# STEP 11
# ERRORS VS FRAUD
# ============================================================

print_section(
    "OUTPUT 5: RECORDED ERRORS VS FRAUD"
)


fraud_error_summary = pd.DataFrame(
    [
        {
            "fraud_label": label,
            **values,
        }

        for label, values
        in error_stats.items()
    ]
)


fraud_error_summary[
    "error_rate"
] = (
    fraud_error_summary[
        "transactions_with_error"
    ]
    /
    fraud_error_summary[
        "labelled_transactions"
    ]
)


fraud_error_summary = (
    fraud_error_summary
    .sort_values(
        "fraud_label"
    )
    .reset_index(
        drop=True
    )
)


print(
    fraud_error_summary.to_string(
        index=False
    )
)


save_table(
    fraud_error_summary,
    "fraud_error_summary.csv"
)


# ============================================================
# STEP 12
# FINAL RECONCILIATION
# ============================================================

print_section(
    "FINAL PHASE 10.10 VALIDATION"
)


channel_total = int(
    fraud_channel_summary[
        "labelled_transactions"
    ].sum()
)

channel_fraud = int(
    fraud_channel_summary[
        "fraud_transactions"
    ].sum()
)

mcc_total = int(
    fraud_mcc_summary[
        "labelled_transactions"
    ].sum()
)

mcc_fraud = int(
    fraud_mcc_summary[
        "fraud_transactions"
    ].sum()
)

error_total = int(
    fraud_error_summary[
        "labelled_transactions"
    ].sum()
)


assert (
    channel_total
    == EXPECTED_LABELS
)

assert (
    channel_fraud
    == EXPECTED_FRAUD_YES
)

assert (
    mcc_total
    == EXPECTED_LABELS
)

assert (
    mcc_fraud
    == EXPECTED_FRAUD_YES
)

assert (
    error_total
    == EXPECTED_LABELS
)


print(
    f"Channel labelled population: "
    f"{channel_total:,} PASS"
)

print(
    f"Channel fraud population: "
    f"{channel_fraud:,} PASS"
)

print(
    f"MCC labelled population: "
    f"{mcc_total:,} PASS"
)

print(
    f"MCC fraud population: "
    f"{mcc_fraud:,} PASS"
)

print(
    f"Error labelled population: "
    f"{error_total:,} PASS"
)


print()
print("=" * 80)
print(
    "PHASE 10.10 FRAUD EDA STATUS: PASS"
)
print("=" * 80)

print()
print(
    f"Outputs saved to:"
)

print(
    OUTPUT_DIR
)