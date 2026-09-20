#!/usr/bin/env bash
# .env를 읽어 src/app/scripts/ 아래 스크립트를 실행한다.
# 사용법: bash ~/services/deploy/run_script.sh rename_restaurant.py --from "옛이름" --to "새이름"
set -euo pipefail

APP_ROOT="${APP_ROOT:-/home/ubuntu/services}"
SCRIPT_NAME="${1:?실행할 스크립트 이름을 첫 인자로 주세요 (예: rename_restaurant.py)}"
shift

cd "${APP_ROOT}/src/app"

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

PYTHONPATH="${APP_ROOT}/src/app" "${APP_ROOT}/.venv/bin/python" "scripts/${SCRIPT_NAME}" "$@"
