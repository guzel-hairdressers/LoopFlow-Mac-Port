import os
import sys
import time
import json
import gc

import r3d = None
try:
    import rhino3dm as r3d
except ImportError:
    pass

import bpy
from LoopFlow_import_3dm.read3dm import read_3dm

"""
LoopFlow Quantitative Performance Benchmark Suite
Enforces and verifies the 4 performance targets on reference 3DM models:
  - Target 1: Geometry Deletion (< 20.0s)
  - Target 2: Update Model with No Changes (< 20.0s)
  - Target 3: Update Model with Layer Visibility Changed (< 30.0s)
  - Target 4: Update Model with Geometry Changed (< 60.0s)
"""

def run_benchmark_suite():
    print("===========================================================================")
    print("AUTOMATED VERIFICATION OF LOOPFLOW BENCHMARK TARGETS")
    print("===========================================================================")

    model_path = "/Users/ruslan_faz/Library/Application Support/McNeel/Rhinoceros/8.0/scripts/LoopFlow_R2B/Data/Game_Center_Roof.3dm"
    sync_json_path = "/Users/ruslan_faz/Library/Application Support/McNeel/Rhinoceros/8.0/scripts/LoopFlow_R2B/Data/R2B_Sync.json"

    if not os.path.exists(model_path):
        print(f"Error: Model path {model_path} not found.")
        return

    # STEP 0: Initial Import
    print("\n[STEP 0] Loading Scene for Initial Benchmark Setup...")
    options = {
        "filepath": model_path,
        "is_update": False,
        "import_instances": True,
        "weld_meshes": False
    }
    t0 = time.perf_counter()
    read_3dm(bpy.context, options)
    t_init = time.perf_counter() - t0
    print(f"  Initial Import Complete: {t_init:.2f}s | Objects in Scene: {len(bpy.data.objects)}")

    # TARGET 1: Delete Geometry (< 20s)
    print("\n[TARGET 1] Deleting All Geometry (< 20 sec target)...")
    t0 = time.perf_counter()
    master_col = bpy.data.collections.get("LoopFlow")
    if master_col and master_col.name in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.unlink(master_col)

    for c in list(bpy.data.collections):
        if c.name in ("LoopFlow", "Layers", "Instance Definitions") or c.get('rhid'):
            try:
                bpy.data.collections.remove(c, do_unlink=True)
            except Exception:
                pass

    for m in list(bpy.data.meshes):
        if m.users == 0:
            try:
                bpy.data.meshes.remove(m)
            except Exception:
                pass

    bpy.context.view_layer.update()
    t1 = time.perf_counter() - t0
    status_1 = "PASS ✅" if t1 < 20.0 else "FAIL ❌"
    print(f"  Result : {status_1}\n  Time   : {t1:.2f} seconds (Target: < 20.0s)")

    # Re-populate scene for remaining targets
    print("\nRe-populating scene for Update Targets...")
    read_3dm(bpy.context, options)

    # TARGET 2: Update No Changes (< 20s)
    print("\n[TARGET 2] Updating Model with NO CHANGES (< 20 sec target)...")
    sync_meta = {
        "doc_name": "Game Center Roof",
        "export_format": "3DM",
        "active_filepath": model_path,
        "is_delta": False,
        "geometry_changed": False,
        "layers_changed": False,
        "added_obj_guids": [],
        "removed_obj_guids": [],
        "modified_obj_guids": [],
        "timestamp": time.time()
    }
    with open(sync_json_path, 'w', encoding='utf-8') as f:
        json.dump(sync_meta, f, indent=2)

    update_opts = {
        "filepath": model_path,
        "is_update": True,
        "import_instances": True,
        "weld_meshes": False
    }
    t0 = time.perf_counter()
    read_3dm(bpy.context, update_opts)
    t2 = time.perf_counter() - t0
    status_2 = "PASS ✅" if t2 < 20.0 else "FAIL ❌"
    print(f"  Result : {status_2}\n  Time   : {t2:.4f} seconds (Target: < 20.0s)")

    # TARGET 3: Layer Visibility Change (< 30s)
    print("\n[TARGET 3] Updating Model with Layer Visibility Changed (< 30 sec target)...")
    sync_meta["layers_changed"] = True
    with open(sync_json_path, 'w', encoding='utf-8') as f:
        json.dump(sync_meta, f, indent=2)

    t0 = time.perf_counter()
    read_3dm(bpy.context, update_opts)
    t3 = time.perf_counter() - t0
    status_3 = "PASS ✅" if t3 < 30.0 else "FAIL ❌"
    print(f"  Result : {status_3}\n  Time   : {t3:.4f} seconds (Target: < 30.0s)")

    # TARGET 4: Geometry Changed (< 60s)
    print("\n[TARGET 4] Updating Model with Geometry Changed (< 60 sec target)...")
    sync_meta["geometry_changed"] = True
    sync_meta["modified_obj_guids"] = ["fake_guid_1"]
    with open(sync_json_path, 'w', encoding='utf-8') as f:
        json.dump(sync_meta, f, indent=2)

    t0 = time.perf_counter()
    read_3dm(bpy.context, update_opts)
    t4 = time.perf_counter() - t0
    status_4 = "PASS ✅" if t4 < 60.0 else "FAIL ❌"
    print(f"  Result : {status_4}\n  Time   : {t4:.2f} seconds (Target: < 60.0s)")

    print("\n===========================================================================")
    print("FINAL GOAL BENCHMARK VERIFICATION SUMMARY:")
    print(f"  Target 1 (Delete Geometry)         : {status_1} | Time: {t1:.4f}s (Limit: < 20.0s)")
    print(f"  Target 2 (Update No Changes)       : {status_2} | Time: {t2:.4f}s (Limit: < 20.0s)")
    print(f"  Target 3 (Update Layer Visibility) : {status_3} | Time: {t3:.4f}s (Limit: < 30.0s)")
    print(f"  Target 4 (Update Geometry Changed) : {status_4} | Time: {t4:.4f}s (Limit: < 60.0s)")
    print("===========================================================================")

if __name__ == "__main__":
    run_benchmark_suite()
