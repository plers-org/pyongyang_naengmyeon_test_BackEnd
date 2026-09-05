"""결과 ID 발급과 결과 조회 검증 (PRD `docs/prd-result-share.md` §11)."""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from main import app
from services.recommendation_service import InMemoryProfileRepository
from services.response_repository import InMemoryResponseRepository
from services.taste_type_data import TASTE_TYPES


client = TestClient(app)


PROFILE_ROWS = [
    {
        "restaurant_name": "진한면옥",
        "meat_aroma_score": 5,
        "umami_score": 4,
        "buckwheat_aroma_score": 1,
        "acidity_score": 1,
        "profile_confidence": "high",
        "operating_status": "open",
        "fit_sentence": "설명",
        "evidence_summary": "근거",
        "type_key": "uraeok",
        "address": "서울시 중구",
        "map_url": "https://example.com/map",
    },
]


def _install(monkeypatch, profile_rows=PROFILE_ROWS):
    """가게 저장소와 결과 저장소를 인메모리 구현으로 갈아끼운다."""
    profiles = InMemoryProfileRepository(profile_rows)
    results = InMemoryResponseRepository()
    monkeypatch.setattr("api.v1.recommendation.recommendation_service.get_profile_repository", lambda: profiles)
    monkeypatch.setattr("api.v1.recommendation.response_repository.get_response_repository", lambda: results)
    return results


@pytest.fixture
def results(monkeypatch):
    return _install(monkeypatch)


def _submit(session_id=None):
    payload = {
        "experience_level": "expert",
        "answers": [
            {"question_id": index, "selected_choice_id": choice}
            for index, choice in enumerate([1, 2, 3, 1, 1, 1], 1)
        ],
    }
    if session_id is not None:
        payload["session_id"] = session_id
    return client.post("/api/recommendation/submit", json=payload)


def _lookup(result_id):
    return client.get(f"/api/recommendation/results/{result_id}")


# --- 결과 발급 -------------------------------------------------------------


def test_submit_issues_uuid_v4_result_id(results):
    """#1 정상 제출은 유효한 UUIDv4와 생성 시각을 함께 돌려준다."""
    body = _submit().json()

    assert UUID(body["result_id"]).version == 4
    assert body["created_at"]


def test_each_submission_issues_a_new_id(results):
    """#2 같은 답변을 두 번 제출해도 서로 다른 ID가 발급된다."""
    first = _submit().json()["result_id"]
    second = _submit().json()["result_id"]

    assert first != second


def test_storage_failure_returns_null_id_with_intact_body(monkeypatch, results, caplog):
    """#3 저장이 실패해도 결과 본문은 정상이고 result_id만 null이 된다."""

    class BrokenRepository:
        def record(self, **_):
            raise RuntimeError("DB 연결 실패")

    monkeypatch.setattr("api.v1.recommendation.response_repository.get_response_repository", BrokenRepository)

    response = _submit()
    body = response.json()

    assert response.status_code == 200
    assert body["result_id"] is None
    assert body["primary_type"]["key"] == "uraeok"
    assert body["recommended_restaurants"][0]["restaurant_name"] == "진한면옥"
    assert "기록에 실패" in caplog.text


def test_no_recommendation_still_issues_id(monkeypatch):
    """#4 추천 가게가 없어도 ID는 발급되고 status가 스냅샷에 남는다."""
    results = _install(monkeypatch, profile_rows=[])

    body = _submit().json()

    assert body["status"] == "no_recommendation"
    assert UUID(body["result_id"]).version == 4
    assert results.records[0]["status"] == "no_recommendation"


# --- 결과 조회 -------------------------------------------------------------


def test_lookup_returns_identical_payload(results):
    """#5 조회 응답은 제출 응답과 필드·값이 모두 같다."""
    submitted = _submit().json()

    response = _lookup(submitted["result_id"])

    assert response.status_code == 200
    assert response.json() == submitted


def test_lookup_is_repeatable(results):
    """#6 같은 ID를 여러 번 조회해도 결과가 변하지 않는다."""
    result_id = _submit().json()["result_id"]

    payloads = [_lookup(result_id).json() for _ in range(3)]

    assert payloads[0] == payloads[1] == payloads[2]


def test_lookup_sets_cache_header(results):
    """결과가 불변이므로 캐시 헤더가 함께 내려간다."""
    result_id = _submit().json()["result_id"]

    assert _lookup(result_id).headers["cache-control"] == "public, max-age=3600"


def test_unknown_result_id_is_404(results):
    """#7 존재하지 않는 UUID는 404다."""
    response = _lookup("9f1c4b2e-3a5d-4e77-8b21-6c0d5f8a1234")

    assert response.status_code == 404
    assert response.json()["detail"] == "결과를 찾을 수 없습니다."


def test_malformed_result_id_is_422(results):
    """#8 UUID 형식이 아닌 값은 422다. 프론트가 잘못된 링크를 구분할 수 있다."""
    assert _lookup("abc").status_code == 422


def test_lookup_never_exposes_session_id(results):
    """#9 session_id는 조회 응답 어디에도 실리지 않는다."""
    submitted = _submit(session_id="anon-1234").json()

    body = _lookup(submitted["result_id"]).text

    assert "session_id" not in body
    assert "anon-1234" not in body


def test_no_recommendation_result_is_restored(monkeypatch):
    """#10 추천이 없던 결과도 유형·그래프는 채워진 채로 복원된다."""
    _install(monkeypatch, profile_rows=[])
    submitted = _submit().json()

    body = _lookup(submitted["result_id"]).json()

    assert body["status"] == "no_recommendation"
    assert body["message"] == "추천 가능한 식당이 없습니다."
    assert body["recommended_restaurants"] == []
    assert body["primary_type"]["key"]
    assert len(body["taste_profile"]["traits"]) == 4


# --- 저장/조립 경계 (PRD §5.2) ---------------------------------------------


def test_copy_edits_reach_already_shared_links(monkeypatch, results):
    """#11 유형 카피는 조회 시점에 조립되므로 수정이 기존 링크에 반영된다."""
    result_id = _submit().json()["result_id"]

    monkeypatch.setitem(TASTE_TYPES["uraeok"], "title", "고친 제목")

    assert _lookup(result_id).json()["primary_type"]["title"] == "고친 제목"


def test_restaurant_cards_survive_profile_deletion(monkeypatch, results):
    """#12 가게가 DB에서 사라져도 추천 카드는 스냅샷 그대로 남는다."""
    submitted = _submit().json()

    monkeypatch.setattr(
        "api.v1.recommendation.recommendation_service.get_profile_repository",
        lambda: InMemoryProfileRepository([]),
    )

    body = _lookup(submitted["result_id"]).json()

    assert body["recommended_restaurants"] == submitted["recommended_restaurants"]
    assert body["recommended_restaurants"][0]["address"] == "서울시 중구"


def test_judgement_is_frozen_against_logic_changes(monkeypatch, results):
    """#13 판정 로직이 바뀌어도 이미 발급된 결과는 제출 시점 값을 유지한다."""
    submitted = _submit().json()

    monkeypatch.setattr(
        "services.recommendation_service.rank_types",
        lambda *_: [("dongchimi", 1.0), ("uraeok", 0.5), ("uijeongbu", 0.3), ("jangchungdong", 0.1)],
    )

    body = _lookup(submitted["result_id"]).json()

    assert body["primary_type"]["key"] == submitted["primary_type"]["key"]
    assert body["type_scores"] == submitted["type_scores"]
    assert body["taste_profile"] == submitted["taste_profile"]


# --- 마이그레이션 / 기존 동작 -----------------------------------------------


def test_legacy_rows_without_result_id_are_not_reachable(results):
    """#15 result_id가 없는 기존 로그 행은 조회 대상이 되지 않는다."""
    results.records.append({"result_id": None, "experience_level": "expert"})

    assert _lookup("9f1c4b2e-3a5d-4e77-8b21-6c0d5f8a1234").status_code == 404


def test_unrestorable_type_key_is_404(results):
    """유형 체계가 개편돼 해석할 수 없는 결과는 500이 아니라 404다 (PRD §6.2)."""
    result_id = _submit().json()["result_id"]
    results.records[-1]["type_ranking"] = [{"key": "사라진유형", "match_score": 1.0}]

    response = _lookup(result_id)

    assert response.status_code == 404
    assert response.json()["detail"] == "이 결과는 더 이상 표시할 수 없습니다."


def test_existing_submit_fields_are_unchanged(results):
    """#17 기존 응답 필드는 이름·구조 모두 그대로다."""
    body = _submit().json()

    assert set(body) == {
        "result_id",
        "created_at",
        "status",
        "message",
        "experience_level",
        "primary_type",
        "secondary_type",
        "farthest_type",
        "type_scores",
        "taste_profile",
        "recommended_restaurants",
    }


# --- PostgreSQL 어댑터 -----------------------------------------------------
#
# 로컬에 Postgres가 없어 실제 실행 검증은 못 하므로, 가짜 커넥션으로 SQL의
# 컬럼 수와 파라미터 수가 어긋나지 않는지, SELECT 결과가 스냅샷으로 옳게
# 옮겨지는지를 확인한다. 컬럼을 추가할 때 가장 틀리기 쉬운 지점이다.


class _FakeCursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeConnection:
    def __init__(self, row=None):
        self.row = row
        self.executed = []
        self.committed = False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return _FakeCursor(self.row)

    def commit(self):
        self.committed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


@pytest.fixture
def fake_psycopg(monkeypatch):
    import sys
    import types

    holder = {}

    def connect(_url):
        return holder["connection"]

    module = types.ModuleType("psycopg")
    module.connect = connect
    monkeypatch.setitem(sys.modules, "psycopg", module)
    return holder


def _insert_statement(connection):
    return next(sql for sql, _ in connection.executed if "INSERT INTO survey_responses" in sql)


def test_postgres_insert_columns_match_parameters(fake_psycopg):
    """INSERT의 컬럼 수·플레이스홀더 수·실제 값 개수가 모두 일치해야 한다."""
    from datetime import datetime, timezone

    from services.response_repository import PostgresResponseRepository

    connection = _FakeConnection()
    fake_psycopg["connection"] = connection
    repository = PostgresResponseRepository("postgresql://example")

    repository.record(
        result_id="9f1c4b2e-3a5d-4e77-8b21-6c0d5f8a1234",
        session_id=None,
        experience_level="expert",
        answers=[{"question_id": 1, "selected_choice_id": 1}],
        taste_vector={"meat_aroma": 4.0},
        primary_type="uraeok",
        secondary_type="dongchimi",
        type_ranking=[{"key": "uraeok", "match_score": 1.0}],
        recommended=[{"restaurant_name": "진한면옥"}],
        status="recommended",
        message=None,
        created_at=datetime.now(timezone.utc),
    )

    sql, params = next(item for item in connection.executed if "INSERT INTO" in item[0])
    columns = sql.split("(", 1)[1].split(")", 1)[0]

    assert len(columns.split(",")) == sql.count("%s") == len(params)
    assert connection.committed


def test_postgres_schema_is_prepared_only_once(fake_psycopg):
    """스키마 DDL은 프로세스당 한 번만 실행된다."""
    from datetime import datetime, timezone

    from services.response_repository import PostgresResponseRepository

    connection = _FakeConnection()
    fake_psycopg["connection"] = connection
    repository = PostgresResponseRepository("postgresql://example")

    payload = dict(
        result_id="9f1c4b2e-3a5d-4e77-8b21-6c0d5f8a1234",
        session_id=None,
        experience_level="expert",
        answers=[],
        taste_vector={},
        primary_type="uraeok",
        secondary_type="dongchimi",
        type_ranking=[],
        recommended=[],
        status="recommended",
        message=None,
        created_at=datetime.now(timezone.utc),
    )
    repository.record(**payload)
    repository.record(**payload)

    assert sum("CREATE TABLE" in sql for sql, _ in connection.executed) == 1
    assert sum("ALTER TABLE" in sql for sql, _ in connection.executed) == 1


def test_postgres_select_columns_map_onto_snapshot(fake_psycopg):
    """SELECT 컬럼 순서와 스냅샷 필드 매핑이 어긋나지 않아야 한다."""
    from datetime import datetime, timezone

    from services.response_repository import SNAPSHOT_COLUMNS, PostgresResponseRepository

    created_at = datetime.now(timezone.utc)
    row = (
        "9f1c4b2e-3a5d-4e77-8b21-6c0d5f8a1234",
        "expert",
        [{"question_id": 1, "selected_choice_id": 1}],
        {"meat_aroma": 4.0},
        [{"key": "uraeok", "match_score": 1.0}],
        [{"restaurant_name": "진한면옥"}],
        "recommended",
        None,
        created_at,
    )
    connection = _FakeConnection(row=row)
    fake_psycopg["connection"] = connection
    repository = PostgresResponseRepository("postgresql://example")

    snapshot = repository.find_by_result_id("9f1c4b2e-3a5d-4e77-8b21-6c0d5f8a1234")

    assert len(SNAPSHOT_COLUMNS.split(",")) == len(row)
    assert snapshot["experience_level"] == "expert"
    assert snapshot["status"] == "recommended"
    assert snapshot["created_at"] == created_at


def test_postgres_missing_row_returns_none(fake_psycopg):
    """일치하는 행이 없으면 None을 돌려 라우터가 404로 바꾼다."""
    from services.response_repository import PostgresResponseRepository

    fake_psycopg["connection"] = _FakeConnection(row=None)

    assert PostgresResponseRepository("postgresql://example").find_by_result_id("x") is None


def test_lookup_returns_503_when_storage_is_unavailable(monkeypatch):
    """저장소를 쓸 수 없으면 500이 아니라 503으로 알린다."""
    from services.response_repository import PostgresResponseRepository

    monkeypatch.setattr(
        "api.v1.recommendation.response_repository.get_response_repository",
        lambda: PostgresResponseRepository(""),
    )

    response = _lookup("9f1c4b2e-3a5d-4e77-8b21-6c0d5f8a1234")

    assert response.status_code == 503
    assert response.json()["detail"] == "결과 조회를 사용할 수 없습니다."
