#!/usr/bin/env bash
# .env를 읽어 RDS 스키마를 최신 상태로 맞춘다.
# CREATE/ALTER 모두 IF NOT EXISTS라 여러 번 실행해도 안전하다.
# 최초 세팅(setup_ec2.sh)과 재배포(deploy.sh) 양쪽에서 호출한다.
set -euo pipefail

APP_ROOT="${APP_ROOT:-/home/ubuntu/services}"

cd "${APP_ROOT}/src/app"

# .env를 source하지 않고 한 줄씩 읽어 그대로 넣는다.
# 암호에 $ ` " 같은 문자가 있으면 셸이 변수나 명령으로 해석해 값이 깨진다.
# (systemd의 EnvironmentFile은 원래 값을 그대로 읽으므로 앱 실행에는 영향이 없다.)
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
PYTHONPATH="${APP_ROOT}/src/app" "${APP_ROOT}/.venv/bin/python" scripts/init_db.py
