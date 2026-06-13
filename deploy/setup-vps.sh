#!/usr/bin/env bash
# Einmaliges Bootstrap-Script fuer den Hostinger VPS (Ubuntu/Debian).
# Als root oder mit sudo ausfuehren:  bash setup-vps.sh <git-clone-url>
set -euo pipefail

REPO_URL="${1:?Bitte Git-Clone-URL angeben, z.B. https://github.com/<user>/project-hub.git}"
APP_DIR="/opt/project-hub"
APP_USER="projecthub"

echo "==> System-Pakete"
apt-get update -y
apt-get install -y python3 python3-venv python3-pip git nginx

echo "==> Service-User anlegen"
id -u "$APP_USER" &>/dev/null || useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"

echo "==> Repo klonen"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull
else
  git clone "$REPO_URL" "$APP_DIR"
fi

echo "==> Virtualenv + Dependencies"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

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
systemctl restart project-hub

echo "==> Nginx"
cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/project-hub
ln -sf /etc/nginx/sites-available/project-hub /etc/nginx/sites-enabled/project-hub
nginx -t && systemctl reload nginx

echo ""
echo "Fertig. Naechste Schritte:"
echo "  1) $APP_DIR/.env mit Token/Owner/Template fuellen"
echo "  2) sudo systemctl restart project-hub"
echo "  3) server_name in nginx.conf anpassen + 'sudo certbot --nginx -d <domain>'"
echo "  4) Deploy-User braucht sudo-Rechte fuer 'systemctl restart project-hub' (siehe README)"
