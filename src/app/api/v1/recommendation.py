from fastapi import APIRouter, HTTPException, Path

from schemas.recommendation import (
    PrimaryType,
    RecommendationQuestionsResponse,
    RecommendationResultResponse,
    RecommendationSubmitRequest,
    RecommendedRestaurant,
    TasteProfile,
    TraitScore,
    TypeScore,
    TypeSummary,
)
from services import recommendation_service, response_repository
from services.recommendation_data import TEMP_ADDRESS_URL, TRAIT_LABELS, TRAITS
from services.taste_type_data import TASTE_TYPES


router = APIRouter()


@router.get(
    "/recommendation/questions/{experience_level}",
    response_model=RecommendationQuestionsResponse,
    summary="취향 테스트 문항 6개 받아오기",
    description=(
        "**언제 호출하나** — 사용자가 시작 화면에서 입문자/경험자를 고른 직후, 테스트당 한 번만 호출합니다.\n\n"
        "**무엇이 오나** — 6개 문항이 한 번에 옵니다. 문항마다 4개의 선택지가 들어 있고, "
        "`question_id`(1~6)와 `choice_id`(1~4)는 나중에 답을 제출할 때 그대로 다시 보내야 하는 값입니다.\n\n"
        "문항을 하나씩 요청하는 API는 없습니다. 받아온 6문항을 프론트가 순서대로 보여주면서 "
        "사용자의 선택을 모아두었다가, 마지막에 `POST /api/recommendation/submit` 으로 한 번에 제출하세요.\n\n"
        "`progress` 는 그 문항까지 왔을 때의 진행률(%)이라 진행 바에 그대로 쓸 수 있습니다. "
        "(1번 문항 16.7 → 6번 문항 100.0)\n\n"
        "**두 문항 세트의 차이** — 문항 수와 구조는 같고 표현만 다릅니다. "
        "`beginner` 는 평양냉면이 처음인 사람도 답할 수 있게 일반적인 음식 취향을 묻고, "
        "`expert` 는 육수·면발 같은 용어를 그대로 씁니다."
    ),
    responses={
        404: {
            "description": "`experience_level` 이 `beginner` 도 `expert` 도 아닌 경우",
            "content": {"application/json": {"example": {"detail": "지원하지 않는 경험 수준입니다."}}},
        },
    },
)
def get_recommendation_questions(
    experience_level: str = Path(
        description="문항 세트 종류. `beginner`(평양냉면이 처음인 사용자) 또는 `expert`(먹어본 적 있는 사용자).",
        examples=["beginner"],
    ),
) -> RecommendationQuestionsResponse:
    if experience_level not in ("beginner", "expert"):
        raise HTTPException(status_code=404, detail="지원하지 않는 경험 수준입니다.")
    return RecommendationQuestionsResponse(
        experience_level=experience_level,
        questions=recommendation_service.get_questions(experience_level),
    )


@router.post(
    "/recommendation/submit",
    response_model=RecommendationResultResponse,
    summary="답변을 제출하고 결과 화면 데이터 받기",
    description=(
        "**언제 호출하나** — 사용자가 6문항을 모두 답한 뒤 한 번만 호출합니다. "
        "이 API 하나로 취향 유형 판정과 가게 추천이 동시에 끝납니다.\n\n"
        "**무엇을 보내나** — 앞서 받아온 문항의 `question_id` 와 사용자가 고른 `choice_id` 짝을 "
        "`answers` 배열에 담아 보냅니다. 6문항 전부 채워 보내세요.\n\n"
        "**무엇이 오나** — 결과 화면 하나를 그릴 재료가 전부 들어 있어서, 추가 호출이 필요 없습니다.\n\n"
        "- `primary_type` — 대표 유형. 제목·부제·배지·설명 문구와 테마 색까지 들어 있어 그대로 화면에 쓰면 됩니다. "
        "문구를 서버에서 내려주므로 프론트에 유형별 텍스트를 하드코딩하지 마세요.\n"
        "- `secondary_type` / `farthest_type` — 2순위 유형과 가장 안 맞는 유형. 이름과 캐릭터만 들어 있습니다.\n"
        "- `type_scores` — 4개 유형 전체의 일치도. 막대 그래프용입니다.\n"
        "- `taste_profile` — 육향·감칠맛·메밀향·산미 4축 점수(1~5). 축 이름(`label`)도 함께 오므로 "
        "그래프 축 이름을 프론트에 적어둘 필요가 없습니다.\n"
        "- `recommended_restaurants` — 추천 가게 2곳. 순위, 추천 이유 문장, 주소, 지도 링크가 들어 있습니다.\n\n"
        "**가게가 없을 수 있습니다** — `status` 가 `no_recommendation` 이면 `recommended_restaurants` 가 빈 배열로 "
        "오고 `message` 에 안내 문구가 담깁니다. 이때도 유형 판정과 취향 그래프는 정상적으로 채워지므로, "
        "가게 목록 영역만 비우고 나머지 결과는 그대로 보여주면 됩니다.\n\n"
        "**`session_id` 는 선택입니다** — 프론트가 만든 익명 UUID를 넣으면 같은 사용자의 응답을 묶어 "
        "유형 분포를 집계할 수 있습니다. 로그인과 무관하며 개인정보를 넣어서는 안 됩니다. 생략해도 결과는 같습니다."
    ),
)
def submit_recommendation(request: RecommendationSubmitRequest) -> RecommendationResultResponse:
    result = recommendation_service.recommend(request, recommendation_service.get_profile_repository())

    restaurants = [
        RecommendedRestaurant(
            rank=rank,
            restaurant_name=profile.restaurant_name,
            fit_score=score,
            type_key=profile.type_key,
            fit_sentence=profile.fit_sentence,
            evidence_summary=profile.evidence_summary,
            scores=dict(profile.scores),
            address=profile.address,
            # 수집된 링크가 있으면 그것을 쓰고, 없을 때만 임시 값으로 채운다.
            map_url=profile.map_url or TEMP_ADDRESS_URL,
        )
        for rank, (score, profile) in enumerate(result.restaurants, 1)
    ]

    response_repository.record_safely(
        response_repository.get_response_repository(),
        session_id=request.session_id,
        experience_level=request.experience_level,
        answers=[answer.model_dump() for answer in request.answers],
        taste_vector=dict(result.preferred),
        primary_type=result.type_ranking[0][0],
        secondary_type=result.type_ranking[1][0],
        recommended=[
            {"restaurant_name": item.restaurant_name, "fit_score": item.fit_score} for item in restaurants
        ],
    )

    return RecommendationResultResponse(
        status="recommended" if restaurants else "no_recommendation",
        message=None if restaurants else "추천 가능한 식당이 없습니다.",
        experience_level=request.experience_level,
        primary_type=_primary_type(*result.type_ranking[0]),
        secondary_type=_type_summary(*result.type_ranking[1]),
        farthest_type=_type_summary(*result.type_ranking[-1]),
        type_scores=[
            TypeScore(key=key, name=TASTE_TYPES[key]["name"], match_score=score)
            for key, score in result.type_ranking
        ],
        taste_profile=TasteProfile(
            traits=[
                TraitScore(key=trait, label=TRAIT_LABELS[trait], score=result.preferred[trait])
                for trait in TRAITS
            ]
        ),
        recommended_restaurants=restaurants,
    )


def _primary_type(key: str, score: float) -> PrimaryType:
    payload = TASTE_TYPES[key]
    return PrimaryType(
        key=key,
        name=payload["name"],
        character_key=key,
        match_score=score,
        title=payload["title"],
        subtitle=payload["subtitle"],
        badge=payload["badge"],
        reason=payload["reason"],
        theme_color=payload["theme_color"],
    )


def _type_summary(key: str, score: float) -> TypeSummary:
    return TypeSummary(
        key=key,
        name=TASTE_TYPES[key]["name"],
        character_key=key,
        match_score=score,
    )
