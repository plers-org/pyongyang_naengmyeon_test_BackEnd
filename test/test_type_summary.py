"""대표·2순위·최원거리 유형의 불변식과 해시태그 노출을 고정한다.

결과 화면이 세 유형을 나란히 보여주므로, 셋 중 둘이 같은 유형이 되면
"두 번째로 잘 맞는 유형"과 "가장 거리가 먼 유형"에 같은 카드가 뜬다.
어떤 답변 조합에서도 그런 일이 없어야 한다.
"""

from itertools import product

import pytest

from services.recommendation_data import CHOICE_VECTORS
from services.recommendation_service import calculate_taste_vector
from services.taste_type_data import TASTE_TYPES, rank_types
from schemas.recommendation import RecommendationSubmitRequest


EXPECTED_HASHTAGS = {
    "uraeok": ["진한육향", "깊은감칠맛", "본질파"],
    "dongchimi": ["시원한동치미", "깔끔한끝맛", "청량파"],
    "uijeongbu": ["맑고담백", "은근한 여운", "담백파"],
    "jangchungdong": ["구수한육향", "풍성한감칠맛", "균형파"],
}


def _ranking(experience_level, combo):
    request = RecommendationSubmitRequest(
        experience_level=experience_level,
        answers=[
            {"question_id": index + 1, "selected_choice_id": choice}
            for index, choice in enumerate(combo)
        ],
    )
    preferred = calculate_taste_vector(request)
    selections = [(index + 1, choice) for index, choice in enumerate(combo)]
    return rank_types(preferred, selections, experience_level)


@pytest.mark.parametrize("experience_level", sorted(CHOICE_VECTORS))
def test_ranking_covers_every_type_exactly_once(experience_level):
    """어떤 답변 조합에서도 4개 유형이 중복 없이 한 번씩 정렬되어 온다."""
    for combo in product(range(1, 5), repeat=6):
        keys = [key for key, _ in _ranking(experience_level, combo)]
        assert sorted(keys) == sorted(TASTE_TYPES), combo


@pytest.mark.parametrize("experience_level", sorted(CHOICE_VECTORS))
def test_primary_secondary_farthest_are_distinct(experience_level):
    """대표·2순위·최원거리가 서로 다른 유형이다. 화면에 같은 카드가 두 번 뜨지 않는다."""
    for combo in product(range(1, 5), repeat=6):
        ranking = _ranking(experience_level, combo)
        primary, secondary, farthest = ranking[0][0], ranking[1][0], ranking[-1][0]
        assert len({primary, secondary, farthest}) == 3, combo


@pytest.mark.parametrize("experience_level", sorted(CHOICE_VECTORS))
def test_scores_are_descending(experience_level):
    """점수가 내림차순이라 2순위가 최원거리보다 항상 높거나 같다."""
    for combo in product(range(1, 5), repeat=6):
        scores = [score for _, score in _ranking(experience_level, combo)]
        assert scores == sorted(scores, reverse=True), combo


def test_every_type_has_three_hashtags():
    for key, expected in EXPECTED_HASHTAGS.items():
        assert list(TASTE_TYPES[key]["hashtags"]) == expected


def test_hashtags_have_no_leading_hash():
    """`#` 은 프론트가 붙인다. 서버 값에 들어가면 `##진한육향` 이 된다."""
    for payload in TASTE_TYPES.values():
        for tag in payload["hashtags"]:
            assert not tag.startswith("#")


def test_hashtags_come_through_api(monkeypatch):
    """제출 응답의 세 유형 카드에 해시태그 3개가 모두 실린다."""
    from fastapi.testclient import TestClient

    from main import app

    client = TestClient(app)
    response = client.post(
        "/api/recommendation/submit",
        json={
            "experience_level": "beginner",
            "answers": [
                {"question_id": index, "selected_choice_id": (index % 4) + 1}
                for index in range(1, 7)
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()

    seen = set()
    for field in ("primary_type", "secondary_type", "farthest_type"):
        card = body[field]
        assert card["hashtags"] == EXPECTED_HASHTAGS[card["key"]]
        seen.add(card["key"])

    # 세 카드가 서로 다른 유형이어야 화면에 같은 캐릭터가 두 번 뜨지 않는다.
    assert len(seen) == 3
