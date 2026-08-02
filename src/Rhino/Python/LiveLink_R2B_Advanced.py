# -*- coding: utf-8 -*-
"""
=====================================================
LiveLink Rhino to Blender (Advanced Link - Left Panel Design)
=====================================================
Script Name        : LiveLink_R2B_Advanced
Version            : v6.0
Date               : 2026-08-01
Author             : LoopFlow Team
Environment        : Rhino 8 / CPython 3.9

[Description]
Advanced Export Link using Rhino's Left Options Panel / Command Bar:
- Options displayed in Left Command Panel (Rhino.Input.Custom.GetOption)
- ExportCurves=Yes/No toggle
- ExportAllLayers=Yes/No toggle
- SelectLayer option
- Click 'Done' or press Enter to Export!
"""
import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from LiveLink_R2B__Config import load_r2b_config, save_r2b_config, save_r2b_sync_metadata, DATA_DIR

def AdvancedLinkExport():
    t0 = time.time()
    orig_path = sc.doc.Path
    if orig_path:
        doc_basename = os.path.splitext(os.path.basename(orig_path))[0]
    else:
        doc_basename = "R2B_Model"

    clean_doc_name = "".join([c if (c.isalnum() or c in ('-', '_')) else '_' for c in doc_basename])
    if not clean_doc_name:
        clean_doc_name = "R2B_Model"

    cfg = load_r2b_config()

    all_layers = [l.FullPath for l in sc.doc.Layers if not l.IsDeleted]
    if not all_layers:
        rs.MessageBox("No layers found in document!")
        return

    last_layer = cfg.get("LastModelLayer", "")
    last_curves = cfg.get("ExportCurves", "False")
    last_export_all = cfg.get("ExportAllLayers", "True")

    ALL_OPTION = "[Export All Layers]"
    current_target_layer = last_layer if last_layer in all_layers else ALL_OPTION

    # --- RHINO NATIVE LEFT COMMAND PANEL DESIGN ---
    go = Rhino.Input.Custom.GetOption()
    go.SetCommandPrompt("LiveLink")
    go.AcceptString(False) # Hides string input box
    
    # 1. ExportCurves Option Toggle (Yes/No)
    opt_curves = Rhino.Input.Custom.OptionToggle(last_curves == "True", "No", "Yes")
    go.AddOptionToggle("ExportCurves", opt_curves)
    
    # 2. ExportAllLayers Option Toggle (Yes/No)
    opt_all = Rhino.Input.Custom.OptionToggle(last_export_all == "True", "No", "Yes")
    go.AddOptionToggle("ExportAllLayers", opt_all)
    
    # 3. SelectLayer Option
    opt_layer_idx = go.AddOption("SelectLayer")
    
    # Accept Enter / Space / Done button in left panel
    go.AcceptNothing(True)

    export_curves = False
    export_all_layers = True
    selected_target_layer = ALL_OPTION

    while True:
        res = go.Get()
        
        if res == Rhino.Input.GetResult.Nothing:
            # User pressed Enter or clicked Done in left panel -> Finish and Export!
            export_curves = bool(opt_curves.CurrentValue)
            export_all_layers = bool(opt_all.CurrentValue)
            selected_target_layer = current_target_layer
            break
            
        elif res == Rhino.Input.GetResult.Option:
            opt_index = go.OptionIndex()
            if opt_index == opt_layer_idx:
                # Open native layer picker
                picked = rs.GetLayer("Select model layer to export", layer=current_target_layer if current_target_layer != ALL_OPTION else None)
                if picked:
                    current_target_layer = picked
                    opt_all.CurrentValue = False
            continue
            
        elif res == Rhino.Input.GetResult.Cancel:
            return # User pressed Cancel or Escape in left panel

    # Always use 3DM format (OBJ removed)
    chosen_format = "3DM"

    cfg["ExportFormat"] = chosen_format
    cfg["ExportCurves"] = str(export_curves)
    cfg["ExportAllLayers"] = str(export_all_layers)
    cfg["LastModelLayer"] = selected_target_layer
    save_r2b_config(cfg)

    model_dir = cfg.get("ModelDir", "").strip() or DATA_DIR
    if not os.path.exists(model_dir):
        os.makedirs(model_dir)

    ext = ".3dm"
    export_filename = clean_doc_name + ext
    export_full_path = os.path.join(model_dir, export_filename)
    fallback_path = os.path.join(model_dir, "R2B" + ext)

    rs.EnableRedraw(False)
    try:
        rs.UnselectAllObjects()

        target_objs = []
        hidden_layers = []
        hidden_objects = []

        # Identify hidden layers to exclude in Blender
        for layer in sc.doc.Layers:
            if not layer.IsDeleted and not layer.IsVisible:
                hidden_layers.append(layer.FullPath)

        for obj in sc.doc.Objects:
            if obj.IsDeleted:
                continue

            rhinolayer = sc.doc.Layers[obj.Attributes.LayerIndex]
            if not rhinolayer:
                continue

            # Check layer filtering (when not exporting all layers)
            if not export_all_layers and selected_target_layer and selected_target_layer != ALL_OPTION:
                fp = rhinolayer.FullPath
                matched = (fp == selected_target_layer or fp.startswith(selected_target_layer + "::"))
                if not matched:
                    continue

            # Check Curve filtering
            if not export_curves and obj.Geometry and obj.Geometry.ObjectType == Rhino.DocObjects.ObjectType.Curve:
                continue

            # Record object visibility status for Blender viewport hiding
            if not obj.Attributes.Visible or not rhinolayer.IsVisible:
                hidden_objects.append(str(obj.Id))

            target_objs.append(obj.Id)

        if not target_objs:
            rs.MessageBox("No objects found matching selected layers and settings!", 0, "LiveLink Advanced")
            return

        rs.SelectObjects(target_objs)

        quote = chr(34)
        export_cmd = '_-SaveSelected ' + quote + export_full_path + quote + ' _Enter'
        rs.Command(export_cmd, False)
        if export_full_path != fallback_path:
            rs.Command('_-SaveSelected ' + quote + fallback_path + quote + ' _Enter', False)

        rs.UnselectAllObjects()

        t_elapsed = round(time.time() - t0, 2)

        obj_manifest = {}
        for ob in sc.doc.Objects:
            if ob.IsDeleted:
                continue
            try:
                rhid = str(ob.Id)
                obj_manifest[rhid] = {
                    "layer": sc.doc.Layers[ob.Attributes.LayerIndex].FullPath,
                    "visible": bool(ob.Attributes.Visible),
                    "runtime_sn": int(ob.RuntimeSerialNumber)
                }
            except Exception:
                pass

        layer_manifest = {}
        for layer in sc.doc.Layers:
            if layer.IsDeleted:
                continue
            try:
                layer_manifest[layer.FullPath] = {
                    "visible": bool(layer.IsVisible),
                    "effective_visible": bool(layer.IsEffectiveVisible),
                    "color": [layer.Color.R, layer.Color.G, layer.Color.B]
                }
            except Exception:
                pass

        meta = {
            "doc_name": doc_basename,
            "export_format": chosen_format,
            "active_filepath": export_full_path,
            "fallback_filepath": fallback_path,
            "export_curves": export_curves,
            "export_all_layers": export_all_layers,
            "selected_layer": selected_target_layer,
            "hidden_layers": hidden_layers,
            "hidden_objects": hidden_objects,
            "object_count": len(target_objs),
            "export_time_sec": t_elapsed,
            "object_manifest": obj_manifest,
            "layers": layer_manifest
        }
        save_r2b_sync_metadata(meta)

        print(f"LiveLink Advanced: Exported '{export_filename}' ({len(target_objs)} objects) in {t_elapsed}s! Click 'Update Models' in Blender.")
    finally:
        rs.EnableRedraw(True)

if __name__ == "__main__":
    AdvancedLinkExport()
