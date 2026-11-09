#!/usr/bin/env bash
# Noćna rezervna kopija baze (cron 02:30). Čuva poslednjih 30 kopija.
set -euo pipefail
DB=/home/elektromax/data/elektromax.db
DIR=/home/elektromax/backup
mkdir -p "$DIR"
F="$DIR/elektromax-$(date +%Y-%m-%d_%H%M).db"
sqlite3 "$DB" ".backup '$F'"          # bezbedna kopija i dok aplikacija radi
gzip -f "$F"
chown elektromax:elektromax "$F.gz"
ls -1t "$DIR"/elektromax-*.db.gz | tail -n +31 | xargs -r rm -f
