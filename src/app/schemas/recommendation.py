from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


ExperienceLevel = Literal["beginner", "expert"]
TypeKey = Literal["uraeok", "uijeongbu", "jangchungdong", "dongchimi"]
TraitKey = Literal["meat_aroma", "umami", "buckwheat_aroma", "acidity"]


class RecommendationChoice(BaseModel):
    """문항 하나에 딸린 선택지."""

    choice_id: int = Field(
        description="선택지 번호(1~4). 사용자가 이 선택지를 고르면 답변 제출 시 `selected_choice_id` 로 그대로 보낸다.",
    )
    choice_text: str = Field(description="화면에 그대로 노출할 선택지 문구.")


class RecommendationQuestion(BaseModel):
    """취향 테스트 문항 하나."""

    question_id: int = Field(description="문항 번호(1~6). 답변 제출 시 그대로 다시 보낸다.")
    question_text: str = Field(description="화면에 그대로 노출할 질문 문구.")
    choices: List[RecommendationChoice] = Field(description="선택지 4개. 배열 순서대로 보여주면 된다.")
    progress: float = Field(
        description="이 문항까지 왔을 때의 진행률(%). 진행 바에 그대로 쓴다. 1번 16.7 ~ 6번 100.0.",
    )


class RecommendationQuestionsResponse(BaseModel):
    """문항 조회 응답. 6문항이 한 번에 온다."""

    experience_level: ExperienceLevel = Field(description="요청한 문항 세트 종류를 그대로 돌려준다.")
    questions: List[RecommendationQuestion] = Field(description="문항 6개. 배열 순서가 곧 출제 순서다.")


class RecommendationAnswer(BaseModel):
    """사용자가 문항 하나에 답한 결과."""

    question_id: int = Field(ge=1, le=6, description="답한 문항 번호. 문항 조회 응답의 `question_id` 를 그대로 쓴다.")
    selected_choice_id: int = Field(
        ge=1,
        le=4,
        description="사용자가 고른 선택지 번호. 문항 조회 응답의 `choice_id` 를 그대로 쓴다.",
    )


class RecommendationSubmitRequest(BaseModel):
    """답변 제출 요청. 6문항을 모두 답한 뒤 한 번에 보낸다."""

    experience_level: ExperienceLevel = Field(description="문항을 받아올 때 쓴 값과 같아야 한다.")
    answers: List[RecommendationAnswer] = Field(description="6문항의 답변. 순서는 상관없다.")
    # 프론트가 생성한 익명 UUID. 유형 분포·퍼널 분석용이며 개인정보는 담지 않는다.
    session_id: Optional[str] = Field(
        default=None,
        max_length=64,
        description=(
            "프론트가 만든 익명 식별자(UUID 등). 통계 집계용이며 생략해도 결과는 같다. "
            "로그인과 무관하고 개인정보를 담아서는 안 된다."
        ),
    )


class TypeSummary(BaseModel):
    """보조 유형(2순위·최원거리)에 쓰는 축약형. 화면에는 캐릭터와 이름만 노출된다."""

    key: TypeKey = Field(description="유형 키. 캐릭터 이미지 등 프론트 리소스를 고르는 기준으로 쓴다.")
    name: str = Field(description="화면에 노출할 유형 이름. 예: `우래옥형`.")
    character_key: str = Field(description="캐릭터 이미지 키. 현재는 `key` 와 같은 값이 온다.")
    match_score: float = Field(ge=0.0, le=1.0, description="이 유형과의 일치도(0.0~1.0). 백분율로 바꿔 표시한다.")


class PrimaryType(TypeSummary):
    """대표 유형. 결과 화면 상단 카드에 필요한 카피를 모두 포함한다.

    문구가 모두 서버에서 오므로 프론트에 유형별 텍스트를 하드코딩하지 않는다.
    카피를 고칠 때 서버만 배포하면 되도록 한 구조다.
    """

    title: str = Field(description="결과 카드 제목. 예: `진하고 든든한 우래옥형`.")
    subtitle: str = Field(description="제목 아래 한 줄 설명.")
    badge: str = Field(description="카드에 붙는 짧은 배지 문구.")
    reason: str = Field(description="이 유형으로 판정된 이유를 설명하는 본문(2~3문장).")
    theme_color: str = Field(description="결과 카드에 쓸 테마 색상 HEX 코드. 예: `#C98A3C`.")


class TypeScore(BaseModel):
    """유형 하나의 일치도. 4개 유형 전체를 그래프로 보여줄 때 쓴다."""

    key: TypeKey = Field(description="유형 키.")
    name: str = Field(description="화면에 노출할 유형 이름.")
    match_score: float = Field(ge=0.0, le=1.0, description="일치도(0.0~1.0). 내림차순으로 정렬되어 온다.")


class TraitScale(BaseModel):
    """취향 그래프 축의 눈금 범위. 그래프 최소·최대값을 이 값으로 잡는다."""

    min: float = Field(default=1.0, description="축 최소값. 항상 1.0이다.")
    max: float = Field(default=5.0, description="축 최대값. 항상 5.0이다.")


class TraitScore(BaseModel):
    """맛 축 하나의 점수."""

    key: TraitKey = Field(description="축 키. `meat_aroma`(육향) / `umami`(감칠맛) / `buckwheat_aroma`(메밀향) / `acidity`(산미).")
    label: str = Field(description="화면에 노출할 축 이름. 예: `육향`. 프론트에 축 이름을 적어둘 필요가 없다.")
    score: float = Field(ge=1.0, le=5.0, description="해당 축의 취향 점수(1.0~5.0). 높을수록 그 맛을 선호한다.")


class TasteProfile(BaseModel):
    """사용자의 취향을 4개 축으로 나타낸 그래프 데이터."""

    scale: TraitScale = Field(default=TraitScale(), description="그래프 눈금 범위(1~5).")
    traits: List[TraitScore] = Field(description="4개 축의 점수. 육향·감칠맛·메밀향·산미 순으로 온다.")


class RecommendedRestaurant(BaseModel):
    """추천 가게 한 곳."""

    rank: int = Field(description="추천 순위. 1부터 시작한다.")
    restaurant_name: str = Field(description="가게 이름.")
    fit_score: float = Field(ge=0.0, le=1.0, description="사용자 취향과의 적합도(0.0~1.0).")
    type_key: Optional[TypeKey] = Field(default=None, description="이 가게가 속한 취향 유형. 분류되지 않은 가게는 null.")
    fit_sentence: str = Field(description="이 가게를 추천하는 이유 한 문장. 카드에 그대로 노출한다.")
    evidence_summary: str = Field(description="추천 근거 요약. 리뷰에서 추출한 맛 특징 설명이다.")
    scores: Dict[str, float] = Field(
        description="가게의 4축 점수. 키는 `taste_profile` 의 축 키와 같아서 사용자 취향과 겹쳐 그릴 수 있다.",
    )
    address: Optional[str] = Field(default=None, description="가게 주소. 수집 전인 가게는 null.")
    map_url: Optional[str] = Field(
        default=None,
        description="지도 링크. 아직 수집되지 않은 가게는 임시 링크가 내려오므로, 버튼 노출 여부는 이 값으로 판단하지 않는다.",
    )


class RecommendationResultResponse(BaseModel):
    """결과 화면 전체를 한 번에 그릴 수 있는 응답.

    유형 판정과 취향 그래프는 사용자 답변만으로 계산되므로 가게 데이터와
    무관하게 항상 채워진다. 가게 추천만 비어 있을 수 있다.
    """

    result_id: Optional[str] = Field(
        default=None,
        description=(
            "이 결과의 영구 주소(UUID). `GET /api/recommendation/results/{result_id}` 의 경로에 그대로 넣으면 "
            "같은 결과를 다시 조회할 수 있고, 그 주소를 그대로 공유하면 된다.\n\n"
            "**null 일 수 있다.** 결과 저장에 실패한 경우이며, 이때도 아래 결과 필드는 모두 정상이다. "
            "프론트는 값이 있으면 결과 페이지로 이동하고, null이면 이 응답 본문으로 결과를 그린 뒤 공유 버튼만 숨기면 된다."
        ),
    )
    created_at: datetime = Field(
        description="결과가 만들어진 시각(UTC, ISO 8601). 조회 시에도 제출 당시의 값이 그대로 온다.",
    )
    status: Literal["recommended", "no_recommendation"] = Field(
        description=(
            "`recommended` 면 추천 가게가 담겨 있고, `no_recommendation` 이면 "
            "`recommended_restaurants` 가 빈 배열이다. 후자여도 유형과 그래프는 정상이므로 "
            "가게 목록 영역만 비우고 나머지는 그대로 보여주면 된다."
        ),
    )
    message: Optional[str] = Field(
        default=None,
        description="추천할 가게가 없을 때의 안내 문구. 추천이 있으면 null이다.",
    )
    experience_level: ExperienceLevel = Field(description="요청에 담겨 온 값을 그대로 돌려준다.")
    primary_type: PrimaryType = Field(description="대표 유형. 결과 화면 상단 카드에 필요한 문구가 모두 들어 있다.")
    secondary_type: TypeSummary = Field(description="2순위 유형. 이름과 캐릭터만 노출한다.")
    farthest_type: TypeSummary = Field(description="가장 거리가 먼 유형. `이런 맛은 덜 맞아요` 식의 대비 노출에 쓴다.")
    type_scores: List[TypeScore] = Field(description="4개 유형 전체의 일치도. 일치도 내림차순으로 온다.")
    taste_profile: TasteProfile = Field(description="사용자 취향의 4축 점수. 취향 그래프에 쓴다.")
    recommended_restaurants: List[RecommendedRestaurant] = Field(
        description="적합도 순으로 정렬된 추천 가게 목록. 기본 2곳이며 비어 있을 수 있다.",
    )
