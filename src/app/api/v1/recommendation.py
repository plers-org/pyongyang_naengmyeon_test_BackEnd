from datetime import datetime, timezone
from typing import List, Mapping, Optional, Sequence, Tuple
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Path, Response
from pydantic import ValidationError

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

# 결과는 한 번 만들어지면 바뀌지 않으므로 조회 응답을 캐싱해도 된다.
# 유형 카피는 조회 시점에 조립되므로 카피 수정 반영이 이 시간만큼 늦어진다.
RESULT_CACHE_CONTROL = "public, max-age=3600"


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
        "- `result_id` — 이 결과의 영구 주소입니다. 결과 페이지 URL에 넣어두면 새로고침해도, 남에게 링크를 보내도 "
        "`GET /api/recommendation/results/{result_id}` 로 같은 결과를 다시 그릴 수 있습니다. "
        "**저장에 실패하면 `null` 이 옵니다.** 이때도 아래 결과는 정상이므로, 이 응답 본문으로 화면을 그리고 "
        "공유 버튼만 숨기면 됩니다.\n"
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
        "유형 분포를 집계할 수 있습니다. 로그인과 무관하며 개인정보를 넣어서는 안 됩니다. 생략해도 결과는 같습니다. "
        "`result_id` 와는 다른 값이며, `session_id` 로 결과를 조회할 수는 없습니다."
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
    status = "recommended" if restaurants else "no_recommendation"
    message = None if restaurants else "추천 가능한 식당이 없습니다."

    # created_at은 DB 기본값에 맡기지 않고 여기서 만든다. 제출 응답과 조회 응답의
    # 값이 어긋나면 같은 결과가 다르게 보이기 때문이다.
    result_id = str(uuid4())
    created_at = datetime.now(timezone.utc)

    stored = response_repository.record_safely(
        response_repository.get_response_repository(),
        result_id=result_id,
        session_id=request.session_id,
        experience_level=request.experience_level,
        answers=[answer.model_dump() for answer in request.answers],
        taste_vector=dict(result.preferred),
        primary_type=result.type_ranking[0][0],
        secondary_type=result.type_ranking[1][0],
        type_ranking=[{"key": key, "match_score": score} for key, score in result.type_ranking],
        recommended=[restaurant.model_dump() for restaurant in restaurants],
        status=status,
        message=message,
        created_at=created_at,
    )

    return _build_response(
        # 저장에 실패했다면 조회되지 않을 주소이므로 내려보내지 않는다.
        result_id=result_id if stored else None,
        created_at=created_at,
        status=status,
        message=message,
        experience_level=request.experience_level,
        type_ranking=result.type_ranking,
        taste_vector=result.preferred,
        restaurants=restaurants,
    )


@router.get(
    "/recommendation/results/{result_id}",
    response_model=RecommendationResultResponse,
    summary="발급받은 결과 ID로 결과 화면 데이터 다시 받기",
    description=(
        "**언제 호출하나** — 결과 페이지가 열릴 때마다 호출합니다. 본인이 방금 제출한 경우든, "
        "공유 링크를 받고 들어온 다른 사람이든 동일합니다.\n\n"
        "**무엇을 보내나** — `POST /api/recommendation/submit` 응답의 `result_id` 를 경로에 그대로 넣습니다. "
        "답변을 다시 보낼 필요가 없어 **서버 컴포넌트에서 그대로 호출**할 수 있습니다.\n\n"
        "**무엇이 오나** — `submit` 과 **완전히 같은 형태**의 응답입니다. 결과 화면 컴포넌트를 하나만 두고 "
        "두 API의 응답을 같은 타입으로 다루면 됩니다.\n\n"
        "**같은 ID는 항상 같은 결과** — 유형 판정·취향 점수·추천 가게는 제출 시점에 저장된 값을 그대로 돌려줍니다. "
        "그 뒤 추천 로직이나 가게 데이터가 바뀌어도 이미 공유된 결과는 달라지지 않습니다. "
        "다만 유형 카피(`title`·`reason` 등)와 축 이름은 조회 시점의 최신 문구로 조립되므로, "
        "문구 오타를 고치면 기존 링크에도 반영됩니다.\n\n"
        "**응답은 캐시해도 됩니다** — 결과가 불변이라 `Cache-Control: public, max-age=3600` 이 함께 옵니다."
    ),
    responses={
        404: {
            "description": "존재하지 않거나 더 이상 표시할 수 없는 결과",
            "content": {"application/json": {"example": {"detail": "결과를 찾을 수 없습니다."}}},
        },
        503: {
            "description": "결과 저장소를 쓸 수 없는 상태",
            "content": {"application/json": {"example": {"detail": "결과 조회를 사용할 수 없습니다."}}},
        },
    },
)
def get_recommendation_result(
    response: Response,
    result_id: UUID = Path(
        description="`submit` 응답으로 받은 결과 ID(UUID). 이 값이 곧 공유 가능한 결과의 주소다.",
        examples=["9f1c4b2e-3a5d-4e77-8b21-6c0d5f8a1234"],
    ),
) -> RecommendationResultResponse:
    repository = response_repository.get_response_repository()
    try:
        snapshot = repository.find_by_result_id(str(result_id))
    except Exception as exc:  # noqa: BLE001 - 저장소 장애를 503으로 바꿔 전달한다
        raise HTTPException(status_code=503, detail="결과 조회를 사용할 수 없습니다.") from exc

    if snapshot is None:
        raise HTTPException(status_code=404, detail="결과를 찾을 수 없습니다.")

    restored = _restore_result(snapshot)
    response.headers["Cache-Control"] = RESULT_CACHE_CONTROL
    return restored


def _restore_result(snapshot: Mapping[str, object]) -> RecommendationResultResponse:
    """저장된 스냅샷을 조회 응답으로 되돌린다.

    판정 결과는 스냅샷 값을 그대로 쓰고, 유형 카피와 축 라벨만 지금 시점의
    코드 상수에서 읽는다. 경계와 근거는 PRD §5.2에 있다.
    """
    ranking = [
        (str(entry["key"]), float(entry["match_score"]))
        for entry in (snapshot.get("type_ranking") or [])
        if isinstance(entry, Mapping) and "key" in entry and "match_score" in entry
    ]
    taste_vector = snapshot.get("taste_vector") or {}

    # 유형 체계가 개편되어 저장된 키를 더 이상 해석할 수 없는 결과는 500이 아니라
    # "표시할 수 없는 결과"로 다룬다.
    if len(ranking) < 2 or any(key not in TASTE_TYPES for key, _ in ranking):
        raise HTTPException(status_code=404, detail="이 결과는 더 이상 표시할 수 없습니다.")
    if any(trait not in taste_vector for trait in TRAITS):
        raise HTTPException(status_code=404, detail="이 결과는 더 이상 표시할 수 없습니다.")

    return _build_response(
        result_id=str(snapshot["result_id"]),
        created_at=snapshot["created_at"],
        status=snapshot.get("status") or "no_recommendation",
        message=snapshot.get("message"),
        experience_level=str(snapshot["experience_level"]),
        type_ranking=ranking,
        taste_vector={trait: float(taste_vector[trait]) for trait in TRAITS},
        restaurants=_restore_restaurants(snapshot.get("recommended") or []),
    )


def _restore_restaurants(rows: Sequence[Mapping[str, object]]) -> List[RecommendedRestaurant]:
    """저장된 가게 카드를 되살린다.

    가게 정보는 조회 시점에 다시 읽지 않고 스냅샷을 그대로 쓴다. 폐업·재적재로
    가게가 사라져도 이미 공유된 결과 화면이 비지 않게 하기 위함이다.
    """
    restaurants = []
    for row in rows:
        try:
            restaurants.append(RecommendedRestaurant(**row))
        except (ValidationError, TypeError):
            # 결과 조회 도입 이전 형식으로 저장된 행은 카드를 그릴 수 없으므로 건너뛴다.
            continue
    return restaurants


def _build_response(
    *,
    result_id: Optional[str],
    created_at: datetime,
    status: str,
    message: Optional[str],
    experience_level: str,
    type_ranking: Sequence[Tuple[str, float]],
    taste_vector: Mapping[str, float],
    restaurants: Sequence[RecommendedRestaurant],
) -> RecommendationResultResponse:
    """제출 경로와 조회 경로가 공유하는 응답 조립부.

    두 경로가 같은 함수를 쓰므로 응답 형태가 갈라질 수 없다.
    """
    return RecommendationResultResponse(
        result_id=result_id,
        created_at=created_at,
        status=status,
        message=message,
        experience_level=experience_level,
        primary_type=_primary_type(*type_ranking[0]),
        secondary_type=_type_summary(*type_ranking[1]),
        farthest_type=_type_summary(*type_ranking[-1]),
        type_scores=[
            TypeScore(key=key, name=TASTE_TYPES[key]["name"], match_score=score)
            for key, score in type_ranking
        ],
        taste_profile=TasteProfile(
            traits=[
                TraitScore(key=trait, label=TRAIT_LABELS[trait], score=taste_vector[trait])
                for trait in TRAITS
            ]
        ),
        recommended_restaurants=list(restaurants),
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
