#!/bin/sh

# HELP: Read EPUB books with full link, footnote, and image support
# ICON: picoreader
# GRID: PicoReader

. /opt/muos/script/var/func.sh

APP_BIN="python3"
SETUP_APP "$APP_BIN" ""

# -----------------------------------------------------------------------------
APP_DIR="/run/muos/storage/application/PicoReader"
$APP_BIN "$APP_DIR/main.py"
