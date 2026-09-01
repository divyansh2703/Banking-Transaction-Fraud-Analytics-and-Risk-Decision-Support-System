from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


CREDIT_SCORE_MIN = 300
CREDIT_SCORE_MAX = 850
CREDIT_SCORE_SOURCE = "https://www.myfico.com/credit-education/credit-scores"

REQUIRED_COLUMNS = (
    "current_age",
    "retirement_age",
    "birth_year",
    "birth_month",
    "credit_score",
    "num_credit_cards",
    "latitude",
    "longitude",
)


def parse_arguments() -> argparse.Namespace:
    """Read the optional CSV path supplied in the VS Code terminal."""
    parser = argparse.ArgumentParser(
        description="Run exact data quality checks on users_data.csv."
    )
    parser.add_argument(
        "csv_path",
        nargs="?",
        default="users_data.csv",
        help="Path to users_data.csv. Default: users_data.csv",
    )
    return parser.parse_args()


def validate_columns(users_data: pd.DataFrame) -> None:
    """Stop with a clear message if a required field is unavailable."""
    missing_columns = [
        column for column in REQUIRED_COLUMNS if column not in users_data.columns
    ]

    if missing_columns:
        raise KeyError(f"Required columns not found: {missing_columns}")


def get_numeric_columns(users_data: pd.DataFrame) -> dict[str, pd.Series]:
    """Return numeric versions of checked fields without altering users_data."""
    numeric_columns: dict[str, pd.Series] = {}
    conversion_failures: dict[str, int] = {}

    for column in REQUIRED_COLUMNS:
        converted = pd.to_numeric(users_data[column], errors="coerce")

        non_numeric_mask = users_data[column].notna() & converted.isna()
        non_numeric_count = int(non_numeric_mask.sum())

        if non_numeric_count > 0:
            conversion_failures[column] = non_numeric_count

        numeric_columns[column] = converted

    if conversion_failures:
        raise ValueError(
            "Non numeric values were found in fields required for range checks: "
            f"{conversion_failures}. Profile these values before continuing."
        )

    return numeric_columns


def infer_reference_year(
    birth_year: pd.Series,
    current_age: pd.Series,
) -> int:
    """Infer the snapshot year from birth year and current age.

    For a snapshot taken during year Y, birth_year + current_age can be Y for
    customers whose birthday has occurred, or Y minus 1 for customers whose
    birthday has not occurred. Therefore, one implied year or two consecutive
    implied years is internally consistent. The later year is the reference.
    """
    complete_mask = birth_year.notna() & current_age.notna()
    implied_year = birth_year.loc[complete_mask] + current_age.loc[complete_mask]

    if implied_year.empty:
        raise ValueError(
            "Dataset customer reference year cannot be inferred because no "
            "complete birth_year and current_age pairs are available."
        )

    non_integer_mask = implied_year.mod(1).ne(0)
    if bool(non_integer_mask.any()):
        raise ValueError(
            "Dataset customer reference year cannot be inferred because some "
            "birth_year + current_age results are not whole years."
        )

    implied_year = implied_year.astype("int64")
    observed_implied_years = sorted(int(year) for year in implied_year.unique())
    reference_year = max(observed_implied_years)
    valid_implied_years = {reference_year - 1, reference_year}

    if not set(observed_implied_years).issubset(valid_implied_years):
        year_counts = implied_year.value_counts().sort_index().to_dict()
        raise ValueError(
            "Dataset customer reference year is ambiguous. The implied year "
            f"counts are: {year_counts}"
        )

    return reference_year


def run_quality_checks(users_data: pd.DataFrame) -> dict[str, int | str]:
    """Calculate all requested checks and return their exact results."""
    if users_data.empty:
        raise ValueError("users_data contains no rows.")

    validate_columns(users_data)
    numeric = get_numeric_columns(users_data)

    current_age = numeric["current_age"]
    retirement_age = numeric["retirement_age"]
    birth_year = numeric["birth_year"]
    birth_month = numeric["birth_month"]
    credit_score = numeric["credit_score"]
    num_credit_cards = numeric["num_credit_cards"]
    latitude = numeric["latitude"]
    longitude = numeric["longitude"]

    reference_year = infer_reference_year(birth_year, current_age)

    return {
        "Age below 18": int(current_age.lt(18).sum()),
        "Age above 110": int(current_age.gt(110).sum()),
        "Retirement age below 0": int(retirement_age.lt(0).sum()),
        "Retirement age above 120": int(retirement_age.gt(120).sum()),
        "Current age above retirement age": int(
            current_age.gt(retirement_age).sum()
        ),
        "Invalid birth months": int(
            (birth_month.lt(1) | birth_month.gt(12)).sum()
        ),
        "Credit score documented valid range": (
            f"{CREDIT_SCORE_MIN} to {CREDIT_SCORE_MAX} inclusive"
        ),
        "Credit score values outside range": int(
            (
                credit_score.lt(CREDIT_SCORE_MIN)
                | credit_score.gt(CREDIT_SCORE_MAX)
            ).sum()
        ),
        "Customers with num_credit_cards <= 0": int(
            num_credit_cards.le(0).sum()
        ),
        "Maximum num_credit_cards": int(num_credit_cards.max()),
        "Invalid latitude": int(
            (latitude.lt(-90) | latitude.gt(90)).sum()
        ),
        "Invalid longitude": int(
            (longitude.lt(-180) | longitude.gt(180)).sum()
        ),
        "Dataset customer reference year": reference_year,
    }


def print_results(results: dict[str, int | str]) -> None:
    """Print results in the requested project template."""
    print("USERS DATA QUALITY CHECKS")
    print()
    print(f"Age below 18: {results['Age below 18']}")
    print(f"Age above 110: {results['Age above 110']}")
    print()
    print(f"Retirement age below 0: {results['Retirement age below 0']}")
    print(f"Retirement age above 120: {results['Retirement age above 120']}")
    print(
        "Current age above retirement age: "
        f"{results['Current age above retirement age']}"
    )
    print()
    print(f"Invalid birth months: {results['Invalid birth months']}")
    print()
    print(
        "Credit score documented valid range: "
        f"{results['Credit score documented valid range']}"
    )
    print(
        "Credit score values outside range: "
        f"{results['Credit score values outside range']}"
    )
    print()
    print(
        "Customers with num_credit_cards <= 0: "
        f"{results['Customers with num_credit_cards <= 0']}"
    )
    print(
        "Maximum num_credit_cards: "
        f"{results['Maximum num_credit_cards']}"
    )
    print()
    print(f"Invalid latitude: {results['Invalid latitude']}")
    print(f"Invalid longitude: {results['Invalid longitude']}")
    print()
    print(
        "Dataset customer reference year: "
        f"{results['Dataset customer reference year']}"
    )


def main() -> None:
    """Load users_data.csv, run checks and print the results."""
    arguments = parse_arguments()
    csv_path = Path(arguments.csv_path).expanduser()

    if not csv_path.is_file():
        raise FileNotFoundError(
            f"CSV file not found: {csv_path.resolve()}"
        )

    users_data = pd.read_csv(csv_path, low_memory=False)
    results = run_quality_checks(users_data)
    print_results(results)


if __name__ == "__main__":
    main()