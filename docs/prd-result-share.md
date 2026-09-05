# [PRD] 결과 ID 발급 및 결과 조회 API

- 문서 버전: **v1.0**
- 작성일: 2026-08-23
- 대상 서비스: `services/src/app` (FastAPI 백엔드)
- 선행 문서: [PRD: 평냉 취향 유형 판정 및 결과 화면 API](prd-recommendation-result.md) (이하 **결과 PRD**)
- 근거: 프론트엔드 요청(2026-08-23) — ① Next.js 서버 컴포넌트에서 결과 화면을 그리려면 `GET`이 필요하다 ② 결과 페이지를 타인에게 공유하려면 결과를 가리키는 식별자가 있어야 한다

---

## 1. 배경 — 왜 지금 구조로는 안 되는가

### 1.1 현재 구조

결과 화면 데이터는 `POST /api/recommendation/submit` **응답으로만** 존재한다. 응답을 받은 뒤 어디에도 다시 꺼낼 수 있는 주소가 없다.

응답 로그는 이미 `survey_responses` 테이블에 기록되고 있으나(`response_repository.py`), 다음 세 가지 이유로 조회에 쓸 수 없다.

| 항목 | 현재 | 조회에 쓸 수 없는 이유 |
| --- | --- | --- |
| 기본키 | `BIGSERIAL id` | 순차 정수라 **남의 결과를 URL로 훑을 수 있다**. 공유 링크의 식별자로 부적격 |
| 저장 범위 | `primary_type`, `secondary_type`, `taste_vector`, `recommended`(가게명·점수만) | `farthest_type`, 4개 유형 전체 점수, 가게 상세가 없어 **결과 화면을 복원할 수 없다** |
| 쓰기 보장 | best-effort (`record_safely`가 예외를 삼킴) | 저장 실패해도 응답이 성공하므로 **ID를 준 뒤 조회가 404**가 될 수 있다 |

즉 "로그로서의 저장"은 있으나 "조회 대상으로서의 저장"은 없다.

### 1.2 프론트엔드가 막히는 지점

Next.js App Router의 서버 컴포넌트는 **렌더링 시점에 데이터를 가져와야** 한다. 그런데 결과 데이터를 얻는 유일한 경로가 `POST`라서 다음 문제가 생긴다.

- 서버 컴포넌트는 사용자 입력(6개 답변)을 갖고 있지 않다. 답변은 클라이언트 상태에 있다.
- 답변을 URL 쿼리로 넘겨 서버 컴포넌트가 `POST`를 대신 호출하는 우회는 가능하지만, URL이 길어지고 새로고침마다 재계산되며 공유도 되지 않는다.
- 결국 결과 화면 전체가 클라이언트 컴포넌트가 되어, SSR·메타데이터·캐싱을 모두 포기하게 된다.

### 1.3 공유 요구

결과 페이지를 타인에게 보내는 것은 이 서비스의 주요 확산 경로다. 공유가 성립하려면 **받는 사람이 답변 없이도 같은 결과를 볼 수 있어야** 한다. 답변을 URL에 담는 방식은 링크를 뜯어보면 남의 답변이 노출되고, 문항이 바뀌면 링크가 깨진다.

→ 결과에 **주소를 부여**하는 것이 두 요구를 동시에 푸는 해법이다.

---

## 2. 목표 / 비목표

### 2.1 목표

1. 답변 제출 시 서버가 **추측 불가능한 `result_id`를 발급**하고 결과를 영속화한다.
2. `GET /api/recommendation/results/{result_id}` 로 **제출 없이 결과 화면 전체를 조회**할 수 있다.
3. 조회 응답은 `submit` 응답과 **같은 스키마**여서 프론트가 결과 화면 컴포넌트를 하나만 유지하면 된다.
4. 같은 `result_id`는 **몇 번을 조회해도 같은 판정 결과**를 돌려준다.
5. 기존 `POST /api/recommendation/submit` 사용처가 깨지지 않는다(하위 호환).

### 2.2 비목표

| 항목 | 이유 |
| --- | --- |
| 로그인 / 소유자 인증 | 서비스에 인증이 없다. 결과에 개인정보가 없어 링크를 아는 사람만 보는 수준으로 충분(§7.1) |
| 결과 수정·삭제 API | 결과는 불변이다. 재테스트는 새 `result_id` 발급으로 해결 |
| 내 결과 목록 조회 | 사용자 식별 수단이 없다. `session_id`는 익명 통계용이며 조회 키가 아니다 |
| OG 이미지 / 공유 메타 태그 생성 | 프론트엔드 영역. 서버는 `character_key`·유형명까지만 제공 |
| 짧은 공유 URL(단축 링크) | 별도 요구가 없다. 필요해지면 §9 대안으로 전환 가능 |
| 조회수·공유수 집계 | 이번 범위 밖. 필요 시 후속(§11) |

---

## 3. 사용자 플로우

```
[클라이언트 컴포넌트]                    [서버]                      [DB]
 6문항 답변 완료
        │
        │  POST /api/recommendation/submit
        ├──────────────────────────────────▶ 판정 계산
        │                                    result_id 발급(UUIDv4)
        │                                    결과 스냅샷 저장 ──────▶ survey_responses
        │  ◀───────────────────────────────  200 { result_id, ...결과 전체 }
        │
        │  router.push(`/result/${result_id}`)
        ▼
[서버 컴포넌트 /result/[id]]
        │  GET /api/recommendation/results/{result_id}
        ├──────────────────────────────────▶ 스냅샷 조회 ◀──────────  survey_responses
        │                                    최신 카피와 조립
        │  ◀───────────────────────────────  200 { ...결과 전체 }
        ▼
   결과 화면 SSR
        │
        └─▶ 링크 공유 ─▶ 타인이 같은 URL 진입 ─▶ 위 GET만 수행(제출 불필요)
```

**핵심**: `submit`은 여전히 결과 전체를 돌려준다. 프론트는 `result_id`만 챙겨 이동하면 되고, 즉시 렌더가 필요하면 응답 본문을 그대로 써도 된다. 어느 쪽을 택할지는 프론트 결정 사항이다.

---

## 4. API 명세

### 4.1 `POST /api/recommendation/submit` — 응답에 필드 2개 추가

요청은 **변경 없다.**

응답에 다음 두 필드가 추가된다. 기존 필드는 이름·타입·의미 모두 그대로다.

```jsonc
{
  "result_id": "9f1c4b2e-3a5d-4e77-8b21-6c0d5f8a1234",  // 신규
  "created_at": "2026-08-23T10:12:33.482Z",             // 신규
  "status": "recommended",
  "experience_level": "expert",
  "primary_type": { ... },
  "secondary_type": { ... },
  "farthest_type": { ... },
  "type_scores": [ ... ],
  "taste_profile": { ... },
  "recommended_restaurants": [ ... ]
}
```

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `result_id` | `string \| null` | 이 결과의 영구 주소. 조회 API의 경로 파라미터로 그대로 쓴다. **저장에 실패하면 `null`**이며, 이때 결과 본문은 정상이다(§6.3) |
| `created_at` | `string(ISO 8601, UTC)` | 결과 생성 시각 |

### 4.2 `GET /api/recommendation/results/{result_id}` — 신규

**언제 호출하나** — 결과 페이지가 열릴 때마다. 본인이 방금 제출한 경우든 공유 링크로 들어온 타인이든 동일하다.

**응답** — `submit`과 **완전히 동일한 스키마**(`result_id`·`created_at` 포함). 프론트는 두 API의 응답을 같은 타입으로 다루면 된다.

**오류**

| 코드 | 조건 | 본문 |
| --- | --- | --- |
| 404 | 존재하지 않거나 삭제된 `result_id` | `{"detail": "결과를 찾을 수 없습니다."}` |
| 422 | `result_id`가 UUID 형식이 아님 | FastAPI 기본 검증 응답 |
| 503 | `DATABASE_URL` 미설정 등 저장소 사용 불가 | `{"detail": "결과 조회를 사용할 수 없습니다."}` |

> 404와 422를 나누는 이유: 프론트가 "잘못된 링크"와 "만료·삭제된 결과"를 구분해 다른 안내를 띄울 수 있게 하기 위함이다. 다만 **존재 여부를 알려주는 것 자체가 정보 노출**이 되는 상황은 아니다(결과에 개인정보 없음).

**캐시 헤더** — 결과는 불변이므로 `Cache-Control: public, max-age=3600` 을 내려 Next.js 및 CDN 캐싱을 허용한다. 카피 수정이 반영되는 데 최대 1시간 지연되는 것을 감수한 값이다.

---

## 5. 데이터 모델

### 5.1 `result_id` 형식 — UUIDv4

| 후보 | 판단 |
| --- | --- |
| 순차 정수 | ❌ 남의 결과를 훑을 수 있다 |
| **UUIDv4 (채택)** | ✅ 122비트 난수라 열거 불가. 표준이라 Python·JS 양쪽에서 검증·생성이 공짜 |
| base62 단축 ID(12자 내외) | 링크가 짧지만 충돌 처리·재시도 로직이 필요. 지금 필요한 이점이 없다(§9) |

생성 주체는 **서버**다. 클라이언트가 만든 ID를 받으면 중복 삽입·위조 삽입을 서버가 방어해야 하므로 이득이 없다.

### 5.2 무엇을 저장하고 무엇을 조회 시점에 조립하나

결과를 통째로 스냅샷하면 카피 오타를 고쳐도 공유된 링크에는 영영 반영되지 않는다. 반대로 답변만 저장하고 매번 재계산하면 알고리즘·가게 데이터가 바뀔 때 **공유한 결과와 받는 사람이 보는 결과가 달라진다.**

→ **판정 결과는 고정, 표시 문구는 최신**으로 나눈다.

| 구분 | 항목 | 처리 |
| --- | --- | --- |
| **저장(고정)** | `experience_level`, `answers` | 재현·재계산 검증의 원본 |
| | `taste_vector` (4축 점수) | 그래프가 흔들리면 안 된다 |
| | `type_ranking` (4개 유형 전체 key + score) | `primary`/`secondary`/`farthest`/`type_scores`를 모두 여기서 복원 |
| | `recommended` (가게 카드 전체: `rank`·`restaurant_name`·`fit_score`·`type_key`·`fit_sentence`·`evidence_summary`·`scores`·`address`·`map_url`) | 가게가 DB에서 삭제·수정돼도 공유 링크가 깨지지 않아야 한다 |
| | `status`, `message` | 제출 당시 추천 유무를 그대로 유지 |
| **조립(최신)** | 유형 카피 — `title`·`subtitle`·`badge`·`reason`·`theme_color`·`name` | `services/taste_type_data.py`의 `TASTE_TYPES`에서 조회 시점에 읽는다. **카피 수정이 기존 링크에 반영된다** |
| | 축 라벨 — `TraitScore.label` | `TRAIT_LABELS`에서 읽는다 |
| | `character_key` | 현재는 유형 키와 동일 |

가게 정보를 조립이 아닌 저장으로 둔 이유: 가게는 폐업·재적재로 사라질 수 있고, 사라진 순간 공유된 결과 화면의 카드가 통째로 비게 된다. 문구와 달리 **없어질 수 있는 데이터**라 스냅샷이 맞다.

### 5.3 DB 스키마 — `survey_responses` 확장

신규 테이블을 만들지 않고 기존 로그 테이블을 확장한다. 같은 제출 1건에 대한 데이터를 두 테이블에 이중 저장하지 않기 위함이다.

스키마 적용은 **CREATE → ALTER → CREATE INDEX** 세 단계로 나눈다. 한 덩어리로 두면 기존 테이블에 `result_id` 컬럼이 아직 없는 상태에서 그 컬럼에 인덱스를 만들려다 실패한다. `_ensure_schema()`가 이 순서로 실행한다.

```sql
-- 1. RESPONSE_TABLE_SQL — 신규 환경에서 테이블을 만든다
CREATE TABLE IF NOT EXISTS survey_responses (
  id BIGSERIAL PRIMARY KEY,
  result_id UUID,                        -- 🆕 공개 식별자
  session_id TEXT,
  experience_level TEXT NOT NULL,
  answers JSONB NOT NULL,
  taste_vector JSONB NOT NULL,
  primary_type TEXT NOT NULL,
  secondary_type TEXT NOT NULL,
  type_ranking JSONB,                    -- 🆕 4개 유형 전체 점수
  recommended JSONB NOT NULL,            -- 🔄 가게 카드 전체로 확장
  result_status TEXT,                    -- 🆕 recommended / no_recommendation
  result_message TEXT,                   -- 🆕
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

```sql
-- 2. RESPONSE_MIGRATION_SQL — 기존 테이블에 컬럼을 덧붙인다
ALTER TABLE survey_responses
  ADD COLUMN IF NOT EXISTS result_id UUID,
  ADD COLUMN IF NOT EXISTS type_ranking JSONB,
  ADD COLUMN IF NOT EXISTS result_status TEXT,
  ADD COLUMN IF NOT EXISTS result_message TEXT;
```

```sql
-- 3. RESPONSE_INDEX_SQL — 컬럼이 모두 갖춰진 뒤에 만든다
CREATE INDEX IF NOT EXISTS survey_responses_created_at_idx ON survey_responses (created_at);
CREATE INDEX IF NOT EXISTS survey_responses_primary_type_idx ON survey_responses (primary_type);
CREATE UNIQUE INDEX IF NOT EXISTS survey_responses_result_id_idx ON survey_responses (result_id);
```

- `result_id`를 `NOT NULL`로 두지 않는다. 마이그레이션 이전에 쌓인 기존 로그 행에는 값이 없기 때문이다. 신규 행은 애플리케이션이 항상 채운다. PostgreSQL의 `UNIQUE`는 `NULL` 중복을 허용하므로 기존 행이 여럿이어도 유니크 인덱스 생성이 실패하지 않는다.
- `id BIGSERIAL`은 내부 키로 유지한다. 외부에 노출하지 않는다.
- `recommended`의 구조가 바뀌지만 **읽는 쪽이 지금까지 없었으므로** 기존 행 마이그레이션은 불필요하다. 조회 시 필드가 없으면 해당 카드를 비운다.
- 스키마 보장은 **프로세스당 한 번**만 수행한다. 매 삽입마다 `ALTER TABLE`을 돌리면 컬럼이 이미 있어도 짧은 배타 락을 반복해 잡게 된다.

---

## 6. 비즈니스 로직

### 6.1 제출 경로 (`POST /submit`)

```
1. 기존과 동일하게 recommend() 실행 → 판정·추천 계산
2. 응답 객체(RecommendationResultResponse) 조립          ← 기존 로직 그대로
3. result_id = uuid4() 생성
4. 스냅샷 저장 (§5.2 저장 항목)
   ├ 성공 → result_id, created_at 을 응답에 채움
   └ 실패 → result_id = null, created_at = 현재 시각. 예외는 로깅만    (§6.3)
5. 응답 반환
```

**3번이 2번 뒤인 이유**: 저장할 스냅샷이 응답 객체에서 그대로 나오므로, 응답을 먼저 만들고 그것을 직렬화해 저장하면 두 경로의 데이터가 어긋날 수 없다.

### 6.2 조회 경로 (`GET /results/{result_id}`)

```
1. result_id 로 스냅샷 조회 → 없으면 404
2. 저장된 type_ranking → primary/secondary/farthest/type_scores 복원
   이때 카피는 TASTE_TYPES 에서 읽는다                    (§5.2 조립)
3. 저장된 taste_vector → TRAIT_LABELS 를 붙여 taste_profile 복원
4. 저장된 recommended → RecommendedRestaurant 그대로 복원
5. submit 과 동일한 응답 모델로 반환
```

**유형 키가 코드에서 사라진 경우** — 유형 체계는 4벌 고정이라 현실성이 낮으나, 방어적으로 알 수 없는 키를 만나면 500이 아니라 **404**로 처리하고 "이 결과는 더 이상 표시할 수 없습니다" 문구를 남긴다. 유형 개편이 일어나면 §11에서 재검토한다.

### 6.3 저장 실패 시 동작 — 결과 본문을 우선한다

`record_safely`의 best-effort 원칙을 유지한다. DB가 잠시 죽었다고 해서 **사용자가 방금 푼 테스트 결과를 못 보는 것이 더 나쁘다.**

| 상황 | 응답 | 프론트 처리 |
| --- | --- | --- |
| 저장 성공 | 200, `result_id` 있음 | `/result/{id}` 로 이동 |
| 저장 실패 | 200, `result_id: null` | 이동하지 않고 **응답 본문으로 결과를 그대로 렌더**. 공유 버튼만 숨긴다 |

→ 프론트는 `result_id`가 `null`일 수 있음을 반드시 처리해야 한다. 이것이 이번 변경에서 프론트가 유일하게 새로 감당하는 분기다.

`DATABASE_URL` 미설정 환경(로컬 개발)에서는 `InMemoryResponseRepository`가 동작하므로 프로세스가 살아 있는 동안 조회가 정상 동작한다. 재시작하면 사라진다.

---

## 7. 보안 · 개인정보

### 7.1 접근 통제 — 링크를 아는 사람만

인증이 없으므로 `result_id`를 아는 사람은 누구나 조회할 수 있다. 이는 **의도된 설계**다. 공유가 목적이기 때문이다.

성립 근거:

- 저장 데이터에 **개인 식별 정보가 없다.** 답변 6개, 취향 점수, 유형, 가게 목록이 전부다.
- `session_id`는 프론트 생성 익명 UUID이며 **응답에 내려가지 않는다.** 조회 응답에 절대 포함하지 않는다.
- UUIDv4는 열거 공격으로 유효한 ID를 찾을 수 없다.

### 7.2 지켜야 할 선

| 항목 | 규칙 |
| --- | --- |
| `session_id` | 조회 응답에 **포함 금지**. 같은 사용자의 다른 결과를 엮을 수 있는 단서다 |
| 내부 `id`(BIGSERIAL) | 외부 노출 금지 |
| IP·User-Agent | 수집하지 않는다 |
| 보관 기간 | 무기한. 개인정보가 없고 공유 링크가 살아 있어야 한다. 정리가 필요해지면 별도 배치(§11) |

### 7.3 남용 방지

`POST`가 저장을 동반하므로 무한 호출 시 테이블이 커진다. 다만 현재 트래픽 규모에서 실질 위험이 아니고, 레이트 리밋은 nginx 계층의 관심사다. **이번 범위에서는 다루지 않되**, 배포 후 행 증가 추이를 확인한다(§11).

---

## 8. 프론트엔드 연동 가이드

Next.js App Router 기준 권장 형태다.

```tsx
// app/result/[resultId]/page.tsx  — 서버 컴포넌트
export default async function ResultPage({ params }: { params: { resultId: string } }) {
  const res = await fetch(
    `${API_BASE}/api/recommendation/results/${params.resultId}`,
    { next: { revalidate: 3600 } },   // 결과는 불변이라 캐싱 가능
  );
  if (res.status === 404) notFound();
  const result = await res.json();
  return <ResultView data={result} />;  // submit 응답과 같은 타입
}
```

```tsx
// 제출은 클라이언트 컴포넌트에서
const result = await submitAnswers(answers);
if (result.result_id) {
  router.push(`/result/${result.result_id}`);
} else {
  setInlineResult(result);   // 저장 실패 폴백 — 공유 버튼 숨김
}
```

`generateMetadata`에서 같은 `GET`을 호출하면 유형명 기반 OG 태그를 만들 수 있다. Next.js가 같은 요청을 중복 제거하므로 추가 호출 비용은 없다.

---

## 9. 결정 사항

| 항목 | 결정 | 근거 |
| --- | --- | --- |
| 식별자 형식 | **UUIDv4** | 열거 불가 + 표준. 단축 ID는 충돌 처리 비용만 추가(§5.1) |
| 식별자 생성 주체 | **서버** | 클라이언트 생성 시 중복·위조 방어를 서버가 떠안는다 |
| `submit` 응답 | **필드 추가(하위 호환)**, 202+ID-only 아님 | 기존 사용처가 깨지지 않고, 프론트가 즉시 렌더/이동 중 선택할 수 있다 |
| `GET` 응답 스키마 | **`submit`과 동일** | 결과 화면 컴포넌트를 하나만 유지 |
| 저장 범위 | **판정 결과는 스냅샷, 카피는 조회 시 조립** | 결과 재현성과 카피 수정 반영을 동시에 만족(§5.2) |
| 가게 정보 | **스냅샷 저장** | 폐업·재적재로 사라지면 공유 링크가 깨진다 |
| 테이블 | **`survey_responses` 확장**, 신규 테이블 아님 | 같은 제출 1건을 두 곳에 저장하지 않는다 |
| 저장 실패 시 | **200 + `result_id: null`**, 5xx 아님 | 결과를 못 보는 것이 저장 실패보다 나쁘다(§6.3) |
| 인증 | **없음** | 개인정보 미포함 + 공유가 목적(§7.1) |
| 보관 기간 | **무기한** | 공유 링크가 언제 열릴지 알 수 없다 |
| `GET` 캐시 | `public, max-age=3600` | 불변 데이터. 카피 수정 반영 지연 1시간은 수용 |

---

## 10. 작업 항목

### Phase 1 — 저장소 확장

| # | 대상 | 작업 |
| --- | --- | --- |
| 1-1 | `services/response_repository.py` | `RESPONSE_TABLE_SQL`에 `result_id`·`type_ranking`·`result_status`·`result_message` 추가, `RESPONSE_MIGRATION_SQL`·`RESPONSE_INDEX_SQL` 신규 ✅ |
| 1-2 | `services/response_repository.py` | `record()` 시그니처에 `result_id`·`type_ranking`·`status`·`message`·`created_at` 추가, `recommended`를 가게 카드 전체로 확장 ✅ |
| 1-3 | `services/response_repository.py` | `find_by_result_id(result_id)` 신규 — `Postgres`/`InMemory` 양쪽 구현 ✅ |
| 1-4 | `services/response_repository.py` | `_ensure_schema` 패턴 도입(`profile_repository` 참조), `initialize_response_table`에 마이그레이션 반영 ✅ |
| 1-5 | `scripts/init_db.py` | 변경 없음(기존 호출이 마이그레이션까지 수행하도록 1-4에서 처리) ✅ |
| 1-6 | `services/response_repository.py` | 스키마 보장을 프로세스당 1회로 제한. 매 삽입마다 `ALTER TABLE`이 짧은 배타 락을 반복해 잡는 것을 피한다 ✅ |

### Phase 2 — 응답 스키마 및 라우터

| # | 대상 | 작업 |
| --- | --- | --- |
| 2-1 | `schemas/recommendation.py` | `RecommendationResultResponse`에 `result_id: Optional[str]`, `created_at: datetime` 추가 ✅ |
| 2-2 | `api/v1/recommendation.py` | `submit`에서 `uuid4()` 발급 → 응답 조립 → 스냅샷 저장 순서로 재배치(§6.1) ✅ |
| 2-3 | `api/v1/recommendation.py` | `GET /recommendation/results/{result_id}` 신규 + 404/503 처리 + `Cache-Control` ✅ |
| 2-4 | `api/v1/recommendation.py` | 스냅샷 → 응답 복원 함수 `_restore_result()` 분리, 조립부 `_build_response()`를 두 경로가 공유 ✅ |
| 2-5 | `main.py` | `DESCRIPTION`에 결과 조회·공유 흐름 문단 추가 ✅ |

### Phase 3 — 문서 · 테스트

| # | 대상 | 작업 |
| --- | --- | --- |
| 3-1 | `test/test_result_lookup.py` 🆕 | §11 테스트 + Postgres 어댑터 정합성 테스트 ✅ (22개) |
| 3-2 | `test/test_response_logging.py` | 확장된 `record()` 시그니처 반영 — `record_safely(**payload)` 구조라 수정 없이 통과 ✅ |
| 3-3 | `src/app/README.md` | API 표에 `GET /results/{result_id}` 추가, 저장/조립 경계 설명 ✅ |
| 3-4 | `docs/api-reference.html` | `python scripts/export_api_docs.py` 재생성 ✅ |
| 3-5 | `deploy/migrate_db.sh` 🆕, `deploy/deploy.sh`, `deploy/setup_ec2.sh` | 재배포 시에도 마이그레이션이 자동 적용되도록 분리·연결 ✅ — **미적용 시 결과 저장이 조용히 실패해 `result_id`가 계속 `null`이 된다** |

---

## 11. 테스트 케이스 (수용 기준)

### 결과 발급

| # | 조건 | 기대 |
| --- | --- | --- |
| 1 | 정상 제출 | 200, `result_id`가 유효한 UUIDv4, `created_at` 존재 |
| 2 | 두 번 제출 | 두 `result_id`가 서로 다르다 |
| 3 | 저장소가 예외를 던짐 | 200, `result_id`가 `null`, **결과 본문은 정상**, 예외 로그 기록 |
| 4 | 추천 가게 없음(`no_recommendation`) | `result_id` 정상 발급, 스냅샷에 `status`가 그대로 저장 |

### 결과 조회

| # | 조건 | 기대 |
| --- | --- | --- |
| 5 | 방금 발급한 `result_id` 조회 | 200, **`submit` 응답과 필드·값이 동일**(`created_at` 포함) |
| 6 | 같은 ID를 3회 조회 | 3회 모두 동일한 응답 |
| 7 | 존재하지 않는 UUID | 404, `detail`이 한글 안내 문구 |
| 8 | UUID가 아닌 문자열(`abc`) | 422 |
| 9 | 조회 응답 본문 | `session_id`가 **어떤 필드에도 없다** |
| 10 | `no_recommendation` 결과 조회 | `status`·`message` 보존, `recommended_restaurants`가 빈 배열, 유형·그래프는 채워짐 |

### 저장/조립 경계

| # | 조건 | 기대 |
| --- | --- | --- |
| 11 | 저장 후 `TASTE_TYPES`의 `title`을 변경하고 조회 | **변경된 카피**가 내려온다 |
| 12 | 저장 후 가게 프로필을 DB에서 전부 삭제하고 조회 | 추천 카드가 **스냅샷 그대로** 유지된다 |
| 13 | 저장 후 추천 알고리즘 상수를 바꾸고 조회 | `type_scores`·`taste_profile`이 **제출 시점 값** 그대로 |

### 마이그레이션 / 기존 동작

| # | 조건 | 기대 |
| --- | --- | --- |
| 14 | 구 스키마 테이블에 마이그레이션 실행 | 컬럼이 추가되고 기존 행이 보존된다. 재실행해도 안전 |
| 15 | `result_id`가 `NULL`인 기존 행 | 조회 대상이 되지 않으며 오류도 나지 않는다 |
| 16 | `GET /questions/{level}` | 기존과 동일 |
| 17 | `POST /submit`의 기존 필드 | 이름·타입·값 모두 변경 없음 |

---

## 12. 열린 질문

| # | 질문 | 현재 가정 | 결정 필요 시점 |
| --- | --- | --- | --- |
| 1 | 공유 URL의 길이가 문제가 되는가? (UUID 36자) | 문제없다고 가정 | 프론트가 URL 미관·QR 크기를 문제 삼으면 base62 단축 ID로 전환(§5.1) |
| 2 | 결과 보관 기간을 두어야 하는가? | 무기한 | 행 수가 수백만에 이르면 재검토 |
| 3 | 조회수·공유수를 집계할 것인가? | 이번 범위 밖 | 마케팅 지표 요구가 생기면 `result_views` 별도 테이블 |
| 4 | 유형 체계가 개편되면 기존 링크는? | 알 수 없는 유형 키는 404 | 유형 개편이 실제로 논의될 때 |
| 5 | 같은 답변을 재제출하면 같은 ID를 줄 것인가? | 아니오, 항상 새 ID | 중복 저장이 문제가 되면 답변 해시 기준 dedup 검토 |
| 6 | `POST` 남용에 레이트 리밋이 필요한가? | 지금은 불필요 | 배포 후 행 증가 추이 확인(§7.3) |
