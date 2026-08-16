import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Protocol, Sequence, Tuple

from fastapi import HTTPException

from schemas.recommendation import RecommendationSubmitRequest
from services.recommendation_data import (
    CHOICE_VECTORS,
    QUESTIONS,
    RECOMMENDATION_COUNT,
    TRAITS,
)
from services.taste_type_data import rank_types


@dataclass(frozen=True)
class RestaurantProfile:
    restaurant_name: str
    scores: Mapping[str, float]
    profile_confidence: str
    operating_status: str
    fit_sentence: str
    evidence_summary: str
    type_key: Optional[str] = None
    address: Optional[str] = None
    map_url: Optional[str] = None


@dataclass(frozen=True)
class RecommendationResult:
    """추천 계산 결과.

    preferred와 type_ranking은 사용자 답변만으로 결정되므로 가게 데이터가
    없어도 항상 채워진다. restaurants만 비어 있을 수 있다.
    """

    preferred: Mapping[str, float]
    type_ranking: Sequence[Tuple[str, float]]
    restaurants: Sequence[Tuple[float, RestaurantProfile]]


class ProfileRepository(Protocol):
    def list_profiles(self) -> Sequence[RestaurantProfile]: ...


def _optional_str(value: object) -> Optional[str]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return str(value)


class InMemoryProfileRepository:
    def __init__(self, rows: Iterable[Mapping[str, object]] = ()) -> None:
        self._profiles = []
        for row in rows:
            try:
                scores = {trait: float(row[f"{trait}_score"]) for trait in TRAITS}
            except (KeyError, TypeError, ValueError):
                # 근거가 부족해 4축 점수를 매기지 못한 프로필은 추천 대상이 아니다.
                continue
            self._profiles.append(
                RestaurantProfile(
                    restaurant_name=str(row["restaurant_name"]),
                    scores=scores,
                    profile_confidence=str(row.get("profile_confidence", "low")),
                    operating_status=str(row.get("operating_status", "unknown")),
                    fit_sentence=str(row.get("fit_sentence", "")),
                    evidence_summary=str(row.get("evidence_summary", "")),
                    type_key=_optional_str(row.get("type_key")),
                    address=_optional_str(row.get("address")),
                    map_url=_optional_str(row.get("map_url")),
                )
            )

    def list_profiles(self) -> Sequence[RestaurantProfile]:
        return self._profiles


_default_repository: Optional[ProfileRepository] = None


def get_profile_repository() -> ProfileRepository:
    global _default_repository
    if _default_repository is None:
        from services.profile_repository import PostgresProfileRepository

        _default_repository = PostgresProfileRepository(os.getenv("DATABASE_URL", ""))
    return _default_repository


def get_questions(experience_level: str):
    return QUESTIONS[experience_level]


def calculate_taste_vector(request: RecommendationSubmitRequest) -> Dict[str, float]:
    """6개 답변의 선택지 벡터를 축별로 평균해 1~5 범위의 취향 점수를 만든다."""
    if len(request.answers) != 6 or {answer.question_id for answer in request.answers} != set(range(1, 7)):
        raise HTTPException(status_code=400, detail="6개의 질문에 중복 없이 답변해야 합니다.")

    totals = [0.0] * len(TRAITS)
    for answer in request.answers:
        try:
            vector = CHOICE_VECTORS[request.experience_level][answer.question_id][answer.selected_choice_id - 1]
        except (KeyError, IndexError):
            raise HTTPException(status_code=400, detail="질문과 선택지 조합이 올바르지 않습니다.")
        for index, value in enumerate(vector):
            totals[index] += value
    return {trait: round(totals[index] / 6, 2) for index, trait in enumerate(TRAITS)}


def recommend(request: RecommendationSubmitRequest, repository: ProfileRepository) -> RecommendationResult:
    """취향 벡터, 유형 순위, 추천 가게를 한 번에 계산한다.

    추천할 가게가 없어도 유형과 취향 그래프는 반환해야 하므로 None을 돌려주지 않는다.
    호출부는 restaurants가 비었는지로 no_recommendation 여부를 판단한다.
    """
    preferred = calculate_taste_vector(request)
    type_ranking = rank_types(
        preferred,
        [(answer.question_id, answer.selected_choice_id) for answer in request.answers],
        request.experience_level,
    )

    candidates = []
    for profile in repository.list_profiles():
        # operating_status가 unknown인 가게는 폐업 근거가 없을 뿐이므로 후보에 남긴다.
        # 확인된 폐업(closed)과 근거가 부족한 프로필(low)만 제외한다.
        if profile.operating_status == "closed" or profile.profile_confidence == "low":
            continue
        distance = sum(abs(profile.scores[trait] - preferred[trait]) / 4 for trait in TRAITS)
        candidates.append((round(1 - distance / len(TRAITS), 4), profile))

    # 동점은 가게명 오름차순으로 확정한다. 결과 화면은 항상 채워져야 하므로
    # 동점이라는 이유로 추천을 포기하지 않는다.
    candidates.sort(key=lambda item: (-item[0], item[1].restaurant_name))

    return RecommendationResult(
        preferred=preferred,
        type_ranking=type_ranking,
        restaurants=candidates[:RECOMMENDATION_COUNT],
    )
