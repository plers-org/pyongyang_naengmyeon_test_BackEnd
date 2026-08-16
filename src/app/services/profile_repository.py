from typing import Iterable, List, Mapping

from services.recommendation_service import RestaurantProfile


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
                       operating_status, fit_sentence, evidence_summary
                FROM restaurant_recommendation_profiles
                """
            ).fetchall()
        return [
            RestaurantProfile(
                restaurant_name=row[0],
                scores={"meat_aroma": row[1], "umami": row[2], "buckwheat_aroma": row[3], "acidity": row[4]},
                profile_confidence=row[5],
                operating_status=row[6],
                fit_sentence=row[7],
                evidence_summary=row[8],
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
  profile_version TEXT NOT NULL DEFAULT 'phase2-v1',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def initialize_postgres(database_url: str) -> None:
    if not database_url:
        raise ValueError("DATABASE_URL이 필요합니다.")
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("PostgreSQL 연동을 사용하려면 psycopg[binary]가 필요합니다.") from exc
    with psycopg.connect(database_url) as connection:
        connection.execute(PROFILE_TABLE_SQL)
        connection.commit()


def import_profiles(database_url: str, rows: Iterable[Mapping[str, object]]) -> int:
    if not database_url:
        raise ValueError("DATABASE_URL이 필요합니다.")
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("PostgreSQL 연동을 사용하려면 psycopg[binary]가 필요합니다.") from exc
    values = list(rows)
    with psycopg.connect(database_url) as connection:
        connection.execute(PROFILE_TABLE_SQL)
        connection.executemany(
            """
            INSERT INTO restaurant_recommendation_profiles (
              restaurant_name, meat_aroma_score, umami_score,
              buckwheat_aroma_score, acidity_score, profile_confidence,
              operating_status, fit_sentence, evidence_summary, profile_version
            ) VALUES (%(restaurant_name)s, %(meat_aroma_score)s, %(umami_score)s,
              %(buckwheat_aroma_score)s, %(acidity_score)s, %(profile_confidence)s,
              %(operating_status)s, %(fit_sentence)s, %(evidence_summary)s, %(profile_version)s)
            ON CONFLICT (restaurant_name) DO UPDATE SET
              meat_aroma_score = EXCLUDED.meat_aroma_score,
              umami_score = EXCLUDED.umami_score,
              buckwheat_aroma_score = EXCLUDED.buckwheat_aroma_score,
              acidity_score = EXCLUDED.acidity_score,
              profile_confidence = EXCLUDED.profile_confidence,
              operating_status = EXCLUDED.operating_status,
              fit_sentence = EXCLUDED.fit_sentence,
              evidence_summary = EXCLUDED.evidence_summary,
              profile_version = EXCLUDED.profile_version,
              updated_at = NOW()
            """,
            values,
        )
        connection.commit()
    return len(values)


def profile_row_from_search_profile(profile: dict) -> dict:
    traits = profile.get("traits", {})
    return {
        "restaurant_name": profile["restaurant_name"],
        "meat_aroma_score": traits.get("meat_aroma", {}).get("score"),
        "umami_score": traits.get("umami", {}).get("score"),
        "buckwheat_aroma_score": traits.get("buckwheat_aroma", {}).get("score"),
        "acidity_score": traits.get("acidity", {}).get("score"),
        "profile_confidence": "low" if profile.get("review_status") == "needs_more_evidence" else "medium",
        "operating_status": "unknown",
        "fit_sentence": "",
        "evidence_summary": profile.get("special_note", ""),
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
        "meat_aroma_score": profile.get("meat_aroma_score"),
        "umami_score": profile.get("umami_score"),
        "buckwheat_aroma_score": profile.get("buckwheat_aroma_score"),
        "acidity_score": profile.get("acidity_score"),
        "profile_confidence": "low" if profile.get("review_status") == "needs_more_evidence" else "medium",
        "operating_status": str(availability.get("operating_status", "unknown")),
        "fit_sentence": str(copy.get("fit_sentence", "")),
        "evidence_summary": str(profile.get("special_note", "")),
        "profile_version": str(profile.get("profile_version", "phase2-v1")),
    }
