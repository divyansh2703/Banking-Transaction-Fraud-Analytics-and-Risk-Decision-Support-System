from pathlib import Path
from datetime import datetime, timezone
import argparse
import csv
import sys
import uuid

import numpy as np
import pandas as pd


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_USERS_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "users_cleaned.csv"
)

DEFAULT_CARDS_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "cards_cleaned.csv"
)

DEFAULT_TRANSACTIONS_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "transactions_cleaned.csv"
)

DEFAULT_MCC_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "mcc_codes_cleaned.csv"
)

DEFAULT_FRAUD_FILE = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "fraud_labels_cleaned.csv"
)

VALIDATION_LOG = (
    PROJECT_ROOT
    / "logs"
    / "interim_validation_report.csv"
)


# ============================================================
# VERIFIED CONTROL TOTALS
# ============================================================

EXPECTED_USERS = 2_000
EXPECTED_CARDS = 6_146
EXPECTED_TRANSACTIONS = 13_305_915
EXPECTED_MCC = 109
EXPECTED_FRAUD_LABELS = 8_914_963

EXPECTED_FRAUD_YES = 13_332
EXPECTED_FRAUD_NO = 8_901_631

EXPECTED_NEGATIVE_AMOUNTS = 660_049
EXPECTED_ZERO_AMOUNTS = 10_639

EXPECTED_BEFORE_OPENING = 309
EXPECTED_AFTER_EXPIRY = 83
EXPECTED_CHANNEL_LOCATION = 5_788

EXPECTED_MISSING_STATE = 1_563_700
EXPECTED_MISSING_ZIP = 1_652_706
EXPECTED_MISSING_ERRORS = 13_094_522

EXPECTED_TRANSACTION_ID_MIN = 7_475_327
EXPECTED_TRANSACTION_ID_MAX = 23_761_874

TRANSACTION_CHUNK_SIZE = 100_000
FRAUD_CHUNK_SIZE = 250_000


ALLOWED_USE_CHIP = {
    "Chip Transaction",
    "Online Transaction",
    "Swipe Transaction",
}

ALLOWED_FRAUD_LABELS = {
    "Yes",
    "No",
}


# ============================================================
# EXPECTED INTERIM SCHEMAS
# ============================================================

EXPECTED_USERS_COLUMNS = {
    "client_id",
    "current_age",
    "retirement_age",
    "birth_year",
    "birth_month",
    "gender",
    "address",
    "latitude",
    "longitude",
    "per_capita_income",
    "yearly_income",
    "total_debt",
    "credit_score",
    "num_credit_cards",
}

EXPECTED_CARDS_COLUMNS = {
    "card_id",
    "client_id",
    "card_brand",
    "card_type",
    "expires",
    "has_chip",
    "num_cards_issued",
    "credit_limit",
    "acct_open_date",
    "year_pin_last_changed",
    "card_on_dark_web",
}

EXPECTED_TRANSACTION_COLUMNS = {
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
}

EXPECTED_MCC_COLUMNS = {
    "mcc",
    "mcc_description",
}

EXPECTED_FRAUD_COLUMNS = {
    "transaction_id",
    "fraud_label",
}


# ============================================================
# REPORTING HELPERS
# ============================================================

def add_check(
    report,
    issues,
    check_name,
    actual,
    expected,
):
    """
    Store one validation check and add an issue when it fails.
    """

    passed = actual == expected

    report.append(
        {
            "check_name": check_name,
            "actual": actual,
            "expected": expected,
            "status": "PASS" if passed else "FAIL",
        }
    )

    if not passed:
        issues.append(
            f"{check_name}: "
            f"expected {expected}, found {actual}"
        )


def print_section(title):
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def validate_file_exists(path):
    if not path.exists():
        raise FileNotFoundError(
            f"Required interim file not found: {path}"
        )


def validate_schema(
    columns,
    expected_columns,
    table_name,
):
    """
    Fail if interim table structure differs from expectation.
    """

    actual = set(columns)

    missing = expected_columns - actual
    unexpected = actual - expected_columns

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
            f"{table_name} schema validation failed. "
            + "; ".join(problems)
        )


# ============================================================
# USERS VALIDATION
# ============================================================

def validate_users(
    users_file,
    report,
    issues,
):
    print_section("A. USERS VALIDATION")

    users = pd.read_csv(
        users_file
    )

    validate_schema(
        users.columns,
        EXPECTED_USERS_COLUMNS,
        "users_cleaned"
    )

    add_check(
        report,
        issues,
        "Users row count",
        len(users),
        EXPECTED_USERS
    )

    add_check(
        report,
        issues,
        "Users unique client_id",
        users["client_id"].nunique(
            dropna=True
        ),
        EXPECTED_USERS
    )

    add_check(
        report,
        issues,
        "Users missing client_id",
        int(
            users["client_id"]
            .isna()
            .sum()
        ),
        0
    )

    add_check(
        report,
        issues,
        "Users duplicate client_id occurrences",
        int(
            users["client_id"]
            .duplicated()
            .sum()
        ),
        0
    )

    money_columns = [
        "per_capita_income",
        "yearly_income",
        "total_debt",
    ]

    monetary_failures = 0

    for column in money_columns:

        numeric = pd.to_numeric(
            users[column],
            errors="coerce"
        )

        failures = int(
            numeric.isna().sum()
        )

        monetary_failures += failures

        add_check(
            report,
            issues,
            f"{column} parse failures",
            failures,
            0
        )

    print(
        f"Rows: {len(users):,}"
    )

    print(
        f"Unique client_id: "
        f"{users['client_id'].nunique():,}"
    )

    print(
        f"Monetary transformation failures: "
        f"{monetary_failures:,}"
    )

    return users


# ============================================================
# CARDS VALIDATION
# ============================================================

def validate_cards(
    cards_file,
    users,
    report,
    issues,
):
    print_section("B. CARDS VALIDATION")

    cards = pd.read_csv(
        cards_file,
        dtype={
            "acct_open_date": "string",
            "expires": "string",
        }
    )

    validate_schema(
        cards.columns,
        EXPECTED_CARDS_COLUMNS,
        "cards_cleaned"
    )

    add_check(
        report,
        issues,
        "Cards row count",
        len(cards),
        EXPECTED_CARDS
    )

    add_check(
        report,
        issues,
        "Cards unique card_id",
        cards["card_id"].nunique(
            dropna=True
        ),
        EXPECTED_CARDS
    )

    add_check(
        report,
        issues,
        "Cards missing card_id",
        int(
            cards["card_id"]
            .isna()
            .sum()
        ),
        0
    )

    add_check(
        report,
        issues,
        "Cards duplicate card_id occurrences",
        int(
            cards["card_id"]
            .duplicated()
            .sum()
        ),
        0
    )

    # --------------------------------------------------------
    # Sensitive fields should not exist
    # --------------------------------------------------------

    add_check(
        report,
        issues,
        "card_number present in analytical cards",
        int(
            "card_number"
            in cards.columns
        ),
        0
    )

    add_check(
        report,
        issues,
        "cvv present in analytical cards",
        int(
            "cvv"
            in cards.columns
        ),
        0
    )

    # --------------------------------------------------------
    # Customer relationship
    # --------------------------------------------------------

    user_ids = set(
        users["client_id"]
        .tolist()
    )

    unknown_customers = int(
        (
            ~cards["client_id"].isin(
                user_ids
            )
        ).sum()
    )

    add_check(
        report,
        issues,
        "Cards unknown customer references",
        unknown_customers,
        0
    )

    # --------------------------------------------------------
    # Customer documented card count vs actual
    # --------------------------------------------------------

    expected_counts = (
        users
        .set_index("client_id")[
            "num_credit_cards"
        ]
    )

    actual_counts = (
        cards
        .groupby("client_id")
        .size()
    )

    comparison = pd.concat(
        [
            expected_counts.rename(
                "expected"
            ),
            actual_counts.rename(
                "actual"
            ),
        ],
        axis=1
    ).fillna(0)

    card_count_mismatches = int(
        (
            comparison["expected"]
            != comparison["actual"]
        ).sum()
    )

    add_check(
        report,
        issues,
        "Customer card-count mismatches",
        card_count_mismatches,
        0
    )

    # --------------------------------------------------------
    # Credit limit
    # --------------------------------------------------------

    credit_limit = pd.to_numeric(
        cards["credit_limit"],
        errors="coerce"
    )

    credit_limit_failures = int(
        credit_limit.isna().sum()
    )

    add_check(
        report,
        issues,
        "Credit limit parse failures",
        credit_limit_failures,
        0
    )

    # --------------------------------------------------------
    # Parse cleaned YYYY-MM month fields
    # --------------------------------------------------------

    cards["acct_open_parsed"] = (
        pd.to_datetime(
            cards["acct_open_date"],
            format="%Y-%m",
            errors="coerce"
        )
    )

    cards["expires_parsed"] = (
        pd.to_datetime(
            cards["expires"],
            format="%Y-%m",
            errors="coerce"
        )
    )

    opening_failures = int(
        cards[
            "acct_open_parsed"
        ]
        .isna()
        .sum()
    )

    expiry_failures = int(
        cards[
            "expires_parsed"
        ]
        .isna()
        .sum()
    )

    add_check(
        report,
        issues,
        "Account opening date parse failures",
        opening_failures,
        0
    )

    add_check(
        report,
        issues,
        "Expiry date parse failures",
        expiry_failures,
        0
    )

    # --------------------------------------------------------
    # Convert dates to numeric month ordinals.
    #
    # Example:
    # year * 12 + month
    #
    # This lets later lifecycle comparisons use NumPy
    # positional arrays rather than pandas index alignment.
    # --------------------------------------------------------

    cards["acct_open_month_number"] = (
        cards[
            "acct_open_parsed"
        ].dt.year
        * 12
        +
        cards[
            "acct_open_parsed"
        ].dt.month
    )

    cards["expiry_month_number"] = (
        cards[
            "expires_parsed"
        ].dt.year
        * 12
        +
        cards[
            "expires_parsed"
        ].dt.month
    )

    print(
        f"Rows: {len(cards):,}"
    )

    print(
        f"Unique card_id: "
        f"{cards['card_id'].nunique():,}"
    )

    print(
        f"Unknown customer references: "
        f"{unknown_customers:,}"
    )

    print(
        f"Customer card-count mismatches: "
        f"{card_count_mismatches:,}"
    )

    print(
        f"card_number present: "
        f"{'card_number' in cards.columns}"
    )

    print(
        f"cvv present: "
        f"{'cvv' in cards.columns}"
    )

    return cards


# ============================================================
# MCC VALIDATION
# ============================================================

def validate_mcc(
    mcc_file,
    report,
    issues,
):
    print_section("C. MCC VALIDATION")

    mcc = pd.read_csv(
        mcc_file,
        dtype={
            "mcc": "string"
        }
    )

    validate_schema(
        mcc.columns,
        EXPECTED_MCC_COLUMNS,
        "mcc_codes_cleaned"
    )

    mcc["mcc"] = (
        mcc["mcc"]
        .astype("string")
        .str.strip()
        .str.zfill(4)
    )

    add_check(
        report,
        issues,
        "MCC row count",
        len(mcc),
        EXPECTED_MCC
    )

    add_check(
        report,
        issues,
        "MCC unique codes",
        mcc["mcc"].nunique(
            dropna=True
        ),
        EXPECTED_MCC
    )

    invalid_format = int(
        (
            ~mcc["mcc"]
            .str.fullmatch(
                r"\d{4}",
                na=False
            )
        ).sum()
    )

    add_check(
        report,
        issues,
        "Invalid MCC formats",
        invalid_format,
        0
    )

    descriptions = (
        mcc[
            "mcc_description"
        ]
        .astype("string")
        .str.strip()
    )

    blank_descriptions = int(
        (
            descriptions.isna()
            |
            descriptions.eq("")
        ).sum()
    )

    add_check(
        report,
        issues,
        "Blank MCC descriptions",
        blank_descriptions,
        0
    )

    print(
        f"Rows: {len(mcc):,}"
    )

    print(
        f"Unique MCC codes: "
        f"{mcc['mcc'].nunique():,}"
    )

    return set(
        mcc["mcc"]
        .dropna()
        .tolist()
    )


# ============================================================
# TRANSACTION VALIDATION
# ============================================================

def validate_transactions(
    transactions_file,
    users,
    cards,
    valid_mcc,
    report,
    issues,
):
    print_section(
        "D. TRANSACTIONS VALIDATION"
    )

    # --------------------------------------------------------
    # Validate transaction schema before reading all rows
    # --------------------------------------------------------

    transaction_header = pd.read_csv(
        transactions_file,
        nrows=0
    )

    validate_schema(
        transaction_header.columns,
        EXPECTED_TRANSACTION_COLUMNS,
        "transactions_cleaned"
    )

    user_ids = set(
        users["client_id"]
        .tolist()
    )

    # --------------------------------------------------------
    # Build compact card lookup table
    # --------------------------------------------------------

    card_reference = (
        cards[
            [
                "card_id",
                "client_id",
                "acct_open_month_number",
                "expiry_month_number",
            ]
        ]
        .rename(
            columns={
                "client_id":
                    "card_client_id"
            }
        )
        .copy()
    )

    # --------------------------------------------------------
    # Boolean bitmap for transaction ID uniqueness
    #
    # ~24 million bools is far smaller than storing
    # 13.3 million Python integers in a set.
    # --------------------------------------------------------

    transaction_seen = np.zeros(
        EXPECTED_TRANSACTION_ID_MAX + 1,
        dtype=np.bool_
    )

    totals = {
        "rows": 0,

        "missing_transaction_id": 0,
        "invalid_transaction_id": 0,
        "duplicate_transaction_id": 0,

        "unknown_customer": 0,
        "unknown_card": 0,
        "ownership_mismatch": 0,

        "date_parse_failure": 0,
        "amount_parse_failure": 0,

        "invalid_channel": 0,

        "unknown_mcc": 0,
        "invalid_mcc_format": 0,

        "negative_amount": 0,
        "zero_amount": 0,

        "missing_state": 0,
        "missing_zip": 0,
        "missing_errors": 0,

        "before_opening": 0,
        "after_expiry": 0,
        "channel_location": 0,

        "before_flag_mismatch": 0,
        "after_flag_mismatch": 0,
        "channel_flag_mismatch": 0,
    }

    min_transaction_id = None
    max_transaction_id = None

    reader = pd.read_csv(
        transactions_file,
        chunksize=TRANSACTION_CHUNK_SIZE,
        dtype={
            "mcc": "string",
            "zip": "string",
        },
        on_bad_lines="error"
    )

    for chunk_number, chunk in enumerate(
        reader,
        start=1
    ):

        # ====================================================
        # CRITICAL:
        # reset every incoming chunk's index.
        # ====================================================

        chunk = (
            chunk
            .reset_index(drop=True)
            .copy()
        )

        totals["rows"] += len(chunk)

        # ====================================================
        # TRANSACTION ID VALIDATION
        # ====================================================

        raw_ids = pd.to_numeric(
            chunk["transaction_id"],
            errors="coerce"
        )

        missing_id = (
            chunk["transaction_id"]
            .isna()
        )

        non_integer_id = (
            raw_ids.notna()
            &
            (raw_ids % 1 != 0)
        )

        out_of_range_id = (
            raw_ids.notna()
            &
            (
                (raw_ids < 0)
                |
                (
                    raw_ids
                    > EXPECTED_TRANSACTION_ID_MAX
                )
            )
        )

        invalid_id = (
            raw_ids.isna()
            |
            non_integer_id
            |
            out_of_range_id
        )

        totals[
            "missing_transaction_id"
        ] += int(
            missing_id.sum()
        )

        totals[
            "invalid_transaction_id"
        ] += int(
            invalid_id.sum()
        )

        valid_ids = (
            raw_ids[
                ~invalid_id
            ]
            .astype("int64")
            .to_numpy()
        )

        if valid_ids.size > 0:

            chunk_min = int(
                valid_ids.min()
            )

            chunk_max = int(
                valid_ids.max()
            )

            if min_transaction_id is None:
                min_transaction_id = chunk_min
            else:
                min_transaction_id = min(
                    min_transaction_id,
                    chunk_min
                )

            if max_transaction_id is None:
                max_transaction_id = chunk_max
            else:
                max_transaction_id = max(
                    max_transaction_id,
                    chunk_max
                )

            unique_ids, counts = np.unique(
                valid_ids,
                return_counts=True
            )

            previously_seen = (
                transaction_seen[
                    unique_ids
                ]
            )

            # IDs already seen in previous chunks:
            # all occurrences in current chunk are duplicates.
            duplicate_from_previous = int(
                counts[
                    previously_seen
                ].sum()
            )

            # IDs first appearing in this chunk:
            # only occurrences after first count as duplicate.
            duplicate_inside_chunk = int(
                (
                    counts[
                        ~previously_seen
                    ]
                    - 1
                ).sum()
            )

            totals[
                "duplicate_transaction_id"
            ] += (
                duplicate_from_previous
                +
                duplicate_inside_chunk
            )

            transaction_seen[
                unique_ids
            ] = True

        # ====================================================
        # CUSTOMER RELATIONSHIP
        # ====================================================

        totals[
            "unknown_customer"
        ] += int(
            (
                ~chunk[
                    "client_id"
                ].isin(
                    user_ids
                )
            ).sum()
        )

        # ====================================================
        # AMOUNT VALIDATION
        # ====================================================

        amount = pd.to_numeric(
            chunk["amount"],
            errors="coerce"
        )

        totals[
            "amount_parse_failure"
        ] += int(
            amount.isna().sum()
        )

        totals[
            "negative_amount"
        ] += int(
            (amount < 0).sum()
        )

        totals[
            "zero_amount"
        ] += int(
            (amount == 0).sum()
        )

        # ====================================================
        # CHANNEL VALIDATION
        # ====================================================

        invalid_channel = (
            chunk["use_chip"].isna()
            |
            ~chunk["use_chip"].isin(
                ALLOWED_USE_CHIP
            )
        )

        totals[
            "invalid_channel"
        ] += int(
            invalid_channel.sum()
        )

        # ====================================================
        # MCC VALIDATION
        # ====================================================

        mcc_values = (
            chunk["mcc"]
            .astype("string")
            .str.strip()
            .str.zfill(4)
        )

        invalid_mcc_format = (
            ~mcc_values
            .str.fullmatch(
                r"\d{4}",
                na=False
            )
        )

        totals[
            "invalid_mcc_format"
        ] += int(
            invalid_mcc_format.sum()
        )

        totals[
            "unknown_mcc"
        ] += int(
            (
                ~mcc_values.isin(
                    valid_mcc
                )
            ).sum()
        )

        # ====================================================
        # MISSINGNESS RECONCILIATION
        # ====================================================

        totals[
            "missing_state"
        ] += int(
            chunk[
                "merchant_state"
            ]
            .isna()
            .sum()
        )

        totals[
            "missing_zip"
        ] += int(
            chunk[
                "zip"
            ]
            .isna()
            .sum()
        )

        totals[
            "missing_errors"
        ] += int(
            chunk[
                "errors"
            ]
            .isna()
            .sum()
        )

        # ====================================================
        # MERGE CARD REFERENCE
        # ====================================================

        merged = (
            chunk.merge(
                card_reference,
                how="left",
                on="card_id",
                validate="many_to_one",
                sort=False
            )
            .reset_index(drop=True)
        )

        # Critical reconciliation:
        # many-to-one merge must preserve transaction row count.
        if len(merged) != len(chunk):
            raise ValueError(
                "Card reference merge changed "
                "transaction row count. "
                f"Before merge: {len(chunk):,}, "
                f"after merge: {len(merged):,}."
            )

        # ====================================================
        # CARD EXISTENCE
        # ====================================================

        card_client_values = (
            merged[
                "card_client_id"
            ]
            .to_numpy()
        )

        unknown_card_mask = (
            pd.isna(
                card_client_values
            )
        )

        totals[
            "unknown_card"
        ] += int(
            unknown_card_mask.sum()
        )

        # ====================================================
        # OWNERSHIP VALIDATION
        #
        # NumPy positional comparison eliminates
        # pandas index-alignment issues.
        # ====================================================

        transaction_client_values = (
            merged[
                "client_id"
            ]
            .to_numpy()
        )

        ownership_mismatch_mask = (
            ~unknown_card_mask
            &
            (
                transaction_client_values
                !=
                card_client_values
            )
        )

        totals[
            "ownership_mismatch"
        ] += int(
            ownership_mismatch_mask.sum()
        )

        # ====================================================
        # TRANSACTION DATE PARSING
        #
        # Parse AFTER merge so lifecycle calculations use
        # the same merged row structure.
        # ====================================================

        parsed_date = pd.to_datetime(
            merged["date"],
            format="%Y-%m-%d %H:%M:%S",
            errors="coerce"
        )

        date_parse_failures = int(
            parsed_date.isna().sum()
        )

        totals[
            "date_parse_failure"
        ] += date_parse_failures

        # ----------------------------------------------------
        # Convert transaction dates to month numbers.
        #
        # year * 12 + month
        # ----------------------------------------------------

        transaction_month_number = (
            (
                parsed_date.dt.year
                * 12
            )
            +
            parsed_date.dt.month
        ).to_numpy(
            dtype="float64"
        )

        opening_month_number = (
            pd.to_numeric(
                merged[
                    "acct_open_month_number"
                ],
                errors="coerce"
            )
            .to_numpy(
                dtype="float64"
            )
        )

        expiry_month_number = (
            pd.to_numeric(
                merged[
                    "expiry_month_number"
                ],
                errors="coerce"
            )
            .to_numpy(
                dtype="float64"
            )
        )

        valid_transaction_month = (
            np.isfinite(
                transaction_month_number
            )
        )

        valid_opening_month = (
            np.isfinite(
                opening_month_number
            )
        )

        valid_expiry_month = (
            np.isfinite(
                expiry_month_number
            )
        )

        # ====================================================
        # RECOMPUTE BEFORE-OPENING FLAG
        # ====================================================

        recomputed_before = (
            valid_transaction_month
            &
            valid_opening_month
            &
            (
                transaction_month_number
                <
                opening_month_number
            )
        )

        totals[
            "before_opening"
        ] += int(
            recomputed_before.sum()
        )

        # ====================================================
        # RECOMPUTE AFTER-EXPIRY FLAG
        # ====================================================

        recomputed_after = (
            valid_transaction_month
            &
            valid_expiry_month
            &
            (
                transaction_month_number
                >
                expiry_month_number
            )
        )

        totals[
            "after_expiry"
        ] += int(
            recomputed_after.sum()
        )

        # ====================================================
        # VALIDATE STORED BEFORE-OPENING FLAG
        # ====================================================

        stored_before = (
            pd.to_numeric(
                merged[
                    "transaction_before_card_open_flag"
                ],
                errors="coerce"
            )
            .to_numpy(
                dtype="float64"
            )
        )

        valid_stored_before = (
            np.isfinite(
                stored_before
            )
            &
            np.isin(
                stored_before,
                [0.0, 1.0]
            )
        )

        expected_before_numeric = (
            recomputed_before
            .astype(np.int8)
        )

        before_flag_mismatch = (
            ~valid_stored_before
            |
            (
                stored_before
                !=
                expected_before_numeric
            )
        )

        totals[
            "before_flag_mismatch"
        ] += int(
            before_flag_mismatch.sum()
        )

        # ====================================================
        # VALIDATE STORED AFTER-EXPIRY FLAG
        # ====================================================

        stored_after = (
            pd.to_numeric(
                merged[
                    "transaction_after_card_expiry_flag"
                ],
                errors="coerce"
            )
            .to_numpy(
                dtype="float64"
            )
        )

        valid_stored_after = (
            np.isfinite(
                stored_after
            )
            &
            np.isin(
                stored_after,
                [0.0, 1.0]
            )
        )

        expected_after_numeric = (
            recomputed_after
            .astype(np.int8)
        )

        after_flag_mismatch = (
            ~valid_stored_after
            |
            (
                stored_after
                !=
                expected_after_numeric
            )
        )

        totals[
            "after_flag_mismatch"
        ] += int(
            after_flag_mismatch.sum()
        )

        # ====================================================
        # RECOMPUTE CHANNEL / LOCATION FLAG
        #
        # Again use positional NumPy arrays.
        # ====================================================

        use_chip_values = (
            merged[
                "use_chip"
            ]
            .astype("string")
            .fillna("")
            .to_numpy()
        )

        merchant_city_values = (
            merged[
                "merchant_city"
            ]
            .astype("string")
            .fillna("")
            .str.strip()
            .str.upper()
            .to_numpy()
        )

        recomputed_channel_location = (
            (
                use_chip_values
                ==
                "Chip Transaction"
            )
            &
            (
                merchant_city_values
                ==
                "ONLINE"
            )
        )

        totals[
            "channel_location"
        ] += int(
            recomputed_channel_location.sum()
        )

        # ====================================================
        # VALIDATE STORED CHANNEL/LOCATION FLAG
        # ====================================================

        stored_channel = (
            pd.to_numeric(
                merged[
                    "channel_location_inconsistency_flag"
                ],
                errors="coerce"
            )
            .to_numpy(
                dtype="float64"
            )
        )

        valid_stored_channel = (
            np.isfinite(
                stored_channel
            )
            &
            np.isin(
                stored_channel,
                [0.0, 1.0]
            )
        )

        expected_channel_numeric = (
            recomputed_channel_location
            .astype(np.int8)
        )

        channel_flag_mismatch = (
            ~valid_stored_channel
            |
            (
                stored_channel
                !=
                expected_channel_numeric
            )
        )

        totals[
            "channel_flag_mismatch"
        ] += int(
            channel_flag_mismatch.sum()
        )

        print(
            f"Validated transaction chunk "
            f"{chunk_number}: "
            f"{totals['rows']:,} rows"
        )

    # ========================================================
    # FINAL TRANSACTION CHECKS
    # ========================================================

    distinct_transaction_ids = int(
        transaction_seen.sum()
    )

    add_check(
        report,
        issues,
        "Transaction row count",
        totals["rows"],
        EXPECTED_TRANSACTIONS
    )

    add_check(
        report,
        issues,
        "Distinct transaction IDs",
        distinct_transaction_ids,
        EXPECTED_TRANSACTIONS
    )

    add_check(
        report,
        issues,
        "Missing transaction IDs",
        totals[
            "missing_transaction_id"
        ],
        0
    )

    add_check(
        report,
        issues,
        "Invalid transaction IDs",
        totals[
            "invalid_transaction_id"
        ],
        0
    )

    add_check(
        report,
        issues,
        "Duplicate transaction ID occurrences",
        totals[
            "duplicate_transaction_id"
        ],
        0
    )

    add_check(
        report,
        issues,
        "Minimum transaction ID",
        min_transaction_id,
        EXPECTED_TRANSACTION_ID_MIN
    )

    add_check(
        report,
        issues,
        "Maximum transaction ID",
        max_transaction_id,
        EXPECTED_TRANSACTION_ID_MAX
    )

    add_check(
        report,
        issues,
        "Unknown transaction customer references",
        totals["unknown_customer"],
        0
    )

    add_check(
        report,
        issues,
        "Unknown transaction card references",
        totals["unknown_card"],
        0
    )

    add_check(
        report,
        issues,
        "Transaction card ownership mismatches",
        totals["ownership_mismatch"],
        0
    )

    add_check(
        report,
        issues,
        "Transaction date parse failures",
        totals["date_parse_failure"],
        0
    )

    add_check(
        report,
        issues,
        "Transaction amount parse failures",
        totals["amount_parse_failure"],
        0
    )

    add_check(
        report,
        issues,
        "Invalid transaction channels",
        totals["invalid_channel"],
        0
    )

    add_check(
        report,
        issues,
        "Invalid transaction MCC formats",
        totals["invalid_mcc_format"],
        0
    )

    add_check(
        report,
        issues,
        "Unmapped transaction MCC values",
        totals["unknown_mcc"],
        0
    )

    # --------------------------------------------------------
    # Known baseline reconciliation
    # --------------------------------------------------------

    add_check(
        report,
        issues,
        "Negative transaction amounts",
        totals["negative_amount"],
        EXPECTED_NEGATIVE_AMOUNTS
    )

    add_check(
        report,
        issues,
        "Zero transaction amounts",
        totals["zero_amount"],
        EXPECTED_ZERO_AMOUNTS
    )

    add_check(
        report,
        issues,
        "Missing merchant_state",
        totals["missing_state"],
        EXPECTED_MISSING_STATE
    )

    add_check(
        report,
        issues,
        "Missing ZIP",
        totals["missing_zip"],
        EXPECTED_MISSING_ZIP
    )

    add_check(
        report,
        issues,
        "Missing errors",
        totals["missing_errors"],
        EXPECTED_MISSING_ERRORS
    )

    add_check(
        report,
        issues,
        "Recomputed before-opening flags",
        totals["before_opening"],
        EXPECTED_BEFORE_OPENING
    )

    add_check(
        report,
        issues,
        "Recomputed after-expiry flags",
        totals["after_expiry"],
        EXPECTED_AFTER_EXPIRY
    )

    add_check(
        report,
        issues,
        "Recomputed channel/location flags",
        totals["channel_location"],
        EXPECTED_CHANNEL_LOCATION
    )

    # --------------------------------------------------------
    # Critical independent flag validation
    # --------------------------------------------------------

    add_check(
        report,
        issues,
        "Before-opening flag mismatches",
        totals[
            "before_flag_mismatch"
        ],
        0
    )

    add_check(
        report,
        issues,
        "After-expiry flag mismatches",
        totals[
            "after_flag_mismatch"
        ],
        0
    )

    add_check(
        report,
        issues,
        "Channel/location flag mismatches",
        totals[
            "channel_flag_mismatch"
        ],
        0
    )

    print()
    print(
        f"Rows validated: "
        f"{totals['rows']:,}"
    )

    print(
        f"Distinct transaction IDs: "
        f"{distinct_transaction_ids:,}"
    )

    print(
        f"Unknown customers: "
        f"{totals['unknown_customer']:,}"
    )

    print(
        f"Unknown cards: "
        f"{totals['unknown_card']:,}"
    )

    print(
        f"Ownership mismatches: "
        f"{totals['ownership_mismatch']:,}"
    )

    print(
        f"Before-opening flag mismatches: "
        f"{totals['before_flag_mismatch']:,}"
    )

    print(
        f"After-expiry flag mismatches: "
        f"{totals['after_flag_mismatch']:,}"
    )

    print(
        f"Channel/location flag mismatches: "
        f"{totals['channel_flag_mismatch']:,}"
    )

    return transaction_seen


# ============================================================
# FRAUD LABEL VALIDATION
# ============================================================

def validate_fraud_labels(
    fraud_file,
    transaction_seen,
    report,
    issues,
):
    print_section(
        "E. FRAUD LABEL VALIDATION"
    )

    fraud_header = pd.read_csv(
        fraud_file,
        nrows=0
    )

    validate_schema(
        fraud_header.columns,
        EXPECTED_FRAUD_COLUMNS,
        "fraud_labels_cleaned"
    )

    # --------------------------------------------------------
    # Boolean bitmap for fraud transaction ID uniqueness
    # --------------------------------------------------------

    fraud_seen = np.zeros(
        EXPECTED_TRANSACTION_ID_MAX + 1,
        dtype=np.bool_
    )

    totals = {
        "rows": 0,
        "invalid_transaction_id": 0,
        "duplicate_transaction_id": 0,
        "transaction_not_found": 0,
        "yes": 0,
        "no": 0,
        "unexpected_label": 0,
    }

    reader = pd.read_csv(
        fraud_file,
        chunksize=FRAUD_CHUNK_SIZE,
        dtype={
            "fraud_label": "string"
        },
        on_bad_lines="error"
    )

    for chunk_number, chunk in enumerate(
        reader,
        start=1
    ):

        chunk = (
            chunk
            .reset_index(drop=True)
            .copy()
        )

        totals["rows"] += len(chunk)

        # ====================================================
        # FRAUD TRANSACTION ID
        # ====================================================

        raw_ids = pd.to_numeric(
            chunk["transaction_id"],
            errors="coerce"
        )

        invalid = (
            raw_ids.isna()
            |
            (raw_ids % 1 != 0)
            |
            (raw_ids < 0)
            |
            (
                raw_ids
                >
                EXPECTED_TRANSACTION_ID_MAX
            )
        )

        totals[
            "invalid_transaction_id"
        ] += int(
            invalid.sum()
        )

        valid_ids = (
            raw_ids[
                ~invalid
            ]
            .astype("int64")
            .to_numpy()
        )

        if valid_ids.size > 0:

            unique_ids, counts = np.unique(
                valid_ids,
                return_counts=True
            )

            previously_seen = (
                fraud_seen[
                    unique_ids
                ]
            )

            duplicate_from_previous = int(
                counts[
                    previously_seen
                ].sum()
            )

            duplicate_inside_chunk = int(
                (
                    counts[
                        ~previously_seen
                    ]
                    - 1
                ).sum()
            )

            totals[
                "duplicate_transaction_id"
            ] += (
                duplicate_from_previous
                +
                duplicate_inside_chunk
            )

            fraud_seen[
                unique_ids
            ] = True

            # ------------------------------------------------
            # Every fraud-label transaction ID must exist
            # in cleaned transactions.
            # ------------------------------------------------

            totals[
                "transaction_not_found"
            ] += int(
                (
                    ~transaction_seen[
                        valid_ids
                    ]
                ).sum()
            )

        # ====================================================
        # FRAUD LABEL VALIDATION
        # ====================================================

        labels = (
            chunk["fraud_label"]
            .astype("string")
            .str.strip()
        )

        totals["yes"] += int(
            labels.eq("Yes").sum()
        )

        totals["no"] += int(
            labels.eq("No").sum()
        )

        totals[
            "unexpected_label"
        ] += int(
            (
                ~labels.isin(
                    ALLOWED_FRAUD_LABELS
                )
            ).sum()
        )

        print(
            f"Validated fraud chunk "
            f"{chunk_number}: "
            f"{totals['rows']:,} labels"
        )

    distinct_fraud_ids = int(
        fraud_seen.sum()
    )

    # ========================================================
    # FINAL FRAUD CHECKS
    # ========================================================

    add_check(
        report,
        issues,
        "Fraud label row count",
        totals["rows"],
        EXPECTED_FRAUD_LABELS
    )

    add_check(
        report,
        issues,
        "Distinct fraud transaction IDs",
        distinct_fraud_ids,
        EXPECTED_FRAUD_LABELS
    )

    add_check(
        report,
        issues,
        "Invalid fraud transaction IDs",
        totals[
            "invalid_transaction_id"
        ],
        0
    )

    add_check(
        report,
        issues,
        "Duplicate fraud transaction IDs",
        totals[
            "duplicate_transaction_id"
        ],
        0
    )

    add_check(
        report,
        issues,
        "Fraud IDs absent from transactions",
        totals[
            "transaction_not_found"
        ],
        0
    )

    add_check(
        report,
        issues,
        "Fraud Yes labels",
        totals["yes"],
        EXPECTED_FRAUD_YES
    )

    add_check(
        report,
        issues,
        "Fraud No labels",
        totals["no"],
        EXPECTED_FRAUD_NO
    )

    add_check(
        report,
        issues,
        "Unexpected fraud labels",
        totals[
            "unexpected_label"
        ],
        0
    )

    print()
    print(
        f"Labels validated: "
        f"{totals['rows']:,}"
    )

    print(
        f"Distinct fraud IDs: "
        f"{distinct_fraud_ids:,}"
    )

    print(
        f"Fraud IDs absent from transactions: "
        f"{totals['transaction_not_found']:,}"
    )

    print(
        f"Yes labels: "
        f"{totals['yes']:,}"
    )

    print(
        f"No labels: "
        f"{totals['no']:,}"
    )


# ============================================================
# WRITE AUDIT LOG
# ============================================================

def write_validation_log(
    report,
    overall_status,
):
    VALIDATION_LOG.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    run_id = str(
        uuid.uuid4()
    )

    timestamp = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    rows = []

    for item in report:

        rows.append(
            {
                "run_id": run_id,
                "timestamp_utc": timestamp,
                "check_name":
                    item["check_name"],
                "actual":
                    item["actual"],
                "expected":
                    item["expected"],
                "status":
                    item["status"],
                "overall_status":
                    overall_status,
            }
        )

    file_exists = (
        VALIDATION_LOG.exists()
    )

    with open(
        VALIDATION_LOG,
        "a",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=[
                "run_id",
                "timestamp_utc",
                "check_name",
                "actual",
                "expected",
                "status",
                "overall_status",
            ]
        )

        if not file_exists:
            writer.writeheader()

        writer.writerows(
            rows
        )

    return run_id


# ============================================================
# FINAL REPORT
# ============================================================

def print_final_report(
    report,
    issues,
    run_id,
):
    print_section(
        "FINAL POST-CLEANING VALIDATION"
    )

    passed = sum(
        item["status"] == "PASS"
        for item in report
    )

    failed = sum(
        item["status"] == "FAIL"
        for item in report
    )

    print(
        f"Checks executed: "
        f"{len(report):,}"
    )

    print(
        f"Checks passed: "
        f"{passed:,}"
    )

    print(
        f"Checks failed: "
        f"{failed:,}"
    )

    print(
        f"Validation run ID: "
        f"{run_id}"
    )

    print(
        f"Audit log: "
        f"{VALIDATION_LOG}"
    )

    print()

    if issues:

        print("FAILED CHECKS")

        for issue in issues:
            print(
                f"  {issue}"
            )

        print()

        print(
            "POST-CLEANING VALIDATION STATUS: FAIL"
        )

    else:

        print(
            "POST-CLEANING VALIDATION STATUS: PASS"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Independently validate all cleaned "
            "interim datasets after Phase 7."
        )
    )

    parser.add_argument(
        "--users",
        type=Path,
        default=DEFAULT_USERS_FILE
    )

    parser.add_argument(
        "--cards",
        type=Path,
        default=DEFAULT_CARDS_FILE
    )

    parser.add_argument(
        "--transactions",
        type=Path,
        default=DEFAULT_TRANSACTIONS_FILE
    )

    parser.add_argument(
        "--mcc",
        type=Path,
        default=DEFAULT_MCC_FILE
    )

    parser.add_argument(
        "--fraud",
        type=Path,
        default=DEFAULT_FRAUD_FILE
    )

    args = parser.parse_args()

    users_file = (
        args.users.resolve()
    )

    cards_file = (
        args.cards.resolve()
    )

    transactions_file = (
        args.transactions.resolve()
    )

    mcc_file = (
        args.mcc.resolve()
    )

    fraud_file = (
        args.fraud.resolve()
    )

    files = [
        users_file,
        cards_file,
        transactions_file,
        mcc_file,
        fraud_file,
    ]

    try:

        print("=" * 70)
        print(
            "POST-CLEANING INTERIM DATA VALIDATION"
        )
        print("=" * 70)

        print()
        print(
            "This validation is independent "
            "of the cleaning pipelines."
        )

        # ====================================================
        # FILE EXISTENCE
        # ====================================================

        for file_path in files:
            validate_file_exists(
                file_path
            )

        report = []
        issues = []

        # ====================================================
        # USERS
        # ====================================================

        users = validate_users(
            users_file,
            report,
            issues
        )

        # ====================================================
        # CARDS
        # ====================================================

        cards = validate_cards(
            cards_file,
            users,
            report,
            issues
        )

        # ====================================================
        # MCC
        # ====================================================

        valid_mcc = validate_mcc(
            mcc_file,
            report,
            issues
        )

        # ====================================================
        # TRANSACTIONS
        # ====================================================

        transaction_seen = (
            validate_transactions(
                transactions_file,
                users,
                cards,
                valid_mcc,
                report,
                issues
            )
        )

        # ====================================================
        # FRAUD LABELS
        # ====================================================

        validate_fraud_labels(
            fraud_file,
            transaction_seen,
            report,
            issues
        )

        # ====================================================
        # FINAL STATUS
        # ====================================================

        overall_status = (
            "PASS"
            if not issues
            else "FAIL"
        )

        run_id = write_validation_log(
            report,
            overall_status
        )

        print_final_report(
            report,
            issues,
            run_id
        )

        if issues:
            sys.exit(1)

    except Exception as error:

        print()
        print("=" * 70)
        print(
            "POST-CLEANING VALIDATION STATUS: FAIL"
        )
        print("=" * 70)

        print(
            f"Error: {error}"
        )

        sys.exit(1)


if __name__ == "__main__":
    main()