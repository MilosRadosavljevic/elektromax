#!/usr/bin/env bash
# Ažuriranje aplikacije na serveru posle novog push-a na GitHub (pokreće root):  elektromax-azuriraj
set -euo pipefail
APP=/home/elektromax/app
ENV_FAJL=/home/elektromax/elektromax.env

/usr/local/bin/elektromax-backup                       # kopija baze pre svake nadogradnje
sudo -H -u elektromax git -C "$APP" pull --ff-only
sudo -H -u elektromax "$APP/.venv/bin/pip" install -q -r "$APP/requirements.txt" -r "$APP/requirements-server.txt"
sudo -H -u elektromax cp -n "$APP"/static/uploads/*.* /home/elektromax/data/uploads/ 2>/dev/null || true
sudo -H -u elektromax env $(grep -v '^#' "$ENV_FAJL" | xargs) "$APP/.venv/bin/python" "$APP/migracije.py"
install -m 755 "$APP/deploy/azuriraj.sh" /usr/local/bin/elektromax-azuriraj
install -m 755 "$APP/deploy/elektromax-lozinka" /usr/local/bin/elektromax-lozinka
systemctl restart elektromax
sleep 2
curl -fsS -o /dev/null -w "Provera aplikacije: HTTP %{http_code}\n" http://127.0.0.1:8000/
echo "Verzija: $(sudo -H -u elektromax git -C "$APP" log -1 --format='%h %s')"
