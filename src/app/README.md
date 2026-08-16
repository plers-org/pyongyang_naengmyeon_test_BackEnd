# app

평양냉면 취향 추천 서비스 백엔드 (FastAPI).

경험 수준(입문자/경험자)에 맞는 6문항에 답하면, 답변을 **4축 취향 벡터**(육향·감칠맛·메밀향·산미)로 변환해 가게 프로필과의 거리를 계산하고 가장 잘 맞는 가게를 추천합니다.

## 구조

```
api/v1/recommendation.py    라우터
schemas/recommendation.py   Pydantic 요청/응답 모델
services/
  recommendation_data.py    문항 데이터 + 선택지별 취향 벡터(CHOICE_VECTORS)
  taste_type_data.py        취향 유형 4종의 카피·기준 벡터·선택지 매핑
  recommendation_service.py 취향 벡터 산출, 유형 판정, 가게 매칭
  profile_repository.py     PostgreSQL 가게 프로필 조회/적재
  response_repository.py    취향 테스트 응답 기록 (best-effort)
scripts/
  init_db.py                RDS 테이블 생성 (배포 후 1회)
  migrate_search_profiles.py search 리포트 → DB 적재
  export_api_docs.py        OpenAPI → docs/api-reference.html
```

## 실행

```bash
cd src/app
pip install -r requirements.txt
uvicorn main:app --reload
```

## API

| Method | Endpoint | 설명 |
| --- | --- | --- |
| GET | `/api/recommendation/questions/{experience_level}` | 경험 수준(`beginner`/`expert`)별 6문항 일괄 조회 |
| POST | `/api/recommendation/submit` | 6개 답변 제출 → 결과 화면 전체 데이터 |

문항은 시작 시 한 번에 받고, 답변은 마지막에 한 번에 제출합니다.

`submit` 응답 하나로 결과 화면을 모두 그릴 수 있습니다.

| 필드 | 내용 |
| --- | --- |
| `primary_type` | 대표 유형 + 제목·부제·배지·도출 이유·배색 |
| `secondary_type` | 두 번째로 잘 맞는 유형 |
| `farthest_type` | 가장 거리가 먼 유형 |
| `type_scores` | 4개 유형 전체 일치도 |
| `taste_profile` | 4축 취향 점수(1~5)와 스케일 |
| `recommended_restaurants` | 추천 가게 상위 2곳 |

유형 판정과 취향 그래프는 답변만으로 계산되므로 가게 데이터가 없어도 항상 채워집니다.
추천할 가게가 없으면 `status`가 `no_recommendation`이 되고 `recommended_restaurants`만 빕니다.

> `map_url`은 아직 수집 전이라 임시로 `TEMP_ADDRESS_URL`이 내려갑니다.
> `restaurant_availability.csv`에 `map_url` 컬럼을 채우면 해당 가게부터 실제 링크로 바뀝니다.

요청에 `session_id`(프론트 생성 익명 UUID)를 넣으면 응답 로그가 함께 기록됩니다. 선택 항목입니다.

## 취향 유형

| key | 유형 |
| --- | --- |
| `uraeok` | 우래옥형 — 진한 육향, 깊은 감칠맛 |
| `dongchimi` | 동치미형 — 동치미 산미, 청량감 |
| `uijeongbu` | 의정부형 — 맑은 육수, 은은한 여운 |
| `jangchungdong` | 장충동형 — 강한 메밀 향, 거친 면 |

유형은 각 선택지가 대표하는 유형을 6문항에서 카운팅해 정합니다. 4축 벡터 거리를
쓰지 않는 이유는 `services/taste_type_data.py` 상단 주석과 PRD §9.1에 있습니다.

## 취향 4축

| key | 표시명 |
| --- | --- |
| `meat_aroma` | 육향 |
| `umami` | 감칠맛 |
| `buckwheat_aroma` | 메밀향 |
| `acidity` | 산미 |

각 선택지는 4축 벡터(1~5)를 가지며, 6문항 평균이 사용자의 취향 점수가 됩니다.

## 환경변수

| 변수 | 용도 |
| --- | --- |
| `DATABASE_URL` | PostgreSQL 접속 문자열. 미설정 시 가게 프로필이 비어 추천 불가 |

## 테스트

```bash
PYTHONPATH=src/app pytest test/
```

## 문서

- [PRD: 취향테스트 결과 응답 확장](../../docs/prd-recommendation-result.md)
- `docs/api-reference.html` — `python scripts/export_api_docs.py`로 갱신
