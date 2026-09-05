"""평냉 취향 유형 4종의 판정 기준과 결과 화면 카피.

유형 체계는 search/docs/questions.md의 정의를, 사용자 노출 문구는 결과 화면 시안을 따른다.

유형 판정은 선택지-유형 매핑(CHOICE_TYPES) 카운팅으로 한다. 4축 벡터 거리로
판정하지 않는 이유는 두 가지다.

1. 6문항 평균은 중앙으로 수렴하므로, 유형 기준 벡터 중 가장 중앙에 가까운 하나가
   대부분의 결과를 흡수한다. 실측 시 4096개 답변 조합의 88%가 한 유형으로 쏠렸다.
2. 실제 가게 데이터에서 유형별 중심을 유도해도 변별되지 않는다. 육향이 전 유형
   4.6~5.0, 메밀향이 4.33~5.0으로 사실상 동일하다. 점수가 리뷰 텍스트 기반 자동
   산출이라 "언급되면 높은 점수"가 되어 상향 편중된 탓이다.

가게 추천은 기존대로 4축 거리를 쓴다. 후보 간 상대 비교라 절대 편중이 상쇄된다.
"""

from collections import Counter
from typing import Dict, List, Mapping, Sequence, Tuple

from services.recommendation_data import TRAITS


# 선언 순서가 동점 시 tie-break 순서가 된다.
TASTE_TYPES: Dict[str, Mapping[str, object]] = {
    "uraeok": {
        "name": "우래옥형",
        "title": "진하고 든든한 우래옥형",
        "subtitle": "가장 진한 고기 향과 깊은 감칠맛을 좋아하는 본질파 타입이에요",
        "badge": "맑고 순수한 맛에서 진짜 깊이를 찾아요",
        "reason": (
            "고기 향이 뚜렷한 육수의 묵직함과 메밀 면발이 진짜 평양냉면이라고 느끼는 타입이에요. "
            "다른 계열보다 진한 육향과 감칠맛에서 깊이를 찾아요. "
            "평양냉면의 슴슴함이 아직 낯선 사람도 맛있게 즐기기 좋은 스타일이에요."
        ),
        "theme_color": "#C98A3C",
        "hashtags": ["진한육향", "깊은감칠맛", "본질파"],
        "vector": {"meat_aroma": 5.0, "umami": 4.0, "buckwheat_aroma": 2.0, "acidity": 1.0},
        "legacy_category": "우래옥",
    },
    "dongchimi": {
        "name": "동치미형",
        "title": "산뜻하고 개운한 동치미형",
        "subtitle": "시원한 동치미 향과 깔끔한 끝맛이 매력적인 청량파 타입이에요",
        "badge": "마지막 한입까지 개운해야 해요",
        "reason": (
            "시원한 동치미 육수와 산뜻하게 넘어가는 메밀 면발이 진짜 평양냉면이라고 느끼는 타입이에요. "
            "묵직한 고기 향보다는 새콤하고 개운한 맛에서 매력을 찾아요. "
            "깔끔하고 청량한 평양냉면을 좋아하는 사람들이 즐겨 찾는 스타일이에요."
        ),
        "theme_color": "#3D8FD1",
        "hashtags": ["시원한동치미", "깔끔한끝맛", "청량파"],
        "vector": {"meat_aroma": 2.0, "umami": 4.0, "buckwheat_aroma": 2.0, "acidity": 5.0},
        "legacy_category": "동치미",
    },
    "uijeongbu": {
        "name": "의정부형",
        "title": "맑고 담백한 의정부형",
        "subtitle": "깔끔한 육수와 은은한 여운을 즐기는 담백파 타입이에요",
        "badge": "조용히 스며드는 맛이 오래 남아요",
        "reason": (
            "맑고 담백한 육수와 부드럽게 끊기는 메밀 면발이 진짜 평양냉면이라고 느끼는 타입이에요. "
            "우래옥보다는 감칠맛이 조금 더 느껴지는 편안하고 균형 잡힌 맛을 좋아해요. "
            "평냉에 입문한 사람도 부담 없이 즐기기 좋은 스타일이에요."
        ),
        "theme_color": "#5FA845",
        "hashtags": ["맑고담백", "은근한 여운", "담백파"],
        "vector": {"meat_aroma": 2.0, "umami": 3.0, "buckwheat_aroma": 3.0, "acidity": 1.0},
        "legacy_category": "의정부",
    },
    "jangchungdong": {
        "name": "장충동형",
        "title": "구수하고 풍성한 장충동형",
        "subtitle": "은은한 고기 향과 감칠맛이 조화로운 균형파 타입이에요",
        "badge": "맛있는 포인트는 절대로 놓치지 않아요",
        "reason": (
            "물처럼 맑은 육수와 곡향이 강한 메밀 면발이 진짜 평양냉면이라고 느끼는 타입이에요. "
            "의정부 계열보다도 더 슴슴하고 은은한 맛에서 깊이를 찾아요. "
            "평냉 고수들이 즐겨 찾는 스타일이에요."
        ),
        "theme_color": "#8C8C8C",
        "hashtags": ["구수한육향", "풍성한감칠맛", "균형파"],
        "vector": {"meat_aroma": 1.0, "umami": 1.0, "buckwheat_aroma": 5.0, "acidity": 1.0},
        "legacy_category": "장충동",
    },
}


# search의 legacy_category(한글) → type_key 매핑.
LEGACY_CATEGORY_TO_TYPE_KEY: Dict[str, str] = {
    str(payload["legacy_category"]): key for key, payload in TASTE_TYPES.items()
}


# 각 문항의 선택지 1~4가 대표하는 유형. 선택지 문구의 의미를 그대로 선언한다.
# 대부분의 문항은 (우래옥, 의정부, 장충동, 동치미) 순서지만 Q2·Q3은 순서가 다르다.
_STANDARD = ("uraeok", "uijeongbu", "jangchungdong", "dongchimi")
_CHOICE_TYPES_BY_QUESTION = {
    # Q1 육수/국물 첫 느낌: 진한 고기향 / 슴슴+감칠맛 / 맑음 / 새콤 청량
    1: _STANDARD,
    # Q2 "싱겁다"는 말에: 그게 매력(슴슴 고수) / 자극적인 데로 / 새콤달콤 / 은은한 감칠맛
    2: ("jangchungdong", "uraeok", "dongchimi", "uijeongbu"),
    # Q3 면발: 거친 순면 / 적당한 탄력 / 면보다 육수 / 면 향과 식감이 뚜렷
    3: ("jangchungdong", "uijeongbu", "uraeok", "jangchungdong"),
    # Q4 고명: 두툼한 편육 / 파+고춧가루 / 오이 채 / 새콤한 배·무
    4: _STANDARD,
    # Q5 끌리는 평양냉면, Q6 평소 좋아하는 맛
    5: _STANDARD,
    6: _STANDARD,
}
CHOICE_TYPES: Dict[str, Dict[int, Tuple[str, ...]]] = {
    "expert": dict(_CHOICE_TYPES_BY_QUESTION),
    "beginner": dict(_CHOICE_TYPES_BY_QUESTION),
}


def type_match_score(preferred: Mapping[str, float], vector: Mapping[str, float]) -> float:
    """취향 벡터와 유형 기준 벡터의 일치도. 동점 유형을 가르는 보조 지표로만 쓴다."""
    distance = sum(abs(vector[trait] - preferred[trait]) / 4 for trait in TRAITS)
    return round(1 - distance / len(TRAITS), 4)


def rank_types(
    preferred: Mapping[str, float],
    selections: Sequence[Tuple[int, int]],
    experience_level: str,
) -> List[Tuple[str, float]]:
    """유형을 선택 비율 내림차순으로 정렬한다.

    selections는 (question_id, selected_choice_id) 목록이다.
    같은 횟수로 선택된 유형은 취향 벡터와의 거리로, 그래도 같으면
    TASTE_TYPES 선언 순서로 가른다.

    반환하는 점수는 6문항 중 해당 유형을 고른 비율(0.0~1.0)이다.
    """
    choice_types = CHOICE_TYPES[experience_level]
    counts = Counter(
        choice_types[question_id][choice_id - 1]
        for question_id, choice_id in selections
        if question_id in choice_types
    )

    order = {key: index for index, key in enumerate(TASTE_TYPES)}
    total = len(selections) or 1
    ranked = sorted(
        TASTE_TYPES,
        key=lambda key: (
            -counts.get(key, 0),
            -type_match_score(preferred, TASTE_TYPES[key]["vector"]),
            order[key],
        ),
    )
    return [(key, round(counts.get(key, 0) / total, 4)) for key in ranked]
