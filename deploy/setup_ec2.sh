#!/usr/bin/env bash
# EC2(Ubuntu 24.04)에서 1회 실행하는 초기 세팅 스크립트.
# 사용법: bash ~/services/deploy/setup_ec2.sh
set -euo pipefail

APP_ROOT="/home/ubuntu/services"

echo "==> 1/5 시스템 패키지 설치"
sudo apt-get update -y
sudo apt-get install -y python3-venv python3-pip nginx git

echo "==> 2/5 파이썬 가상환경 생성"
python3 -m venv "${APP_ROOT}/.venv"
"${APP_ROOT}/.venv/bin/pip" install --upgrade pip
"${APP_ROOT}/.venv/bin/pip" install -r "${APP_ROOT}/src/app/requirements.txt"

echo "==> 3/5 systemd 서비스 등록"
sudo cp "${APP_ROOT}/deploy/plers-api.service" /etc/systemd/system/plers-api.service
sudo systemctl daemon-reload
sudo systemctl enable plers-api

echo "==> 4/5 nginx 설정"
sudo cp "${APP_ROOT}/deploy/nginx-plers.conf" /etc/nginx/sites-available/plers
sudo ln -sf /etc/nginx/sites-available/plers /etc/nginx/sites-enabled/plers
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

echo "==> 5/5 DB 테이블 생성"
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

sudo systemctl restart plers-api
echo "==> 완료. 상태 확인: sudo systemctl status plers-api"
