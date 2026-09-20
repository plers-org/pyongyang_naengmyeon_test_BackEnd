# 인수인계 — 배포 구조와 데이터 적재

작성 2026-09-20 · 기준 브랜치 `dev` (`7690203`)

이 문서는 2026-09-20 가게 데이터 적재 작업에서 드러난 문제와 현재 상태를 남긴다.
다음 사람이 배포하거나 데이터를 다시 넣을 때 같은 데서 막히지 않게 하는 것이 목적이다.

---

## 1. 서버는 git 저장소가 아니다 — `deploy.sh`가 동작하지 않는다

**가장 먼저 알아야 할 사실이다.**

EC2의 `/home/ubuntu/services`는 git 저장소가 아니다. 홈 어디에도 `.git`이 없고,
서버에 GitHub 자격증명도 없다 (`~/.ssh`에 인바운드용 `authorized_keys`만 있고
배포 키 없음, GitHub host key 미등록).

그런데 `deploy/deploy.sh`는 이렇게 시작한다.

```bash
set -euo pipefail
cd "${APP_ROOT}"
git pull        # ← 여기서 무조건 죽는다
```

`set -e`라 첫 실패에서 중단된다. **문서와 스크립트가 전제하는 배포 흐름이
서버 실제 상태와 어긋나 있다.** 지금까지는 누군가 파일을 수동 복사해 왔고,
그래서 서버에 무엇이 올라가 있는지 아무도 확신할 수 없다.

실제로 2026-09-20 배포 직전 서버 코드는 9월 5일 13:11 복사본이었고,
`import_places.sh` · `run_script.sh` · `import_restaurant_places.py`가 아예 없었다.

### 지금 쓰는 우회 방법

`git archive`로 커밋 내용을 그대로 tar 전송한다. `.env`와 `.venv`는 git에 없으니
덮어쓰이지 않는다.

```bash
# 맥에서
cd ~/plers/services
git archive --format=tar origin/dev | ssh -i ~/.ssh/pyongyang-naengmyeon-key.pem \
  ubuntu@15.165.89.181 'tar -x -C ~/services'

# 서버에서
cd ~/services
.venv/bin/pip install -r src/app/requirements.txt
APP_ROOT=/home/ubuntu/services bash deploy/migrate_db.sh
sudo systemctl restart plers-api && systemctl status plers-api --no-pager
```

### 제대로 고치려면

`~/services`를 진짜 클론으로 교체해야 한다. GitHub 저장소에 배포 키(read-only)를
등록하고 서버에 개인키를 넣은 뒤, 기존 디렉터리를 백업하고 클론한 다음
`.env`와 `.venv`를 옮겨 붙인다. 그래야 `deploy.sh`가 원래 의도대로 동작한다.

**미해결 상태다.** 이 작업 전까지는 위 우회 방법을 쓸 것.

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

| 파일 | 내용 |
|---|---|
| `~/services-backup-20260920-1121.tar.gz` | 배포 직전 코드 (118K) |
| `~/profiles-before-20260920-1125.sql` | 적재 직전 프로필 테이블 (17곳) |

적재 자체는 upsert라 CSV를 고쳐 다시 돌리면 교정된다.
설문 응답(`survey_responses`)은 이번 작업에서 건드리지 않았다.

---

## 8. 남은 작업

- [ ] **`~/services`를 git clone으로 교체** — 배포 키 등록 필요. §1 참고. 가장 시급하다
- [ ] **임시점수 15곳의 4축 점수 검수** — 채워 넣으면 추천 후보로 올라온다.
      `profile_version LIKE '%+provisional'`로 골라낼 수 있다
- [ ] **류경회관 지점 결정** — §5 참고
- [ ] **v2 DB 외부 백업**
- [ ] `docs/todo-backend.md`의 HTTPS(certbot) 항목 — 아직 http다
