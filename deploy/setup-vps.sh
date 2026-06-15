#!/usr/bin/env bash
# Einmaliges Bootstrap-Script fuer den Hostinger VPS (Ubuntu/Debian).
# Als root oder mit sudo ausfuehren:  bash setup-vps.sh <git-clone-url>
set -euo pipefail

REPO_URL="${1:?Bitte Git-Clone-URL angeben, z.B. https://github.com/<user>/project-hub.git}"
APP_DIR="/opt/project-hub"
APP_USER="projecthub"

echo "==> System-Pakete"
apt-get update -y
apt-get install -y git nginx docker.io docker-compose-plugin

echo "==> Docker aktivieren"
systemctl enable docker
systemctl start docker

echo "==> Service-User anlegen"
id -u "$APP_USER" &>/dev/null || useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"
usermod -aG docker "$APP_USER"

echo "==> Repo klonen"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull
else
  git clone "$REPO_URL" "$APP_DIR"
fi

echo "==> .env vorbereiten"
if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  echo "    -> WICHTIG: $APP_DIR/.env jetzt mit deinem GITHUB_TOKEN etc. fuellen!"
fi

echo "==> Rechte setzen"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "==> systemd-Service"
cp "$APP_DIR/deploy/project-hub.service" /etc/systemd/system/project-hub.service
systemctl daemon-reload
systemctl enable project-hub

echo "==> Nginx"
cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/project-hub
ln -sf /etc/nginx/sites-available/project-hub /etc/nginx/sites-enabled/project-hub
nginx -t && systemctl reload nginx

echo ""
echo "Fertig. Naechste Schritte:"
echo "  1) $APP_DIR/.env mit Token/Owner/Template fuellen"
echo "  2) sudo -u $APP_USER docker compose -f $APP_DIR/docker-compose.yml up -d --build"
echo "  3) server_name in nginx.conf anpassen + 'sudo certbot --nginx -d <domain>'"
echo "  4) GitHub Secrets setzen: VPS_HOST, VPS_USER ($APP_USER), VPS_PORT, VPS_SSH_KEY"
