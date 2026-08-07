"""Quick benchmark on Game Center Roof.3dm"""
import os, sys, time, gc
addons_dir = os.path.expanduser("~/Library/Application Support/Blender/5.2/scripts/addons")
sys.path.insert(0, addons_dir)
import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.preferences.addon_enable(module="LoopFlow_import_3dm")
from LoopFlow_import_3dm.read3dm import read_3dm
import rhino3dm as r3d

model_path = os.path.expanduser("~/Desktop/Game Center Roof.3dm")
file_size_mb = os.path.getsize(model_path) / (1024 * 1024)

# Quick pre-scan to count object types
print(f"Pre-scanning {file_size_mb:.0f}MB model...")
m = r3d.File3dm.Read(model_path)
from collections import Counter
types = Counter()
for ob in m.Objects:
    if ob.Geometry:
        types[ob.Geometry.ObjectType] += 1
print(f"Objects: {len(m.Objects)} | Breps: {types.get(r3d.ObjectType.Brep, 0)} | Meshes: {types.get(r3d.ObjectType.Mesh, 0)} | InstRefs: {types.get(r3d.ObjectType.InstanceReference, 0)} | Curves: {types.get(r3d.ObjectType.Curve, 0)}")
del m

print(f"\nImporting...")
gc.collect(); gc.disable()

options = {
    "filepath": model_path, "is_update": False, "import_instances": True,
    "import_curves": False, "import_meshes": True,
    "weld_meshes": True, "nurbs_density": 0.5, "subd_subsurf_level": 3,
    "update_materials": False, "import_mode": "SYNC", "link_materials_to": "PREFERENCES",
}

t0 = time.perf_counter()
result = read_3dm(bpy.context, options)
dt = time.perf_counter() - t0
print(f"\nTotal: {dt:.2f}s ({dt/60:.2f} min) | Objects: {len(bpy.data.objects)} | Meshes: {len(bpy.data.meshes)}")
