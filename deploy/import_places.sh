#!/usr/bin/env bash
# search의 restaurant_places.csv를 읽어 프로필 테이블의 주소·지도 링크·좌표를 채운다.
# RDS는 퍼블릭 접근이 막혀 있어 EC2에서 실행해야 한다.
#
# 사용법:
#   bash ~/services/deploy/import_places.sh ~/restaurant_places.csv --include-review --dry-run
#   bash ~/services/deploy/import_places.sh ~/restaurant_places.csv --include-review
set -euo pipefail

APP_ROOT="${APP_ROOT:-/home/ubuntu/services}"
CSV_PATH="${1:?restaurant_places.csv 경로를 첫 인자로 주세요}"
shift

cd "${APP_ROOT}/src/app"

# migrate_db.sh와 같은 방식으로 .env를 읽는다.
# source하면 암호에 든 $ ` " 를 셸이 해석해 DATABASE_URL이 깨진다.
while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line%$'\r'}"
    if [[ -z "${line}" || "${line}" == \#* || "${line}" != *=* ]]; then
        continue
    fi
    key="${line%%=*}"
    if [[ ! "${key}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
        continue
    fi
    printf -v "${key}" '%s' "${line#*=}"
    export "${key}"
done < "${APP_ROOT}/.env"

# scripts/ 하위 파일을 실행하면 import 기준이 scripts/가 되어 services 패키지를 찾지 못한다.
PYTHONPATH="${APP_ROOT}/src/app" "${APP_ROOT}/.venv/bin/python" \
    scripts/import_restaurant_places.py --input "${CSV_PATH}" "$@"
