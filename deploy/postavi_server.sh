#!/usr/bin/env bash
# Prvo podešavanje Elektromax aplikacije na Ubuntu serveru (pokreće root). Bezbedno je pokrenuti ponovo.
#   bash postavi_server.sh
# Pretpostavke: postoji korisnik "elektromax" sa deploy ključem za GitHub (~elektromax/.ssh/github_deploy),
# instalirani su nginx, python3-venv, git, sqlite3 (vidi DEPLOY.md).
set -euo pipefail

KORISNIK=elektromax
HOME_DIR=/home/$KORISNIK
APP=$HOME_DIR/app
DATA=$HOME_DIR/data
BACKUP=$HOME_DIR/backup
ENV_FAJL=$HOME_DIR/elektromax.env
REPO=git@github.com:MilosRadosavljevic/elektromax-store.git
LOZINKE=/root/elektromax-lozinke.txt

echo "== kod"
if [ ! -d "$APP/.git" ]; then
  sudo -H -u $KORISNIK git clone -q "$REPO" "$APP"
else
  sudo -H -u $KORISNIK git -C "$APP" pull -q --ff-only
fi

echo "== python okruženje"
sudo -H -u $KORISNIK python3 -m venv "$APP/.venv"
sudo -H -u $KORISNIK "$APP/.venv/bin/pip" install -q --upgrade pip
sudo -H -u $KORISNIK "$APP/.venv/bin/pip" install -q -r "$APP/requirements.txt" -r "$APP/requirements-server.txt"

echo "== podaci (van koda)"
sudo -H -u $KORISNIK mkdir -p "$DATA/uploads" "$BACKUP"
sudo -H -u $KORISNIK cp -n "$APP"/static/uploads/*.* "$DATA/uploads/" 2>/dev/null || true

echo "== tajne (samo na serveru)"
if [ ! -f "$ENV_FAJL" ]; then
  cat > "$ENV_FAJL" <<EOF
ELEKTROMAX_PRODUKCIJA=1
ELEKTROMAX_HTTPS=0
ELEKTROMAX_SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
ELEKTROMAX_DB=$DATA/elektromax.db
ELEKTROMAX_UPLOAD_DIR=$DATA/uploads
EOF
  chown root:$KORISNIK "$ENV_FAJL"; chmod 640 "$ENV_FAJL"
fi
set -a; . "$ENV_FAJL"; set +a

echo "== baza"
if [ ! -f "$ELEKTROMAX_DB" ]; then
  sudo -H -u $KORISNIK cp "$APP/elektromax.db" "$ELEKTROMAX_DB"
  # Demo nalozi imaju lozinke koje su u git-u -> na serveru dobijaju nove, nasumične
  sudo -H -u $KORISNIK env ELEKTROMAX_DB="$ELEKTROMAX_DB" "$APP/.venv/bin/python" - > "$LOZINKE" <<'PY'
import os, secrets, sqlite3
from werkzeug.security import generate_password_hash
con = sqlite3.connect(os.environ["ELEKTROMAX_DB"])
print("Elektromax – nove lozinke demo naloga na serveru (fajl čita samo root)")
for ime in ("admin", "radnik", "jovana"):
    if con.execute("SELECT 1 FROM korisnici WHERE korisnicko_ime = ?", (ime,)).fetchone():
        loz = secrets.token_urlsafe(9)
        con.execute("UPDATE korisnici SET lozinka_hash = ? WHERE korisnicko_ime = ?", (generate_password_hash(loz), ime))
        print(f"{ime}: {loz}")
con.execute("DELETE FROM api_tokeni")
con.commit()
PY
  chmod 600 "$LOZINKE"
fi
sudo -H -u $KORISNIK env $(grep -v '^#' "$ENV_FAJL" | xargs) "$APP/.venv/bin/python" "$APP/migracije.py"

echo "== dozvole za nginx"
usermod -aG $KORISNIK www-data
chmod 750 "$HOME_DIR"; chmod -R g+rX "$APP/static" "$DATA/uploads"; chmod g+x "$DATA" "$APP"

echo "== servis, nginx, rezervne kopije"
install -m 644 "$APP/deploy/elektromax.service" /etc/systemd/system/elektromax.service
# nginx konfiguracija se postavlja samo prvi put – posle je menja certbot (HTTPS), pa je ne gazimo
[ -f /etc/nginx/sites-available/elektromax ] || install -m 644 "$APP/deploy/nginx-elektromax.conf" /etc/nginx/sites-available/elektromax
ln -sf /etc/nginx/sites-available/elektromax /etc/nginx/sites-enabled/elektromax
rm -f /etc/nginx/sites-enabled/default
install -m 755 "$APP/deploy/backup.sh" /usr/local/bin/elektromax-backup
echo "30 2 * * * root /usr/local/bin/elektromax-backup" > /etc/cron.d/elektromax-backup
install -m 755 "$APP/deploy/azuriraj.sh" /usr/local/bin/elektromax-azuriraj
install -m 755 "$APP/deploy/elektromax-lozinka" /usr/local/bin/elektromax-lozinka
systemctl daemon-reload
systemctl enable --now elektromax
systemctl restart elektromax
nginx -t && systemctl reload nginx

sleep 2
curl -fsS -o /dev/null -w "== provera: HTTP %{http_code}\n" http://127.0.0.1/
echo "Gotovo. Nove lozinke demo naloga: $LOZINKE"
