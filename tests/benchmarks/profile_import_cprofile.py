"""cProfile the import to find real hotspots"""
import os, sys, time, cProfile, pstats, io
addons_dir = os.path.expanduser("~/Library/Application Support/Blender/5.2/scripts/addons")
sys.path.insert(0, addons_dir)
import bpy

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.preferences.addon_enable(module="LoopFlow_import_3dm")

from LoopFlow_import_3dm.read3dm import read_3dm

model_path = os.path.expanduser("~/Desktop/Roof Link.3dm")
# Only import first 10000 objects for quick profiling
# We monkey-patch the model to have fewer objects

import LoopFlow_import_3dm.read3dm as r3dm_mod
original_internal = r3dm_mod._read_3dm_internal

def profiled_read(options):
    # Load full model
    import rhino3dm as r3d
    model = r3d.File3dm.Read(model_path)
    # Truncate to first 10000 objects
    original_objects = model.Objects
    # We can't truncate easily, so just profile the original
    return original_internal(bpy.context, options)

r3dm_mod._read_3dm_internal = profiled_read

options = {
    "filepath": model_path, "is_update": False, "import_instances": True,
    "import_curves": False, "import_meshes": True,
    "weld_meshes": True, "nurbs_density": 0.5, "subd_subsurf_level": 3,
    "update_materials": False, "import_mode": "SYNC", "link_materials_to": "PREFERENCES",
}

# Profile just the import
print("Profiling...")
profiler = cProfile.Profile()
profiler.enable()
t0 = time.perf_counter()
result = read_3dm(bpy.context, options)
dt = time.perf_counter() - t0
profiler.disable()
print(f"Import took {dt:.2f}s")

# Print top 30 functions by cumulative time
s = io.StringIO()
ps = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
ps.print_stats(30)
print(s.getvalue())

# Also by tottime
s2 = io.StringIO()
ps2 = pstats.Stats(profiler, stream=s2).sort_stats('tottime')
ps2.print_stats(30)
print(s2.getvalue())
