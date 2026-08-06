import os
import sys
import time
import json
import gc
import resource

from pathlib import Path

import bpy
from typing import Dict, Any, Set

from . import converters
import rhino3dm as r3d

def get_process_ram_mb():
    try:
        import psutil
        return psutil.Process().memory_info().rss / (1024.0 * 1024.0)
    except Exception:
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == 'darwin':
            return rss / (1024.0 * 1024.0)
        return rss / 1024.0

class SubOpProfiler:
    def __init__(self, op_name, log_file_path):
        self.op_name = op_name
        self.log_file_path = log_file_path
        self.start_total_time = time.perf_counter()
        self.start_ram = get_process_ram_mb()
        self.last_step_time = self.start_total_time
        self.last_ram = self.start_ram
        self.steps = []

    def step(self, step_name):
        now_time = time.perf_counter()
        now_ram = get_process_ram_mb()
        dt = round(now_time - self.last_step_time, 4)
        ram_delta = round(now_ram - self.last_ram, 2)
        
        step_data = {
            "step": step_name,
            "dt_sec": dt,
            "ram_mb": round(now_ram, 2),
            "ram_delta_mb": ram_delta
        }
        self.steps.append(step_data)
        print(f"  - [{step_name}]: {dt}s | RAM: {round(now_ram, 2)}MB ({ram_delta:+}MB)", flush=True)

        self.last_step_time = now_time
        self.last_ram = now_ram

    def finish(self, info_msg=""):
        total_time = round(time.perf_counter() - self.start_total_time, 4)
        final_ram = round(get_process_ram_mb(), 2)
        total_ram_delta = round(final_ram - self.start_ram, 2)

        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "version": "0.0.52",
            "op": self.op_name,
            "total_sec": total_time,
            "ram_mb": final_ram,
            "ram_delta_mb": total_ram_delta,
            "info": info_msg,
            "steps": self.steps
        }

        log_json_line = json.dumps(entry)
        print(f"LoopFlow Execution Profile: {log_json_line}", flush=True)

        try:
            os.makedirs(os.path.dirname(self.log_file_path), exist_ok=True)
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                f.write(log_json_line + "\n")
        except Exception as e:
            print(f"LoopFlow Profiler Warning: Could not write log file: {e}")

def create_or_get_top_layer(context, filepath, is_update=False):
    master_col_name = "LoopFlow"
    top_collection_name = Path(filepath).stem if filepath else "R2B"

    master_col = context.blend_data.collections.get(master_col_name)
    if not master_col:
        master_col = context.blend_data.collections.new(name=master_col_name)
    if master_col.name not in context.scene.collection.children:
        try:
            context.scene.collection.children.link(master_col)
        except Exception:
            pass

    toplayer = context.blend_data.collections.get(top_collection_name)
    if not toplayer:
        toplayer = context.blend_data.collections.new(name=top_collection_name)
    if toplayer.name not in master_col.children:
        try:
            master_col.children.link(toplayer)
        except Exception:
            pass

    if is_update:
        return toplayer

    # Full Import: Batch unlink & remove old collections in C++ natively (< 0.5s)
    if master_col and master_col.name in context.scene.collection.children:
        try:
            context.scene.collection.children.unlink(master_col)
        except Exception:
            pass

    for c in list(context.blend_data.collections):
        if c.name in (master_col_name, top_collection_name, "Layers", "Instance Definitions") or c.get('rhid') is not None:
            try:
                context.blend_data.collections.remove(c, do_unlink=True)
            except Exception:
                pass

    # Batch purge orphan meshes & curves
    for m in list(context.blend_data.meshes):
        if m.users == 0:
            try:
                context.blend_data.meshes.remove(m)
            except Exception:
                pass

    for cu in list(context.blend_data.curves):
        if cu.users == 0:
            try:
                context.blend_data.curves.remove(cu)
            except Exception:
                pass

    context.view_layer.update()

    master_col = context.blend_data.collections.new(name=master_col_name)
    context.scene.collection.children.link(master_col)

    toplayer = context.blend_data.collections.new(name=top_collection_name)
    master_col.children.link(toplayer)
    return toplayer

def read_3dm(context : bpy.types.Context, options : Dict[str, Any]) -> Set[str]:
    filepath : str = options.get("filepath", "")
    data_dir = os.path.dirname(filepath) if filepath else os.path.expanduser("~/Desktop")
    
    log_file_path = os.path.join(data_dir, "LoopFlow_Performance.log")
    if not os.path.exists(os.path.dirname(log_file_path)):
        log_file_path = os.path.expanduser("~/Library/Application Support/McNeel/Rhinoceros/8.0/scripts/LoopFlow_R2B/Data/LoopFlow_Performance.log")

    is_update = bool(options.get("is_update", False))
    
    # Check if LoopFlow master collection exists and is linked to the current Scene Collection
    master_col_name = "LoopFlow"
    master_col = context.blend_data.collections.get(master_col_name)
    top_collection_name = Path(filepath).stem if filepath else "R2B"
    toplayer = context.blend_data.collections.get(top_collection_name)

    is_imported = (master_col is not None) and (master_col.name in context.scene.collection.children) and (toplayer is not None)

    # AUTO-DETECT FIRST RUN IN BLENDER SESSION (IF LOOPFLOW COLLECTION IS MISSING)
    if is_update and not is_imported and options.get("import_mode") != "APPEND":
        is_update = False  # Automatically perform initial full import into LoopFlow collection!
        op_title = "Update Model (Initial Session Full Import)"
    elif is_update and options.get("import_mode") == "APPEND":
        op_title = "Import Model (Append Mode)"
    elif is_update:
        op_title = "Update Model (In-Memory Fast Sync)"
    else:
        op_title = "Import Model (Full Scene Re-read)"
    
    profiler = SubOpProfiler(op_title, log_file_path)

    # 1. INITIALIZE & READ SYNC METADATA
    converters.initialize(context)
    
    sync_candidates = [
        os.path.join(data_dir, "R2B_Sync.json"),
        os.path.expanduser("~/Library/Application Support/McNeel/Rhinoceros/8.0/scripts/LoopFlow_R2B/Data/R2B_Sync.json")
    ]

    sync_json_path = None
    latest_mtime = -1
    for cand in sync_candidates:
        if os.path.exists(cand):
            try:
                mtime = os.path.getmtime(cand)
                if mtime > latest_mtime:
                    latest_mtime = mtime
                    sync_json_path = cand
            except Exception:
                pass

    sync_meta = {}
    if sync_json_path and os.path.exists(sync_json_path):
        try:
            with open(sync_json_path, 'r', encoding='utf-8') as f:
                sync_meta = json.load(f)
        except Exception:
            pass

    profiler.step("1. Read Sync Metadata (R2B_Sync.json)")

    geom_changed = sync_meta.get("geometry_changed", True)
    added_guids = sync_meta.get("added_obj_guids", [])
    removed_guids = sync_meta.get("removed_obj_guids", [])
    modified_guids = sync_meta.get("modified_obj_guids", [])
    hidden_objs = set(sync_meta.get("hidden_objects", []))
    hidden_layers = set(sync_meta.get("hidden_layers", []))
    layer_manifest = sync_meta.get("layers", {})

    has_geom_delta = bool(added_guids or removed_guids or modified_guids)

    # INSTANT FAST PATH 1: NO GEOMETRY DELTAS OR geom_changed IS FALSE (< 0.05s)
    if is_update and (geom_changed is False or not has_geom_delta) and is_imported:
        if hidden_objs:
            for obj in context.blend_data.objects:
                rhid = str(obj.get("rhid", ""))
                if rhid:
                    is_hidden = (rhid in hidden_objs)
                    obj.hide_viewport = is_hidden
                    obj.hide_render = is_hidden
            profiler.step("2. Update Viewport and Render Hiding for Objects")

        def _fast_update_layer_collections(lc):
            if not lc:
                return
            col = lc.collection
            col_name = col.name
            col_rhid = str(col.get("rhid", ""))

            found_info = None
            if col_rhid and col_rhid in layer_manifest:
                found_info = layer_manifest[col_rhid]
            elif col_name in layer_manifest:
                found_info = layer_manifest[col_name]
            else:
                rh_full = col.get("rhino_full_path", "")
                rh_name = col.get("rhino_layer_name", "")
                if rh_full and rh_full in layer_manifest:
                    found_info = layer_manifest[rh_full]
                elif rh_name and rh_name in layer_manifest:
                    found_info = layer_manifest[rh_name]
                else:
                    for full_p, info in layer_manifest.items():
                        leaf = full_p.split("::")[-1]
                        if leaf == col_name or full_p == col_name:
                            found_info = info
                            break

            if found_info:
                eff_vis = found_info.get("effective_visible", True)
                lc.exclude = not eff_vis

            for child in lc.children:
                _fast_update_layer_collections(child)

        try:
            _fast_update_layer_collections(context.view_layer.layer_collection)
            context.view_layer.update()
        except Exception as e:
            print(f"LoopFlow Fast Sync Exception: {e}")

        profiler.step("3. Update View Layer Collection Exclude States")
        profiler.finish("Fast Path Sync Executed (<0.06s)")
        return {'FINISHED'}

    # FAST DELTA GEOMETRY UPDATE PATH (< 0.5s)
    if is_update and is_imported and has_geom_delta:
        converters.utils.clear_all_dict()
        profiler.step("2. Reset Plugin Dictionary Cache")

        try:
            model = r3d.File3dm.Read(filepath)
        except Exception:
            model = None

        if model:
            profiler.step(f"3. Read 3DM File from Disk ({os.path.getsize(filepath) / (1024*1024):.1f} MB)")
            options["rh_model"] = model
            toplayer = create_or_get_top_layer(context, filepath, is_update=True)
            profiler.step("4. Access Top-Level Scene Collection")

            scale = r3d.UnitSystem.UnitScale(model.Settings.ModelUnitSystem, r3d.UnitSystem.Meters) / context.scene.unit_settings.scale_length
            layerids, materials = {}, {}
            update_mats_flag = options.get("update_materials", False)

            converters.handle_materials(context, model, materials, update_mats_flag)
            profiler.step("5. Material Conversion and Binding")

            layer_visibility = converters.handle_layers(context, model, toplayer, layerids, materials, update_mats_flag, True)
            profiler.step("6. Layer Hierarchy Construction")

            link_options = options.copy()
            link_options["update_materials"] = True

            # 1. Handle Removed Objects
            if removed_guids:
                rem_set = set(removed_guids)
                for obj in list(context.blend_data.objects):
                    rhid = str(obj.get("rhid", ""))
                    if rhid in rem_set:
                        try:
                            context.blend_data.objects.remove(obj, do_unlink=True)
                        except Exception:
                            pass
                profiler.step(f"7. Remove Deleted Delta Objects ({len(removed_guids)} items)")

            # 2. Handle Modified & Added Objects
            mod_add_set = set(added_guids + modified_guids)
            if mod_add_set:
                for obj in list(context.blend_data.objects):
                    rhid = str(obj.get("rhid", ""))
                    if rhid in set(modified_guids):
                        try:
                            context.blend_data.objects.remove(obj, do_unlink=True)
                        except Exception:
                            pass

                converted_count = 0
                for ob in model.Objects:
                    rhid = str(ob.Attributes.Id)
                    if rhid in mod_add_set:
                        converters.convert_object(context, ob, model, layerids, materials, scale, link_options)
                        converted_count += 1
                profiler.step(f"8. Convert Delta Geometry ({converted_count} items)")

            def _fast_update_layer_collections(lc):
                if not lc:
                    return
                col = lc.collection
                col_name = col.name
                found_info = None
                if col_name in layer_manifest:
                    found_info = layer_manifest[col_name]
                else:
                    rh_full = col.get("rhino_full_path", "")
                    rh_name = col.get("rhino_layer_name", "")
                    if rh_full and rh_full in layer_manifest:
                        found_info = layer_manifest[rh_full]
                    elif rh_name and rh_name in layer_manifest:
                        found_info = layer_manifest[rh_name]
                    else:
                        for full_p, info in layer_manifest.items():
                            leaf = full_p.split("::")[-1]
                            if leaf == col_name or full_p == col_name:
                                found_info = info
                                break
                if found_info:
                    eff_vis = found_info.get("effective_visible", True)
                    lc.exclude = not eff_vis
                for child in lc.children:
                    _fast_update_layer_collections(child)

            try:
                _fast_update_layer_collections(context.view_layer.layer_collection)
                context.view_layer.update()
            except Exception:
                pass

            profiler.step("9. Update View Layer Collection Exclude States")
            profiler.finish(f"Delta Geometry Sync Complete ({len(mod_add_set)} modified/added, {len(removed_guids)} removed)")
            return {'FINISHED'}

    # -------------------------------------------------------------------
    # FULL IMPORT / DELTA GEOMETRY IMPORT
    # -------------------------------------------------------------------
    converters.utils.clear_all_dict()
    profiler.step("2. Reset Plugin Dictionary Cache")
    
    try:
        model = r3d.File3dm.Read(filepath)
    except Exception as e:
        print(f"LoopFlow: Exception reading file {filepath}: {e}")
        return {'CANCELLED'}

    if not model:
        print(f"LoopFlow Error: Could not read 3dm file: {filepath}")
        return {'CANCELLED'}

    profiler.step(f"3. Read 3DM File from Disk ({os.path.getsize(filepath) / (1024*1024):.1f} MB)")

    options["rh_model"] = model
    toplayer = create_or_get_top_layer(context, filepath, is_update=is_update)
    profiler.step("4. Create and Teardown Scene Collections")

    converters.utils.reset_all_dict(context)
    profiler.step("5. Re-initialize Cache Dictionaries")
    
    scale = r3d.UnitSystem.UnitScale(model.Settings.ModelUnitSystem, r3d.UnitSystem.Meters) / context.scene.unit_settings.scale_length
    layerids, materials = {}, {}

    update_mats_flag = options.get("update_materials", False)

    converters.handle_materials(context, model, materials, update_mats_flag)
    profiler.step("6. Material Conversion and Binding")

    layer_visibility = converters.handle_layers(context, model, toplayer, layerids, materials, update_mats_flag, True)
    profiler.step("7. Layer Hierarchy Construction")

    link_options = options.copy()
    link_options["update_materials"] = True 

    import_instances = options.get("import_instances", True)
    if import_instances and hasattr(model, "InstanceDefinitions") and len(model.InstanceDefinitions) > 0:
        converters.handle_instance_definitions(context, model, toplayer, "Instance Definitions")
        profiler.step("8. Instance Definitions Setup")

    import_curves = options.get("import_curves", True)
    hidden_objects = []

    for ob in model.Objects:
        og = ob.Geometry
        if not og:
            continue

        if not import_curves and og.ObjectType == r3d.ObjectType.Curve:
            continue

        try:
            if not ob.Attributes.Visible:
                hidden_objects.append(ob)
                continue
        except Exception:
            pass

        t = converters.convert_object(context, ob, model, layerids, materials, scale, link_options)

    profiler.step(f"9. Convert Visible Objects ({len(model.Objects)} items)")

    for ob in hidden_objects:
        try:
            t = converters.convert_object(context, ob, model, layerids, materials, scale, link_options)
            if t and hasattr(t, "hide_viewport"):
                t.hide_viewport = True
                t.hide_render = True
        except Exception:
            pass

    profiler.step(f"10. Convert Hidden Objects ({len(hidden_objects)} items)")

    if import_instances and hasattr(model, "InstanceDefinitions") and len(model.InstanceDefinitions) > 0:
        try:
            converters.populate_instance_definitions(context, model, toplayer, "Instance Definitions", options, scale)
            profiler.step("11. Populate Instance Objects")
        except Exception as e:
            print(f"LoopFlow: Exception populating instance definitions: {e}")

    def _apply_layer_visibilities(layer_col, layer_visibility):
        if not layer_col:
            return
        for child in layer_col.children:
            c_name = child.collection.name
            if c_name in layer_visibility:
                info = layer_visibility[c_name]
                eff_vis = info.get("effective_visible", True)
                child.exclude = not eff_vis
            _apply_layer_visibilities(child, layer_visibility)

    try:
        vl = context.view_layer
        _apply_layer_visibilities(vl.layer_collection, layer_visibility)
    except Exception as e:
        print(f"LoopFlow: Exception applying layer visibilities: {e}")

    profiler.step("12. Apply Layer Visibilities to View Layer")
    profiler.finish(f"Full Model Import Complete ({len(context.blend_data.objects)} total objects in scene)")

    return {'FINISHED'}