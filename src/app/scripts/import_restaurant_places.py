"""search의 restaurant_places.csv를 읽어 프로필 테이블의 지도 정보를 채운다.

4축 점수 컬럼이 NOT NULL이라 새 행은 만들지 않는다. 이미 프로필이 있는 식당의
주소·지도 링크·좌표만 UPDATE한다.

기본은 매칭이 확정된 행(match_status=matched, manual)만 넣는다. manual은 사람이
place_overrides.csv로 직접 바로잡은 행이라 자동 매칭보다 믿을 만하다. 지점이
어긋났을 수 있는 review 행까지 넣으려면 --include-review 를 준다.
"""

import argparse
import csv
import os
from pathlib import Path

from services.profile_repository import (
    place_row_from_search_csv,
    select_place_targets,
    update_places,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path, help="restaurant_places.csv")
    parser.add_argument(
        "--include-review",
        action="store_true",
        help="지점 확인이 필요한 match_status=review 행까지 적재한다.",
    )
    parser.add_argument("--dry-run", action="store_true", help="DB에 쓰지 않고 대상만 출력한다.")
    args = parser.parse_args()

    places = list(csv.DictReader(args.input.open(encoding="utf-8-sig", newline="")))
    targets, skipped = select_place_targets(places, args.include_review)

    if skipped:
        print(f"skipped {len(skipped)} places with unconfirmed match_status: {', '.join(skipped)}")

    rows = [place_row_from_search_csv(place) for place in targets]

    if args.dry_run:
        for row in rows:
            print(f"  {row['restaurant_name']:24s} {row['map_url']}  {row['address']}")
        print(f"dry-run: {len(rows)} places would be updated")
        return

    updated, missing = update_places(os.environ["DATABASE_URL"], rows)
    print(f"updated {updated} restaurant places")
    if missing:
        print(f"프로필 테이블에 없어 건너뛴 식당 {len(missing)}곳: {', '.join(missing)}")


if __name__ == "__main__":
    main()
