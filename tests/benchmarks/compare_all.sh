#!/bin/bash
# Compare Legacy vs OBJ on all 3 models, 5-min kill switch each
BLENDER="/Applications/Blender.app/Contents/MacOS/Blender"
ADDON="$HOME/Library/Application Support/Blender/5.2/scripts/addons"
SRC="$PWD/src/LoopFlow_import_3dm"

# Sync latest code
for f in __init__.py read3dm.py; do cp "$SRC/$f" "$ADDON/LoopFlow_import_3dm/$f"; done
for f in __init__.py utils.py render_mesh.py instances.py material.py; do cp "$SRC/converters/$f" "$ADDON/LoopFlow_import_3dm/converters/$f"; done

declare -A MODELS
MODELS["B1M 9.2"]="$HOME/Desktop/B1M 9.2.3dm"
MODELS["Game Center Roof"]="$HOME/Desktop/Game Center Roof.3dm"
MODELS["Roof Link"]="$HOME/Desktop/Roof Link.3dm"

run_test() {
    local name="$1" path="$2" fast="$3"
    local mode; if [ "$fast" = "1" ]; then mode="OBJ"; else mode="LEGACY"; fi
    local size; size=$(du -h "$path" | cut -f1)
    echo "============================================================"
    echo "$name ($size) — $mode"
    echo "============================================================"
    timeout 300 $BLENDER --background --python-expr "
import os,sys,time,gc
sys.path.insert(0,os.path.expanduser('$ADDON'))
import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.preferences.addon_enable(module='LoopFlow_import_3dm')
from LoopFlow_import_3dm.read3dm import read_3dm
mp=r'$path'
opts={'filepath':mp,'is_update':False,'import_instances':True,'import_curves':False,'import_meshes':True,'weld_meshes':True,'nurbs_density':0.5,'subd_subsurf_level':3,'update_materials':False,'import_mode':'SYNC','link_materials_to':'PREFERENCES','use_fast_import':$fast}
gc.disable()
t0=time.perf_counter(); read_3dm(bpy.context,opts); dt=time.perf_counter()-t0
objs=len(bpy.data.objects); meshes=len(bpy.data.meshes)
verts=sum(len(o.data.vertices) for o in bpy.data.objects if o.type=='MESH')
faces=sum(len(o.data.polygons) for o in bpy.data.objects if o.type=='MESH')
print(f'RESULT: {dt:.1f}s | {objs} objs | {meshes} meshes | {verts:,} verts | {faces:,} faces')
" 2>&1 | grep "RESULT\|traceback\|Error" || echo "  $mode: TIMEOUT (>5 min)"
}

for name in "B1M 9.2" "Game Center Roof" "Roof Link"; do
    path="${MODELS[$name]}"
    [ -f "$path" ] || { echo "SKIP $name: not found"; continue; }
    run_test "$name" "$path" 0  # Legacy
    run_test "$name" "$path" 1  # OBJ
done

echo "Done!"
