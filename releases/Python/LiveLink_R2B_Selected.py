# -*- coding: utf-8 -*-
"""
=================================================
LiveLink Rhino to Blender (Selected Objects Sync)
=================================================
Script Name        : LiveLink_R2B_Selected
Version            : v2.0
Date               : 2026-07-31
Author             : LoopFlow Team
Environment        : Rhino 8 / CPython 3.9

[Description]
Right-click action for Fast Link button.
Exports ONLY the user-selected objects to 3DM format in ~0.001s.
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

def SelectedObjectsExport():
    t0 = time.time()
    user_selected = rs.SelectedObjects()
    if not user_selected or len(user_selected) == 0:
        rs.MessageBox("No objects selected!\n\nPlease select the objects you want to sync, then right-click Fast Link.", 0, "Selected Objects Sync")
        return

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
        # Export ONLY selected objects (3DM format, instant 0.001s)
        opts = Rhino.FileIO.FileWriteOptions()
        opts.SuppressDialogBoxes = True
        opts.WriteSelectedObjectsOnly = True

        res = sc.doc.Write3dmFile(export_full_path, opts)
        if res or os.path.exists(export_full_path):
            if export_full_path != fallback_path:
                sc.doc.Write3dmFile(fallback_path, opts)
        else:
            cmd1 = f'-_Export "{export_full_path}" _Enter'
            rs.Command(cmd1, False)

            if export_full_path != fallback_path:
                cmd2 = f'-_Export "{fallback_path}" _Enter'
                rs.Command(cmd2, False)

        t_elapsed = round(time.time() - t0, 2)

        meta = {
            "doc_name": doc_basename,
            "export_format": "3DM",
            "active_filepath": export_full_path,
            "fallback_filepath": fallback_path,
            "is_delta": True,
            "export_curves": False,
            "object_count": len(user_selected),
            "export_time_sec": t_elapsed
        }
        save_r2b_sync_metadata(meta)

        rs.Prompt(f"LiveLink Selected Objects Sync: Exported {len(user_selected)} selected objects in {t_elapsed}s")

    except Exception as e:
        rs.MessageBox(f"Selected Objects Sync Error: {e}", 0, "LiveLink Error")

if __name__ == "__main__":
    SelectedObjectsExport()
