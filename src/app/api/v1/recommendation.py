from typing import Union

from fastapi import APIRouter

from schemas.recommendation import (
    NoRecommendationResponse,
    RecommendationQuestionsResponse,
    RecommendationResponse,
    RecommendationSubmitRequest,
    RecommendationSuccessResponse,
)
from services import recommendation_service


router = APIRouter()


@router.get("/recommendation/questions/{experience_level}", response_model=RecommendationQuestionsResponse)
def get_recommendation_questions(experience_level: str) -> RecommendationQuestionsResponse:
    if experience_level not in ("beginner", "expert"):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="지원하지 않는 경험 수준입니다.")
    return RecommendationQuestionsResponse(
        experience_level=experience_level,
        questions=recommendation_service.get_questions(experience_level),
    )


@router.post(
    "/recommendation/submit",
    response_model=Union[RecommendationSuccessResponse, NoRecommendationResponse],
)
def submit_recommendation(request: RecommendationSubmitRequest) -> RecommendationResponse:
    result = recommendation_service.recommend(request, recommendation_service.get_profile_repository())
    if result is None:
        return NoRecommendationResponse()
    score, profile = result
    return RecommendationSuccessResponse(
        restaurant_name=profile.restaurant_name,
        fit_score=score,
        explanation=profile.fit_sentence,
        evidence_summary=profile.evidence_summary,
    )
