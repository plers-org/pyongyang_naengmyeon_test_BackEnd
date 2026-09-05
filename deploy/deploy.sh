#!/usr/bin/env bash
# 코드 수정 후 EC2에서 재배포할 때 실행.
# 사용법: bash ~/services/deploy/deploy.sh
set -euo pipefail

APP_ROOT="/home/ubuntu/services"

cd "${APP_ROOT}"
git pull
"${APP_ROOT}/.venv/bin/pip" install -r "${APP_ROOT}/src/app/requirements.txt"

# 스키마를 먼저 맞추고 앱을 올린다. 컬럼이 없는 채로 뜨면 결과 저장이 조용히 실패해
# result_id가 계속 null로 내려간다.
APP_ROOT="${APP_ROOT}" bash "${APP_ROOT}/deploy/migrate_db.sh"

sudo systemctl restart plers-api
sleep 2
sudo systemctl status plers-api --no-pager
