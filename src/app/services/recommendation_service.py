import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Protocol, Sequence, Tuple

from fastapi import HTTPException

from schemas.recommendation import RecommendationSubmitRequest
from services.recommendation_data import CHOICE_VECTORS, QUESTIONS, TRAITS


@dataclass(frozen=True)
class RestaurantProfile:
    restaurant_name: str
    scores: Mapping[str, float]
    profile_confidence: str
    operating_status: str
    fit_sentence: str
    evidence_summary: str


class ProfileRepository(Protocol):
    def list_profiles(self) -> Sequence[RestaurantProfile]: ...


class InMemoryProfileRepository:
    def __init__(self, rows: Iterable[Mapping[str, object]] = ()) -> None:
        self._profiles = [
            RestaurantProfile(
                restaurant_name=str(row["restaurant_name"]),
                scores={trait: float(row[f"{trait}_score"]) for trait in TRAITS},
                profile_confidence=str(row.get("profile_confidence", "low")),
                operating_status=str(row.get("operating_status", "unknown")),
                fit_sentence=str(row.get("fit_sentence", "")),
                evidence_summary=str(row.get("evidence_summary", "")),
            )
            for row in rows
        ]

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


def recommend(request: RecommendationSubmitRequest, repository: ProfileRepository):
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
    preferred = [value / 6 for value in totals]

    candidates = []
    for profile in repository.list_profiles():
        if profile.operating_status != "open" or profile.profile_confidence == "low":
            continue
        score = 1 - sum(abs(profile.scores[trait] - preferred[index]) / 4 for index, trait in enumerate(TRAITS)) / len(TRAITS)
        candidates.append((round(score, 4), profile))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1].restaurant_name))
    if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
        return None
    return candidates[0]
