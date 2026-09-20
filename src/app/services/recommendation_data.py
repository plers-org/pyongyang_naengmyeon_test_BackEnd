from typing import Dict, List, Tuple

from schemas.recommendation import RecommendationQuestion, RecommendationChoice


# Trait order: meat aroma, umami, buckwheat aroma, acidity.
TRAITS = ("meat_aroma", "umami", "buckwheat_aroma", "acidity")
TraitVector = Tuple[float, float, float, float]

# 취향 그래프에 표시할 축 이름. 문구 변경 시 서버만 배포하면 되도록 응답에 함께 내려준다.
TRAIT_LABELS: Dict[str, str] = {
    "meat_aroma": "육향",
    "umami": "감칠맛",
    "buckwheat_aroma": "메밀향",
    "acidity": "산미",
}

# 결과 화면에 노출할 추천 가게 수.
RECOMMENDATION_COUNT = 2


def _question(question_id: int, text: str, choices: List[str]) -> RecommendationQuestion:
    return RecommendationQuestion(
        question_id=question_id,
        question_text=text,
        choices=[RecommendationChoice(choice_id=i, choice_text=value) for i, value in enumerate(choices, 1)],
        progress=round(question_id / 6 * 100, 1),
    )


QUESTIONS: Dict[str, List[RecommendationQuestion]] = {
    "beginner": [
        _question(1, "좋아하는 국물의 첫 느낌은?", ["깊고 진한 고기 맛과 향이 느껴져야", "슴슴한데 은은한 감칠맛이 있어야", "아주 맑고 담백해야", "새콤하고 개운해야"]),
        _question(2, '“이 국물 좀 싱거운데?”라는 말을 들으면?', ["그 맛으로 먹는 건데?", "맛이 좀 더 진하고 확실한 게 좋아", "새콤달콤하게 가자", "밍밍하지 않게 은은한 감칠맛은 있어야 해"]),
        _question(3, "면 요리에서 끌리는 면발은?", ["메밀 향이 느껴지고 툭툭 끊기는 거친 면", "적당히 탄력있고 잘 끊기는 면", "면발보다 육수가 중요", "새로운 식감이면 좋아"]),
        _question(4, "고명으로 가장 반가운 건?", ["두툼한 편육", "파 + 고춧가루 솔솔", "오이 채", "새콤하고 아삭한 배나 무"]),
        _question(5, "새로운 음식에 도전하고 싶다면, 어떤 맛?", ["육향 진한", "슴슴하면서 감칠맛 밸런스가 좋은", "맑고 담백하며 미묘함이 또렷한", "새콤한 맛이 살아있는"]),
        _question(6, "평소 좋아하는 음식의 맛은?", ["맛과 향이 진하고 확실한", "담백하면서 감칠맛이 균형 잡힌", "자극적이지 않고 은은한", "산뜻하고 개운한"]),
    ],
    "expert": [
        _question(1, "육수 첫 느낌은 어때야 만족?", ["진한 고기 향이 확 올라와야", "슴슴한데 감칠맛이 은은히 있어야", "거의 맹물처럼 맑아야", "새콤하고 청량해야"]),
        _question(2, '“이 육수 좀 싱거운데?”라는 말을 들으면?', ["그게 매력인데?", "그럼 좀 자극적인 데로 가자", "새콤달콤하게 가자", "은은한 감칠맛은 있어야 해"]),
        _question(3, "면발은 어때야 만족?", ["툭툭 끊기는 거친 순면", "적당히 탄력있고 잘 끊기는 면", "크게 상관없음, 육수가 중요", "면 향과 식감이 뚜렷하면 좋음"]),
        _question(4, "고명으로 가장 반가운 건?", ["두툼한 편육", "파 + 고춧가루 솔솔", "오이 채", "새콤하고 아삭한 배나 무"]),
        _question(5, "평소 가장 끌리는 평양냉면은?", ["욱향 진한", "슴슴하면서 감칠맛 밸런스가 좋은", "맑고 담백하며 미묘함이 또렷한", "동치미의 산뜻하고 새콤한 맛이 살아있는"]),
        _question(6, "평양냉면을 다 먹고 어떤 느낌이면 만족?", ["이 정도는 자극적이어야 먹은 것 같아", "슴슴+감칠맛 조화가 딱 좋아", "밍밍한 진짜, 슴슴할수록 고수", "새콤함이 없으면 심심해"]),
    ],
}


CHOICE_VECTORS: Dict[str, Dict[int, TraitVector]] = {
    "beginner": {
        1: ((5, 4, 1, 1), (1, 4, 2, 1), (1, 1, 3, 1), (1, 1, 1, 5)),
        2: ((1, 1, 1, 1), (5, 4, 1, 1), (1, 1, 1, 5), (1, 4, 2, 1)),
        3: ((1, 2, 5, 1), (1, 3, 3, 1), (1, 4, 1, 1), (1, 2, 4, 1)),
        4: ((2, 2, 1, 1), (1, 3, 2, 1), (1, 1, 2, 1), (1, 1, 1, 5)),
        5: ((5, 4, 1, 1), (1, 5, 2, 1), (1, 1, 4, 1), (1, 1, 1, 5)),
        6: ((5, 4, 1, 1), (1, 5, 2, 1), (1, 2, 4, 1), (1, 1, 1, 5)),
    },
    "expert": {
        1: ((5, 4, 1, 1), (1, 4, 2, 1), (1, 1, 4, 1), (1, 1, 1, 5)),
        2: ((1, 1, 1, 1), (5, 4, 1, 1), (1, 1, 1, 5), (1, 4, 2, 1)),
        3: ((1, 2, 5, 1), (1, 3, 3, 1), (1, 4, 1, 1), (1, 2, 4, 1)),
        4: ((2, 2, 1, 1), (1, 3, 2, 1), (1, 1, 2, 1), (1, 1, 1, 5)),
        5: ((5, 4, 1, 1), (1, 5, 2, 1), (1, 1, 4, 1), (1, 1, 1, 5)),
        6: ((5, 4, 1, 1), (1, 5, 2, 1), (1, 2, 5, 1), (1, 1, 1, 5)),
    },
}
