from fastapi.testclient import TestClient

from main import app
from services.recommendation_service import InMemoryProfileRepository


client = TestClient(app)


def test_questions_are_selected_by_experience_level():
    beginner = client.get("/api/recommendation/questions/beginner")
    expert = client.get("/api/recommendation/questions/expert")

    assert beginner.status_code == 200
    assert expert.status_code == 200
    assert len(beginner.json()["questions"]) == 6
    assert len(expert.json()["questions"]) == 6
    assert beginner.json()["questions"][0]["question_text"] == "좋아하는 국물의 첫 느낌은?"
    assert expert.json()["questions"][0]["question_text"] == "육수 첫 느낌은 어때야 만족?"


def test_submit_returns_best_restaurant_with_explanation(monkeypatch):
    repository = InMemoryProfileRepository(
        [
            {
                "restaurant_name": "진한면옥",
                "meat_aroma_score": 5,
                "umami_score": 5,
                "buckwheat_aroma_score": 1,
                "acidity_score": 1,
                "profile_confidence": "high",
                "operating_status": "open",
                "fit_sentence": "진한 육향과 감칠맛을 좋아하는 분께 잘 맞아요.",
                "evidence_summary": "육향과 깊은 맛에 대한 근거가 충분합니다.",
            },
            {
                "restaurant_name": "맑은면옥",
                "meat_aroma_score": 1,
                "umami_score": 1,
                "buckwheat_aroma_score": 5,
                "acidity_score": 5,
                "profile_confidence": "high",
                "operating_status": "open",
                "fit_sentence": "메밀 향과 산뜻함을 좋아하는 분께 잘 맞아요.",
                "evidence_summary": "메밀 향과 동치미 산미에 대한 근거가 충분합니다.",
            },
        ]
    )
    monkeypatch.setattr("api.v1.recommendation.recommendation_service.get_profile_repository", lambda: repository)

    response = client.post(
        "/api/recommendation/submit",
        json={
            "experience_level": "beginner",
            "answers": [
                {"question_id": index, "selected_choice_id": 1}
                for index in range(1, 7)
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["restaurant_name"] == "진한면옥"
    assert payload["explanation"]
    assert payload["evidence_summary"]
    assert 0 <= payload["fit_score"] <= 1


def test_submit_returns_no_recommendation_when_profiles_are_not_eligible(monkeypatch):
    repository = InMemoryProfileRepository(
        [
            {
                "restaurant_name": "검수대기면옥",
                "meat_aroma_score": 3,
                "umami_score": 3,
                "buckwheat_aroma_score": 3,
                "acidity_score": 3,
                "profile_confidence": "low",
                "operating_status": "open",
                "fit_sentence": "설명",
                "evidence_summary": "근거",
            }
        ]
    )
    monkeypatch.setattr("api.v1.recommendation.recommendation_service.get_profile_repository", lambda: repository)

    response = client.post(
        "/api/recommendation/submit",
        json={
            "experience_level": "expert",
            "answers": [
                {"question_id": index, "selected_choice_id": 1}
                for index in range(1, 7)
            ],
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "no_recommendation",
        "message": "추천 가능한 식당이 없습니다.",
    }


def _profile(name, operating_status="unknown", profile_confidence="medium"):
    return {
        "restaurant_name": name,
        "meat_aroma_score": 5,
        "umami_score": 4,
        "buckwheat_aroma_score": 1,
        "acidity_score": 1,
        "profile_confidence": profile_confidence,
        "operating_status": operating_status,
        "fit_sentence": "설명",
        "evidence_summary": "근거",
    }


def _submit(monkeypatch, rows):
    repository = InMemoryProfileRepository(rows)
    monkeypatch.setattr("api.v1.recommendation.recommendation_service.get_profile_repository", lambda: repository)
    return client.post(
        "/api/recommendation/submit",
        json={
            "experience_level": "expert",
            "answers": [{"question_id": index, "selected_choice_id": 1} for index in range(1, 7)],
        },
    )


def test_unknown_operating_status_stays_in_candidates(monkeypatch):
    """영업 상태 미확인(unknown)은 폐업 근거가 아니므로 후보에 남는다."""
    response = _submit(monkeypatch, [_profile("미확인면옥", operating_status="unknown")])

    assert response.status_code == 200
    assert response.json()["restaurant_name"] == "미확인면옥"


def test_closed_restaurants_are_excluded(monkeypatch):
    response = _submit(monkeypatch, [_profile("폐업면옥", operating_status="closed")])

    assert response.status_code == 200
    assert response.json()["status"] == "no_recommendation"


def test_low_confidence_profiles_are_excluded(monkeypatch):
    response = _submit(monkeypatch, [_profile("근거부족면옥", profile_confidence="low")])

    assert response.status_code == 200
    assert response.json()["status"] == "no_recommendation"
