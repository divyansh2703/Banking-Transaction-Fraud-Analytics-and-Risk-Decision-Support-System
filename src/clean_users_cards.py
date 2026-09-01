from pathlib import Path
from time import perf_counter
import argparse
import sys

import pandas as pd


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_USERS_FILE = PROJECT_ROOT / "data" / "raw" / "users_data.csv"
DEFAULT_CARDS_FILE = PROJECT_ROOT / "data" / "raw" / "cards_data.csv"

INTERIM_DIR = PROJECT_ROOT / "data" / "interim"

USERS_OUTPUT_FILE = INTERIM_DIR / "users_cleaned.csv"
CARDS_OUTPUT_FILE = INTERIM_DIR / "cards_cleaned.csv"


# ============================================================
# EXPECTED SOURCE STRUCTURE
# ============================================================

EXPECTED_USERS_ROWS = 2_000
EXPECTED_CARDS_ROWS = 6_146

EXPECTED_USERS_COLUMNS = [
    "id",
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
]

EXPECTED_CARDS_COLUMNS = [
    "id",
    "client_id",
    "card_brand",
    "card_type",
    "card_number",
    "expires",
    "cvv",
    "has_chip",
    "num_cards_issued",
    "credit_limit",
    "acct_open_date",
    "year_pin_last_changed",
    "card_on_dark_web",
]


# ============================================================
# GENERAL VALIDATION FUNCTIONS
# ============================================================

def validate_file_exists(file_path):
    """Fail if a required source file does not exist."""

    if not file_path.exists():
        raise FileNotFoundError(
            f"Required source file not found: {file_path}"
        )


def validate_schema(df, expected_columns, table_name):
    """
    Ensure the source contains exactly the expected columns.
    """

    actual_columns = list(df.columns)

    missing_columns = set(expected_columns) - set(actual_columns)
    unexpected_columns = set(actual_columns) - set(expected_columns)

    problems = []

    if missing_columns:
        problems.append(
            f"Missing columns: {sorted(missing_columns)}"
        )

    if unexpected_columns:
        problems.append(
            f"Unexpected columns: {sorted(unexpected_columns)}"
        )

    if problems:
        raise ValueError(
            f"{table_name} schema validation failed. "
            + "; ".join(problems)
        )


def validate_row_count(df, expected_rows, table_name):
    """Ensure cleaning has not lost or created rows."""

    actual_rows = len(df)

    if actual_rows != expected_rows:
        raise ValueError(
            f"{table_name} row reconciliation failed. "
            f"Expected {expected_rows:,}, "
            f"found {actual_rows:,}."
        )


def validate_unique_key(df, key_column, table_name):
    """Validate completeness and uniqueness of primary identifier."""

    missing_count = df[key_column].isna().sum()

    duplicate_count = df[key_column].duplicated().sum()

    if missing_count > 0:
        raise ValueError(
            f"{table_name}.{key_column} contains "
            f"{missing_count:,} missing values."
        )

    if duplicate_count > 0:
        raise ValueError(
            f"{table_name}.{key_column} contains "
            f"{duplicate_count:,} duplicate occurrences."
        )


# ============================================================
# MONEY CLEANING
# ============================================================

def parse_money_column(series, column_name):
    """
    Convert monetary strings such as:

        $59696
        $1,250
        -$500
        $0

    into numeric values.

    Fail if any non-null source value cannot be parsed.
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

    unparseable_count = newly_unparseable.sum()

    if unparseable_count > 0:

        examples = (
            series[newly_unparseable]
            .head(5)
            .tolist()
        )

        raise ValueError(
            f"{column_name}: "
            f"{unparseable_count:,} values could not be parsed. "
            f"Examples: {examples}"
        )

    return numeric


# ============================================================
# MONTH FIELD CLEANING
# ============================================================

def parse_month_column(series, column_name):
    """
    Validate MM/YYYY values using an explicit format.

    The output is stored as YYYY-MM because the source only
    provides month-level precision.

    We intentionally do NOT invent a day such as 01 or 31.
    """

    parsed = pd.to_datetime(
        series,
        format="%m/%Y",
        errors="coerce"
    )

    invalid = parsed.isna() & series.notna()

    invalid_count = invalid.sum()

    if invalid_count > 0:

        examples = (
            series[invalid]
            .head(5)
            .tolist()
        )

        raise ValueError(
            f"{column_name}: "
            f"{invalid_count:,} values could not be parsed "
            f"using MM/YYYY. "
            f"Examples: {examples}"
        )

    return parsed.dt.strftime("%Y-%m")


# ============================================================
# USERS CLEANING
# ============================================================

def clean_users(users_file):
    """Create cleaned analytical users table."""

    print("Cleaning users_data...")

    users = pd.read_csv(
        users_file,
        on_bad_lines="error"
    )

    validate_schema(
        users,
        EXPECTED_USERS_COLUMNS,
        "users_data"
    )

    validate_row_count(
        users,
        EXPECTED_USERS_ROWS,
        "users_data"
    )

    validate_unique_key(
        users,
        "id",
        "users_data"
    )

    # --------------------------------------------------------
    # Rename analytical identifier
    # --------------------------------------------------------

    users = users.rename(
        columns={
            "id": "client_id"
        }
    )

    # --------------------------------------------------------
    # Parse monetary fields
    # --------------------------------------------------------

    money_columns = [
        "per_capita_income",
        "yearly_income",
        "total_debt",
    ]

    for column in money_columns:
        users[column] = parse_money_column(
            users[column],
            column
        )

    # --------------------------------------------------------
    # Preserve column order
    # --------------------------------------------------------

    users = users[
        [
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
        ]
    ]

    return users


# ============================================================
# CARDS CLEANING
# ============================================================

def clean_cards(cards_file):
    """Create cleaned analytical cards table."""

    print("Cleaning cards_data...")

    # Read card_number and cvv as strings.
    # They will later be removed, but this prevents unnecessary
    # reinterpretation during source ingestion.
    cards = pd.read_csv(
        cards_file,
        dtype={
            "card_number": "string",
            "cvv": "string",
        },
        on_bad_lines="error"
    )

    validate_schema(
        cards,
        EXPECTED_CARDS_COLUMNS,
        "cards_data"
    )

    validate_row_count(
        cards,
        EXPECTED_CARDS_ROWS,
        "cards_data"
    )

    validate_unique_key(
        cards,
        "id",
        "cards_data"
    )

    # --------------------------------------------------------
    # Rename analytical identifier
    # --------------------------------------------------------

    cards = cards.rename(
        columns={
            "id": "card_id"
        }
    )

    # --------------------------------------------------------
    # Parse monetary field
    # --------------------------------------------------------

    cards["credit_limit"] = parse_money_column(
        cards["credit_limit"],
        "credit_limit"
    )

    # --------------------------------------------------------
    # Standardize month fields
    # --------------------------------------------------------

    cards["expires"] = parse_month_column(
        cards["expires"],
        "expires"
    )

    cards["acct_open_date"] = parse_month_column(
        cards["acct_open_date"],
        "acct_open_date"
    )

    # --------------------------------------------------------
    # Data minimisation
    #
    # Deliberately exclude card_number and cvv from the
    # analytical/interim dataset.
    # --------------------------------------------------------

    cards = cards.drop(
        columns=[
            "card_number",
            "cvv",
        ]
    )

    # --------------------------------------------------------
    # Preserve intended analytical column order
    # --------------------------------------------------------

    cards = cards[
        [
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
        ]
    ]

    return cards


# ============================================================
# POST-CLEANING VALIDATION
# ============================================================

def validate_cleaned_users(users):
    """Validate cleaned users table."""

    print()
    print("VALIDATING CLEANED USERS")

    validate_row_count(
        users,
        EXPECTED_USERS_ROWS,
        "users_cleaned"
    )

    validate_unique_key(
        users,
        "client_id",
        "users_cleaned"
    )

    monetary_columns = [
        "per_capita_income",
        "yearly_income",
        "total_debt",
    ]

    for column in monetary_columns:

        if not pd.api.types.is_numeric_dtype(users[column]):

            raise TypeError(
                f"{column} is not numeric after cleaning."
            )

    print(
        f"Rows: {len(users):,}"
    )

    print(
        f"Unique client_id values: "
        f"{users['client_id'].nunique():,}"
    )

    print(
        "Unparseable monetary values: 0"
    )

    print(
        "Users validation status: PASS"
    )


def validate_cleaned_cards(cards):
    """Validate cleaned cards table."""

    print()
    print("VALIDATING CLEANED CARDS")

    validate_row_count(
        cards,
        EXPECTED_CARDS_ROWS,
        "cards_cleaned"
    )

    validate_unique_key(
        cards,
        "card_id",
        "cards_cleaned"
    )

    if not pd.api.types.is_numeric_dtype(
        cards["credit_limit"]
    ):
        raise TypeError(
            "credit_limit is not numeric after cleaning."
        )

    sensitive_columns = {
        "card_number",
        "cvv"
    }

    remaining_sensitive = (
        sensitive_columns
        .intersection(cards.columns)
    )

    if remaining_sensitive:
        raise ValueError(
            "Sensitive columns remain in cleaned cards table: "
            f"{sorted(remaining_sensitive)}"
        )

    print(
        f"Rows: {len(cards):,}"
    )

    print(
        f"Unique card_id values: "
        f"{cards['card_id'].nunique():,}"
    )

    print(
        "Unparseable credit limits: 0"
    )

    print(
        "Unparseable account opening dates: 0"
    )

    print(
        "Unparseable expiry dates: 0"
    )

    print(
        f"card_number present: "
        f"{'card_number' in cards.columns}"
    )

    print(
        f"cvv present: "
        f"{'cvv' in cards.columns}"
    )

    print(
        "Cards validation status: PASS"
    )


def validate_relationships(users, cards):
    """
    Recheck customer/card relationships after transformation.
    """

    print()
    print("VALIDATING CLEANED TABLE RELATIONSHIPS")

    user_ids = set(
        users["client_id"]
    )

    unknown_customer_refs = (
        ~cards["client_id"].isin(user_ids)
    ).sum()

    if unknown_customer_refs > 0:
        raise ValueError(
            f"{unknown_customer_refs:,} card rows reference "
            f"unknown customer IDs."
        )

    documented_counts = (
        users
        .set_index("client_id")["num_credit_cards"]
    )

    actual_counts = (
        cards
        .groupby("client_id")
        .size()
    )

    comparison = pd.concat(
        [
            documented_counts.rename("documented"),
            actual_counts.rename("actual")
        ],
        axis=1
    ).fillna(0)

    count_mismatches = (
        comparison["documented"]
        != comparison["actual"]
    ).sum()

    if count_mismatches > 0:
        raise ValueError(
            f"{count_mismatches:,} customers have "
            f"card-count inconsistencies after cleaning."
        )

    print(
        "Unknown customer references: 0"
    )

    print(
        "Customer/card count mismatches: 0"
    )

    print(
        "Relationship validation status: PASS"
    )


# ============================================================
# OUTPUT
# ============================================================

def save_outputs(users, cards):
    """Write cleaned interim datasets."""

    INTERIM_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    users.to_csv(
        USERS_OUTPUT_FILE,
        index=False
    )

    cards.to_csv(
        CARDS_OUTPUT_FILE,
        index=False
    )


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Clean and standardize users_data.csv "
            "and cards_data.csv."
        )
    )

    parser.add_argument(
        "--users",
        type=Path,
        default=DEFAULT_USERS_FILE,
        help="Path to users_data.csv"
    )

    parser.add_argument(
        "--cards",
        type=Path,
        default=DEFAULT_CARDS_FILE,
        help="Path to cards_data.csv"
    )

    args = parser.parse_args()

    users_file = args.users.resolve()
    cards_file = args.cards.resolve()

    validate_file_exists(users_file)
    validate_file_exists(cards_file)

    start_time = perf_counter()

    try:

        print("=" * 60)
        print("USERS AND CARDS CLEANING PIPELINE")
        print("=" * 60)
        print()

        # ----------------------------------------------------
        # Clean
        # ----------------------------------------------------

        users_cleaned = clean_users(
            users_file
        )

        cards_cleaned = clean_cards(
            cards_file
        )

        # ----------------------------------------------------
        # Validate
        # ----------------------------------------------------

        validate_cleaned_users(
            users_cleaned
        )

        validate_cleaned_cards(
            cards_cleaned
        )

        validate_relationships(
            users_cleaned,
            cards_cleaned
        )

        # ----------------------------------------------------
        # Save only after validation passes
        # ----------------------------------------------------

        save_outputs(
            users_cleaned,
            cards_cleaned
        )

        elapsed = perf_counter() - start_time

        print()
        print("=" * 60)
        print("CLEANING PIPELINE STATUS: PASS")
        print("=" * 60)

        print(
            f"users_cleaned.csv: "
            f"{USERS_OUTPUT_FILE}"
        )

        print(
            f"cards_cleaned.csv: "
            f"{CARDS_OUTPUT_FILE}"
        )

        print(
            f"Processing time: "
            f"{elapsed:.6f} seconds"
        )

    except Exception as error:

        print()
        print("=" * 60)
        print("CLEANING PIPELINE STATUS: FAIL")
        print("=" * 60)

        print(
            f"Error: {error}"
        )

        sys.exit(1)


if __name__ == "__main__":
    main()