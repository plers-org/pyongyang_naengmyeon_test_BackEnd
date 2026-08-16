"""Import JSON exported from search's restaurant_taste_profiles report."""

import argparse
import csv
import json
import os
from pathlib import Path

from services.profile_repository import (
    has_complete_scores,
    import_profiles,
    profile_row_from_search_csv,
    profile_row_from_search_profile,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path, help="search JSON 또는 restaurant_taste_profiles.csv")
    parser.add_argument("--copy", type=Path, help="restaurant_recommendation_copy.csv")
    parser.add_argument("--availability", type=Path, help="restaurant_availability.csv")
    args = parser.parse_args()
    if args.input.suffix.lower() == ".csv":
        profiles = list(csv.DictReader(args.input.open(encoding="utf-8-sig", newline="")))
        copies = _index_csv(args.copy) if args.copy else {}
        availability = _index_csv(args.availability) if args.availability else {}
        rows = [
            profile_row_from_search_csv(item, copies.get(item["restaurant_name"]), availability.get(item["restaurant_name"]))
            for item in profiles
        ]
    else:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        rows = [profile_row_from_search_profile(item) for item in payload]

    complete = [row for row in rows if has_complete_scores(row)]
    skipped = len(rows) - len(complete)
    if skipped:
        names = ", ".join(str(row["restaurant_name"]) for row in rows if not has_complete_scores(row))
        print(f"skipped {skipped} profiles with missing trait scores: {names}")
    count = import_profiles(os.environ["DATABASE_URL"], complete)
    print(f"imported {count} restaurant profiles")


def _index_csv(path: Path) -> dict[str, dict[str, object]]:
    return {row["restaurant_name"]: row for row in csv.DictReader(path.open(encoding="utf-8-sig", newline=""))}


if __name__ == "__main__":
    main()
