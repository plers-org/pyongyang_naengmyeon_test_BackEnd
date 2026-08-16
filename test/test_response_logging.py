"""취향 테스트 응답 기록 검증."""

import pytest
from fastapi.testclient import TestClient

from main import app
from services.recommendation_service import InMemoryProfileRepository
from services.response_repository import InMemoryResponseRepository, record_safely


client = TestClient(app)


@pytest.fixture
def recorder(monkeypatch):
    repository = InMemoryProfileRepository(
        [
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
            }
        ]
    )
    recorder = InMemoryResponseRepository()
    monkeypatch.setattr("api.v1.recommendation.recommendation_service.get_profile_repository", lambda: repository)
    monkeypatch.setattr("api.v1.recommendation.response_repository.get_response_repository", lambda: recorder)
    return recorder


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


def test_submission_is_recorded(recorder):
    assert _submit(session_id="anon-1234").status_code == 200
    assert len(recorder.records) == 1

    record = recorder.records[0]
    assert record["session_id"] == "anon-1234"
    assert record["experience_level"] == "expert"
    assert len(record["answers"]) == 6
    assert set(record["taste_vector"]) == {"meat_aroma", "umami", "buckwheat_aroma", "acidity"}
    assert record["primary_type"] == "uraeok"
    assert record["secondary_type"]
    assert record["recommended"][0]["restaurant_name"] == "진한면옥"


def test_session_id_is_optional(recorder):
    assert _submit().status_code == 200
    assert recorder.records[0]["session_id"] is None


def test_over_long_session_id_is_rejected(recorder):
    response = _submit(session_id="x" * 65)

    assert response.status_code == 422
    assert recorder.records == []


def test_recording_failure_does_not_break_response(monkeypatch, recorder):
    """기록이 실패해도 추천 응답은 정상 반환되어야 한다."""

    class BrokenRepository:
        def record(self, **_):
            raise RuntimeError("DB 연결 실패")

    monkeypatch.setattr("api.v1.recommendation.response_repository.get_response_repository", BrokenRepository)

    response = _submit(session_id="anon-1234")

    assert response.status_code == 200
    assert response.json()["primary_type"]["key"] == "uraeok"


def test_record_safely_swallows_exceptions(caplog):
    class BrokenRepository:
        def record(self, **_):
            raise RuntimeError("boom")

    record_safely(BrokenRepository(), session_id=None)

    assert "기록에 실패" in caplog.text
