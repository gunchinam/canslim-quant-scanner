#!/bin/bash
# Oracle Cloud Always Free ARM 인스턴스 초기 세팅 스크립트
# 사용법: ssh ubuntu@<IP> 접속 후
#   curl -sSL https://raw.githubusercontent.com/gunchinam/canslim-quant-scanner/main/deploy/setup-oracle.sh | bash

set -e

echo "=== 1. 시스템 업데이트 ==="
sudo apt update && sudo apt upgrade -y

echo "=== 2. Python 3.11+ 설치 ==="
sudo apt install -y python3 python3-pip python3-venv git nginx certbot python3-certbot-nginx

echo "=== 3. 프로젝트 클론 ==="
cd /home/ubuntu
if [ -d "canslim-quant-scanner" ]; then
    cd canslim-quant-scanner && git pull
else
    git clone https://github.com/gunchinam/canslim-quant-scanner.git
    cd canslim-quant-scanner
fi

echo "=== 4. 가상환경 + 의존성 설치 ==="
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "=== 5. 환경변수 설정 ==="
if [ ! -f .env ]; then
    cat > .env << 'ENVEOF'
# API 키 (필요시 입력)
FINNHUB_API_KEY=
KIS_APP_KEY=
KIS_APP_SECRET=
KIS_ACCOUNT=
ENVEOF
    echo ".env 파일 생성됨 — nano .env 로 API 키를 입력하세요"
fi

echo "=== 6. systemd 서비스 등록 ==="
sudo tee /etc/systemd/system/scanner.service > /dev/null << 'SVCEOF'
[Unit]
Description=Stock Scanner Web App
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/canslim-quant-scanner
Environment=PATH=/home/ubuntu/canslim-quant-scanner/venv/bin:/usr/bin
ExecStart=/home/ubuntu/canslim-quant-scanner/venv/bin/gunicorn \
    --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker \
    --workers 2 --threads 4 \
    --bind 127.0.0.1:5000 \
    --timeout 120 \
    web_app.app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVCEOF

sudo systemctl daemon-reload
sudo systemctl enable scanner
sudo systemctl start scanner

echo "=== 7. Nginx 리버스 프록시 ==="
sudo tee /etc/nginx/sites-available/scanner > /dev/null << 'NGXEOF'
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
}
NGXEOF

sudo ln -sf /etc/nginx/sites-available/scanner /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx

echo "=== 8. 방화벽 오픈 ==="
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save 2>/dev/null || true

echo ""
echo "========================================="
echo "  세팅 완료!"
echo "  http://<서버IP> 로 접속 가능"
echo ""
echo "  업데이트: cd canslim-quant-scanner && git pull && sudo systemctl restart scanner"
echo "  로그 확인: sudo journalctl -u scanner -f"
echo "  API 키 설정: nano .env && sudo systemctl restart scanner"
echo "========================================="
