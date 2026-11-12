#!/bin/bash
# ==============================================================================
# DocUrgent 24/7 — Vercel Deployment Helper
# Syncs frontend assets into public/, bundles Python backend safely, and deploys.
# ==============================================================================

set -e
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SRC_DIR="$DIR/docurgent"
VERCEL_DIR="$DIR/docurgent-vercel"

mkdir -p "$VERCEL_DIR/public" "$VERCEL_DIR/api"

# Sync static frontend assets privately into public/ (prevents exposing backend files)
cp "$SRC_DIR/index.html" "$VERCEL_DIR/public/index.html"
cp "$SRC_DIR/styles.css" "$VERCEL_DIR/public/styles.css"
cp "$SRC_DIR/app.js" "$VERCEL_DIR/public/app.js"

# Sync Python backend modules
cp "$SRC_DIR/server.py" "$VERCEL_DIR/server.py"
cp "$SRC_DIR/db.py" "$VERCEL_DIR/db.py"
cp "$SRC_DIR/backup_manager.py" "$VERCEL_DIR/backup_manager.py"

# Checkpoint and export a clean single-file SQLite snapshot (demo data only)
rm -f "$VERCEL_DIR/docurgent.db"*
python3 -c "
import sqlite3
src = sqlite3.connect('$SRC_DIR/docurgent.db')
dst = sqlite3.connect('$VERCEL_DIR/docurgent.db')
with dst:
    src.backup(dst)
dst.close()
src.close()
"

cd "$VERCEL_DIR"
vercel --prod --yes
