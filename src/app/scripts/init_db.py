"""RDS PostgreSQL에 필요한 테이블을 생성한다. 배포 후 1회 실행."""

import os

from services.profile_repository import initialize_postgres


def main() -> None:
    database_url = os.environ["DATABASE_URL"]
    initialize_postgres(database_url)
    print("restaurant_recommendation_profiles 테이블 준비 완료")


if __name__ == "__main__":
    main()
