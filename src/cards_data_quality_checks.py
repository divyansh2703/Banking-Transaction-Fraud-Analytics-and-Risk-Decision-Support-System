from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd


CARD_COLUMNS = (
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
)

USER_COLUMNS = (
    "id",
    "current_age",
    "birth_year",
    "num_credit_cards",
)


def parse_arguments() -> argparse.Namespace:
    """Read CSV paths supplied in the VS Code terminal."""
    parser = argparse.ArgumentParser(
        description="Run exact data quality checks on cards_data.csv."
    )
    parser.add_argument(
        "cards_csv_path",
        nargs="?",
        default="cards_data.csv",
        help="Path to cards_data.csv. Default: cards_data.csv",
    )
    parser.add_argument(
        "users_csv_path",
        nargs="?",
        default="users_data.csv",
        help="Path to users_data.csv. Default: users_data.csv",
    )
    return parser.parse_args()


def validate_columns(
    frame: pd.DataFrame,
    required_columns: tuple[str, ...],
    frame_name: str,
) -> None:
    """Stop if a required field is unavailable."""
    missing_columns = [
        column for column in required_columns if column not in frame.columns
    ]

    if missing_columns:
        raise KeyError(
            f"Required columns not found in {frame_name}: {missing_columns}"
        )


def normalized_text(series: pd.Series) -> pd.Series:
    """Return stripped text and represent blank strings as missing."""
    return series.astype("string").str.strip().replace("", pd.NA)


def normalized_key(series: pd.Series) -> pd.Series:
    """Normalize identifier text without changing the source DataFrame."""
    return normalized_text(series)


def category_counts(series: pd.Series) -> dict[str, int]:
    """Return exact counts for each nonblank observed category."""
    text = normalized_text(series)
    counts = text.dropna().value_counts(sort=False)
    return {
        str(category): int(count)
        for category, count in sorted(counts.items(), key=lambda item: str(item[0]))
    }


def numeric_series(series: pd.Series) -> tuple[pd.Series, int, int]:
    """Parse numeric values and return missing and nonnumeric counts."""
    text = normalized_text(series)
    converted = pd.to_numeric(text, errors="coerce")
    missing_count = int(text.isna().sum())
    nonnumeric_count = int((text.notna() & converted.isna()).sum())
    return converted, missing_count, nonnumeric_count


def parse_money_to_cents(
    series: pd.Series,
) -> tuple[pd.Series, int, int]:
    """Parse currency strings into exact integer cents for validation only."""
    cents = pd.Series(pd.NA, index=series.index, dtype="Int64")
    missing_count = 0
    invalid_count = 0

    for index, raw_value in series.items():
        if pd.isna(raw_value):
            missing_count += 1
            continue

        text = str(raw_value).strip()
        if text == "":
            missing_count += 1
            continue

        cleaned = text.replace("$", "").replace(",", "").strip()

        try:
            amount = Decimal(cleaned)
        except InvalidOperation:
            invalid_count += 1
            continue

        if not amount.is_finite():
            invalid_count += 1
            continue

        amount_in_cents = amount * Decimal(100)
        if amount_in_cents != amount_in_cents.to_integral_value():
            invalid_count += 1
            continue

        cents.loc[index] = int(amount_in_cents)

    return cents, missing_count, invalid_count


def format_cents(value: int | None) -> str:
    """Format exact integer cents without floating point conversion."""
    if value is None:
        return "Not available"

    sign = "-" if value < 0 else ""
    absolute_value = abs(value)
    dollars, cents = divmod(absolute_value, 100)
    return f"{sign}${dollars}.{cents:02d}"


def parse_month_year(
    series: pd.Series,
) -> tuple[pd.Series, int, int]:
    """Parse exact MM/YYYY values and return missing and invalid counts."""
    text = normalized_text(series)
    format_mask = text.str.fullmatch(r"(?:0[1-9]|1[0-2])/\d{4}", na=False)

    parsed = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    if bool(format_mask.any()):
        parsed.loc[format_mask] = pd.to_datetime(
            text.loc[format_mask],
            format="%m/%Y",
            errors="coerce",
        )

    missing_count = int(text.isna().sum())
    invalid_count = int((text.notna() & parsed.isna()).sum())
    return parsed, missing_count, invalid_count


def month_number(parsed_dates: pd.Series) -> pd.Series:
    """Convert parsed months to a comparable exact integer month number."""
    values = pd.Series(pd.NA, index=parsed_dates.index, dtype="Int64")
    valid_mask = parsed_dates.notna()

    if bool(valid_mask.any()):
        values.loc[valid_mask] = (
            parsed_dates.loc[valid_mask].dt.year * 12
            + parsed_dates.loc[valid_mask].dt.month
        ).astype("int64")

    return values


def infer_reference_year(users_data: pd.DataFrame) -> int:
    """Infer the customer snapshot year from birth year and current age."""
    current_age, _, age_nonnumeric = numeric_series(users_data["current_age"])
    birth_year, _, year_nonnumeric = numeric_series(users_data["birth_year"])

    if age_nonnumeric > 0 or year_nonnumeric > 0:
        raise ValueError(
            "The customer reference year cannot be inferred because current_age "
            "or birth_year contains nonnumeric values."
        )

    complete_mask = current_age.notna() & birth_year.notna()
    implied_year = current_age.loc[complete_mask] + birth_year.loc[complete_mask]

    if implied_year.empty:
        raise ValueError(
            "The customer reference year cannot be inferred because no complete "
            "current_age and birth_year pairs are available."
        )

    if bool(implied_year.mod(1).ne(0).any()):
        raise ValueError(
            "The customer reference year cannot be inferred because some implied "
            "years are not whole numbers."
        )

    implied_year = implied_year.astype("int64")
    observed_years = sorted(int(value) for value in implied_year.unique())
    reference_year = max(observed_years)

    if not set(observed_years).issubset({reference_year - 1, reference_year}):
        exact_counts = implied_year.value_counts().sort_index().to_dict()
        raise ValueError(
            "The customer reference year is ambiguous. Implied year counts: "
            f"{exact_counts}"
        )

    return reference_year


def run_quality_checks(
    cards_data: pd.DataFrame,
    users_data: pd.DataFrame,
) -> dict[str, int | str | dict[str, int]]:
    """Calculate every requested card validity and consistency result."""
    if cards_data.empty:
        raise ValueError("cards_data contains no rows.")
    if users_data.empty:
        raise ValueError("users_data contains no rows.")

    validate_columns(cards_data, CARD_COLUMNS, "cards_data")
    validate_columns(users_data, USER_COLUMNS, "users_data")

    card_id = normalized_key(cards_data["id"])
    card_client_id = normalized_key(cards_data["client_id"])
    user_id = normalized_key(users_data["id"])

    valid_card_id = card_id.dropna()
    valid_card_client_id = card_client_id.dropna()
    valid_user_id = user_id.dropna()

    user_id_set = set(valid_user_id)
    unknown_customer_mask = (
        card_client_id.notna() & ~card_client_id.isin(user_id_set)
    )

    card_number = normalized_text(cards_data["card_number"])
    card_number_digit_mask = card_number.str.fullmatch(r"\d+", na=False)
    card_number_length_mask = card_number.str.len().isin([15, 16])

    cvv = normalized_text(cards_data["cvv"])
    cvv_digit_mask = cvv.str.fullmatch(r"\d+", na=False)
    cvv_length_mask = cvv.str.len().isin([3, 4])

    has_chip = normalized_text(cards_data["has_chip"])
    has_chip_normalized = has_chip.str.casefold()
    valid_yes_no = {"yes", "no"}

    dark_web = normalized_text(cards_data["card_on_dark_web"])
    dark_web_normalized = dark_web.str.casefold()

    num_cards_issued, issued_missing, issued_nonnumeric = numeric_series(
        cards_data["num_cards_issued"]
    )
    issued_noninteger = int(
        (num_cards_issued.notna() & num_cards_issued.mod(1).ne(0)).sum()
    )

    credit_limit_cents, limit_missing, limit_invalid = parse_money_to_cents(
        cards_data["credit_limit"]
    )
    valid_limits = credit_limit_cents.dropna()
    maximum_credit_limit = (
        int(valid_limits.max()) if not valid_limits.empty else None
    )

    expiry_date, expiry_missing, expiry_invalid = parse_month_year(
        cards_data["expires"]
    )
    open_date, open_missing, open_invalid = parse_month_year(
        cards_data["acct_open_date"]
    )
    expiry_month = month_number(expiry_date)
    open_month = month_number(open_date)

    pin_year, pin_missing, pin_nonnumeric = numeric_series(
        cards_data["year_pin_last_changed"]
    )
    pin_noninteger = int((pin_year.notna() & pin_year.mod(1).ne(0)).sum())

    reference_year = infer_reference_year(users_data)

    user_birth_year, _, _ = numeric_series(users_data["birth_year"])
    birth_year_by_user = pd.Series(
        user_birth_year.to_numpy(),
        index=user_id,
    )
    birth_year_by_user = birth_year_by_user[
        ~birth_year_by_user.index.isna()
    ]
    birth_year_by_user = birth_year_by_user[
        ~birth_year_by_user.index.duplicated(keep="first")
    ]
    card_customer_birth_year = card_client_id.map(birth_year_by_user)

    actual_cards_per_customer = valid_card_client_id.value_counts()
    documented_cards, documented_missing, documented_nonnumeric = numeric_series(
        users_data["num_credit_cards"]
    )
    actual_card_count_for_user = user_id.map(actual_cards_per_customer).fillna(0)
    comparable_count_mask = (
        user_id.notna()
        & documented_cards.notna()
        & documented_cards.mod(1).eq(0)
    )
    documented_count_mismatch = int(
        (
            comparable_count_mask
            & documented_cards.ne(actual_card_count_for_user)
        ).sum()
    )

    valid_documented_counts = documented_cards.dropna()
    total_documented_cards: int | str
    if documented_missing == 0 and documented_nonnumeric == 0:
        total_documented_cards = int(valid_documented_counts.sum())
    else:
        total_documented_cards = "Not available due to invalid user counts"

    duplicate_card_numbers = int(
        card_number.dropna().duplicated(keep="first").sum()
    )

    maximum_cards_per_customer = (
        int(actual_cards_per_customer.max())
        if not actual_cards_per_customer.empty
        else 0
    )

    return {
        "Rows": int(len(cards_data)),
        "Null card IDs": int(card_id.isna().sum()),
        "Duplicate card IDs beyond first": int(
            valid_card_id.duplicated(keep="first").sum()
        ),
        "Null customer IDs": int(card_client_id.isna().sum()),
        "Unknown customer ID references": int(unknown_customer_mask.sum()),
        "Duplicate customer IDs in users_data beyond first": int(
            valid_user_id.duplicated(keep="first").sum()
        ),
        "Total documented cards in users_data": total_documented_cards,
        "Total card rows in cards_data": int(len(cards_data)),
        "Customers whose documented card count differs": (
            documented_count_mismatch
        ),
        "Maximum cards linked to one customer": maximum_cards_per_customer,
        "Missing card numbers": int(card_number.isna().sum()),
        "Nondigit card numbers": int(
            (card_number.notna() & ~card_number_digit_mask).sum()
        ),
        "Card number lengths outside 15 or 16 digits": int(
            (card_number.notna() & ~card_number_length_mask).sum()
        ),
        "Duplicate card number occurrences beyond first": duplicate_card_numbers,
        "Missing CVVs": int(cvv.isna().sum()),
        "Nondigit CVVs": int((cvv.notna() & ~cvv_digit_mask).sum()),
        "CVV lengths outside 3 or 4 digits": int(
            (cvv.notna() & ~cvv_length_mask).sum()
        ),
        "Observed card brands": category_counts(cards_data["card_brand"]),
        "Blank card brands": int(
            normalized_text(cards_data["card_brand"]).isna().sum()
        ),
        "Observed card types": category_counts(cards_data["card_type"]),
        "Blank card types": int(
            normalized_text(cards_data["card_type"]).isna().sum()
        ),
        "Missing has_chip values": int(has_chip.isna().sum()),
        "Invalid has_chip values": int(
            (has_chip.notna() & ~has_chip_normalized.isin(valid_yes_no)).sum()
        ),
        "Missing card_on_dark_web values": int(dark_web.isna().sum()),
        "Invalid card_on_dark_web values": int(
            (dark_web.notna() & ~dark_web_normalized.isin(valid_yes_no)).sum()
        ),
        "Missing num_cards_issued": issued_missing,
        "Nonnumeric num_cards_issued": issued_nonnumeric,
        "Noninteger num_cards_issued": issued_noninteger,
        "Cards with num_cards_issued <= 0": int(
            num_cards_issued.le(0).sum()
        ),
        "Maximum num_cards_issued": (
            int(num_cards_issued.max())
            if not num_cards_issued.dropna().empty
            else "Not available"
        ),
        "Missing credit limits": limit_missing,
        "Unparseable credit limits": limit_invalid,
        "Credit limits <= 0": int(credit_limit_cents.le(0).sum()),
        "Maximum credit limit": format_cents(maximum_credit_limit),
        "Missing expiry values": expiry_missing,
        "Invalid expiry MM/YYYY values": expiry_invalid,
        "Missing account opening values": open_missing,
        "Invalid account opening MM/YYYY values": open_invalid,
        "Cards expiring before account opening month": int(
            (expiry_month.notna() & open_month.notna() & expiry_month.lt(open_month)).sum()
        ),
        "Accounts opened after customer reference year": int(
            (open_date.notna() & open_date.dt.year.gt(reference_year)).sum()
        ),
        "Accounts opened before customer birth year": int(
            (
                open_date.notna()
                & card_customer_birth_year.notna()
                & open_date.dt.year.lt(card_customer_birth_year)
            ).sum()
        ),
        "Missing PIN change years": pin_missing,
        "Nonnumeric PIN change years": pin_nonnumeric,
        "Noninteger PIN change years": pin_noninteger,
        "PIN change year before account opening year": int(
            (
                pin_year.notna()
                & open_date.notna()
                & pin_year.lt(open_date.dt.year)
            ).sum()
        ),
        "PIN change year after customer reference year": int(
            pin_year.gt(reference_year).sum()
        ),
        "Dataset customer reference year": reference_year,
    }


def print_results(results: dict[str, int | str | dict[str, int]]) -> None:
    """Print the exact results in project sections."""
    print("CARDS DATA QUALITY CHECKS")
    print()
    print("A. IDENTIFIERS AND CUSTOMER RELATIONSHIPS")
    for label in (
        "Rows",
        "Null card IDs",
        "Duplicate card IDs beyond first",
        "Null customer IDs",
        "Unknown customer ID references",
        "Duplicate customer IDs in users_data beyond first",
        "Total documented cards in users_data",
        "Total card rows in cards_data",
        "Customers whose documented card count differs",
        "Maximum cards linked to one customer",
    ):
        print(f"{label}: {results[label]}")

    print()
    print("B. CARD NUMBER AND CVV FORMAT")
    for label in (
        "Missing card numbers",
        "Nondigit card numbers",
        "Card number lengths outside 15 or 16 digits",
        "Duplicate card number occurrences beyond first",
        "Missing CVVs",
        "Nondigit CVVs",
        "CVV lengths outside 3 or 4 digits",
    ):
        print(f"{label}: {results[label]}")

    print()
    print("C. CATEGORICAL VALIDITY")
    for label in (
        "Observed card brands",
        "Blank card brands",
        "Observed card types",
        "Blank card types",
        "Missing has_chip values",
        "Invalid has_chip values",
        "Missing card_on_dark_web values",
        "Invalid card_on_dark_web values",
    ):
        print(f"{label}: {results[label]}")

    print()
    print("D. ISSUANCE AND CREDIT LIMIT VALIDITY")
    for label in (
        "Missing num_cards_issued",
        "Nonnumeric num_cards_issued",
        "Noninteger num_cards_issued",
        "Cards with num_cards_issued <= 0",
        "Maximum num_cards_issued",
        "Missing credit limits",
        "Unparseable credit limits",
        "Credit limits <= 0",
        "Maximum credit limit",
    ):
        print(f"{label}: {results[label]}")

    print()
    print("E. DATE CONSISTENCY")
    for label in (
        "Missing expiry values",
        "Invalid expiry MM/YYYY values",
        "Missing account opening values",
        "Invalid account opening MM/YYYY values",
        "Cards expiring before account opening month",
        "Accounts opened after customer reference year",
        "Accounts opened before customer birth year",
        "Missing PIN change years",
        "Nonnumeric PIN change years",
        "Noninteger PIN change years",
        "PIN change year before account opening year",
        "PIN change year after customer reference year",
        "Dataset customer reference year",
    ):
        print(f"{label}: {results[label]}")


def read_inputs(
    cards_path: Path,
    users_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read card and customer CSVs while preserving identifier text."""
    if not cards_path.is_file():
        raise FileNotFoundError(f"Cards CSV file not found: {cards_path.resolve()}")
    if not users_path.is_file():
        raise FileNotFoundError(f"Users CSV file not found: {users_path.resolve()}")

    cards_data = pd.read_csv(
        cards_path,
        dtype={
            "id": "string",
            "client_id": "string",
            "card_number": "string",
            "cvv": "string",
            "expires": "string",
            "acct_open_date": "string",
        },
        low_memory=False,
    )
    users_data = pd.read_csv(
        users_path,
        dtype={"id": "string"},
        low_memory=False,
    )
    return cards_data, users_data


def main() -> None:
    """Load inputs, run checks and print the exact results."""
    arguments = parse_arguments()
    cards_path = Path(arguments.cards_csv_path).expanduser()
    users_path = Path(arguments.users_csv_path).expanduser()

    cards_data, users_data = read_inputs(cards_path, users_path)
    results = run_quality_checks(cards_data, users_data)
    print_results(results)


if __name__ == "__main__":
    main()