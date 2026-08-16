#!/usr/bin/env bash
# 코드 수정 후 EC2에서 재배포할 때 실행.
# 사용법: bash ~/services/deploy/deploy.sh
set -euo pipefail

APP_ROOT="/home/ubuntu/services"

cd "${APP_ROOT}"
git pull
"${APP_ROOT}/.venv/bin/pip" install -r "${APP_ROOT}/src/app/requirements.txt"
sudo systemctl restart plers-api
sleep 2
sudo systemctl status plers-api --no-pager
