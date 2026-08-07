"""
Baseline benchmark for Roof Link.3dm import performance.
Run: /Applications/Blender.app/Contents/MacOS/Blender --background --python tests/benchmarks/benchmark_roof_link.py
"""
import os
import sys
import time
import gc

# Ensure addons path is available (Blender background mode has this, but be safe)
addons_dir = os.path.expanduser("~/Library/Application Support/Blender/5.2/scripts/addons")
if addons_dir not in sys.path:
    sys.path.insert(0, addons_dir)

import bpy

# Clean scene
bpy.ops.wm.read_factory_settings(use_empty=True)

# Enable the addon so its modules load properly
bpy.ops.preferences.addon_enable(module="LoopFlow_import_3dm")

from LoopFlow_import_3dm.read3dm import read_3dm

model_path = os.path.expanduser("~/Desktop/Roof Link.3dm")

if not os.path.exists(model_path):
    print(f"ERROR: Model not found: {model_path}")
    sys.exit(1)

file_size_mb = os.path.getsize(model_path) / (1024 * 1024)
print(f"\n{'='*70}")
print(f"BASELINE BENCHMARK: Roof Link.3dm ({file_size_mb:.1f} MB)")
print(f"{'='*70}")

gc.collect()
gc.disable()

options = {
    "filepath": model_path,
    "is_update": False,
    "import_instances": True,
    "import_curves": False,
    "import_meshes": True,
    "weld_meshes": True,
    "nurbs_density": 0.5,
    "subd_subsurf_level": 3,
    "update_materials": False,
    "import_mode": "SYNC",
    "link_materials_to": "PREFERENCES",
}

print(f"\nStarting import at: {time.strftime('%H:%M:%S')}")
t_start = time.perf_counter()

result = read_3dm(bpy.context, options)

t_total = time.perf_counter() - t_start
print(f"\nImport complete at: {time.strftime('%H:%M:%S')}")
print(f"Total time: {t_total:.2f} seconds ({t_total/60:.2f} minutes)")
print(f"Objects in scene: {len(bpy.data.objects)}")
print(f"Meshes in scene: {len(bpy.data.meshes)}")
print(f"Materials in scene: {len(bpy.data.materials)}")
print(f"Collections in scene: {len(bpy.data.collections)}")
print(f"Result: {result}")
print(f"{'='*70}")

# Save blend file
try:
    out_path = os.path.expanduser("~/Desktop/Roof_Link_Baseline.blend")
    bpy.ops.wm.save_as_mainfile(filepath=out_path, compress=True, relative_remap=False)
    print(f"Saved: {out_path}")
except Exception as e:
    print(f"Could not save blend: {e}")
