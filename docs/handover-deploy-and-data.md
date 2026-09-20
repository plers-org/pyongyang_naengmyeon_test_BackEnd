# 인수인계 — 배포 구조와 데이터 적재

작성 2026-09-20 · 기준 브랜치 `dev` (`a941228`)

이 문서는 2026-09-20 가게 데이터 적재 작업에서 드러난 문제와 현재 상태를 남긴다.
다음 사람이 배포하거나 데이터를 다시 넣을 때 같은 데서 막히지 않게 하는 것이 목적이다.

---

## 1. 배포 — `deploy.sh` 한 줄

서버에 접속해 이것만 실행하면 된다.

```bash
ssh -i ~/.ssh/pyongyang-naengmyeon-key.pem ubuntu@15.165.89.181
bash ~/services/deploy/deploy.sh
```

`git pull` → 의존성 설치 → `migrate_db.sh`(스키마 반영) → 앱 재시작 순으로 돈다.
스키마를 먼저 맞추고 앱을 올리는 순서가 중요하다. 컬럼이 없는 채로 뜨면 결과 저장이
조용히 실패해 `result_id`가 계속 null로 내려간다.

`~/services`는 `dev` 브랜치 클론이다. 서버가 어느 커밋에 있는지 `git log`로 확인할 수 있다.

### GitHub 접근 방식

저장소의 **배포 키(read-only)**로 pull한다.

| 파일 | 역할 |
|---|---|
| `~/.ssh/github-deploy` | 개인키 (600). 서버 밖으로 나간 적 없다 |
| `~/.ssh/github-deploy.pub` | 공개키. GitHub 저장소 Settings → Deploy keys에 등록됨 |
| `~/.ssh/config` | github.com 접속 시 이 키를 쓰도록 지정 (`IdentitiesOnly yes`) |
| `~/.ssh/known_hosts` | github.com 호스트 키. 없으면 `Host key verification failed` |

읽기 전용이라 **서버에서 저장소로 푸시할 수 없다.** 의도된 제약이다.
서버가 털려도 저장소는 넘어가지 않는다.

확인:

```bash
ssh -T git@github.com
# Hi plers-org/pyongyang_naengmyeon_test_BackEnd! You've successfully authenticated...
```

### 함정 — 조직 정책이 deploy key를 막을 수 있다

2026-09-20 당시 plers-org가 조직 정책으로 deploy key를 꺼둬서, 저장소 Settings에
**"Disabled by plers-org"**가 뜨고 등록이 되지 않았다. 저장소 설정으로는 풀 수 없고
**조직 소유자만** 바꿀 수 있다. 화면에는 "There are no deploy keys for this repository"가
함께 뜨는데 이건 차단 사유가 아니라서 헷갈리기 쉽다.

정책이 다시 꺼지면 기존 키도 함께 무력화되어 `git pull`이 실패한다.
그때는 조직 소유자에게 요청하거나, fine-grained PAT(해당 저장소 `Contents: Read-only`)를
HTTPS로 쓰거나, GitHub Actions에서 서버로 배포하는 방식으로 바꿔야 한다.

### 배경 — 2026-09-20 이전에는 배포가 불가능했다

그전까지 `~/services`는 git 저장소가 아니었다. 누군가 파일을 수동 복사해 왔고,
서버에 GitHub 자격증명도 없었다. 그래서 `git pull`로 시작하는 `deploy.sh`는
`set -e` 때문에 첫 줄에서 죽었다. **문서와 스크립트가 전제하는 흐름이 서버 실제
상태와 어긋나 있었고, 서버에 무엇이 올라가 있는지 아무도 확신할 수 없었다.**

실제로 2026-09-20 배포 직전 서버 코드는 9월 5일 13:11 복사본이었고,
`import_places.sh` · `run_script.sh` · `import_restaurant_places.py`가 아예 없었다.

같은 날 배포 키를 등록하고 `~/services`를 클론으로 교체해 해결했다.
`.env`와 `.venv`는 git에 없으므로 교체 시 그대로 옮겨 붙였다
(`.venv`는 내부에 절대경로가 박혀 있어 최종 디렉터리 이름이 `services`여야 한다).

---

## 2. 접속 정보

| 항목 | 값 |
|---|---|
| EC2 | `ubuntu@15.165.89.181` (ap-northeast-2) |
| SSH 키 | `~/.ssh/pyongyang-naengmyeon-key.pem` (저장소에 없음, 별도 전달) |
| 앱 경로 | `/home/ubuntu/services` |
| 서비스 | `plers-api` (systemd, uvicorn 127.0.0.1:8000) |
| 앞단 | nginx → `proxy_pass 127.0.0.1:8000` |
| DB | RDS PostgreSQL, **퍼블릭 접근 차단** |

같은 디렉터리에 `plers-key.pem`도 있는데 **이 서버 키가 아니다** (Permission denied).

RDS가 막혀 있어 로컬에서 직접 적재할 수 없다. CSV를 EC2로 올리고 거기서 실행한다.
이건 올바른 설정이라 풀지 말 것.

---

## 3. 데이터 적재 파이프라인

```
search 저장소                      services 저장소            RDS
─────────────                      ──────────────            ───
data/reports/**.csv  ──scp──→  ~/*.csv  ──스크립트──→  restaurant_
                                                      recommendation_profiles
```

### 순서가 고정되어 있다

**프로필 먼저, 지도 정보 나중.** 바꾸면 조용히 실패한다.

4축 점수 컬럼이 NOT NULL이라 지도 정보만으로는 행을 만들 수 없다.
`import_places`는 `UPDATE`만 하므로 **프로필 행이 없는 가게는 지도 정보가 그냥 버려진다.**

```bash
# 1. 프로필 (행을 만든다)
bash ~/services/deploy/run_script.sh migrate_search_profiles.py \
  --input ~/restaurant_taste_profiles.csv \
  --copy ~/restaurant_recommendation_copy.csv \
  --availability ~/restaurant_availability.csv \
  --force-incomplete

# 2. 지도 정보 (빈 칸을 채운다) — 먼저 --dry-run 으로 건수 확인
bash ~/services/deploy/import_places.sh ~/restaurant_places.csv --include-review
```

두 스크립트 모두 `restaurant_name` 기준 덮어쓰기다. CSV를 고쳐 다시 돌리면
교정되고 행이 중복으로 쌓이지 않는다.

### `--force-incomplete`가 하는 일

점수가 덜 찬 가게의 빈 축을 임시값 3.0으로 채워 적재한다.
`profile_confidence`가 `low`로 고정되어 **추천 후보에서 빠지므로 추천 결과는 달라지지 않고**,
주소·지도 링크만 미리 확보된다. 임시로 채운 행은 `profile_version`에 `+provisional`이
붙어 나중에 구분해 덮어쓸 수 있다.

```sql
-- 임시점수 행만 골라내기
SELECT * FROM restaurant_recommendation_profiles
WHERE profile_version LIKE '%+provisional';
```

### `.env`를 `source`하지 않는 이유

`migrate_db.sh` · `run_script.sh` · `import_places.sh` 모두 `.env`를 한 줄씩 읽는다.
암호에 `$` `` ` `` `"` 가 들어 있으면 셸이 변수나 명령으로 해석해 `DATABASE_URL`이 깨지기 때문이다.
고칠 때 `source`로 바꾸지 말 것.

---

## 4. 지도 매칭 — `match_status`의 의미

`search`의 `collect-places`가 네이버에서 가게를 찾아 상태를 매긴다.

| 상태 | 뜻 | 적재 |
|---|---|---|
| `matched` | 자동 매칭 확정 | 항상 |
| `manual` | **사람이 `place_overrides.csv`로 지정** | 항상 |
| `review` | 후보가 여러 개라 기계가 확신 못 함 | `--include-review` 줄 때만 |
| `not_found` | 못 찾음 | 안 함 |

`manual`이 가장 믿을 만한 값이다. 과거 적재 대상이 `matched`/`review`뿐이라
사람이 고친 행이 매번 버려지는 버그가 있었다 (`b55b0ab`에서 수정).

### `collect-places`는 반드시 전체를 돌려야 한다

`analysis/place_report.py`의 `_write_place_csv`가 `"w"` 모드 **전체 덮어쓰기**다.
`--restaurants`로 일부만 돌리면 CSV가 그 몇 행짜리로 줄어들고 나머지가 날아간다.

DB(`restaurant_places` 테이블)는 upsert라 살아남지만, **DB에서 CSV를 다시 뽑는
CLI 명령이 없다.** 그냥 전체를 돌릴 것. 네이버 공개 검색을 긁는 방식이라 API 키는 필요 없다.

```bash
cd ~/plers/search
PYTHONPATH=src python3 -m pyongyang_naengmyeon.cli collect-places \
  --database data/pyongyang_naengmyeon_v2.db \
  --output-dir data/reports/3_places
```

`--database`를 **반드시 명시할 것.** `.env.local`의 `PNM_DATABASE_URL`은 구 DB
(`pyongyang_naengmyeon.db`, 식당 7곳, `restaurant_places` 테이블 없음)를 가리킨다.
실제 데이터는 `pyongyang_naengmyeon_v2.db`(32곳)에 있다.

재수집 후에는 `git diff`로 의도한 가게만 바뀌었는지 확인한다.
네이버 검색 결과가 바뀌면 손대지 않은 가게의 매칭도 달라질 수 있다.

---

## 5. 현재 데이터 상태 (2026-09-20 적재 완료)

| 전체 | 지도있음 | 주소있음 | 좌표있음 | 추천제외(low) | 임시점수 |
|---|---|---|---|---|---|
| 32 | 32 | 32 | 32 | 15 | 15 |

- 추천에 실제로 나오는 가게는 **17곳** (4축 점수가 다 찬 곳)
- 나머지 15곳은 임시점수라 추천에서 빠지고, 지도 링크만 들어가 있음
- `match_status`: matched 19 / manual 4 / review 9

### 지점 검수 결과

블로그 **제목**에 나온 지점명 빈도로 판단했다. 본문 전체는 다른 지점 언급이
섞여 신뢰할 수 없다.

바로잡은 곳 (`place_overrides.csv`에 기록됨):

| 가게 | 자동 매칭 | 바로잡음 | 근거 |
|---|---|---|---|
| 서령 | 롯데월드몰점 | 본점(소월로) | 본점·회현 496 vs 잠실·롯데월드 393 |
| 판동면옥 | 역삼 | 여의도점 | 여의도 408 vs 강남 18 |
| 한일관 | 영등포점 | 압구정점 | 압구정·신사 442 vs 타임스퀘어·영등포 289 |
| 만포면옥(구산동 본점) | 양주 장흥면 | 은평구 연서로 | 이전 작업에서 수정 |

**미결 — 류경회관.** 제목 언급이 역삼 110 / 광화문·종로 121로 갈리고 겹치는 제목이
0개라 데이터로 판정이 안 된다. 두 지점이 각자 활발하다는 뜻이다.
현재는 자동 매칭이 고른 **광화문점(삼봉로 81)**으로 들어가 있다.
강남점(논현로71길 18)으로 바꾸려면 override 한 줄을 추가하고 재수집한다.

### 주의 — 점수는 지점별이 아니다

여러 지점을 가진 가게의 맛 점수는 **모든 지점 리뷰를 섞어서** 만든 값이다.
지점 선택은 "어느 지점을 평가했나"가 아니라 "사용자를 어디로 보낼까"의 문제에 가깝다.
지점별로 맛이 갈리는 집이라면 프로필 자체를 지점 단위로 쪼개야 하고, 그건 별도 작업이다.

---

## 6. 로컬에만 있는 자산 — 백업 필요

`search/.gitignore`가 `data/reports/`와 `*.db`를 제외하고 있다.
적재에 직접 쓰는 CSV 4개만 예외로 추적 중이다 (`ee06e93`).

| 파일 | 크기 | 상태 |
|---|---|---|
| `search/data/pyongyang_naengmyeon_v2.db` | 96MB | **git에 없음. 백업 안 되어 있음** |
| `search/data/reports/` 나머지 | 약 65MB | git에 없음 (중간 산출물) |
| 적재용 CSV 4개 | 84KB | git 추적 중 ✓ |

**v2 DB가 유일한 실질적 위험이다.** 크롤링 원문·맛 문장·지점 후보가 전부 여기 들어 있고,
CSV를 다시 만들려면 이 파일이 필요하다. 노트북이 망가지면 크롤링부터 다시 해야 한다.
S3나 외장 디스크로 옮겨둘 것.

---

## 7. 서버에 남겨둔 백업

2026-09-20 작업 중 만든 것들이다. 며칠 지켜본 뒤 `services-old-*`부터 지우면 된다
(디렉터리라 용량을 제일 많이 먹는다). 디스크는 47% 사용 중이라 급하지는 않다.

| 파일 | 내용 |
|---|---|
| `~/services-old-20260920-1146/` | 클론 교체 전 디렉터리 통째로 |
| `~/services-preclone-20260920-1146.tar.gz` | 클론 교체 직전 코드 (126K) |
| `~/services-backup-20260920-1121.tar.gz` | 그날 첫 배포 전 코드 (118K) |
| `~/profiles-before-20260920-1125.sql` | 적재 직전 프로필 테이블 (17곳) |

적재 자체는 upsert라 CSV를 고쳐 다시 돌리면 교정된다.
설문 응답(`survey_responses`)은 이번 작업에서 건드리지 않았다.

---

## 8. 미해결 항목

우선순위 순이다.

### 8.1 v2 DB 외부 백업 — 가장 위험

`search/data/pyongyang_naengmyeon_v2.db`(96MB)가 **이 노트북 한 대에만 있다.**
크롤링 원문·맛 문장·지점 후보가 전부 여기 들어 있고, CSV를 다시 만들려면 이 파일이
필요하다. 노트북이 망가지면 **크롤링부터 다시 해야 한다.**

용량 때문에 git에 넣을 수 없으니 S3나 외장 디스크로 옮길 것. §6 참고.

### 8.2 임시점수 15곳의 4축 점수 검수

`--force-incomplete`로 넣은 15곳은 빈 축이 3.0으로 채워져 있고
`profile_confidence = 'low'`라 **추천 후보에 오르지 않는다.** 주소·지도 링크만 들어가 있다.

```sql
SELECT restaurant_name, profile_version FROM restaurant_recommendation_profiles
WHERE profile_version LIKE '%+provisional';
```

대상: 능라도(강남점), 류경회관, 만포면옥(구산동 본점), 봉밀가, 봉피양(방이 본점),
서관면옥(삼성점), 양각도, 유진식당, 을밀대(본점), 정인면옥(여의도 본점),
진미평양냉면(피양옥), 진영면옥, 평래옥, 평장원, 필동면옥.

대부분 `acidity` 한 축만 비어 있다 (양각도는 `umami`도, 만포면옥은 `umami`가 빈다).
근거를 채워 `restaurant_taste_profiles.csv`를 갱신하고 다시 적재하면
`+provisional` 표시가 사라지면서 추천 후보로 올라온다.

**추천 가능한 가게가 17곳뿐이라 결과가 단조로울 수 있다.** 이 검수가 체감 품질에
가장 크게 영향을 준다.

### 8.3 류경회관 지점 결정

블로그 제목 언급이 역삼 110 / 광화문·종로 121로 갈리고 **겹치는 제목이 0개**라
데이터로 판정이 안 된다. 두 지점이 각자 활발하다는 뜻이다.

현재는 자동 매칭이 고른 **광화문점(삼봉로 81)**이 들어가 있다.
강남점(논현로71길 18)으로 바꾸려면 `place_overrides.csv`에 한 줄 추가하고
`collect-places`를 **전체** 재실행한다. §4 참고.

### 8.4 HTTPS 적용 (certbot)

API가 아직 http다. 프론트가 https로 뜨면 브라우저가 호출을 차단한다.
`deploy/`에 certbot 설정이 없어 신규 작업이다.
도메인 A 레코드 확인 → 인증서 발급 → `nginx-plers.conf`에 443 블록과 80→443 리다이렉트
→ `certbot renew --dry-run` → CORS 허용 오리진 갱신(`main.py`) 순이다.
자세한 체크리스트는 `docs/todo-backend.md` 3번 항목에 있다.

### 8.5 프론트의 `map_url` null 처리 확인

2026-09-20에 구글 홈 폴백을 제거해서, 지도 링크가 없는 가게는 이제 `null`이 내려간다
(스키마상 원래도 `Optional[str]`이었다). **프론트가 항상 문자열로 가정하고 있다면
확인이 필요하다.** 현재 적재된 32곳은 모두 링크가 있어 실사용에서 null이 나오지는
않고, 지도 정보 없는 가게를 새로 추가할 때만 발생한다.

### 8.6 지점별 프로필 분리 (장기)

여러 지점을 가진 가게의 맛 점수는 모든 지점 리뷰를 섞은 값이다. §5 끝 참고.
지점별로 맛이 갈리는 집이라면 프로필을 지점 단위로 쪼개야 한다. 스키마 변경이 필요하다.
