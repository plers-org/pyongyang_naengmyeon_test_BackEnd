"""취향 테스트 응답 기록.

유형 분포와 퍼널 지표를 보기 위한 로그다. 개인정보는 수집하지 않으며
프론트가 생성한 익명 session_id만 받는다.

기록 실패가 추천 응답을 막아서는 안 되므로 쓰기는 best-effort로 처리한다.
"""

import json
import logging
import os
from typing import Mapping, Optional, Protocol, Sequence


logger = logging.getLogger(__name__)


RESPONSE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS survey_responses (
  id BIGSERIAL PRIMARY KEY,
  session_id TEXT,
  experience_level TEXT NOT NULL,
  answers JSONB NOT NULL,
  taste_vector JSONB NOT NULL,
  primary_type TEXT NOT NULL,
  secondary_type TEXT NOT NULL,
  recommended JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS survey_responses_created_at_idx ON survey_responses (created_at);
CREATE INDEX IF NOT EXISTS survey_responses_primary_type_idx ON survey_responses (primary_type);
"""


class ResponseRepository(Protocol):
    def record(
        self,
        session_id: Optional[str],
        experience_level: str,
        answers: Sequence[Mapping[str, int]],
        taste_vector: Mapping[str, float],
        primary_type: str,
        secondary_type: str,
        recommended: Sequence[Mapping[str, object]],
    ) -> None: ...


class InMemoryResponseRepository:
    """테스트 및 DATABASE_URL 미설정 환경에서 쓰는 구현."""

    def __init__(self) -> None:
        self.records = []

    def record(self, session_id, experience_level, answers, taste_vector, primary_type, secondary_type, recommended):
        self.records.append(
            {
                "session_id": session_id,
                "experience_level": experience_level,
                "answers": list(answers),
                "taste_vector": dict(taste_vector),
                "primary_type": primary_type,
                "secondary_type": secondary_type,
                "recommended": list(recommended),
            }
        )


class PostgresResponseRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def record(self, session_id, experience_level, answers, taste_vector, primary_type, secondary_type, recommended):
        if not self.database_url:
            return
        import psycopg

        with psycopg.connect(self.database_url) as connection:
            connection.execute(RESPONSE_TABLE_SQL)
            connection.execute(
                """
                INSERT INTO survey_responses (
                  session_id, experience_level, answers, taste_vector,
                  primary_type, secondary_type, recommended
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    session_id,
                    experience_level,
                    json.dumps(list(answers), ensure_ascii=False),
                    json.dumps(dict(taste_vector), ensure_ascii=False),
                    primary_type,
                    secondary_type,
                    json.dumps(list(recommended), ensure_ascii=False),
                ),
            )
            connection.commit()


_default_repository: Optional[ResponseRepository] = None


def get_response_repository() -> ResponseRepository:
    global _default_repository
    if _default_repository is None:
        database_url = os.getenv("DATABASE_URL", "")
        _default_repository = (
            PostgresResponseRepository(database_url) if database_url else InMemoryResponseRepository()
        )
    return _default_repository


def record_safely(repository: ResponseRepository, **payload) -> None:
    """기록 실패가 추천 응답을 막지 않도록 예외를 로깅만 하고 삼킨다."""
    try:
        repository.record(**payload)
    except Exception:  # noqa: BLE001 - 응답 경로를 보호하는 것이 목적이다
        logger.exception("취향 테스트 응답 기록에 실패했습니다.")


def initialize_response_table(database_url: str) -> None:
    if not database_url:
        raise ValueError("DATABASE_URL이 필요합니다.")
    import psycopg

    with psycopg.connect(database_url) as connection:
        connection.execute(RESPONSE_TABLE_SQL)
        connection.commit()
