"""
Quick A/B benchmark: weld_meshes=False vs True
"""
import os, sys, time, gc
addons_dir = os.path.expanduser("~/Library/Application Support/Blender/5.2/scripts/addons")
if addons_dir not in sys.path:
    sys.path.insert(0, addons_dir)
import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.preferences.addon_enable(module="LoopFlow_import_3dm")
from LoopFlow_import_3dm.read3dm import read_3dm

model_path = os.path.expanduser("~/Desktop/Roof Link.3dm")
print(f"\n{'='*70}")
print("A/B TEST: weld_meshes=FALSE (No BMesh Welding)")
print(f"{'='*70}")

gc.collect()
gc.disable()

options = {
    "filepath": model_path, "is_update": False, "import_instances": True,
    "import_curves": False, "import_meshes": True,
    "weld_meshes": False,  # <-- KEY: NO WELDING
    "nurbs_density": 0.5, "subd_subsurf_level": 3,
    "update_materials": False, "import_mode": "SYNC", "link_materials_to": "PREFERENCES",
}

t_start = time.perf_counter()
result = read_3dm(bpy.context, options)
t_total = time.perf_counter() - t_start
print(f"\nTotal: {t_total:.2f}s ({t_total/60:.2f} min)")
print(f"Objects: {len(bpy.data.objects)} | Meshes: {len(bpy.data.meshes)}")
