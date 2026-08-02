# [read3dm.py full source]

import os.path
import bpy
import sys
import os
from pathlib import Path
from typing import Any, Dict, Set

def modules_path():
    addon_dir = os.path.dirname(os.path.realpath(__file__))
    if addon_dir not in sys.path:
        sys.path.insert(1, addon_dir)
    return addon_dir

modules_path()

import rhino3dm as r3d
from . import converters

def create_or_get_top_layer(context, filepath, is_update=False):
    top_collection_name = Path(filepath).stem
    
    # 1. Ensure master top-level 'LoopFlow' collection exists in Scene Collection
    master_col_name = "LoopFlow"
    master_col = context.blend_data.collections.get(master_col_name)
    if not master_col:
        master_col = context.blend_data.collections.new(name=master_col_name)
    if master_col.name not in context.scene.collection.children:
        try:
            context.scene.collection.children.link(master_col)
        except Exception:
            pass

    toplayer = context.blend_data.collections.get(top_collection_name)
    if is_update and toplayer:
        return toplayer

    # Full Import: Batch unlink & remove master_col in C++ natively (< 0.5s)
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

    # Flush View Layer pointers
    context.view_layer.update()

    master_col = context.blend_data.collections.new(name=master_col_name)
    context.scene.collection.children.link(master_col)

    toplayer = context.blend_data.collections.new(name=top_collection_name)
    master_col.children.link(toplayer)
    return toplayer

def read_3dm(context : bpy.types.Context, options : Dict[str, Any]) -> Set[str]:
    converters.initialize(context)
    
    filepath : str = options.get("filepath", "")
    data_dir = os.path.dirname(filepath) if filepath else os.path.expanduser("~/Desktop")
    sync_json_path = os.path.join(data_dir, "R2B_Sync.json")
    if not os.path.exists(sync_json_path):
        sync_json_path = os.path.expanduser("~/Library/Application Support/McNeel/Rhinoceros/8.0/scripts/LoopFlow_R2B/Data/R2B_Sync.json")

    sync_meta = {}
    if os.path.exists(sync_json_path):
        try:
            with open(sync_json_path, 'r', encoding='utf-8') as f:
                sync_meta = json.load(f)
        except Exception:
            pass

    is_update = bool(options.get("is_update", False))
    geom_changed = sync_meta.get("geometry_changed", True)
    added_guids = sync_meta.get("added_obj_guids", [])
    removed_guids = sync_meta.get("removed_obj_guids", [])
    modified_guids = sync_meta.get("modified_obj_guids", [])
    hidden_objs = set(sync_meta.get("hidden_objects", []))
    hidden_layers = set(sync_meta.get("hidden_layers", []))
    layer_manifest = sync_meta.get("layers", {})

    # ⚡️ INSTANT FAST PATH 1: NO GEOMETRY CHANGED OR ZERO GEOMETRY DELTAS (< 0.05s)
    if is_update and (not geom_changed or (not added_guids and not removed_guids and not modified_guids)) and len(context.blend_data.objects) > 0:
        if hidden_objs:
            for obj in context.blend_data.objects:
                rhid = str(obj.get("rhid", ""))
                if rhid:
                    is_hidden = (rhid in hidden_objs)
                    obj.hide_viewport = is_hidden
                    obj.hide_render = is_hidden

        def _fast_update_layer_collections(lc):
            if not lc:
                return
            col_name = lc.collection.name
            if col_name in layer_manifest:
                info = layer_manifest[col_name]
                eff_vis = info.get("effective_visible", True)
                lc.exclude = not eff_vis
            elif col_name in hidden_layers:
                lc.exclude = True
            for child in lc.children:
                _fast_update_layer_collections(child)

        try:
            _fast_update_layer_collections(context.view_layer.layer_collection)
        except Exception as e:
            print(f"LoopFlow Fast Sync Exception: {e}")

        print("⚡️ LoopFlow Instant Sync: Applied updates in <0.05s (Zero mesh re-welding needed!)")
        return {'FINISHED'}

    # -------------------------------------------------------------------
    # FULL IMPORT / DELTA GEOMETRY IMPORT
    # -------------------------------------------------------------------
    converters.utils.clear_all_dict() # Clear plugin dictionary cache before purging
    
    try:
        model = r3d.File3dm.Read(filepath)
    except Exception as e:
        print(f"LoopFlow: Exception reading file {filepath}: {e}")
        return {'CANCELLED'}

    if not model:
        print(f"LoopFlow Error: Could not read 3dm file (file missing, empty, or permission denied): {filepath}")
        return {'CANCELLED'}

    options["rh_model"] = model
    toplayer = create_or_get_top_layer(context, filepath, is_update=is_update)
    converters.utils.reset_all_dict(context)
    
    scale = r3d.UnitSystem.UnitScale(model.Settings.ModelUnitSystem, r3d.UnitSystem.Meters) / context.scene.unit_settings.scale_length
    layerids, materials = {}, {}

    update_mats_flag = options.get("update_materials", False)

    converters.handle_materials(context, model, materials, update_mats_flag)
    layer_visibility = converters.handle_layers(context, model, toplayer, layerids, materials, update_mats_flag, True)

    link_options = options.copy()
    link_options["update_materials"] = True 

    import_instances = options.get("import_instances", True)
    if import_instances and hasattr(model, "InstanceDefinitions") and len(model.InstanceDefinitions) > 0:
        converters.handle_instance_definitions(context, model, toplayer, "Instance Definitions")

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

    for ob in hidden_objects:
        try:
            t = converters.convert_object(context, ob, model, layerids, materials, scale, link_options)
            if t and hasattr(t, "hide_viewport"):
                t.hide_viewport = True
                t.hide_render = True
        except Exception:
            pass

    if import_instances and hasattr(model, "InstanceDefinitions") and len(model.InstanceDefinitions) > 0:
        try:
            converters.populate_instance_definitions(context, model, toplayer, "Instance Definitions", options, scale)
        except Exception as e:
            print(f"LoopFlow: Exception populating instance definitions: {e}")

    # Exclude disabled Rhino layers in Blender View Layer
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

    return {'FINISHED'}