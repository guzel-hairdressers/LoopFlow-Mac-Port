#!/usr/bin/env bash

set -e

echo ""
echo "============================================================"
echo "  LoopFlow Rhino-to-Blender Installer (macOS)"
echo "============================================================"
echo ""

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SRC_PY="$SCRIPT_DIR/Python"
RHINO_DIR="$HOME/Library/Application Support/McNeel/Rhinoceros/8.0"
DST_ROOT="$RHINO_DIR/scripts/LoopFlow_R2B"
DST_PY="$DST_ROOT/Py"
DST_DATA="$DST_ROOT/Data"

if [ ! -d "$SRC_PY" ]; then
    echo "[ERROR] Cannot find source folder: $SRC_PY"
    exit 1
fi

if [ ! -d "$RHINO_DIR" ]; then
    echo "[WARNING] Rhino 8.0 settings folder not found at:"
    echo "          $RHINO_DIR"
    echo "          Creating folder structure..."
    mkdir -p "$RHINO_DIR"
fi

echo "[1/3] Rhino 8.0 settings folder ... OK"

echo "[2/3] Preparing target folder: $DST_PY ..."
mkdir -p "$DST_PY"
mkdir -p "$DST_DATA"

echo "[3/3] Copying scripts..."
cp -R "$SRC_PY/"* "$DST_PY/"

COPIED_COUNT=$(ls -1 "$DST_PY"/*.py 2>/dev/null | wc -l | tr -d ' ')

echo ""
echo "  Source : $SRC_PY"
echo "  Target : $DST_PY"
echo "  Copied : $COPIED_COUNT python script(s)"
echo ""
echo "============================================================"
echo "  Installation complete!"
echo "============================================================"
echo ""
echo "NEXT STEPS:"
echo "  1. Open Rhino 8 for Mac"
echo "  2. Drag LoopFlow_R2B_Mac.rhc into any Rhino viewport"
echo "  3. The LoopFlow R2B toolbar will appear"
echo ""
