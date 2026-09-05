"""프로필 테이블의 식당명을 바꾼다.

search 쪽에서 식당을 다른 지점으로 다시 잡았을 때, RDS에 남은 옛 이름 행을
정리하는 용도다. 해당 행이 없으면 0을 찍고 조용히 끝나므로 여러 번 실행해도 안전하다.
"""

import argparse
import os

from services.profile_repository import rename_restaurant


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="old_name", required=True)
    parser.add_argument("--to", dest="new_name", required=True)
    args = parser.parse_args()

    affected = rename_restaurant(os.environ["DATABASE_URL"], args.old_name, args.new_name)
    if affected:
        print(f"renamed {affected} row: {args.old_name} -> {args.new_name}")
    else:
        print(f"'{args.old_name}' 행이 없어 아무것도 바꾸지 않았습니다.")


if __name__ == "__main__":
    main()
