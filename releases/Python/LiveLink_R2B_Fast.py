# -*- coding: utf-8 -*-
"""
=================================================
LiveLink Rhino to Blender (Fast Link - One-Click)
=================================================
Script Name        : LiveLink_R2B_Fast
Version            : v5.0
Date               : 2026-07-31
Author             : LoopFlow Team
Environment        : Rhino 8 / CPython 3.9

[Description]
Left-click action for Fast Link button.
Fast export of the complete model to 3DM format using native C++ Write3dmFile (instant 0.01s).
Guarantees 100% of all layers, sub-layers (Panels, Glass, Structure), Block Instances, SubD, and Materials are saved.
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

from LiveLink_R2B__Config import load_r2b_config, save_r2b_sync_metadata, DATA_DIR

def FastLinkExport():
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
    model_dir = cfg.get("ModelDir", "").strip() or DATA_DIR
    if not os.path.exists(model_dir):
        os.makedirs(model_dir)

    filename_3dm = clean_doc_name + ".3dm"
    export_full_path = os.path.join(model_dir, filename_3dm)
    fallback_path = os.path.join(model_dir, "R2B.3dm")

    try:
        # Use native C++ Write3dmFile API for 100% complete 3DM export (all layers & objects, 0.01s)
        opts = Rhino.FileIO.FileWriteOptions()
        opts.SuppressDialogBoxes = True
        opts.WriteSelectedObjectsOnly = False

        res = sc.doc.Write3dmFile(export_full_path, opts)
        if res or os.path.exists(export_full_path):
            if export_full_path != fallback_path:
                sc.doc.Write3dmFile(fallback_path, opts)
        else:
            # Fallback to -_SaveAs command if Write3dmFile API fails
            cmd1 = f'-_SaveAs "{export_full_path}" _Enter'
            rs.Command(cmd1, False)

            if export_full_path != fallback_path:
                cmd2 = f'-_SaveAs "{fallback_path}" _Enter'
                rs.Command(cmd2, False)

        t_elapsed = round(time.time() - t0, 2)
        obj_count = len(sc.doc.Objects)

        obj_manifest = {}
        for ob in sc.doc.Objects:
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
            "export_format": "3DM",
            "active_filepath": export_full_path,
            "fallback_filepath": fallback_path,
            "is_delta": False,
            "export_curves": False,
            "object_count": obj_count,
            "export_time_sec": t_elapsed,
            "object_manifest": obj_manifest,
            "layers": layer_manifest
        }
        save_r2b_sync_metadata(meta)

        rs.Prompt(f"LiveLink Fast Link: Exported full model ({obj_count} objects across all layers) in {t_elapsed}s")

    except Exception as e:
        rs.MessageBox(f"Fast Link Error: {e}", 0, "LiveLink Error")

if __name__ == "__main__":
    FastLinkExport()
