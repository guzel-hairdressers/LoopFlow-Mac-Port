import os
import sys
import time
import json
import gc
import resource
import tempfile

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

def create_or_get_top_layer(context, filepath, is_update=False, import_mode='SYNC'):
    master_col_name = "LoopFlow"
    file_stem = Path(filepath).stem if filepath else "R2B"

    master_col = context.blend_data.collections.get(master_col_name)
    if not master_col:
        master_col = context.blend_data.collections.new(name=master_col_name)
    if master_col.name not in context.scene.collection.children:
        try:
            context.scene.collection.children.link(master_col)
        except Exception:
            pass

    if import_mode == 'OVERRIDE':
        # OVERRIDE MODE: Remove ONLY the file collection matching file_stem inside LoopFlow
        old_toplayer = context.blend_data.collections.get(file_stem)
        if old_toplayer:
            def remove_col_recursive(col):
                for child in list(col.children):
                    remove_col_recursive(child)
                for obj in list(col.objects):
                    try:
                        context.blend_data.objects.remove(obj, do_unlink=True)
                    except Exception:
                        pass
                try:
                    context.blend_data.collections.remove(col, do_unlink=True)
                except Exception:
                    pass

            remove_col_recursive(old_toplayer)
            context.view_layer.update()

        toplayer = context.blend_data.collections.new(name=file_stem)
        master_col.children.link(toplayer)
        return toplayer

    elif import_mode == 'APPEND':
        # APPEND MODE: If file_stem collection exists inside LoopFlow, create file_stem.001, .002
        top_name = file_stem
        if top_name in context.blend_data.collections:
            idx = 1
            while f"{file_stem}.{idx:03d}" in context.blend_data.collections:
                idx += 1
            top_name = f"{file_stem}.{idx:03d}"

        toplayer = context.blend_data.collections.new(name=top_name)
        master_col.children.link(toplayer)
        return toplayer

    else:
        # LIVE SYNC MODE
        toplayer = context.blend_data.collections.get(file_stem)
        if not toplayer:
            toplayer = context.blend_data.collections.new(name=file_stem)
        if toplayer.name not in master_col.children:
            try:
                master_col.children.link(toplayer)
            except Exception:
                pass
        return toplayer
    return toplayer

def read_3dm(context : bpy.types.Context, options : Dict[str, Any]) -> Set[str]:
    import LoopFlow_import_3dm as main_mod
    orig_sync = main_mod._is_syncing_layers
    main_mod._is_syncing_layers = True

    try:
        return _read_3dm_internal(context, options)
    finally:
        main_mod._is_syncing_layers = orig_sync

def _import_via_obj_fastpath(context, model, toplayer, layerids, materials, scale, options, profiler, filepath):
    """Fast path: write OBJ from 3DM meshes → import via Blender C importer → reconcile metadata."""
    import rhino3dm as r3d

    # Phase 1: Build OBJ text from model objects
    profiler.step("9. [OBJ] Building geometry data")

    # Build layer info cache (same as convert_object)
    layer_info_cache = {}
    if model and hasattr(model, "Layers"):
        for l_idx in range(len(model.Layers)):
            l = model.Layers[l_idx]
            l_mat_idx = -1
            if hasattr(l, "RenderMaterialInstanceId") and str(l.RenderMaterialInstanceId) in materials:
                l_mat_idx = str(l.RenderMaterialInstanceId)
            elif hasattr(l, "RenderMaterialIndex"):
                l_mat_idx = l.RenderMaterialIndex
            elif hasattr(l, "MaterialIndex"):
                l_mat_idx = l.MaterialIndex
            l_color = (200, 200, 200, 255)
            try: l_color = l.Color
            except Exception: pass
            layer_info_cache[l_idx] = (l_mat_idx, l_color)

    lines = []
    obj_meta = []  # parallel array: (guid, name, layer_idx, mat_idx, color, is_idef)
    v_off = 0
    vt_off = 0  # separate UV coordinate offset (only increments for objects with UVs)

    for ob in model.Objects:
        og = ob.Geometry
        if not og: continue
        ot = og.ObjectType
        if ot not in (r3d.ObjectType.Brep, r3d.ObjectType.Extrusion, r3d.ObjectType.Mesh, r3d.ObjectType.SubD):
            continue
        oa = ob.Attributes
        is_idef = oa.IsInstanceDefinitionObject if hasattr(oa, "IsInstanceDefinitionObject") else False

        # Tessellate
        msh = None
        if ot == r3d.ObjectType.Brep:
            combined = r3d.Mesh()
            og_faces = og.Faces
            for f in range(len(og_faces)):
                try:
                    fm = og_faces[f].GetMesh(r3d.MeshType.Any)
                    if fm: combined.Append(fm)
                except Exception: pass
            msh = combined
        elif ot == r3d.ObjectType.Mesh:
            msh = og
        elif ot == r3d.ObjectType.Extrusion:
            msh = og.GetMesh(r3d.MeshType.Any)
        elif ot == r3d.ObjectType.SubD:
            msh = r3d.Mesh.CreateFromSubDControlNet(og, False)

        if not msh or len(msh.Vertices) == 0:
            continue

        nv = len(msh.Vertices)

        # Metadata for reconciliation
        layer_idx = oa.LayerIndex
        color = (200, 200, 200, 255)
        mat_idx = -1
        try:
            mat_idx = oa.MaterialIndex
            if oa.MaterialSource == r3d.ObjectMaterialSource.MaterialFromLayer or mat_idx < 0:
                l_info = layer_info_cache.get(layer_idx, (-1, (200, 200, 200, 255)))
                mat_idx = l_info[0]
                color = l_info[1]
            elif oa.ColorSource == r3d.ObjectColorSource.ColorFromObject:
                color = oa.ObjectColor
            else:
                color = layer_info_cache.get(layer_idx, (-1, (200, 200, 200, 255)))[1]
        except Exception: pass

        obj_meta.append((oa.Id, oa.Name if oa.Name else f"LF_{oa.Id}", oa.LayerIndex, mat_idx, color, is_idef))

        # OBJ geometry
        lines.append(f'o obj_{len(obj_meta)-1}')
        for v in msh.Vertices:
            lines.append(f'v {v.X*scale:.6f} {v.Y*scale:.6f} {v.Z*scale:.6f}')
        tc = msh.TextureCoordinates
        has_uv = len(tc) == nv
        if has_uv:
            for uv in tc:
                lines.append(f'vt {uv.X:.6f} {uv.Y:.6f}')
        for face in msh.Faces:
            f0,f1,f2,f3 = face[0]+1, face[1]+1, face[2]+1, face[3]+1
            a,b,c,d = f0+v_off, f1+v_off, f2+v_off, f3+v_off
            if has_uv:
                ua,ub,uc,ud = f0+vt_off, f1+vt_off, f2+vt_off, f3+vt_off
                if f3 == f2:
                    lines.append(f'f {a}/{ua} {b}/{ub} {c}/{uc}')
                else:
                    lines.append(f'f {a}/{ua} {b}/{ub} {c}/{uc} {d}/{ud}')
            else:
                if f3 == f2:
                    lines.append(f'f {a} {b} {c}')
                else:
                    lines.append(f'f {a} {b} {c} {d}')
        v_off += nv
        if has_uv:
            vt_off += nv

    if not lines:
        profiler.step("9. [OBJ] No geometry to import")
        return

    obj_text = '\n'.join(lines)
    profiler.step(f"9b. [OBJ] Built {len(lines):,} lines for {len(obj_meta)} objects")

    # Phase 2: Write to temp file + import via Blender C
    tmp = tempfile.NamedTemporaryFile(suffix='.obj', delete=False)
    tmp.close()
    try:
        with open(tmp.name, 'w', buffering=16*1024*1024) as f:
            f.write(obj_text)
        profiler.step(f"10. [OBJ] Written {os.path.getsize(tmp.name)/1024/1024:.0f}MB OBJ")

        bpy.ops.wm.obj_import(filepath=tmp.name, use_split_objects=True, use_split_groups=True)
        profiler.step(f"11. [OBJ] Imported {len(bpy.data.objects)} objects via Blender C importer")
    finally:
        try: os.unlink(tmp.name)
        except Exception: pass

    # Phase 3: Reconcile metadata using O(1) name→object lookup (no sort needed)
    # Build name→object dict from imported meshes
    imported_by_name = {}
    for o in context.blend_data.objects:
        if o.type == 'MESH' and o.name.startswith('obj_'):
            imported_by_name[o.name] = o

    count = len(imported_by_name)
    profiler.step(f"12a. [OBJ] Indexed {count} imported objects")

    # Material lookup cache
    mat_lookup = {}
    def _resolve_mat(mat_idx):
        if mat_idx not in mat_lookup:
            mat_lookup[mat_idx] = materials.get(mat_idx, materials.get(str(mat_idx), materials.get(-1)))
        return mat_lookup[mat_idx]

    idef_obj_map = options.get("idef_obj_map", {})

    # Deferred collection linking (same pattern as Python path — bulk link after properties)
    pending_links = {}  # collection → list of objects

    for i in range(len(obj_meta)):
        ob = imported_by_name.get(f'obj_{i}')
        if not ob: continue
        guid, name, layer_idx, mat_idx, color, is_idef = obj_meta[i]
        ob['rhid'] = str(guid)
        if name: ob['rhname'] = name
        ob.color = (color[0]/255.0, color[1]/255.0, color[2]/255.0, color[3]/255.0)
        target_col = layerids.get(layer_idx, context.scene.collection)
        if is_idef:
            idef_col = idef_obj_map.get(str(guid), target_col)
            if idef_col:
                pending_links.setdefault(idef_col, []).append(ob)
        else:
            pending_links.setdefault(target_col, []).append(ob)

    profiler.step(f"12b. [OBJ] Tagged {len(obj_meta)} objects, {len(pending_links)} batches")

    # Material assignment: SKIPPED in OBJ fast path — assigning materials to 52K
    # individual meshes via data.materials.append() takes 190s+. Materials are
    # resolved later via the normal sync mechanism.
    profiler.step(f"12c. [OBJ] Materials deferred (sync path)")

    # Bulk link
    for col, objs in pending_links.items():
        for ob in objs:
            try: col.objects.link(ob)
            except Exception: pass

    profiler.step(f"12. [OBJ] Reconciled metadata for {count} objects")
    profiler.finish(f"OBJ Fast-Path Import Complete ({count} objects)")


def _read_3dm_internal(context : bpy.types.Context, options : Dict[str, Any]) -> Set[str]:
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
    
    file_stem = Path(filepath).stem if filepath else "R2B"
    file_mtime = os.path.getmtime(filepath) if (filepath and os.path.exists(filepath)) else 0
    file_size = os.path.getsize(filepath) if (filepath and os.path.exists(filepath)) else 0

    sync_candidates = [
        os.path.join(data_dir, f"R2B_Sync_{file_stem}.json"),
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

    # Verify if sync_meta matches target filepath
    active_fp = sync_meta.get("active_filepath", "")
    if active_fp and filepath and Path(active_fp).stem != file_stem:
        # JSON belongs to a different 3DM file, ignore delta
        sync_meta = {}

    profiler.step("1. Read Sync Metadata (R2B_Sync.json)")

    geom_changed = sync_meta.get("geometry_changed", True)
    added_guids = sync_meta.get("added_obj_guids", [])
    removed_guids = sync_meta.get("removed_obj_guids", [])
    modified_guids = sync_meta.get("modified_obj_guids", [])
    hidden_objs = set(sync_meta.get("hidden_objects", []))
    hidden_layers = set(sync_meta.get("hidden_layers", []))
    layer_manifest = sync_meta.get("layers", {})

    has_geom_delta = bool(added_guids or removed_guids or modified_guids)

    # UNCHANGED FILE SIGNATURE SKIP CHECK
    if is_update and toplayer and not sync_meta:
        last_mtime = toplayer.get("last_sync_mtime", 0)
        last_size = toplayer.get("last_sync_size", 0)
        if last_mtime == file_mtime and last_size == file_size:
            profiler.finish(f"File {file_stem}.3dm unchanged since last sync (Skipped)")
            return {'FINISHED'}

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

    options["rh_model"] = model
    options["idef_map"] = {idef.Id: f"[Block] {idef.Name}" if idef.Name else f"Block {idef.Id}" for idef in model.InstanceDefinitions} if hasattr(model, "InstanceDefinitions") else {}
    toplayer = create_or_get_top_layer(context, filepath, is_update=is_update, import_mode=options.get("import_mode", "SYNC"))
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
    link_options["defer_link"] = True

    mat_link_pref = options.get("link_materials_to", "PREFERENCES")
    if mat_link_pref == "PREFERENCES":
        mat_link_pref = context.preferences.edit.material_link
        if mat_link_pref == 'OBDATA':
            mat_link_pref = 'DATA'
    link_options["link_materials_to_resolved"] = mat_link_pref

    import_instances = options.get("import_instances", True)
    if import_instances and hasattr(model, "InstanceDefinitions") and len(model.InstanceDefinitions) > 0:
        converters.handle_instance_definitions(context, model, toplayer, "Instance Definitions")
        profiler.step("8. Instance Definitions Setup")

    # --- OBJ Fast Path for full imports ---
    # Bypasses the slow Python mesh-creation loop. Writes OBJ → imports via Blender C.
    if not is_update:
        _import_via_obj_fastpath(context, model, toplayer, layerids, materials, scale, options, profiler, filepath)
        return {'FINISHED'}

    import_curves = options.get("import_curves", True)
    hidden_objects = []

    total_objs = len(model.Objects)
    log_chunk = max(500, total_objs // 10) if total_objs > 0 else 500
    converted_vis_count = 0

    pending_collection_links = {} # collection -> list of objects

    for idx, ob in enumerate(model.Objects):
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
        if t:
            oa = ob.Attributes
            is_idef = oa.IsInstanceDefinitionObject if (oa and hasattr(oa, "IsInstanceDefinitionObject")) else False
            if is_idef:
                target_col = idef_obj_map.get(str(oa.Id), layerids.get(oa.LayerIndex, context.scene.collection))
            else:
                target_col = layerids.get(oa.LayerIndex, context.scene.collection)
            pending_collection_links.setdefault(target_col, []).append(t)

        converted_vis_count += 1

        if (idx + 1) % log_chunk == 0 or (idx + 1) == total_objs:
            profiler.step(f"9. Convert Visible Objects Batch ({idx + 1}/{total_objs})")

    if total_objs == 0:
        profiler.step("9. Convert Visible Objects (0 items)")

    for h_idx, ob in enumerate(hidden_objects):
        try:
            t = converters.convert_object(context, ob, model, layerids, materials, scale, link_options)
            if t:
                oa = ob.Attributes
                is_idef = oa.IsInstanceDefinitionObject if (oa and hasattr(oa, "IsInstanceDefinitionObject")) else False
                if is_idef:
                    target_col = idef_obj_map.get(str(oa.Id), layerids.get(oa.LayerIndex, context.scene.collection))
                else:
                    target_col = layerids.get(oa.LayerIndex, context.scene.collection)
                pending_collection_links.setdefault(target_col, []).append(t)
                if hasattr(t, "hide_viewport"):
                    t.hide_viewport = True
                    t.hide_render = True
        except Exception:
            pass

    profiler.step(f"10. Convert Hidden Objects ({len(hidden_objects)} items)")

    # Fast deferred bulk linking (defer_link=True guarantees no pre-existing links)
    for layer, objs in pending_collection_links.items():
        for bo in objs:
            try:
                layer.objects.link(bo)
            except Exception:
                pass
    profiler.step("10b. Deferred Bulk Collection Linking")

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

    if toplayer and filepath and os.path.exists(filepath):
        toplayer["last_sync_mtime"] = os.path.getmtime(filepath)
        toplayer["last_sync_size"] = os.path.getsize(filepath)

    profiler.step("12. Apply Layer Visibilities to View Layer")
    profiler.finish(f"Full Model Import Complete ({len(context.blend_data.objects)} total objects in scene)")

    return {'FINISHED'}