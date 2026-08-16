from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


ExperienceLevel = Literal["beginner", "expert"]
TypeKey = Literal["uraeok", "uijeongbu", "jangchungdong", "dongchimi"]
TraitKey = Literal["meat_aroma", "umami", "buckwheat_aroma", "acidity"]


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


class TypeSummary(BaseModel):
    """보조 유형(2순위·최원거리)에 쓰는 축약형. 화면에는 캐릭터와 이름만 노출된다."""

    key: TypeKey
    name: str
    character_key: str
    match_score: float = Field(ge=0.0, le=1.0)


class PrimaryType(TypeSummary):
    """대표 유형. 결과 화면 상단 카드에 필요한 카피를 모두 포함한다."""

    title: str
    subtitle: str
    badge: str
    reason: str
    theme_color: str


class TypeScore(BaseModel):
    key: TypeKey
    name: str
    match_score: float = Field(ge=0.0, le=1.0)


class TraitScale(BaseModel):
    min: float = 1.0
    max: float = 5.0


class TraitScore(BaseModel):
    key: TraitKey
    label: str
    score: float = Field(ge=1.0, le=5.0)


class TasteProfile(BaseModel):
    scale: TraitScale = TraitScale()
    traits: List[TraitScore]


class RecommendedRestaurant(BaseModel):
    rank: int
    restaurant_name: str
    fit_score: float = Field(ge=0.0, le=1.0)
    type_key: Optional[TypeKey] = None
    fit_sentence: str
    evidence_summary: str
    scores: Dict[str, float]
    address: Optional[str] = None
    map_url: Optional[str] = None


class RecommendationResultResponse(BaseModel):
    """결과 화면 전체를 한 번에 그릴 수 있는 응답.

    유형 판정과 취향 그래프는 사용자 답변만으로 계산되므로 가게 데이터와
    무관하게 항상 채워진다. 가게 추천만 비어 있을 수 있다.
    """

    status: Literal["recommended", "no_recommendation"]
    message: Optional[str] = None
    experience_level: ExperienceLevel
    primary_type: PrimaryType
    secondary_type: TypeSummary
    farthest_type: TypeSummary
    type_scores: List[TypeScore]
    taste_profile: TasteProfile
    recommended_restaurants: List[RecommendedRestaurant]
