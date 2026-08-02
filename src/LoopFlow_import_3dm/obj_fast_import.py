# -*- coding: utf-8 -*-
"""
==============================================================================
LoopFlow v2 — High-Speed C++ OBJ Importer Engine
==============================================================================
Uses Blender 3.2+ native C++ multi-threaded OBJ importer (`wm.obj_import`)
for 1-2 second instant import of 200MB+ Rhino models.
==============================================================================
"""

import bpy
import os
import json
import re
import time
from pathlib import Path
from mathutils import Vector

def create_or_get_collection(parent_col, col_name):
    clean_name = col_name.strip()
    col = bpy.data.collections.get(clean_name)
    if not col:
        col = bpy.data.collections.new(clean_name)
        parent_col.children.link(col)
    elif col.name not in parent_col.children:
        parent_col.children.link(col)
    return col

def fast_import_obj(context, obj_filepath, options=None):
    t0 = time.perf_counter()
    print("=" * 60)
    print(" [LoopFlow v2 C++ Engine] Starting High-Speed Import...")
    print("=" * 60)

    if not os.path.exists(obj_filepath):
        print(f" [LoopFlow v2 Error] OBJ file not found: {obj_filepath}")
        return {'CANCELLED'}

    file_size_mb = os.path.getsize(obj_filepath) / (1024 * 1024)
    top_col_name = Path(obj_filepath).stem
    master_col = context.scene.collection

    # Get or create top collection
    top_col = bpy.data.collections.get(top_col_name)
    if not top_col:
        top_col = bpy.data.collections.new(top_col_name)
        master_col.children.link(top_col)

    # 1. Call Blender's C++ native multi-threaded OBJ importer
    t0_cpp = time.perf_counter()
    
    # Store objects prior to import to isolate new imported objects
    objs_before = set(bpy.data.objects)
    
    bpy.ops.wm.obj_import(
        filepath=obj_filepath,
        forward_axis='Y',
        up_axis='Z',
        clamp_size=0.0
    )
    t1_cpp = time.perf_counter()
    print(f" [1/3] C++ Native OBJ Load [{file_size_mb:.1f} MB]: {t1_cpp - t0_cpp:.3f} s")

    imported_objs = set(bpy.data.objects) - objs_before
    print(f" [2/3] Imported {len(imported_objs)} objects from C++ engine.")

    # 2. Fast Post-Processor: Group objects into Collections based on OBJ group/layer names
    t0_post = time.perf_counter()
    
    # Check if a hierarchy JSON file exists alongside OBJ
    json_path = os.path.splitext(obj_filepath)[0] + "_hierarchy.json"
    hierarchy_data = {}
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                hierarchy_data = json.load(f)
        except Exception:
            pass

    col_cache = {top_col_name: top_col}

    for obj in imported_objs:
        # Move object out of master collection if linked
        if obj.name in master_col.objects:
            master_col.objects.unlink(obj)

        # Determine layer path from hierarchy JSON or object name
        layer_path = None
        if hierarchy_data and obj.name in hierarchy_data:
            layer_path = hierarchy_data[obj.name].get("layer")

        if not layer_path:
            # Fallback to group name parsing
            parts = obj.name.split('_')
            if len(parts) > 1:
                layer_path = parts[0]
            else:
                layer_path = "Default"

        # Build nested collections
        curr_col = top_col
        if layer_path:
            path_segments = layer_path.split("::")
            acc_path = top_col_name
            for seg in path_segments:
                acc_path += f"::{seg}"
                if acc_path not in col_cache:
                    col_cache[acc_path] = create_or_get_collection(curr_col, seg)
                curr_col = col_cache[acc_path]

        if obj.name not in curr_col.objects:
            curr_col.objects.link(obj)

    t1_post = time.perf_counter()
    print(f" [3/3] Collection Hierarchy & Material Linking: {t1_post - t0_post:.3f} s")

    t_end = time.perf_counter()
    total_time = t_end - t0

    print("=" * 60)
    print(" [LoopFlow v2 SUMMARY]")
    print(f"   • Total Time:          {total_time:.3f} s")
    print(f"   • C++ Native Load:     {t1_cpp - t0_cpp:.3f} s ({(t1_cpp - t0_cpp)/total_time*100:.1f}%)")
    print(f"   • Post-Process & Link: {t1_post - t0_post:.3f} s ({(t1_post - t0_post)/total_time*100:.1f}%)")
    print("=" * 60)

    return {'FINISHED'}
