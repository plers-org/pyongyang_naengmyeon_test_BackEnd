"""Import JSON exported from search's restaurant_taste_profiles report."""

import argparse
import csv
import json
import os
from pathlib import Path

from services.profile_repository import (
    PROVISIONAL_PLACEHOLDER_SCORE,
    fill_incomplete_scores,
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
    parser.add_argument(
        "--force-incomplete",
        action="store_true",
        help="4축이 비어 건너뛰던 가게도 임시 점수로 채워 적재한다. "
             "profile_confidence가 low로 고정되어 추천 후보에는 오르지 않는다.",
    )
    parser.add_argument(
        "--placeholder-score",
        type=float,
        default=PROVISIONAL_PLACEHOLDER_SCORE,
        help=f"--force-incomplete로 빈 축을 채울 점수 (기본 {PROVISIONAL_PLACEHOLDER_SCORE})",
    )
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

    if args.force_incomplete:
        complete = []
        forced = []
        for row in rows:
            filled, missing = fill_incomplete_scores(row, args.placeholder_score)
            complete.append(filled)
            if missing:
                forced.append(f"{filled['restaurant_name']}({','.join(m.replace('_score','') for m in missing)})")
        if forced:
            print(
                f"filled {len(forced)} profiles with placeholder {args.placeholder_score} "
                f"(confidence=low, 추천 후보에서 제외됨): {', '.join(forced)}"
            )
    else:
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
