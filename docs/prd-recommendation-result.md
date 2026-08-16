# [PRD] 평냉 취향 유형 판정 및 결과 화면 API

- 문서 버전: **v2.0** (v1.0 전면 개정)
- 작성일: 2026-08-16
- 대상 서비스: `services/src/app` (FastAPI 백엔드)
- 근거 자료: Figma `평양냉면 지도` 와이어프레임 / 결과 화면 시안 4종, `search/docs/questions.md`(기획 원안), 프론트엔드 요청(2026-08-08, 08-13)

> **v1.0 대비 변경점**: v1.0은 "가장 안 맞는 **가게**"를 반환하는 설계였다. 결과 화면 시안 확인 결과 실제 요구는 "가장 거리가 먼 **유형**"이며, 서비스의 중심은 **4가지 취향 유형 체계**(우래옥형·동치미형·의정부형·장충동형)임이 확인되어 설계를 전면 교체한다.

---

## 1. 현황 점검 — "질문 데이터를 저장했다가 추천식당을 전달하는가?"

### 1.1 결론

**절반만 구현되어 있다.** 문항·선택지 데이터와 취향 벡터 계산은 있으나, **결과 화면을 그릴 수 있는 데이터가 하나도 응답에 나오지 않는다.** 또한 현재 데이터 상태로는 **추천이 100% 실패**한다(§1.4).

### 1.2 항목별 점검

| # | 요구 사항 | 상태 | 근거 |
| --- | --- | --- | --- |
| 1 | 평냉 경험 여부로 2분기 (Q0) | ✅ | `experience_level` ∈ `beginner`/`expert` |
| 2 | 분기별 6문항 보유 | ✅ | `recommendation_data.py:20-37`, Figma 문항과 일치 |
| 3 | 문항별 4선택지 보유 | ✅ | 동일 |
| 4 | 선택지 → 취향 벡터 매핑 | ✅ | `recommendation_data.py:40-57` `CHOICE_VECTORS` |
| 5 | 문항 조회 API | ✅ | `GET /api/recommendation/questions/{experience_level}` |
| 6 | 답변 일괄 제출 API | ✅ | `POST /api/recommendation/submit` |
| 7 | 4축 취향 점수 산출 | ⚠️ | `recommendation_service.py:71`에서 계산 후 **폐기** |
| 8 | 취향 그래프 응답 노출 | ❌ | 응답 필드 없음 |
| 9 | **4가지 취향 유형 판정** | ❌ | **유형 개념 자체가 앱에 없음** |
| 10 | 유형별 카피(제목·설명·도출 이유) | ❌ | 없음 |
| 11 | 두 번째로 잘 맞는 유형 | ❌ | 없음 |
| 12 | 가장 거리가 먼 유형 | ❌ | 없음 |
| 13 | 추천 가게 전달 | ⚠️ | **1곳**만 반환. 시안은 **2곳** |
| 14 | 사용자 답변 영구 저장 | ❌ | stateless. 계산 후 폐기 |
| 15 | 가게 위치·지도 링크 | ❌ | DB 컬럼 없음. "평냉 지도 보기" 불가 |
| 16 | 유형별 캐릭터 이미지 | ❌ | 없음 |

### 1.3 문항 데이터의 저장 위치

문항·선택지는 **DB가 아니라 Python 코드에 하드코딩**되어 있다(`recommendation_data.py`).

- 선택지는 각각 4축 벡터(`CHOICE_VECTORS`)와 1:1로 묶여 있고, 이 벡터가 곧 추천 계산의 입력이다.
- 즉 문항 데이터는 "콘텐츠"가 아니라 **계산 로직의 일부**다.

→ 이번 범위에서는 **코드 유지**를 권장한다(§9 결정 사항). 문구만 바뀌는 수정에도 배포가 필요하다는 단점은 있으나, 문항 6개 × 2분기로 규모가 작고 벡터와 분리 저장 시 정합성이 깨질 위험이 더 크다.

### 1.4 🚨 배포 블로커 — 현재 추천 결과가 항상 비어 있음

`search`의 실제 데이터를 현행 변환·필터 로직에 넣어 시뮬레이션한 결과:

```
전체 가게              : 32곳
operating_status=open : 0곳     ← restaurant_availability.csv 전부 "unknown"
profile_confidence≠low: 17곳
────────────────────────────────
필터 통과 (추천 후보)  : 0곳
```

`recommendation_service.py:75`의 필터는 다음과 같다.

```python
if profile.operating_status != "open" or profile.profile_confidence == "low":
    continue
```

- `restaurant_availability.csv`의 `operating_status`가 **32곳 전부 `unknown`** → 첫 조건에서 전부 탈락
- `review_status`가 `pending`(17) / `needs_more_evidence`(15)뿐이라 `profile_confidence`는 `medium`/`low`만 존재

**결과: 어떤 답변을 제출해도 `no_recommendation`이 반환된다.** 기능 개발과 별개로 데이터를 채우지 않으면 서비스가 성립하지 않는다. §10 Phase 0에서 최우선 처리한다.

#### 추가 발견 — 4축 점수 결측으로 적재 자체가 실패

Phase 0 착수 중 확인된 두 번째 문제다. 32곳 중 **15곳은 4축 점수가 비어 있다**(결측 15곳 = `review_status=needs_more_evidence` 15곳과 정확히 일치).

```
능라도(강남점)  {meat_aroma: 5, umami: 2, buckwheat_aroma: 4, acidity: -}
양각도          {meat_aroma: 5, umami: -, buckwheat_aroma: 5, acidity: -}
...
```

`InMemoryProfileRepository`와 `import_profiles`는 **필터링 이전 파싱 단계**에서 모든 행을 `float()` 변환하므로, 빈 문자열을 만나면 `ValueError`로 죽는다. 즉 필터를 완화해도 **마이그레이션 자체가 실패**한다.

→ 4축이 완비된 행만 적재하고, 스킵된 가게명을 출력하도록 처리한다(§10 Phase 0-4). 결측 15곳은 어차피 `profile_confidence=low`로 추천 후보에서 제외되므로 실질 손실은 없다.

---

## 2. 목표 / 비목표

### 2.1 목표

1. 사용자의 6문항 답변으로 **4가지 취향 유형 중 하나를 판정**하고, 2순위·최원거리 유형을 함께 산출한다.
2. 결과 화면(시안)에 필요한 **모든 데이터를 단일 응답**으로 제공한다 — 유형 카피, 취향 그래프, 추천 가게 2곳, 보조 유형.
3. 추천 후보가 0곳이 되는 **데이터 문제를 해소**한다.
4. `search`에 이미 존재하는 유형 데이터(`legacy_category`)를 앱 DB로 **연결**한다.

### 2.2 비목표

- 추천 알고리즘의 근본 개편(협업 필터링, 사용자 로그 기반 추천).
- 문항 내용·개수 변경.
- 지도 화면 자체의 구현(백엔드는 좌표·링크만 제공).
- 결과 공유 이미지(OG) 생성.
- 로그인·사용자 계정.

---

## 3. 유형 체계 정의

`search/docs/questions.md`에 정의된 체계를 그대로 사용한다. 시안의 표기(`○○형`)를 사용자 노출명으로 삼는다.

| key | 유형명 | 시안 타이틀 | 성격 |
| --- | --- | --- | --- |
| `uraeok` | 우래옥형 | 진하고 든든한 우래옥형 | 진한 육향, 깊은 감칠맛 |
| `dongchimi` | 동치미형 | 산뜻하고 개운한 동치미형 | 동치미 산미, 청량감 |
| `uijeongbu` | 의정부형 | 맑고 담백한 의정부형 | 깔끔한 육수, 은은한 여운 |
| `jangchungdong` | 장충동형 | 구수하고 풍성한 장충동형 | 강한 메밀 향, 거친 면 |

> ⚠️ 시안의 부제와 `questions.md`의 유형 특징 간에 불일치가 있다(§12 열린 질문 1).

### 3.1 유형 기준 벡터 (archetype)

`questions.md` §5-1의 가게 특성 예시표에서 4축을 추출해 각 유형의 기준 벡터로 삼는다.

| 유형 | 육향 | 감칠맛 | 메밀향 | 산미 | 출처 |
| --- | --- | --- | --- | --- | --- |
| 우래옥형 | 5 | 4 | 2 | 1 | 우래옥 |
| 의정부형 | 2 | 3 | 3 | 1 | 평양면옥 |
| 장충동형 | 1 | 1 | 5 | 1 | 장충동평양면옥 |
| 동치미형 | 2 | 4 | 2 | 5 | 남포면옥 |

이 값은 확정이 아니며 실사용 데이터로 조정한다(`questions.md`도 동일하게 명시).

---

## 4. 사용자 플로우

```
[인트로] "나는 어떤 평양냉면 타입?"
   ↓
[Q0] 평양냉면을 먹어본 적 있으신가요?   ← 프론트 상태로만 관리, API 호출 없음
   │  네, 먹어봤어요 → expert
   └  아니요, 처음이에요 → beginner
   ↓
GET /api/recommendation/questions/{experience_level}
   → 해당 분기의 6문항 전체 수신
   ↓
[문항 1~6] 진행률 n/6 표시. 서버 왕복 없음
   ↓
POST /api/recommendation/submit   (experience_level + 6개 답변)
   ↓
[결과] 유형 카드 · 취향 그래프 · 도출 이유 · 추천 평냉집 2곳 · 보조 유형 2종
```

---

## 5. API 명세

### 5.1 `GET /api/recommendation/questions/{experience_level}` — 변경 없음

### 5.2 `POST /api/recommendation/submit` — 응답 전면 확장

#### 요청 (변경 없음)

```json
{
  "experience_level": "expert",
  "answers": [
    { "question_id": 1, "selected_choice_id": 1 },
    { "question_id": 2, "selected_choice_id": 3 },
    { "question_id": 3, "selected_choice_id": 1 },
    { "question_id": 4, "selected_choice_id": 2 },
    { "question_id": 5, "selected_choice_id": 4 },
    { "question_id": 6, "selected_choice_id": 2 }
  ]
}
```

#### 응답

```json
{
  "status": "recommended",
  "experience_level": "expert",

  "primary_type": {
    "key": "uraeok",
    "name": "우래옥형",
    "title": "진하고 든든한 우래옥형",
    "subtitle": "가장 진한 고기 향과 깊은 감칠맛을 좋아하는 본질파 타입이에요",
    "badge": "맑고 순수한 맛에서 진짜 깊이를 찾아요",
    "reason": "고기 향이 뚜렷한 육수의 묵직함과 메밀 면발이 진짜 평양냉면이라고 느끼는 타입이에요. 다른 계열보다 진한 육향과 감칠맛에서 깊이를 찾아요. 평양냉면의 슴슴함이 아직 낯선 사람도 맛있게 즐기기 좋은 스타일이에요.",
    "character_key": "uraeok",
    "theme_color": "#C98A3C",
    "match_score": 0.87
  },

  "secondary_type": {
    "key": "uijeongbu", "name": "의정부형",
    "character_key": "uijeongbu", "match_score": 0.71
  },

  "farthest_type": {
    "key": "dongchimi", "name": "동치미형",
    "character_key": "dongchimi", "match_score": 0.34
  },

  "type_scores": [
    { "key": "uraeok",        "name": "우래옥형",   "match_score": 0.87 },
    { "key": "uijeongbu",     "name": "의정부형",   "match_score": 0.71 },
    { "key": "jangchungdong", "name": "장충동형",   "match_score": 0.52 },
    { "key": "dongchimi",     "name": "동치미형",   "match_score": 0.34 }
  ],

  "taste_profile": {
    "scale": { "min": 1.0, "max": 5.0 },
    "traits": [
      { "key": "meat_aroma",      "label": "육향",   "score": 4.17 },
      { "key": "umami",           "label": "감칠맛", "score": 3.83 },
      { "key": "buckwheat_aroma", "label": "메밀향", "score": 2.00 },
      { "key": "acidity",         "label": "산미",   "score": 1.50 }
    ]
  },

  "recommended_restaurants": [
    {
      "rank": 1,
      "restaurant_name": "우래옥",
      "fit_score": 0.91,
      "type_key": "uraeok",
      "fit_sentence": "육향과 감칠맛을 선호하는 사람에게 잘 맞을 수 있어요.",
      "evidence_summary": "육향과 깊은 맛에 대한 근거가 충분합니다.",
      "scores": { "meat_aroma": 5.0, "umami": 4.0, "buckwheat_aroma": 2.0, "acidity": 1.0 },
      "address": "서울 중구 창경궁로 62-29",
      "map_url": "https://map.naver.com/p/entry/place/11665adf"
    },
    { "rank": 2, "restaurant_name": "…" }
  ]
}
```

#### 추천 가게가 없을 때

```json
{
  "status": "no_recommendation",
  "message": "추천 가능한 식당이 없습니다.",
  "experience_level": "expert",
  "primary_type":   { "…": "동일" },
  "secondary_type": { "…": "동일" },
  "farthest_type":  { "…": "동일" },
  "type_scores":    [ "…" ],
  "taste_profile":  { "…": "동일" },
  "recommended_restaurants": []
}
```

> **핵심 원칙**: 유형 판정과 취향 그래프는 **사용자 답변만으로 계산**되므로 가게 데이터와 무관하게 **항상 반환한다**. 가게 추천만 실패할 수 있다. 프론트는 유형 카드·그래프·도출 이유를 정상 렌더링하고, "잘 맞는 평냉집 추천" 영역만 안내 문구로 대체한다.

#### 오류 (변경 없음)

| 코드 | 조건 |
| --- | --- |
| 400 | 답변 6개 아님 / `question_id` 중복·누락 / 잘못된 선택지 조합 |
| 404 | 지원하지 않는 `experience_level` |
| 422 | Pydantic 범위 검증 실패 |

---

## 6. 데이터 모델

### 6.1 신규 Pydantic 스키마 (`schemas/recommendation.py`)

```python
TypeKey = Literal["uraeok", "uijeongbu", "jangchungdong", "dongchimi"]
TraitKey = Literal["meat_aroma", "umami", "buckwheat_aroma", "acidity"]


class TypeSummary(BaseModel):          # 보조 유형용 축약형
    key: TypeKey
    name: str                          # "우래옥형"
    character_key: str                 # 프론트 이미지 매핑 키
    match_score: float                 # 0.0~1.0


class PrimaryType(TypeSummary):        # 대표 유형용 전체형
    title: str                         # "진하고 든든한 우래옥형"
    subtitle: str                      # 캐릭터 아래 한 줄
    badge: str                         # 강조 배지 문구
    reason: str                        # "유형 도출 이유" 본문
    theme_color: str                   # 화면 배색 (#RRGGBB)


class TypeScore(BaseModel):
    key: TypeKey
    name: str
    match_score: float


class TraitScore(BaseModel):
    key: TraitKey
    label: str                         # "육향"
    score: float                       # 1.0~5.0


class TasteProfile(BaseModel):
    scale: TraitScale = TraitScale()   # min=1.0, max=5.0
    traits: List[TraitScore]           # 항상 4개, 고정 순서


class RecommendedRestaurant(BaseModel):
    rank: int
    restaurant_name: str
    fit_score: float                   # 0.0~1.0
    type_key: Optional[TypeKey]        # 가게의 계열
    fit_sentence: str
    evidence_summary: str
    scores: Dict[str, float]           # 가게 4축 원점수
    address: Optional[str] = None
    map_url: Optional[str] = None


class RecommendationResultResponse(BaseModel):
    status: Literal["recommended", "no_recommendation"]
    message: Optional[str] = None
    experience_level: ExperienceLevel
    primary_type: PrimaryType
    secondary_type: TypeSummary
    farthest_type: TypeSummary
    type_scores: List[TypeScore]       # 항상 4개, match_score 내림차순
    taste_profile: TasteProfile
    recommended_restaurants: List[RecommendedRestaurant]  # 0~2개
```

> `status`를 Union 분기가 아닌 단일 모델의 필드로 둔다. 두 경우의 필드 구성이 `recommended_restaurants`의 길이 외에 동일하므로, 프론트가 분기 없이 하나의 파서를 쓸 수 있다.

### 6.2 유형 카피 상수 (`services/taste_type_data.py` — 신규)

```python
TASTE_TYPES = {
    "uraeok": {
        "name": "우래옥형",
        "title": "진하고 든든한 우래옥형",
        "subtitle": "가장 진한 고기 향과 깊은 감칠맛을 좋아하는 본질파 타입이에요",
        "badge": "맑고 순수한 맛에서 진짜 깊이를 찾아요",
        "reason": "…",                          # 시안 "유형 도출 이유" 본문
        "theme_color": "#C98A3C",
        "vector": {"meat_aroma": 5, "umami": 4, "buckwheat_aroma": 2, "acidity": 1},
    },
    # dongchimi / uijeongbu / jangchungdong 동일 구조
}
```

카피 4벌은 변경 빈도가 낮고 이미지·배색과 한 세트로 움직이므로 코드 상수로 둔다.

### 6.3 DB 스키마 확장

`restaurant_recommendation_profiles`에 컬럼을 추가한다.

```sql
ALTER TABLE restaurant_recommendation_profiles
  ADD COLUMN IF NOT EXISTS type_key TEXT
    CHECK (type_key IN ('uraeok','uijeongbu','jangchungdong','dongchimi')),
  ADD COLUMN IF NOT EXISTS address TEXT,
  ADD COLUMN IF NOT EXISTS map_url TEXT,
  ADD COLUMN IF NOT EXISTS latitude  NUMERIC(9, 6),
  ADD COLUMN IF NOT EXISTS longitude NUMERIC(9, 6);
```

`type_key`는 `search`의 `restaurant_taste_profiles.csv` → `legacy_category`(우래옥/의정부/장충동/동치미)를 매핑해 채운다. **해당 데이터는 이미 32곳 전부 존재하나, 현재 마이그레이션 스크립트가 가져오지 않고 있다**(`profile_repository.py:121-139`).

| legacy_category | type_key |
| --- | --- |
| 우래옥 | `uraeok` |
| 의정부 | `uijeongbu` |
| 장충동 | `jangchungdong` |
| 동치미 | `dongchimi` |

---

## 7. 비즈니스 로직

### 7.1 처리 순서

```
1. 답변 검증                     (기존과 동일)
2. 4축 취향 벡터 산출            (기존과 동일, 이제 응답에 노출)
3. 유형별 일치도 계산 ★신규
4. 유형 순위 결정   ★신규        primary / secondary / farthest
5. 가게 후보 필터링              (기존, 조건 완화 §7.4)
6. 가게 적합도 계산·정렬         (기존)
7. 상위 2곳 선정   ★변경         (기존 1곳)
```

### 7.2 유형 판정 (신규) — 선택지 카운팅

> **v2.1 변경**: 당초 4축 벡터 거리로 판정하려 했으나 구현 중 실측에서 심각한 편향이 확인되어 방식을 교체했다. 근거는 §9.1.

각 선택지가 대표하는 유형을 선언해 두고(`CHOICE_TYPES`), 6문항에서 **가장 많이 선택된 유형**을 대표로 삼는다.

```python
counts = Counter(CHOICE_TYPES[level][question_id][choice_id - 1] for ... )

ranked = sorted(TASTE_TYPES, key=lambda key: (
    -counts.get(key, 0),                                   # 1차: 선택 횟수
    -type_match_score(preferred, TASTE_TYPES[key]["vector"]),  # 2차: 취향 벡터 거리
    declaration_order[key],                                # 3차: 선언 순서
))
match_score = counts.get(key, 0) / 6                       # 0.0 ~ 1.0
```

`match_score`는 **6문항 중 해당 유형을 고른 비율**이다. 벡터 거리는 동점을 가르는 보조 지표로만 쓴다.

선택지 → 유형 매핑은 대부분 `(우래옥, 의정부, 장충동, 동치미)` 순이나 Q2·Q3은 문구 의미에 맞춰 순서가 다르다.

| 문항 | 1번 | 2번 | 3번 | 4번 |
| --- | --- | --- | --- | --- |
| Q1 육수 첫 느낌 | 우래옥 | 의정부 | 장충동 | 동치미 |
| Q2 "싱겁다"는 말에 | 장충동 | 우래옥 | 동치미 | 의정부 |
| Q3 면발 | 장충동 | 의정부 | 우래옥 | 장충동 |
| Q4 고명 | 우래옥 | 의정부 | 장충동 | 동치미 |
| Q5 끌리는 평냉 | 우래옥 | 의정부 | 장충동 | 동치미 |
| Q6 평소 좋아하는 맛 | 우래옥 | 의정부 | 장충동 | 동치미 |

> Q3은 면 식감 축이라 4개 유형을 온전히 커버하지 못한다(1·4번 모두 메밀향 계열). 완전 균등 분포가 불가능한 구조적 한계다.

정렬 결과에서:

| 항목 | 선정 |
| --- | --- |
| `primary_type` | 1위 |
| `secondary_type` | 2위 |
| `farthest_type` | **4위(최하위)** |
| `type_scores` | 4개 전부 |

### 7.3 가게 추천 (변경)

- 정렬 기준은 기존과 동일(`fit_score` 내림차순, 동점 시 가게명 오름차순).
- **상위 2곳**을 `rank` 1, 2로 반환한다(`RECOMMENDATION_COUNT = 2` 상수).
- 후보가 1곳이면 1개만, 0곳이면 빈 배열.
- **동점 1위 시 `None` 반환 로직을 제거한다.** 현재 `recommendation_service.py:82-83`은 1·2위가 동점이면 추천을 포기하는데, 정렬 키에 이미 가게명 tie-break가 있어 모순이며 결과 화면이 비는 원인이 된다.

> `questions.md` §4는 추천 3곳(1위 최적합 / 2위 유사하나 일부 상이 / 3위 취향 확장)을 제안하나, 결과 화면 시안은 카드 2개다. 시안을 따르되 상수로 분리해 조정 가능하게 한다(§12 열린 질문 3).

### 7.4 후보 필터 완화 (§1.4 해소)

```python
# 현재 — 데이터 미비 시 전멸
if profile.operating_status != "open" or profile.profile_confidence == "low":
    continue

# 변경 — 미확인(unknown)은 배제하지 않음
if profile.operating_status == "closed":
    continue
if profile.profile_confidence == "low":
    continue
```

`unknown`은 "닫혔다는 근거가 없는 상태"이므로 배제 대상이 아니다. 폐업 확인(`closed`)만 제외한다. 이것만으로 후보가 0곳 → 17곳이 된다.

### 7.5 엣지 케이스

| 상황 | 동작 |
| --- | --- |
| 후보 0곳 | `no_recommendation` + 유형·그래프는 정상 반환 |
| 후보 1곳 | `recommended`, 배열 길이 1 |
| 유형 1·2위 동점 | 선언 순서로 tie-break. 결과는 항상 반환 |
| 4개 유형 전부 동점 | 이론상 가능(모든 축 중앙값). 선언 순서로 결정되며 화면은 정상 동작 |
| `map_url` 미등록 | `null`. 프론트는 "평냉 지도 보기" 버튼을 비활성 처리 |

---

## 8. 사용자 답변 저장 (Phase 3)

현재는 답변을 저장하지 않는다. `questions.md` §7의 퍼널 측정(`taste_result_view`, `recommendation_view` 등)과 유형 분포 분석을 위해 저장이 필요하다.

```sql
CREATE TABLE IF NOT EXISTS survey_responses (
  id                BIGSERIAL PRIMARY KEY,
  session_id        TEXT NOT NULL,          -- 프론트 생성 UUID (비로그인 식별)
  experience_level  TEXT NOT NULL,
  answers           JSONB NOT NULL,         -- [{question_id, selected_choice_id}]
  taste_vector      JSONB NOT NULL,         -- 산출된 4축 점수
  primary_type      TEXT NOT NULL,
  secondary_type    TEXT NOT NULL,
  recommended       JSONB NOT NULL,         -- [{restaurant_name, fit_score}]
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

- 개인정보를 수집하지 않으므로 `session_id`는 프론트가 생성한 익명 UUID로 충분하다.
- 저장 실패가 추천 응답을 막아서는 안 된다 — **쓰기는 best-effort**로 처리하고 예외는 로깅만 한다.

---

## 9. 결정 사항

| 항목 | 결정 | 근거 |
| --- | --- | --- |
| "가장 안 맞는 유형"의 정의 | **유형** (v1.0의 "가게"에서 변경) | 결과 화면 시안이 캐릭터 이미지 + 유형명으로 표시. "두 번째로 잘 맞는 유형"과 한 쌍으로 배치되어 대상이 유형임이 명확 |
| 유형 판정 방식 | **선택지 카운팅** (`questions.md` §5-3 방식) | 벡터 거리 방식은 실측에서 88% 편향. §9.1 참조 |
| 유형 일치도 표현 | 6문항 중 선택 비율 | "6문항 중 4개가 우래옥형"처럼 사용자에게 설명 가능. 벡터 거리는 동점 tie-break로만 사용 |
| 가게 추천 방식 | 4축 벡터 거리 **유지** | 후보 간 상대 비교라 점수의 절대 편중이 상쇄됨 |
| 유형 카피 저장 위치 | 코드 상수 | 4벌 고정, 이미지·배색과 한 세트. DB 분리 시 정합성 관리 비용만 증가 |
| 문항 데이터 저장 위치 | 코드 유지 | 선택지가 취향 벡터와 1:1 결합된 계산 로직의 일부(§1.3) |
| 캐릭터 이미지 | 서버는 `character_key`만 반환 | 이미지는 프론트 정적 자산. 서버가 CDN·해상도를 알 필요 없음 |
| 추천 가게 수 | 2곳 | 결과 화면 시안 기준 |
| `status` 표현 | Union이 아닌 단일 모델의 필드 | 두 응답의 필드 구성이 사실상 동일. 프론트 파서 단순화 |
| `operating_status=unknown` | 추천 후보에 **포함** | 폐업 근거가 없는 상태를 배제하면 전 가게가 탈락(§1.4) |

### 9.1 유형 판정 방식 변경 근거 (실측)

4096개 답변 조합(4선택지 × 6문항)을 전수 계산한 결과다.

| 방식 | 유형 분포 |
| --- | --- |
| 4축 벡터 거리 (당초 설계) | 의정부형 **88.1%** / 동치미 8.5 / 장충동 1.8 / 우래옥 1.5 |
| 벡터 거리 + min-max 정규화 | 의정부형 76.5% (개선 미미) |
| 벡터 거리 + 중심화 | 의정부형 79.6% (개선 미미) |
| **선택지 카운팅 (채택)** | 의정부 **36.4** / 장충동 24.2 / 우래옥 20.5 / 동치미 18.9 |

**원인 1 — 평균의 중앙 수렴.** 6문항 벡터를 평균하면 극단값이 상쇄되어 결과가 중앙에 몰린다. 4개 유형 기준 벡터 중 의정부형 `(2,3,3,1)`만 중앙에 있어 대부분을 흡수한다. 축별 실제 도달 범위도 육향 1.00~3.83, 메밀향 1.00~3.67로 좁아, 우래옥형(육향 5)이나 장충동형(메밀향 5)에는 **어떤 답변으로도 도달할 수 없다**.

**원인 2 — 가게 데이터가 유형을 변별하지 못함.** 기준 벡터를 실제 가게 데이터의 유형별 중심(centroid)으로 대체해도 해결되지 않는다.

| 유형 | 육향 | 감칠맛 | 메밀향 | 산미 | n |
| --- | --- | --- | --- | --- | --- |
| 우래옥형 | 4.60 | 2.60 | 5.00 | 1.80 | 5 |
| 의정부형 | 4.75 | 3.00 | 5.00 | 1.50 | 4 |
| 장충동형 | 5.00 | 2.00 | 5.00 | 2.50 | 2 |
| 동치미형 | 4.67 | 3.00 | 4.33 | 3.67 | 6 |

육향이 전 유형 4.60~5.00, 메밀향이 4.33~5.00으로 **사실상 동일**하다. 유형을 가르는 축이 산미 하나뿐이며, 그마저 범위가 좁다. 특히 장충동형은 "맑은 육수"가 정체성인데 육향이 5.00으로 가장 높아 **라벨과 점수가 모순**이다.

이는 점수가 리뷰 텍스트 기반 자동 산출(`score_type=auto`)이라 *언급되면 높은 점수*가 되는 구조 탓으로 보인다. 표본도 유형당 2~6곳으로 적다. 이 centroid로 판정하면 우래옥형 49.0%로 편향이 남는다.

→ 현재 데이터로는 유형 변별이 불가능하므로, **설문 설계 자체에 인코딩된 의도**(선택지-유형 대응)를 신호로 쓴다. 가게 데이터가 개선되면 재검토한다(§12).

---

## 10. 작업 항목

### Phase 0 — 데이터 블로커 (최우선, §1.4)

| # | 대상 | 작업 |
| --- | --- | --- |
| 0-1 | `recommendation_service.py` | 후보 필터를 `closed`만 제외하도록 완화 ✅ |
| 0-2 | `search/data/.../restaurant_availability.csv` | 실제 영업 상태 조사·입력 — **외부 조사 필요, 미착수** |
| 0-3 | — | 마이그레이션 후 추천 후보 수 > 0 확인 ✅ (0곳 → 17곳) |
| 0-4 | `profile_repository.py`, `migrate_search_profiles.py`, `recommendation_service.py` | 4축 점수 결측 행을 적재에서 제외하고 스킵 내역 출력 ✅ |

### Phase 1 — 유형 판정 및 결과 응답 (핵심)

| # | 대상 | 작업 |
| --- | --- | --- |
| 1-1 | `services/taste_type_data.py` 🆕 | `TASTE_TYPES` 4벌 (카피·배색·기준 벡터) |
| 1-2 | `services/recommendation_data.py` | `TRAIT_LABELS` 추가 |
| 1-3 | `services/recommendation_service.py` | `type_match_score()`, 유형 순위 산출, 상위 2곳 반환, 동점 시 `None` 반환 제거, `RecommendationResult` dataclass |
| 1-4 | `schemas/recommendation.py` | §6.1 스키마 전체 |
| 1-5 | `api/v1/recommendation.py` | 결과 → 응답 매핑. 지역 `HTTPException` import 상단 이동 |
| 1-6 | `test/test_recommendation.py` | §11 테스트 |

### Phase 2 — 가게 유형·위치 연결

| # | 대상 | 작업 |
| --- | --- | --- |
| 2-1 | `services/profile_repository.py` | `PROFILE_TABLE_SQL`에 `type_key`/`address`/`map_url`/좌표 추가, `SELECT`·`INSERT` 확장 ✅ |
| 2-2 | `services/profile_repository.py` | `legacy_category` → `type_key` 매핑 ✅ (32곳 전부 매핑, 미매핑 0곳) |
| 2-3 | 데이터 | 가게 주소·지도 링크 수집 — **외부 조사 필요, 미착수** |
| 2-4 | `scripts/migrate_search_profiles.py` | 확장 필드 반영 확인 ✅ |

**주소·지도 링크 수집 방법**: `restaurant_availability.csv`에 `address`, `map_url` 컬럼을 추가하기만 하면 된다. 변환 함수가 이미 해당 키를 읽으므로 코드 수정 없이 반영된다. 기존 테이블에는 `PROFILE_MIGRATION_SQL`이 컬럼을 추가하고, 재적재 시 `COALESCE`로 기존 주소·링크를 덮어쓰지 않는다.

### Phase 3 — 답변 로그

| # | 대상 | 작업 |
| --- | --- | --- |
| 3-1 | `services/response_repository.py` 🆕 | `survey_responses` 테이블 및 best-effort 기록 |
| 3-2 | `schemas/recommendation.py` | 요청에 `session_id` 옵션 필드 추가 |

### 공통 마무리

- `scripts/export_api_docs.py` 실행 → `docs/api-reference.html` 갱신
- `src/app/README.md` API 표 갱신

---

## 11. 테스트 케이스 (수용 기준)

### 유형 판정

| # | 시나리오 | 기대 |
| --- | --- | --- |
| T1 | 전 문항 1번 선택(육향 최대) | `primary_type.key == "uraeok"` |
| T2 | 전 문항 4번 선택(산미 최대) | `primary_type.key == "dongchimi"` |
| T3 | 임의 답변 | `type_scores` 길이 4, `match_score` 내림차순 |
| T4 | 임의 답변 | `primary` = `type_scores[0]`, `secondary` = `[1]`, `farthest` = `[3]` |
| T5 | 임의 답변 | `primary ≠ secondary ≠ farthest` (키 중복 없음) |
| T6 | `match_score` 범위 | 모든 유형 `0.0 ≤ s ≤ 1.0` |
| T7 | 대표 유형 카피 | `title`/`subtitle`/`badge`/`reason`/`theme_color` 전부 비어있지 않음 |

### 취향 그래프

| # | 시나리오 | 기대 |
| --- | --- | --- |
| T8 | 임의 답변 | `traits` 길이 4, 순서 `meat_aroma→umami→buckwheat_aroma→acidity` |
| T9 | 라벨 | `육향`/`감칠맛`/`메밀향`/`산미` |
| T10 | 범위 | 모든 축 `1.0 ≤ score ≤ 5.0` |

### 가게 추천

| # | 시나리오 | 기대 |
| --- | --- | --- |
| T11 | 후보 3곳 이상 | `recommended_restaurants` 길이 2, `rank` 1·2 |
| T12 | 정렬 | `[0].fit_score ≥ [1].fit_score` |
| T13 | 후보 1곳 | 길이 1 |
| T14 | 후보 0곳 | `status="no_recommendation"`, 배열 `[]`, **유형·그래프는 정상** |
| T15 | `operating_status="unknown"` | **후보에 포함**(회귀 방지, §1.4) |
| T16 | `operating_status="closed"` | 후보에서 제외 |
| T17 | `profile_confidence="low"` | 후보에서 제외 |
| T18 | 전 후보 동점 | 200 + 2곳 반환 (기존 `no_recommendation` 아님) |

### 기존 동작

| # | 시나리오 | 기대 |
| --- | --- | --- |
| T19 | 답변 5개 | 400 |
| T20 | `question_id` 중복 | 400 |
| T21 | `selected_choice_id=5` | 422 |
| T22 | 문항 조회 | 기존과 동일 (회귀) |

---

## 12. 열린 질문

1. **유형 부제 불일치** — 시안의 `동치미형` 부제는 "시원한 동치미 향과 깔끔한 끝맛이 매력적인 청량파", `questions.md`는 "새콤 청량 동치미파"다. 또한 시안의 `우래옥형` 배지 문구("맑고 순수한 맛에서 진짜 깊이를 찾아요")는 우래옥형의 성격(진한 육향)과 어긋나 보인다. **최종 카피 확정본이 필요하다.** 확정 전까지는 시안 문구를 그대로 넣는다.
2. ~~**유형 기준 벡터 검증**~~ — ✅ **해소**. 전수 실측 결과 심각한 편향이 확인되어 판정 방식을 선택지 카운팅으로 교체했다(§9.1). §3.1의 기준 벡터는 이제 **동점 tie-break 보조 지표**로만 쓰인다.
2-1. **가게 데이터 점수 품질** (신규) — 4축 자동 점수가 상향 편중되어 유형 간 변별력이 없다(§9.1 원인 2). `search` 쪽에서 점수 산출 방식(언급 빈도 → 강도 추정)을 재검토하거나 수동 검수가 필요하다. 개선되면 유형 판정에 가게 데이터를 다시 활용할 수 있다.
3. **추천 가게 수** — 시안 2곳 vs `questions.md` 3곳. 시안 기준 2곳으로 구현하되 상수로 분리.
4. **"평냉 지도 보기" 목적지** — 외부 지도 앱(네이버/카카오) 링크인지, 자체 지도 화면인지에 따라 필요한 필드가 달라진다(`map_url` vs 좌표).
5. **경험자/입문자 결과 차별화** — 현재 두 분기의 `CHOICE_VECTORS`는 3개 값만 다르다. 입문자에게 "입문 난이도"를 반영한 별도 추천 순서가 필요한지(`questions.md` §4는 언급) 확인 필요.

---

## 13. 리스크

| 항목 | 내용 | 대응 |
| --- | --- | --- |
| 데이터 | 32곳 전부 `operating_status=unknown`, 15곳 `confidence=low` | Phase 0. 필터 완화 + 영업 상태 조사 |
| 데이터 | 주소·지도 링크 미보유 | Phase 2에서 수집. 미보유 시 버튼 비활성 |
| 카피 | 유형별 "도출 이유" 본문 4벌 미확정 | 시안 문구로 선반영 후 교체 |
| 에셋 | 캐릭터 이미지 4종 전달 필요 | 프론트 정적 자산으로 관리, 서버는 `character_key`만 |
| 로직 | 유형 기준 벡터가 미검증값이라 분포 편향 가능 | 답변 로그(Phase 3) 확보 후 조정 |
