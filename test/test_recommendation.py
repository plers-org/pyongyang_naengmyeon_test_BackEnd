import pytest
from fastapi.testclient import TestClient

from main import app
from services.recommendation_service import InMemoryProfileRepository


client = TestClient(app)

TRAIT_ORDER = ["meat_aroma", "umami", "buckwheat_aroma", "acidity"]
TRAIT_LABELS = ["육향", "감칠맛", "메밀향", "산미"]


def _profile(
    name,
    scores=(5, 4, 1, 1),
    operating_status="unknown",
    profile_confidence="medium",
    **extra,
):
    meat, umami, buckwheat, acidity = scores
    return {
        "restaurant_name": name,
        "meat_aroma_score": meat,
        "umami_score": umami,
        "buckwheat_aroma_score": buckwheat,
        "acidity_score": acidity,
        "profile_confidence": profile_confidence,
        "operating_status": operating_status,
        "fit_sentence": f"{name} 설명",
        "evidence_summary": f"{name} 근거",
        **extra,
    }


def _submit(monkeypatch, rows, experience_level="expert", choice=1):
    repository = InMemoryProfileRepository(rows)
    monkeypatch.setattr("api.v1.recommendation.recommendation_service.get_profile_repository", lambda: repository)
    return client.post(
        "/api/recommendation/submit",
        json={
            "experience_level": experience_level,
            "answers": [{"question_id": index, "selected_choice_id": choice} for index in range(1, 7)],
        },
    )


@pytest.fixture
def two_restaurants():
    return [
        _profile("진한면옥", scores=(5, 5, 1, 1), profile_confidence="high", operating_status="open"),
        _profile("맑은면옥", scores=(1, 1, 5, 5), profile_confidence="high", operating_status="open"),
    ]


# --- 문항 조회 -------------------------------------------------------------


def test_questions_are_selected_by_experience_level():
    beginner = client.get("/api/recommendation/questions/beginner")
    expert = client.get("/api/recommendation/questions/expert")

    assert beginner.status_code == 200
    assert expert.status_code == 200
    assert len(beginner.json()["questions"]) == 6
    assert len(expert.json()["questions"]) == 6
    assert beginner.json()["questions"][0]["question_text"] == "좋아하는 국물의 첫 느낌은?"
    assert expert.json()["questions"][0]["question_text"] == "육수 첫 느낌은 어때야 만족?"


def test_unsupported_experience_level_returns_404():
    assert client.get("/api/recommendation/questions/master").status_code == 404


# --- 유형 판정 (T1~T7) -----------------------------------------------------


@pytest.mark.parametrize(
    "experience_level,choices,expected",
    [
        # 각 유형에 해당하는 선택지만 고르면 그 유형이 대표가 된다.
        # 선택지 번호는 문항마다 다르다(CHOICE_TYPES 참고).
        ("expert", [1, 2, 3, 4, 1, 1], "uraeok"),
        ("expert", [2, 4, 2, 2, 2, 2], "uijeongbu"),
        ("expert", [3, 1, 1, 3, 3, 3], "jangchungdong"),
        ("expert", [4, 3, 4, 4, 4, 4], "dongchimi"),
        ("beginner", [1, 2, 3, 1, 1, 1], "uraeok"),
        ("beginner", [4, 3, 4, 4, 4, 4], "dongchimi"),
    ],
)
def test_answers_resolve_to_expected_type(monkeypatch, two_restaurants, experience_level, choices, expected):
    repository = InMemoryProfileRepository(two_restaurants)
    monkeypatch.setattr("api.v1.recommendation.recommendation_service.get_profile_repository", lambda: repository)

    response = client.post(
        "/api/recommendation/submit",
        json={
            "experience_level": experience_level,
            "answers": [
                {"question_id": index, "selected_choice_id": choice}
                for index, choice in enumerate(choices, 1)
            ],
        },
    )

    assert response.json()["primary_type"]["key"] == expected


def test_match_score_reflects_choice_ratio(monkeypatch, two_restaurants):
    """일치도는 6문항 중 해당 유형을 고른 비율이다."""
    repository = InMemoryProfileRepository(two_restaurants)
    monkeypatch.setattr("api.v1.recommendation.recommendation_service.get_profile_repository", lambda: repository)

    # expert 기준 우래옥형 선택지: Q1=1, Q2=2, Q3=3, Q4=1, Q5=1, Q6=1 → 6/6
    response = client.post(
        "/api/recommendation/submit",
        json={
            "experience_level": "expert",
            "answers": [
                {"question_id": index, "selected_choice_id": choice}
                for index, choice in enumerate([1, 2, 3, 1, 1, 1], 1)
            ],
        },
    )
    payload = response.json()

    assert payload["primary_type"]["key"] == "uraeok"
    assert payload["primary_type"]["match_score"] == 1.0
    assert payload["farthest_type"]["match_score"] == 0.0


def test_type_scores_contain_all_types_in_descending_order(monkeypatch, two_restaurants):
    payload = _submit(monkeypatch, two_restaurants).json()
    scores = payload["type_scores"]

    assert len(scores) == 4
    assert [s["match_score"] for s in scores] == sorted((s["match_score"] for s in scores), reverse=True)
    assert {s["key"] for s in scores} == {"uraeok", "uijeongbu", "jangchungdong", "dongchimi"}


def test_primary_secondary_farthest_map_to_type_ranking(monkeypatch, two_restaurants):
    payload = _submit(monkeypatch, two_restaurants).json()
    scores = payload["type_scores"]

    assert payload["primary_type"]["key"] == scores[0]["key"]
    assert payload["secondary_type"]["key"] == scores[1]["key"]
    assert payload["farthest_type"]["key"] == scores[3]["key"]


def test_three_displayed_types_are_distinct(monkeypatch, two_restaurants):
    payload = _submit(monkeypatch, two_restaurants).json()

    keys = {payload["primary_type"]["key"], payload["secondary_type"]["key"], payload["farthest_type"]["key"]}
    assert len(keys) == 3


def test_match_scores_are_within_range(monkeypatch, two_restaurants):
    payload = _submit(monkeypatch, two_restaurants).json()

    assert all(0.0 <= s["match_score"] <= 1.0 for s in payload["type_scores"])


def test_primary_type_carries_full_copy(monkeypatch, two_restaurants):
    primary = _submit(monkeypatch, two_restaurants).json()["primary_type"]

    for field in ("title", "subtitle", "badge", "reason", "theme_color", "character_key"):
        assert primary[field], f"{field}가 비어 있습니다"
    assert primary["theme_color"].startswith("#")


# --- 취향 그래프 (T8~T10) --------------------------------------------------


def test_taste_profile_has_four_traits_in_fixed_order(monkeypatch, two_restaurants):
    profile = _submit(monkeypatch, two_restaurants).json()["taste_profile"]

    assert [t["key"] for t in profile["traits"]] == TRAIT_ORDER
    assert profile["scale"] == {"min": 1.0, "max": 5.0}


def test_taste_profile_labels_are_korean(monkeypatch, two_restaurants):
    profile = _submit(monkeypatch, two_restaurants).json()["taste_profile"]

    assert [t["label"] for t in profile["traits"]] == TRAIT_LABELS


def test_taste_profile_scores_are_within_scale(monkeypatch, two_restaurants):
    profile = _submit(monkeypatch, two_restaurants).json()["taste_profile"]

    assert all(1.0 <= t["score"] <= 5.0 for t in profile["traits"])


# --- 가게 추천 (T11~T18) ---------------------------------------------------


def test_returns_two_restaurants_ranked(monkeypatch):
    rows = [
        _profile("진한면옥", scores=(5, 5, 1, 1)),
        _profile("중간면옥", scores=(3, 3, 3, 3)),
        _profile("맑은면옥", scores=(1, 1, 5, 5)),
    ]
    restaurants = _submit(monkeypatch, rows).json()["recommended_restaurants"]

    assert len(restaurants) == 2
    assert [r["rank"] for r in restaurants] == [1, 2]
    assert restaurants[0]["fit_score"] >= restaurants[1]["fit_score"]


def test_recommended_restaurant_carries_display_fields(monkeypatch, two_restaurants):
    top = _submit(monkeypatch, two_restaurants).json()["recommended_restaurants"][0]

    assert top["restaurant_name"] == "진한면옥"
    assert top["fit_sentence"] and top["evidence_summary"]
    assert set(top["scores"]) == set(TRAIT_ORDER)
    assert 0.0 <= top["fit_score"] <= 1.0


def test_single_candidate_returns_one_restaurant(monkeypatch):
    payload = _submit(monkeypatch, [_profile("유일면옥")]).json()

    assert payload["status"] == "recommended"
    assert len(payload["recommended_restaurants"]) == 1


def test_no_candidates_still_returns_type_and_graph(monkeypatch):
    """추천할 가게가 없어도 유형과 취향 그래프는 반드시 채워진다."""
    payload = _submit(monkeypatch, []).json()

    assert payload["status"] == "no_recommendation"
    assert payload["message"]
    assert payload["recommended_restaurants"] == []
    assert payload["primary_type"]["key"]
    assert len(payload["taste_profile"]["traits"]) == 4


def test_unknown_operating_status_stays_in_candidates(monkeypatch):
    """영업 상태 미확인(unknown)은 폐업 근거가 아니므로 후보에 남는다."""
    payload = _submit(monkeypatch, [_profile("미확인면옥", operating_status="unknown")]).json()

    assert payload["recommended_restaurants"][0]["restaurant_name"] == "미확인면옥"


def test_closed_restaurants_are_excluded(monkeypatch):
    payload = _submit(monkeypatch, [_profile("폐업면옥", operating_status="closed")]).json()

    assert payload["status"] == "no_recommendation"


def test_low_confidence_profiles_are_excluded(monkeypatch):
    payload = _submit(monkeypatch, [_profile("근거부족면옥", profile_confidence="low")]).json()

    assert payload["status"] == "no_recommendation"


def test_tied_candidates_still_return_recommendations(monkeypatch):
    """적합도가 같아도 추천을 포기하지 않고 가게명 순으로 확정한다."""
    rows = [_profile("나면옥", scores=(3, 3, 3, 3)), _profile("가면옥", scores=(3, 3, 3, 3))]
    payload = _submit(monkeypatch, rows).json()

    assert payload["status"] == "recommended"
    assert [r["restaurant_name"] for r in payload["recommended_restaurants"]] == ["가면옥", "나면옥"]


# --- 입력 검증 (T19~T21) ---------------------------------------------------


def test_incomplete_answers_return_400(monkeypatch):
    repository = InMemoryProfileRepository([])
    monkeypatch.setattr("api.v1.recommendation.recommendation_service.get_profile_repository", lambda: repository)

    response = client.post(
        "/api/recommendation/submit",
        json={
            "experience_level": "expert",
            "answers": [{"question_id": index, "selected_choice_id": 1} for index in range(1, 6)],
        },
    )

    assert response.status_code == 400


def test_duplicated_question_ids_return_400(monkeypatch):
    repository = InMemoryProfileRepository([])
    monkeypatch.setattr("api.v1.recommendation.recommendation_service.get_profile_repository", lambda: repository)

    response = client.post(
        "/api/recommendation/submit",
        json={
            "experience_level": "expert",
            "answers": [{"question_id": 1, "selected_choice_id": 1} for _ in range(6)],
        },
    )

    assert response.status_code == 400


def test_out_of_range_choice_returns_422():
    response = client.post(
        "/api/recommendation/submit",
        json={
            "experience_level": "expert",
            "answers": [{"question_id": index, "selected_choice_id": 5} for index in range(1, 7)],
        },
    )

    assert response.status_code == 422
