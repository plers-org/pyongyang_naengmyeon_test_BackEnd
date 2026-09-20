# 백엔드 TODO (결과 공유 기능 관련)

기준: 2026-09-05 / 기본 브랜치 `dev`

---

## 1. 결과 페이지 공유 — result_id 발급 / 조회 API

코드 작업 완료. PR #3 이 `dev` 로 머지됨(`f9e0f0e`). **아직 배포 전.**

- [x] `survey_responses.result_id` 컬럼 + 유니크 인덱스
- [x] `POST /api/recommendation/submit` 응답에 `result_id`, `created_at`
- [x] `GET /api/recommendation/results/{result_id}` 조회 API
- [x] 결과 스냅샷 저장(제출 시점 유형·점수·추천 가게 고정)
- [x] 저장 실패 시 `result_id` 미발급 / 404·503 분기
- [x] `Cache-Control: public, max-age=3600`
- [x] 테스트 `test/test_result_lookup.py` (전체 66개 통과)
- [ ] **EC2에서 `deploy/deploy.sh` 실행** — `migrate_db.sh` 가 컬럼·인덱스를 반영한 뒤 앱 재시작
- [ ] **운영에서 submit → get 왕복 확인** — 발급된 `result_id` 로 같은 결과가 오는지
- [ ] **`result_id` 가 null 로 안 내려가는지 확인** — null 이면 마이그레이션이 안 된 것
- [ ] **프론트 연동 확인** — 공유 링크를 다른 세션/기기에서 열었을 때 정상 렌더
- [ ] (미확정) 공유 이미지 OG 메타를 백엔드가 줄지 프론트가 처리할지 결정

## 2. 추천 식당 네이버 지도 링크 (`map_url`)

~~`map_url` 이 비면 `TEMP_ADDRESS_URL` 로 폴백 중~~ → **2026-09-20 완료.** 32곳 전부 적재하고 폴백을 제거했다.
(`services/recommendation_data.py:25`, `api/v1/recommendation.py:111`).
= 지금 프론트에 구글 홈이 지도 링크로 나가고 있음.

- [ ] 가게별 네이버 지도 URL 수집 (미수집분)
- [ ] `restaurant_availability.csv` 의 `map_url` 컬럼에 반영
- [ ] `restaurant_recommendation_profiles.map_url` 로 적재 (`profile_repository.py`)
- [ ] 커버리지 쿼리로 전 가게 채워졌는지 확인
- [x] 100% 되면 `TEMP_ADDRESS_URL` 폴백 제거

## 3. HTTPS 적용 (certbot)

`deploy/` 에 certbot 설정 없음 — 신규 작업.
현재 API 가 http 라, 프론트가 https 로 뜨면 브라우저가 호출을 차단함.

- [ ] 도메인 → EC2 A 레코드 확인
- [ ] certbot 설치 + 인증서 발급 (nginx 플러그인)
- [ ] `deploy/nginx-plers.conf` 에 443 블록 / 80 → 443 리다이렉트
- [ ] `certbot renew --dry-run` 으로 자동 갱신 확인
- [ ] CORS 허용 오리진을 https 도메인으로 갱신 (`main.py`)
- [ ] `main.py` DESCRIPTION 의 "현재 서버는 http 입니다" 문구 수정
- [ ] 프론트에 API base URL https 교체 안내

## 4. 실제 테스트 데이터 DB 적재 검증

미착수. 3번까지 끝나고 실사용 트래픽이 들어온 뒤 하는 게 맞음.

- [ ] `survey_responses` 행이 실제로 쌓이는지
- [ ] `answers` / `taste_vector` / `type_ranking` JSON 무결성
- [ ] 신규 행에 `result_id` 가 모두 채워지는지 (구 로그 행은 NULL 허용)
- [ ] 저장 실패 시 API 가 500 없이 정상 응답하는지 (`record_safely` 경로)
- [ ] 집계 쿼리(일별 제출 수, 유형 분포)로 데이터 사용 가능성 확인

---

## 다음에 할 일

**1번 배포** → **3번 HTTPS** → **2번 map_url** → **4번 검증**

1번과 3번이 프론트를 막고 있음. 특히 1번은 코드가 머지만 되고 배포가 안 돼서,
프론트가 붙일 API 가 아직 운영에 없는 상태.
