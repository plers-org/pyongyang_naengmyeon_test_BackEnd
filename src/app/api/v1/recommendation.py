from fastapi import APIRouter, HTTPException

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


@router.get("/recommendation/questions/{experience_level}", response_model=RecommendationQuestionsResponse)
def get_recommendation_questions(experience_level: str) -> RecommendationQuestionsResponse:
    if experience_level not in ("beginner", "expert"):
        raise HTTPException(status_code=404, detail="지원하지 않는 경험 수준입니다.")
    return RecommendationQuestionsResponse(
        experience_level=experience_level,
        questions=recommendation_service.get_questions(experience_level),
    )


@router.post("/recommendation/submit", response_model=RecommendationResultResponse)
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
