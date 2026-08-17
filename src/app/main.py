from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.router import router

DESCRIPTION = """
6문항짜리 취향 테스트로 사용자의 평양냉면 취향을 판정하고, 그 취향에 맞는 가게를 추천하는 API입니다.

## 어떤 화면에서 쓰나

취향 테스트 페이지 하나를 그리는 데 필요한 전부입니다. 화면 흐름은 세 단계입니다.

1. **시작 화면** — 사용자가 "입문자 / 경험자" 중 하나를 고릅니다.
2. **문항 화면** — `GET /api/recommendation/questions/{experience_level}` 로 6문항을 받아 한 문항씩 보여주고, 선택한 답을 프론트가 모아둡니다.
3. **결과 화면** — 6문항을 모두 답하면 `POST /api/recommendation/submit` 으로 한 번에 제출합니다. 응답 하나에 결과 화면을 그릴 재료가 전부 들어 있습니다.

문항을 하나씩 서버에 보낼 필요는 없습니다. 프론트가 답을 모았다가 마지막에 한 번만 제출하는 구조입니다.

## 무엇을 판정하나

답변을 4개의 맛 축으로 환산해 취향 유형을 정합니다.

| 축 | 뜻 |
| --- | --- |
| `meat_aroma` | 육향 — 고기 향이 얼마나 진한가 |
| `umami` | 감칠맛 |
| `buckwheat_aroma` | 메밀향 |
| `acidity` | 산미 — 새콤하고 개운한 정도 |

각 축은 1~5점이며, 이 점수로 아래 4가지 유형 중 가장 가까운 하나를 대표 유형으로 정합니다.

| 유형 키 | 이름 | 성격 |
| --- | --- | --- |
| `uraeok` | 우래옥형 | 진한 고기 향과 깊은 감칠맛 |
| `uijeongbu` | 의정부형 | 맑고 담백한 육수 |
| `jangchungdong` | 장충동형 | 메밀 향이 도드라지는 면 중심 |
| `dongchimi` | 동치미형 | 새콤하고 개운한 끝맛 |

## 알아둘 점

- **인증이 없습니다.** API 키나 토큰 없이 바로 호출하면 됩니다.
- **CORS가 모든 출처에 열려 있습니다.** 로컬 개발 서버에서 바로 붙일 수 있습니다.
- **로그인이 없습니다.** 제출 시 넣는 `session_id` 는 프론트가 만든 익명 식별자이며, 유형 분포 통계에만 쓰입니다. 개인정보를 담아서는 안 됩니다.
- **현재 서버는 `http` 입니다.** https 페이지에서 호출하면 브라우저가 차단하므로, 로컬 개발은 `http://localhost` 에서 진행하세요.
"""

TAGS_METADATA = [
    {
        "name": "recommendation",
        "description": "취향 테스트 문항 제공과 결과 판정. 이 두 개가 서비스의 전부입니다.",
    },
]

app = FastAPI(
    title="평양냉면 취향 추천 서비스",
    version="1.0.0",
    description=DESCRIPTION,
    openapi_tags=TAGS_METADATA,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
