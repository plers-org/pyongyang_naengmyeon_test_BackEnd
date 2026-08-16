# app

평양냉면 취향 추천 서비스 백엔드 (FastAPI).

경험 수준(입문자/경험자)에 맞는 6문항에 답하면, 답변을 **4축 취향 벡터**(육향·감칠맛·메밀향·산미)로 변환해 가게 프로필과의 거리를 계산하고 가장 잘 맞는 가게를 추천합니다.

## 구조

```
api/v1/recommendation.py    라우터
schemas/recommendation.py   Pydantic 요청/응답 모델
services/
  recommendation_data.py    문항 데이터 + 선택지별 취향 벡터(CHOICE_VECTORS)
  recommendation_service.py 취향 벡터 산출 및 가게 매칭 로직
  profile_repository.py     PostgreSQL 가게 프로필 조회/적재
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
| POST | `/api/recommendation/submit` | 6개 답변 제출 → 취향 점수 + 가게 추천 |

문항은 시작 시 한 번에 받고, 답변은 마지막에 한 번에 제출합니다.

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
