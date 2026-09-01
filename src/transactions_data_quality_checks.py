
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


TRANSACTION_COLUMNS = (
    "id",
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
)

CARD_COLUMNS = (
    "id",
    "client_id",
    "expires",
    "acct_open_date",
)

USER_COLUMNS = ("id",)

ALLOWED_USE_CHIP_VALUES = {
    "swipe transaction",
    "online transaction",
    "chip transaction",
}


@dataclass(frozen=True)
class ReferenceData:
    """Small lookup structures used for cross table validation."""

    user_ids: set[str]
    card_to_client: dict[str, str]
    card_open_month: dict[str, int]
    card_expiry_month: dict[str, int]


@dataclass
class TransactionAccumulator:
    """Exact counters accumulated while transaction chunks are processed."""

    rows: int = 0
    missing_transaction_ids: int = 0
    invalid_transaction_id_format: int = 0
    transaction_id_arrays: list[np.ndarray] = field(default_factory=list)
    minimum_transaction_id: int | None = None
    maximum_transaction_id: int | None = None

    missing_client_ids: int = 0
    unknown_client_ids: int = 0
    missing_card_ids: int = 0
    unknown_card_ids: int = 0
    card_client_mismatches: int = 0

    missing_dates: int = 0
    invalid_dates: int = 0
    earliest_date: pd.Timestamp | None = None
    latest_date: pd.Timestamp | None = None
    transactions_before_card_open: int = 0
    transactions_after_card_expiry: int = 0

    missing_amounts: int = 0
    invalid_amounts: int = 0
    negative_amounts: int = 0
    zero_amounts: int = 0
    positive_amounts: int = 0
    minimum_amount_cents: int | None = None
    maximum_amount_cents: int | None = None

    missing_use_chip: int = 0
    invalid_use_chip: int = 0
    use_chip_counts: Counter[str] = field(default_factory=Counter)

    missing_merchant_ids: int = 0
    missing_merchant_cities: int = 0
    missing_merchant_states: int = 0
    missing_zip_values: int = 0
    missing_mcc_values: int = 0
    invalid_mcc_format: int = 0

    rows_with_recorded_errors: int = 0
    error_value_counts: Counter[str] = field(default_factory=Counter)


def parse_arguments() -> argparse.Namespace:
    """Read input paths and the optional chunk size."""
    parser = argparse.ArgumentParser(
        description=(
            "Run exact chunked data quality checks on transactions_data.csv."
        )
    )
    parser.add_argument(
        "transactions_csv_path",
        nargs="?",
        default="transactions_data.csv",
        help="Path to transactions_data.csv.",
    )
    parser.add_argument(
        "cards_csv_path",
        nargs="?",
        default="cards_data.csv",
        help="Path to cards_data.csv.",
    )
    parser.add_argument(
        "users_csv_path",
        nargs="?",
        default="users_data.csv",
        help="Path to users_data.csv.",
    )
    parser.add_argument(
        "chunk_size",
        nargs="?",
        type=int,
        default=500_000,
        help="Rows processed per chunk. Default: 500000.",
    )
    return parser.parse_args()


def validate_columns(
    frame: pd.DataFrame,
    required_columns: tuple[str, ...],
    frame_name: str,
) -> None:
    """Stop if any required field is unavailable."""
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


def parse_month_year(series: pd.Series) -> pd.Series:
    """Parse exact MM/YYYY values for cross table month comparisons."""
    text = normalized_text(series)
    format_mask = text.str.fullmatch(r"(?:0[1-9]|1[0-2])/\d{4}", na=False)
    parsed = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")

    if bool(format_mask.any()):
        parsed.loc[format_mask] = pd.to_datetime(
            text.loc[format_mask],
            format="%m/%Y",
            errors="coerce",
        )

    return parsed


def to_month_number(parsed_dates: pd.Series) -> pd.Series:
    """Convert dates to exact year and month integers for comparison."""
    result = pd.Series(pd.NA, index=parsed_dates.index, dtype="Int64")
    valid_mask = parsed_dates.notna()

    if bool(valid_mask.any()):
        result.loc[valid_mask] = (
            parsed_dates.loc[valid_mask].dt.year * 12
            + parsed_dates.loc[valid_mask].dt.month
        ).astype("int64")

    return result


def parse_transaction_dates(
    series: pd.Series,
) -> tuple[pd.Series, int, int]:
    """Parse timestamps while retaining exact missing and invalid counts."""
    text = normalized_text(series)
    parsed = pd.to_datetime(
        text,
        format="%Y-%m-%d %H:%M:%S",
        errors="coerce",
    )

    fallback_mask = text.notna() & parsed.isna()
    if bool(fallback_mask.any()):
        parsed.loc[fallback_mask] = pd.to_datetime(
            text.loc[fallback_mask],
            errors="coerce",
        )

    missing_count = int(text.isna().sum())
    invalid_count = int((text.notna() & parsed.isna()).sum())
    return parsed, missing_count, invalid_count


def parse_money_to_cents(
    series: pd.Series,
) -> tuple[pd.Series, int, int]:
    """Parse monetary strings into exact integer cents without floats."""
    text = normalized_text(series)
    cleaned = (
        text.str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.strip()
    )

    valid_format = cleaned.str.fullmatch(
        r"[+-]?(?:\d+(?:\.\d{1,2})?|\.\d{1,2})",
        na=False,
    )

    cents = pd.Series(pd.NA, index=series.index, dtype="Int64")

    if bool(valid_format.any()):
        valid_text = cleaned.loc[valid_format]
        negative_mask = valid_text.str.startswith("-")
        unsigned_text = valid_text.str.lstrip("+-")
        parts = unsigned_text.str.split(".", n=1, expand=True)

        whole_text = parts.iloc[:, 0].replace("", "0")
        if parts.shape[1] == 1:
            fraction_text = pd.Series("00", index=whole_text.index)
        else:
            fraction_text = (
                parts.iloc[:, 1]
                .fillna("")
                .str.pad(width=2, side="right", fillchar="0")
            )

        whole_cents = pd.to_numeric(whole_text, errors="raise").astype("int64") * 100
        fraction_cents = pd.to_numeric(
            fraction_text,
            errors="raise",
        ).astype("int64")
        exact_cents = whole_cents + fraction_cents
        exact_cents.loc[negative_mask] = -exact_cents.loc[negative_mask]
        cents.loc[valid_format] = exact_cents.to_numpy(dtype="int64")

    missing_count = int(text.isna().sum())
    invalid_count = int((text.notna() & ~valid_format).sum())
    return cents, missing_count, invalid_count


def format_cents(value: int | None) -> str:
    """Format exact integer cents without floating point conversion."""
    if value is None:
        return "Not available"

    sign = "-" if value < 0 else ""
    absolute_value = abs(value)
    dollars, cents = divmod(absolute_value, 100)
    return f"{sign}${dollars}.{cents:02d}"


def exact_category_counts(counter: Counter[str]) -> dict[str, int]:
    """Return a stable dictionary of exact category counts."""
    return {
        category: int(counter[category])
        for category in sorted(counter)
    }


def update_minimum(
    current_value: int | None,
    candidate: int,
) -> int:
    """Update an exact integer minimum."""
    return candidate if current_value is None else min(current_value, candidate)


def update_maximum(
    current_value: int | None,
    candidate: int,
) -> int:
    """Update an exact integer maximum."""
    return candidate if current_value is None else max(current_value, candidate)


def load_reference_data(
    cards_path: Path,
    users_path: Path,
) -> ReferenceData:
    """Load the small card and customer reference tables."""
    if not cards_path.is_file():
        raise FileNotFoundError(f"Cards CSV file not found: {cards_path.resolve()}")
    if not users_path.is_file():
        raise FileNotFoundError(f"Users CSV file not found: {users_path.resolve()}")

    cards_data = pd.read_csv(
        cards_path,
        usecols=list(CARD_COLUMNS),
        dtype={
            "id": "string",
            "client_id": "string",
            "expires": "string",
            "acct_open_date": "string",
        },
        low_memory=False,
    )
    users_data = pd.read_csv(
        users_path,
        usecols=list(USER_COLUMNS),
        dtype={"id": "string"},
        low_memory=False,
    )

    validate_columns(cards_data, CARD_COLUMNS, "cards_data")
    validate_columns(users_data, USER_COLUMNS, "users_data")

    card_id = normalized_text(cards_data["id"])
    card_client_id = normalized_text(cards_data["client_id"])
    user_id = normalized_text(users_data["id"])

    duplicate_card_id_count = int(
        card_id.dropna().duplicated(keep="first").sum()
    )
    duplicate_user_id_count = int(
        user_id.dropna().duplicated(keep="first").sum()
    )

    if duplicate_card_id_count > 0:
        raise ValueError(
            "cards_data contains duplicate card IDs. Run and resolve the card "
            "quality assessment before transaction relationship checks."
        )
    if duplicate_user_id_count > 0:
        raise ValueError(
            "users_data contains duplicate customer IDs. Run and resolve the "
            "customer quality assessment before transaction relationship checks."
        )

    reference_frame = pd.DataFrame(
        {
            "card_id": card_id,
            "client_id": card_client_id,
            "open_date": parse_month_year(cards_data["acct_open_date"]),
            "expiry_date": parse_month_year(cards_data["expires"]),
        }
    )
    reference_frame = reference_frame.loc[
        reference_frame["card_id"].notna()
    ].copy()

    reference_frame["open_month"] = to_month_number(
        reference_frame["open_date"]
    )
    reference_frame["expiry_month"] = to_month_number(
        reference_frame["expiry_date"]
    )

    card_to_client = (
        reference_frame.dropna(subset=["client_id"])
        .set_index("card_id")["client_id"]
        .astype(str)
        .to_dict()
    )
    card_open_month = (
        reference_frame.dropna(subset=["open_month"])
        .set_index("card_id")["open_month"]
        .astype("int64")
        .to_dict()
    )
    card_expiry_month = (
        reference_frame.dropna(subset=["expiry_month"])
        .set_index("card_id")["expiry_month"]
        .astype("int64")
        .to_dict()
    )

    return ReferenceData(
        user_ids=set(user_id.dropna().astype(str)),
        card_to_client=card_to_client,
        card_open_month=card_open_month,
        card_expiry_month=card_expiry_month,
    )


def update_transaction_id_checks(
    transaction_id: pd.Series,
    accumulator: TransactionAccumulator,
) -> None:
    """Validate IDs and retain compact arrays for an exact duplicate check."""
    text = normalized_text(transaction_id)
    valid_format = text.str.fullmatch(r"\d+", na=False)

    accumulator.missing_transaction_ids += int(text.isna().sum())
    accumulator.invalid_transaction_id_format += int(
        (text.notna() & ~valid_format).sum()
    )

    if bool(valid_format.any()):
        numeric_ids = text.loc[valid_format].astype("int64").to_numpy(copy=True)
        accumulator.transaction_id_arrays.append(numeric_ids)

        chunk_minimum = int(numeric_ids.min())
        chunk_maximum = int(numeric_ids.max())
        accumulator.minimum_transaction_id = update_minimum(
            accumulator.minimum_transaction_id,
            chunk_minimum,
        )
        accumulator.maximum_transaction_id = update_maximum(
            accumulator.maximum_transaction_id,
            chunk_maximum,
        )


def update_relationship_checks(
    client_id: pd.Series,
    card_id: pd.Series,
    reference_data: ReferenceData,
    accumulator: TransactionAccumulator,
) -> tuple[pd.Series, pd.Series]:
    """Validate customer and card foreign keys plus card ownership."""
    client_key = normalized_text(client_id)
    card_key = normalized_text(card_id)

    accumulator.missing_client_ids += int(client_key.isna().sum())
    accumulator.missing_card_ids += int(card_key.isna().sum())
    accumulator.unknown_client_ids += int(
        (client_key.notna() & ~client_key.isin(reference_data.user_ids)).sum()
    )

    known_card_ids = set(reference_data.card_to_client)
    accumulator.unknown_card_ids += int(
        (card_key.notna() & ~card_key.isin(known_card_ids)).sum()
    )

    expected_client = card_key.map(reference_data.card_to_client)
    comparable_mask = (
        card_key.notna()
        & expected_client.notna()
        & client_key.notna()
    )
    accumulator.card_client_mismatches += int(
        (comparable_mask & client_key.ne(expected_client)).sum()
    )

    return client_key, card_key


def update_date_checks(
    raw_dates: pd.Series,
    card_key: pd.Series,
    reference_data: ReferenceData,
    accumulator: TransactionAccumulator,
) -> None:
    """Validate timestamps and compare them with card lifecycle months."""
    parsed_dates, missing_count, invalid_count = parse_transaction_dates(raw_dates)
    accumulator.missing_dates += missing_count
    accumulator.invalid_dates += invalid_count

    valid_dates = parsed_dates.dropna()
    if not valid_dates.empty:
        chunk_earliest = valid_dates.min()
        chunk_latest = valid_dates.max()

        if accumulator.earliest_date is None:
            accumulator.earliest_date = chunk_earliest
        else:
            accumulator.earliest_date = min(
                accumulator.earliest_date,
                chunk_earliest,
            )

        if accumulator.latest_date is None:
            accumulator.latest_date = chunk_latest
        else:
            accumulator.latest_date = max(
                accumulator.latest_date,
                chunk_latest,
            )

    transaction_month = pd.Series(
        pd.NA,
        index=parsed_dates.index,
        dtype="Int64",
    )
    valid_date_mask = parsed_dates.notna()
    if bool(valid_date_mask.any()):
        transaction_month.loc[valid_date_mask] = (
            parsed_dates.loc[valid_date_mask].dt.year * 12
            + parsed_dates.loc[valid_date_mask].dt.month
        ).astype("int64")

    card_open_month = card_key.map(reference_data.card_open_month)
    card_expiry_month = card_key.map(reference_data.card_expiry_month)

    accumulator.transactions_before_card_open += int(
        (
            transaction_month.notna()
            & card_open_month.notna()
            & transaction_month.lt(card_open_month)
        ).sum()
    )
    accumulator.transactions_after_card_expiry += int(
        (
            transaction_month.notna()
            & card_expiry_month.notna()
            & transaction_month.gt(card_expiry_month)
        ).sum()
    )


def update_amount_checks(
    raw_amounts: pd.Series,
    accumulator: TransactionAccumulator,
) -> None:
    """Validate exact transaction amounts and classify their signs."""
    amount_cents, missing_count, invalid_count = parse_money_to_cents(raw_amounts)
    accumulator.missing_amounts += missing_count
    accumulator.invalid_amounts += invalid_count

    accumulator.negative_amounts += int(amount_cents.lt(0).sum())
    accumulator.zero_amounts += int(amount_cents.eq(0).sum())
    accumulator.positive_amounts += int(amount_cents.gt(0).sum())

    valid_amounts = amount_cents.dropna()
    if not valid_amounts.empty:
        chunk_minimum = int(valid_amounts.min())
        chunk_maximum = int(valid_amounts.max())
        accumulator.minimum_amount_cents = update_minimum(
            accumulator.minimum_amount_cents,
            chunk_minimum,
        )
        accumulator.maximum_amount_cents = update_maximum(
            accumulator.maximum_amount_cents,
            chunk_maximum,
        )


def update_category_and_merchant_checks(
    chunk: pd.DataFrame,
    accumulator: TransactionAccumulator,
) -> None:
    """Validate transaction categories and merchant context fields."""
    use_chip = normalized_text(chunk["use_chip"])
    use_chip_normalized = use_chip.str.casefold()
    accumulator.missing_use_chip += int(use_chip.isna().sum())
    accumulator.invalid_use_chip += int(
        (
            use_chip.notna()
            & ~use_chip_normalized.isin(ALLOWED_USE_CHIP_VALUES)
        ).sum()
    )
    accumulator.use_chip_counts.update(
        {
            str(category): int(count)
            for category, count in use_chip.dropna().value_counts(sort=False).items()
        }
    )

    merchant_id = normalized_text(chunk["merchant_id"])
    merchant_city = normalized_text(chunk["merchant_city"])
    merchant_state = normalized_text(chunk["merchant_state"])
    zip_value = normalized_text(chunk["zip"])
    mcc = normalized_text(chunk["mcc"])

    accumulator.missing_merchant_ids += int(merchant_id.isna().sum())
    accumulator.missing_merchant_cities += int(merchant_city.isna().sum())
    accumulator.missing_merchant_states += int(merchant_state.isna().sum())
    accumulator.missing_zip_values += int(zip_value.isna().sum())
    accumulator.missing_mcc_values += int(mcc.isna().sum())
    accumulator.invalid_mcc_format += int(
        (mcc.notna() & ~mcc.str.fullmatch(r"\d{4}", na=False)).sum()
    )

    errors = normalized_text(chunk["errors"])
    recorded_errors = errors.dropna()
    accumulator.rows_with_recorded_errors += int(recorded_errors.shape[0])
    accumulator.error_value_counts.update(
        {
            str(error_value): int(count)
            for error_value, count in recorded_errors.value_counts(sort=False).items()
        }
    )


def calculate_duplicate_transaction_ids(
    id_arrays: list[np.ndarray],
) -> tuple[int, int, int]:
    """Return exact duplicate excess, repeated groups and participating rows."""
    if not id_arrays:
        return 0, 0, 0

    all_ids = np.concatenate(id_arrays)
    id_arrays.clear()
    all_ids.sort(kind="quicksort")

    if all_ids.size < 2:
        return 0, 0, 0

    group_starts = np.concatenate(
        (
            np.array([0], dtype=np.int64),
            np.flatnonzero(all_ids[1:] != all_ids[:-1]) + 1,
        )
    )
    group_ends = np.concatenate(
        (group_starts[1:], np.array([all_ids.size], dtype=np.int64))
    )
    group_sizes = group_ends - group_starts
    repeated_sizes = group_sizes[group_sizes > 1]

    duplicate_excess = int((repeated_sizes - 1).sum())
    repeated_groups = int(repeated_sizes.size)
    participating_rows = int(repeated_sizes.sum())
    return duplicate_excess, repeated_groups, participating_rows


def process_transaction_chunks(
    chunks: Iterable[pd.DataFrame],
    reference_data: ReferenceData,
    show_progress: bool = True,
) -> dict[str, int | str | dict[str, int]]:
    """Process transaction chunks and return all exact results."""
    accumulator = TransactionAccumulator()
    received_a_chunk = False

    for chunk_number, chunk in enumerate(chunks, start=1):
        received_a_chunk = True
        validate_columns(chunk, TRANSACTION_COLUMNS, "transactions_data")
        accumulator.rows += int(len(chunk))

        update_transaction_id_checks(chunk["id"], accumulator)
        _, card_key = update_relationship_checks(
            chunk["client_id"],
            chunk["card_id"],
            reference_data,
            accumulator,
        )
        update_date_checks(
            chunk["date"],
            card_key,
            reference_data,
            accumulator,
        )
        update_amount_checks(chunk["amount"], accumulator)
        update_category_and_merchant_checks(chunk, accumulator)

        if show_progress:
            print(
                f"Processed chunk {chunk_number}: "
                f"{accumulator.rows} total rows"
            )

    if not received_a_chunk or accumulator.rows == 0:
        raise ValueError("transactions_data contains no rows.")

    (
        duplicate_id_excess,
        repeated_id_groups,
        rows_in_repeated_id_groups,
    ) = calculate_duplicate_transaction_ids(accumulator.transaction_id_arrays)

    earliest_date = (
        accumulator.earliest_date.strftime("%Y-%m-%d %H:%M:%S")
        if accumulator.earliest_date is not None
        else "Not available"
    )
    latest_date = (
        accumulator.latest_date.strftime("%Y-%m-%d %H:%M:%S")
        if accumulator.latest_date is not None
        else "Not available"
    )

    return {
        "Rows processed": accumulator.rows,
        "Missing transaction IDs": accumulator.missing_transaction_ids,
        "Invalid transaction ID formats": (
            accumulator.invalid_transaction_id_format
        ),
        "Minimum valid transaction ID": (
            accumulator.minimum_transaction_id
            if accumulator.minimum_transaction_id is not None
            else "Not available"
        ),
        "Maximum valid transaction ID": (
            accumulator.maximum_transaction_id
            if accumulator.maximum_transaction_id is not None
            else "Not available"
        ),
        "Duplicate transaction ID occurrences beyond first": duplicate_id_excess,
        "Repeated transaction ID groups": repeated_id_groups,
        "Rows participating in repeated transaction ID groups": (
            rows_in_repeated_id_groups
        ),
        "Missing customer IDs": accumulator.missing_client_ids,
        "Unknown customer ID references": accumulator.unknown_client_ids,
        "Missing card IDs": accumulator.missing_card_ids,
        "Unknown card ID references": accumulator.unknown_card_ids,
        "Card and customer ownership mismatches": (
            accumulator.card_client_mismatches
        ),
        "Missing transaction dates": accumulator.missing_dates,
        "Unparseable transaction dates": accumulator.invalid_dates,
        "Earliest valid transaction date": earliest_date,
        "Latest valid transaction date": latest_date,
        "Transactions before card opening month": (
            accumulator.transactions_before_card_open
        ),
        "Transactions after card expiry month": (
            accumulator.transactions_after_card_expiry
        ),
        "Missing transaction amounts": accumulator.missing_amounts,
        "Unparseable transaction amounts": accumulator.invalid_amounts,
        "Negative transaction amounts": accumulator.negative_amounts,
        "Zero transaction amounts": accumulator.zero_amounts,
        "Positive transaction amounts": accumulator.positive_amounts,
        "Minimum valid transaction amount": format_cents(
            accumulator.minimum_amount_cents
        ),
        "Maximum valid transaction amount": format_cents(
            accumulator.maximum_amount_cents
        ),
        "Allowed use_chip categories": (
            "Chip Transaction, Online Transaction, Swipe Transaction"
        ),
        "Missing use_chip values": accumulator.missing_use_chip,
        "Invalid use_chip values": accumulator.invalid_use_chip,
        "Observed use_chip categories": exact_category_counts(
            accumulator.use_chip_counts
        ),
        "Missing merchant IDs": accumulator.missing_merchant_ids,
        "Missing merchant cities": accumulator.missing_merchant_cities,
        "Missing merchant states, context only": (
            accumulator.missing_merchant_states
        ),
        "Missing ZIP values, context only": accumulator.missing_zip_values,
        "Missing MCC values": accumulator.missing_mcc_values,
        "MCC values not formatted as four digits": (
            accumulator.invalid_mcc_format
        ),
        "Rows with recorded transaction errors": (
            accumulator.rows_with_recorded_errors
        ),
        "Observed error values": exact_category_counts(
            accumulator.error_value_counts
        ),
    }


def print_results(results: dict[str, int | str | dict[str, int]]) -> None:
    """Print results in compact project sections."""
    print()
    print("TRANSACTIONS DATA QUALITY CHECKS")

    sections = {
        "A. IDENTIFIER UNIQUENESS": (
            "Rows processed",
            "Missing transaction IDs",
            "Invalid transaction ID formats",
            "Minimum valid transaction ID",
            "Maximum valid transaction ID",
            "Duplicate transaction ID occurrences beyond first",
            "Repeated transaction ID groups",
            "Rows participating in repeated transaction ID groups",
        ),
        "B. TABLE RELATIONSHIPS": (
            "Missing customer IDs",
            "Unknown customer ID references",
            "Missing card IDs",
            "Unknown card ID references",
            "Card and customer ownership mismatches",
        ),
        "C. DATE VALIDITY AND CARD LIFECYCLE": (
            "Missing transaction dates",
            "Unparseable transaction dates",
            "Earliest valid transaction date",
            "Latest valid transaction date",
            "Transactions before card opening month",
            "Transactions after card expiry month",
        ),
        "D. AMOUNT VALIDITY": (
            "Missing transaction amounts",
            "Unparseable transaction amounts",
            "Negative transaction amounts",
            "Zero transaction amounts",
            "Positive transaction amounts",
            "Minimum valid transaction amount",
            "Maximum valid transaction amount",
        ),
        "E. CHANNEL VALIDITY": (
            "Allowed use_chip categories",
            "Missing use_chip values",
            "Invalid use_chip values",
            "Observed use_chip categories",
        ),
        "F. MERCHANT AND ERROR CONTEXT": (
            "Missing merchant IDs",
            "Missing merchant cities",
            "Missing merchant states, context only",
            "Missing ZIP values, context only",
            "Missing MCC values",
            "MCC values not formatted as four digits",
            "Rows with recorded transaction errors",
            "Observed error values",
        ),
    }

    for section_name, labels in sections.items():
        print()
        print(section_name)
        for label in labels:
            print(f"{label}: {results[label]}")


def transaction_chunk_iterator(
    transactions_path: Path,
    chunk_size: int,
) -> Iterable[pd.DataFrame]:
    """Yield bounded transaction chunks while preserving raw text fields."""
    if not transactions_path.is_file():
        raise FileNotFoundError(
            f"Transactions CSV file not found: {transactions_path.resolve()}"
        )
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0.")

    header = pd.read_csv(transactions_path, nrows=0)
    validate_columns(header, TRANSACTION_COLUMNS, "transactions_data")

    return pd.read_csv(
        transactions_path,
        usecols=list(TRANSACTION_COLUMNS),
        dtype={column: "string" for column in TRANSACTION_COLUMNS},
        chunksize=chunk_size,
        low_memory=False,
    )


def main() -> None:
    """Load references, stream transactions and print exact results."""
    arguments = parse_arguments()
    transactions_path = Path(arguments.transactions_csv_path).expanduser()
    cards_path = Path(arguments.cards_csv_path).expanduser()
    users_path = Path(arguments.users_csv_path).expanduser()

    reference_data = load_reference_data(cards_path, users_path)
    chunks = transaction_chunk_iterator(
        transactions_path,
        arguments.chunk_size,
    )
    results = process_transaction_chunks(
        chunks,
        reference_data,
        show_progress=True,
    )
    print_results(results)


if __name__ == "__main__":
    main()