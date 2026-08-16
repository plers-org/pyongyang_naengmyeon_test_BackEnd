"""RDS PostgreSQL에 필요한 테이블을 생성한다. 배포 후 1회 실행.

이미 만들어진 테이블에는 누락된 컬럼만 덧붙이므로 여러 번 실행해도 안전하다.
"""

import os

from services.profile_repository import initialize_postgres
from services.response_repository import initialize_response_table


def main() -> None:
    database_url = os.environ["DATABASE_URL"]
    initialize_postgres(database_url)
    print("restaurant_recommendation_profiles 테이블 준비 완료")
    initialize_response_table(database_url)
    print("survey_responses 테이블 준비 완료")


if __name__ == "__main__":
    main()
