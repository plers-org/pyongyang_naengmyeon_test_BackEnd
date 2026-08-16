from typing import Dict, List, Literal, Union

from pydantic import BaseModel, Field


ExperienceLevel = Literal["beginner", "expert"]


class RecommendationChoice(BaseModel):
    choice_id: int
    choice_text: str


class RecommendationQuestion(BaseModel):
    question_id: int
    question_text: str
    choices: List[RecommendationChoice]
    progress: float


class RecommendationQuestionsResponse(BaseModel):
    experience_level: ExperienceLevel
    questions: List[RecommendationQuestion]


class RecommendationAnswer(BaseModel):
    question_id: int = Field(ge=1, le=6)
    selected_choice_id: int = Field(ge=1, le=4)


class RecommendationSubmitRequest(BaseModel):
    experience_level: ExperienceLevel
    answers: List[RecommendationAnswer]


class RecommendationSuccessResponse(BaseModel):
    status: Literal["recommended"] = "recommended"
    restaurant_name: str
    fit_score: float
    explanation: str
    evidence_summary: str


class NoRecommendationResponse(BaseModel):
    status: Literal["no_recommendation"] = "no_recommendation"
    message: str = "추천 가능한 식당이 없습니다."


RecommendationResponse = Union[RecommendationSuccessResponse, NoRecommendationResponse]
