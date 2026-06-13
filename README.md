# Project Hub

Zentrale Übersichtsseite für deine Web-Projekte, gehostet auf deinem Hostinger VPS.
Listet deine GitHub-Repos (gefiltert nach Topic `webapp`) und legt per Klick neue
Projekte aus einem Template-Repo an. FastAPI-Backend + statisches Frontend,
auto-deployed via GitHub Actions über SSH.

```
project-hub/
├── app/
│   ├── main.py            FastAPI: serviert Frontend + API
│   ├── github_client.py   GitHub REST API (listen + aus Template generieren)
│   ├── config.py          .env-Settings
│   └── static/            index.html, style.css, app.js  (Dashboard)
├── deploy/
│   ├── setup-vps.sh       Einmaliges Bootstrap auf dem VPS
│   ├── project-hub.service systemd-Unit (uvicorn)
│   └── nginx.conf         Reverse Proxy
├── .github/workflows/deploy.yml   CI/CD: Push auf main → SSH-Deploy
├── requirements.txt
└── .env.example
```

## Wie es funktioniert

1. Dashboard ruft `GET /api/projects` → Backend liest deine Repos via GitHub API.
2. „+ Neues Projekt" → `POST /api/projects` → Backend generiert ein neues Repo aus
   `TEMPLATE_REPO` (GitHub „Generate from template") und setzt das Topic `webapp`.
3. Das Template-Repo bringt seinen **eigenen** Deploy-Workflow mit → jede neue WebApp
   deployt automatisch auf den VPS (siehe Abschnitt „Template-Repo").

---

## Setup — Schritt für Schritt

### 1. GitHub-Repo anlegen & Code pushen
Da es (noch) keinen GitHub-Connector gibt, legst du das Repo selbst an:

```bash
# lokal, im entpackten project-hub Ordner:
git init -b main
git add .
git commit -m "Initial: Project Hub"
gh repo create project-hub --private --source=. --push
# oder ohne gh CLI: Repo auf github.com anlegen, dann:
#   git remote add origin https://github.com/<user>/project-hub.git && git push -u origin main
```

### 2. Fine-grained PAT erstellen
GitHub → Settings → Developer settings → **Fine-grained tokens** → Generate.
Scope auf deinen Account/Org, Permissions:

| Permission | Zugriff | Wofür |
|---|---|---|
| Administration | Read & Write | Repos anlegen |
| Contents | Read & Write | aus Template generieren |
| Metadata | Read | Repos listen |
| Secrets | Read & Write | VPS-Secrets in neue Repos schreiben |

Außerdem `VPS_HOST`, `VPS_USER`, `VPS_PORT`, `VPS_SSH_KEY` in die `.env` (siehe
`.env.example`) — diese werden beim Anlegen automatisch als Actions-Secrets in
jedes neue Projekt-Repo geschrieben, damit dessen Auto-Deploy funktioniert.

Token notieren → kommt gleich in die `.env` **auf dem VPS** (nie ins Repo!).

### 3. VPS bootstrappen (SSH auf Hostinger)
```bash
ssh root@<vps-ip>
curl -O https://raw.githubusercontent.com/<user>/project-hub/main/deploy/setup-vps.sh
bash setup-vps.sh https://github.com/<user>/project-hub.git
```
Das Script installiert Python/Nginx, klont das Repo nach `/opt/project-hub`,
baut das venv, richtet systemd + Nginx ein.

### 4. `.env` auf dem VPS füllen
```bash
sudo nano /opt/project-hub/.env
```
`GITHUB_TOKEN`, `GITHUB_OWNER`, `TEMPLATE_REPO` setzen, dann:
```bash
sudo systemctl restart project-hub
curl localhost:8080/api/health   # token_configured: true ?
```

### 5. Deploy-User für CI/CD vorbereiten
Damit GitHub Actions den Service neustarten darf, dem Deploy-User passwortloses
sudo nur für diesen einen Befehl geben:
```bash
echo 'projecthub ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart project-hub' \
  | sudo tee /etc/sudoers.d/project-hub
```
SSH-Key fürs Deployment erzeugen (auf dem VPS) und Public Key autorisieren:
```bash
ssh-keygen -t ed25519 -f ~/deploy_key -N ""
cat ~/deploy_key.pub >> /home/projecthub/.ssh/authorized_keys   # ggf. anlegen
cat ~/deploy_key   # PRIVATE Key -> GitHub Secret VPS_SSH_KEY
```

### 6. GitHub Secrets setzen
Repo → Settings → Secrets and variables → **Actions**:

| Secret | Wert |
|---|---|
| `VPS_HOST` | IP/Hostname des VPS |
| `VPS_USER` | `projecthub` (oder root) |
| `VPS_PORT` | `22` |
| `VPS_SSH_KEY` | privater Deploy-Key aus Schritt 5 |

### 7. SSL + Domain
DNS-A-Record deiner Subdomain (z.B. `hub.deine-domain.de`) auf die VPS-IP.
`server_name` in `/etc/nginx/sites-available/project-hub` anpassen, dann:
```bash
sudo certbot --nginx -d hub.deine-domain.de
```

Ab jetzt: **Push auf `main` → automatischer Deploy.** Fertig.

---

## Template-Repo (für die neuen WebApps)

Damit „Neues Projekt" funktioniert, brauchst du ein Repo, das in GitHub als
**Template repository** markiert ist (Settings → ☑ Template repository) und in
`TEMPLATE_REPO` eingetragen wird. Lege darin schon `.github/workflows/deploy.yml`
+ einen passenden systemd/nginx-Block an, dann erbt jede neue App das Deployment.
Sag Bescheid, dann baue ich dir das `webapp-template` als nächstes Repo gleich mit.

---

## Lokal entwickeln
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Token eintragen
uvicorn app.main:app --reload --port 8080
# http://localhost:8080
```

## Sicherheits-Hinweise
- `.env` / Token **niemals** committen (steht in `.gitignore`).
- Dashboard optional mit `DASHBOARD_TOKEN` absichern (Header `X-Dashboard-Token`)
  oder Nginx Basic-Auth davorsetzen — der PAT hat Schreibrechte auf deine Repos.
- Fine-grained PAT mit Ablaufdatum + minimalem Scope verwenden.
