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
APP_ROOT="${APP_ROOT}" bash "${APP_ROOT}/deploy/migrate_db.sh"

sudo systemctl restart plers-api
echo "==> 완료. 상태 확인: sudo systemctl status plers-api"
