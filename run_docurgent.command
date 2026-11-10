#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR/docurgent"
PY_BIN="/usr/bin/python3"
if [ ! -x "$PY_BIN" ]; then PY_BIN="python3"; fi
$PY_BIN server.py
