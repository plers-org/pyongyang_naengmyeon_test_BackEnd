from typing import Iterable, List, Mapping

from services.recommendation_service import RestaurantProfile
from services.taste_type_data import LEGACY_CATEGORY_TO_TYPE_KEY


class PostgresProfileRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def list_profiles(self) -> List[RestaurantProfile]:
        if not self.database_url:
            return []
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("PostgreSQL 연동을 사용하려면 psycopg[binary]가 필요합니다.") from exc
        with psycopg.connect(self.database_url) as connection:
            rows = connection.execute(
                """
                SELECT restaurant_name, meat_aroma_score, umami_score,
                       buckwheat_aroma_score, acidity_score, profile_confidence,
                       operating_status, fit_sentence, evidence_summary,
                       type_key, address, map_url
                FROM restaurant_recommendation_profiles
                """
            ).fetchall()
        return [
            RestaurantProfile(
                restaurant_name=row[0],
                # NUMERIC 컬럼은 Decimal로 오므로 float으로 맞춘다.
                # 취향 벡터가 float이라 그대로 두면 거리 계산에서 타입 오류가 난다.
                scores={
                    "meat_aroma": float(row[1]),
                    "umami": float(row[2]),
                    "buckwheat_aroma": float(row[3]),
                    "acidity": float(row[4]),
                },
                profile_confidence=row[5],
                operating_status=row[6],
                fit_sentence=row[7],
                evidence_summary=row[8],
                type_key=row[9],
                address=row[10],
                map_url=row[11],
            )
            for row in rows
        ]


PROFILE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS restaurant_recommendation_profiles (
  restaurant_name TEXT PRIMARY KEY,
  meat_aroma_score NUMERIC(3, 2) NOT NULL CHECK (meat_aroma_score BETWEEN 1 AND 5),
  umami_score NUMERIC(3, 2) NOT NULL CHECK (umami_score BETWEEN 1 AND 5),
  buckwheat_aroma_score NUMERIC(3, 2) NOT NULL CHECK (buckwheat_aroma_score BETWEEN 1 AND 5),
  acidity_score NUMERIC(3, 2) NOT NULL CHECK (acidity_score BETWEEN 1 AND 5),
  profile_confidence TEXT NOT NULL CHECK (profile_confidence IN ('high', 'medium', 'low')),
  operating_status TEXT NOT NULL DEFAULT 'unknown',
  fit_sentence TEXT NOT NULL DEFAULT '',
  evidence_summary TEXT NOT NULL DEFAULT '',
  type_key TEXT CHECK (type_key IN ('uraeok', 'uijeongbu', 'jangchungdong', 'dongchimi')),
  address TEXT,
  map_url TEXT,
  latitude NUMERIC(9, 6),
  longitude NUMERIC(9, 6),
  profile_version TEXT NOT NULL DEFAULT 'phase2-v1',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

# 이미 만들어진 테이블에도 Phase 2 컬럼이 생기도록 별도로 적용한다.
PROFILE_MIGRATION_SQL = """
ALTER TABLE restaurant_recommendation_profiles
  ADD COLUMN IF NOT EXISTS type_key TEXT,
  ADD COLUMN IF NOT EXISTS address TEXT,
  ADD COLUMN IF NOT EXISTS map_url TEXT,
  ADD COLUMN IF NOT EXISTS latitude NUMERIC(9, 6),
  ADD COLUMN IF NOT EXISTS longitude NUMERIC(9, 6);
"""


def _ensure_schema(connection) -> None:
    connection.execute(PROFILE_TABLE_SQL)
    connection.execute(PROFILE_MIGRATION_SQL)


def initialize_postgres(database_url: str) -> None:
    if not database_url:
        raise ValueError("DATABASE_URL이 필요합니다.")
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("PostgreSQL 연동을 사용하려면 psycopg[binary]가 필요합니다.") from exc
    with psycopg.connect(database_url) as connection:
        _ensure_schema(connection)
        connection.commit()


def import_profiles(database_url: str, rows: Iterable[Mapping[str, object]]) -> int:
    if not database_url:
        raise ValueError("DATABASE_URL이 필요합니다.")
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("PostgreSQL 연동을 사용하려면 psycopg[binary]가 필요합니다.") from exc
    values = list(rows)
    if not values:
        return 0
    # executemany는 커서에만 있다. 커넥션에는 execute만 있어 여러 행을 한 번에 넣지 못한다.
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        _ensure_schema(connection)
        cursor.executemany(
            """
            INSERT INTO restaurant_recommendation_profiles (
              restaurant_name, meat_aroma_score, umami_score,
              buckwheat_aroma_score, acidity_score, profile_confidence,
              operating_status, fit_sentence, evidence_summary,
              type_key, address, map_url, profile_version
            ) VALUES (%(restaurant_name)s, %(meat_aroma_score)s, %(umami_score)s,
              %(buckwheat_aroma_score)s, %(acidity_score)s, %(profile_confidence)s,
              %(operating_status)s, %(fit_sentence)s, %(evidence_summary)s,
              %(type_key)s, %(address)s, %(map_url)s, %(profile_version)s)
            ON CONFLICT (restaurant_name) DO UPDATE SET
              meat_aroma_score = EXCLUDED.meat_aroma_score,
              umami_score = EXCLUDED.umami_score,
              buckwheat_aroma_score = EXCLUDED.buckwheat_aroma_score,
              acidity_score = EXCLUDED.acidity_score,
              profile_confidence = EXCLUDED.profile_confidence,
              operating_status = EXCLUDED.operating_status,
              fit_sentence = EXCLUDED.fit_sentence,
              evidence_summary = EXCLUDED.evidence_summary,
              type_key = EXCLUDED.type_key,
              -- 주소·지도 링크는 별도로 채워 넣는 값이므로 새 값이 없으면 기존 값을 지키다.
              address = COALESCE(EXCLUDED.address, restaurant_recommendation_profiles.address),
              map_url = COALESCE(EXCLUDED.map_url, restaurant_recommendation_profiles.map_url),
              profile_version = EXCLUDED.profile_version,
              updated_at = NOW()
            """,
            values,
        )
        connection.commit()
    return len(values)


TRAIT_COLUMNS = ("meat_aroma_score", "umami_score", "buckwheat_aroma_score", "acidity_score")


def _score(value: object) -> float | None:
    """비어 있거나 숫자가 아닌 점수는 None으로 돌려 적재 대상에서 걸러낸다."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def has_complete_scores(row: Mapping[str, object]) -> bool:
    """4축 점수가 모두 채워진 행만 적재한다."""
    return all(row.get(column) is not None for column in TRAIT_COLUMNS)


def _type_key(legacy_category: object) -> str | None:
    """search의 legacy_category(우래옥/의정부/장충동/동치미)를 type_key로 옮긴다."""
    if not legacy_category:
        return None
    return LEGACY_CATEGORY_TO_TYPE_KEY.get(str(legacy_category).strip())


def _text(value: object) -> str | None:
    if value is None or not str(value).strip():
        return None
    return str(value).strip()


def profile_row_from_search_profile(profile: dict) -> dict:
    traits = profile.get("traits", {})
    return {
        "restaurant_name": profile["restaurant_name"],
        "meat_aroma_score": _score(traits.get("meat_aroma", {}).get("score")),
        "umami_score": _score(traits.get("umami", {}).get("score")),
        "buckwheat_aroma_score": _score(traits.get("buckwheat_aroma", {}).get("score")),
        "acidity_score": _score(traits.get("acidity", {}).get("score")),
        "profile_confidence": "low" if profile.get("review_status") == "needs_more_evidence" else "medium",
        "operating_status": "unknown",
        "fit_sentence": "",
        "evidence_summary": profile.get("special_note", ""),
        "type_key": _type_key(profile.get("legacy_category")),
        "address": _text(profile.get("address")),
        "map_url": _text(profile.get("map_url")),
        "profile_version": profile.get("profile_version", "phase2-v1"),
    }


def profile_row_from_search_csv(
    profile: Mapping[str, object],
    copy: Mapping[str, object] | None = None,
    availability: Mapping[str, object] | None = None,
) -> dict:
    copy = copy or {}
    availability = availability or {}
    return {
        "restaurant_name": str(profile["restaurant_name"]),
        "meat_aroma_score": _score(profile.get("meat_aroma_score")),
        "umami_score": _score(profile.get("umami_score")),
        "buckwheat_aroma_score": _score(profile.get("buckwheat_aroma_score")),
        "acidity_score": _score(profile.get("acidity_score")),
        "profile_confidence": "low" if profile.get("review_status") == "needs_more_evidence" else "medium",
        "operating_status": str(availability.get("operating_status") or "unknown"),
        "fit_sentence": str(copy.get("fit_sentence", "")),
        "evidence_summary": str(profile.get("special_note", "")),
        "type_key": _type_key(profile.get("legacy_category")),
        "address": _text(availability.get("address")),
        "map_url": _text(availability.get("map_url")),
        "profile_version": str(profile.get("profile_version", "phase2-v1")),
    }
