"""취향 테스트 응답 기록과 결과 조회.

두 가지 역할을 겸한다.

1. 유형 분포·퍼널 지표를 보기 위한 **응답 로그**
2. `result_id` 로 결과 화면을 다시 그리기 위한 **결과 스냅샷**

개인정보는 수집하지 않으며 프론트가 생성한 익명 session_id만 받는다.
session_id는 통계 집계용이라 조회 응답에는 절대 싣지 않는다.

무엇을 저장하고 무엇을 조회 시점에 조립하는지는 PRD §5.2에 있다. 요약하면
**판정 결과는 스냅샷으로 고정하고, 유형 카피와 축 라벨은 조회 시점 코드 상수에서
읽는다.** 카피 수정이 이미 공유된 링크에도 반영되게 하기 위함이다.

기록 실패가 추천 응답을 막아서는 안 되므로 쓰기는 best-effort로 처리한다.
다만 record_safely가 성공 여부를 돌려주어, 호출부가 result_id를 내려보낼지
결정할 수 있게 한다.
"""

import json
import logging
import os
from datetime import datetime
from typing import Mapping, Optional, Protocol, Sequence


logger = logging.getLogger(__name__)


RESPONSE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS survey_responses (
  id BIGSERIAL PRIMARY KEY,
  result_id UUID,
  session_id TEXT,
  experience_level TEXT NOT NULL,
  answers JSONB NOT NULL,
  taste_vector JSONB NOT NULL,
  primary_type TEXT NOT NULL,
  secondary_type TEXT NOT NULL,
  type_ranking JSONB,
  recommended JSONB NOT NULL,
  result_status TEXT,
  result_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

# 이미 만들어진 테이블에도 결과 조회용 컬럼이 생기도록 별도로 적용한다.
# result_id를 NOT NULL로 두지 않는 이유: 이 마이그레이션 이전에 쌓인 로그 행에는
# 값이 없다. 신규 행은 애플리케이션이 항상 채운다.
RESPONSE_MIGRATION_SQL = """
ALTER TABLE survey_responses
  ADD COLUMN IF NOT EXISTS result_id UUID,
  ADD COLUMN IF NOT EXISTS type_ranking JSONB,
  ADD COLUMN IF NOT EXISTS result_status TEXT,
  ADD COLUMN IF NOT EXISTS result_message TEXT;
"""

# 인덱스는 컬럼이 모두 갖춰진 뒤에 만들어야 하므로 마지막에 따로 실행한다.
RESPONSE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS survey_responses_created_at_idx ON survey_responses (created_at);
CREATE INDEX IF NOT EXISTS survey_responses_primary_type_idx ON survey_responses (primary_type);
CREATE UNIQUE INDEX IF NOT EXISTS survey_responses_result_id_idx ON survey_responses (result_id);
"""

SNAPSHOT_COLUMNS = """
  result_id, experience_level, answers, taste_vector, type_ranking,
  recommended, result_status, result_message, created_at
"""


class ResponseRepository(Protocol):
    def record(
        self,
        result_id: str,
        session_id: Optional[str],
        experience_level: str,
        answers: Sequence[Mapping[str, int]],
        taste_vector: Mapping[str, float],
        primary_type: str,
        secondary_type: str,
        type_ranking: Sequence[Mapping[str, object]],
        recommended: Sequence[Mapping[str, object]],
        status: str,
        message: Optional[str],
        created_at: datetime,
    ) -> None: ...

    def find_by_result_id(self, result_id: str) -> Optional[Mapping[str, object]]: ...


def _snapshot(row: Sequence[object]) -> dict:
    """SELECT 결과 한 행을 조회 응답 복원에 쓰는 형태로 옮긴다."""
    return {
        "result_id": str(row[0]),
        "experience_level": row[1],
        "answers": row[2],
        "taste_vector": row[3],
        "type_ranking": row[4],
        "recommended": row[5],
        "status": row[6],
        "message": row[7],
        "created_at": row[8],
    }


class InMemoryResponseRepository:
    """테스트 및 DATABASE_URL 미설정 환경에서 쓰는 구현.

    프로세스가 살아 있는 동안만 조회가 되고 재시작하면 사라진다.
    """

    def __init__(self) -> None:
        self.records = []

    def record(
        self,
        result_id,
        session_id,
        experience_level,
        answers,
        taste_vector,
        primary_type,
        secondary_type,
        type_ranking,
        recommended,
        status,
        message,
        created_at,
    ):
        self.records.append(
            {
                "result_id": result_id,
                "session_id": session_id,
                "experience_level": experience_level,
                "answers": list(answers),
                "taste_vector": dict(taste_vector),
                "primary_type": primary_type,
                "secondary_type": secondary_type,
                "type_ranking": list(type_ranking),
                "recommended": list(recommended),
                "status": status,
                "message": message,
                "created_at": created_at,
            }
        )

    def find_by_result_id(self, result_id):
        for record in reversed(self.records):
            # result_id가 없는 행(구 로그)은 조회 대상이 아니다.
            if record.get("result_id") and record["result_id"] == result_id:
                return record
        return None


class PostgresResponseRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        # 스키마 보장은 프로세스당 한 번이면 된다. 매 삽입마다 ALTER TABLE을 돌리면
        # 컬럼이 이미 있어도 짧은 배타 락을 반복해서 잡게 된다.
        self._schema_ready = False

    def _prepare(self, connection) -> None:
        if self._schema_ready:
            return
        _ensure_schema(connection)
        self._schema_ready = True

    def record(
        self,
        result_id,
        session_id,
        experience_level,
        answers,
        taste_vector,
        primary_type,
        secondary_type,
        type_ranking,
        recommended,
        status,
        message,
        created_at,
    ):
        if not self.database_url:
            return
        import psycopg

        with psycopg.connect(self.database_url) as connection:
            self._prepare(connection)
            connection.execute(
                """
                INSERT INTO survey_responses (
                  result_id, session_id, experience_level, answers, taste_vector,
                  primary_type, secondary_type, type_ranking, recommended,
                  result_status, result_message, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    result_id,
                    session_id,
                    experience_level,
                    json.dumps(list(answers), ensure_ascii=False),
                    json.dumps(dict(taste_vector), ensure_ascii=False),
                    primary_type,
                    secondary_type,
                    json.dumps(list(type_ranking), ensure_ascii=False),
                    json.dumps(list(recommended), ensure_ascii=False),
                    status,
                    message,
                    created_at,
                ),
            )
            connection.commit()

    def find_by_result_id(self, result_id):
        if not self.database_url:
            raise RuntimeError("DATABASE_URL이 필요합니다.")
        import psycopg

        with psycopg.connect(self.database_url) as connection:
            row = connection.execute(
                f"SELECT {SNAPSHOT_COLUMNS} FROM survey_responses WHERE result_id = %s",
                (result_id,),
            ).fetchone()
        return _snapshot(row) if row else None


_default_repository: Optional[ResponseRepository] = None


def get_response_repository() -> ResponseRepository:
    global _default_repository
    if _default_repository is None:
        database_url = os.getenv("DATABASE_URL", "")
        _default_repository = (
            PostgresResponseRepository(database_url) if database_url else InMemoryResponseRepository()
        )
    return _default_repository


def record_safely(repository: ResponseRepository, **payload) -> bool:
    """기록 실패가 추천 응답을 막지 않도록 예외를 로깅만 하고 삼킨다.

    저장에 성공했는지를 돌려준다. 호출부는 실패했을 때 result_id를 내리지 않아,
    프론트가 조회되지 않을 링크로 이동하는 일을 막는다(PRD §6.3).
    """
    try:
        repository.record(**payload)
    except Exception:  # noqa: BLE001 - 응답 경로를 보호하는 것이 목적이다
        logger.exception("취향 테스트 응답 기록에 실패했습니다.")
        return False
    return True


def _ensure_schema(connection) -> None:
    connection.execute(RESPONSE_TABLE_SQL)
    connection.execute(RESPONSE_MIGRATION_SQL)
    connection.execute(RESPONSE_INDEX_SQL)


def initialize_response_table(database_url: str) -> None:
    if not database_url:
        raise ValueError("DATABASE_URL이 필요합니다.")
    import psycopg

    with psycopg.connect(database_url) as connection:
        _ensure_schema(connection)
        connection.commit()
