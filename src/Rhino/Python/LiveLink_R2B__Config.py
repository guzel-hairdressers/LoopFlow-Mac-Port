# -*- coding: utf-8 -*-
"""
============================================================
Module Name        : LiveLink_R2B__Config
Version            : v2.0
Date               : 2026-07-31
Author             : LoopFlow Team
Environment        : Rhino 8 (CPython 3.9) / Python 3
============================================================
[Description]
Shared configuration module for the LiveLink R2B script series.
Centralizes reading, writing, and default values for R2B_Path.txt
and R2B_Sync.json metadata.
"""
import os
import json
import time

# ── Global path resolution (auto-derived from install location) ──
_PYTHON_DIR    = os.path.dirname(os.path.abspath(__file__))
INSTALL_DIR    = os.path.dirname(_PYTHON_DIR)
DATA_DIR       = os.path.join(INSTALL_DIR, "Data")
CONFIG_FILE    = os.path.join(DATA_DIR, "R2B_Path.txt")
SYNC_JSON_FILE = os.path.join(DATA_DIR, "R2B_Sync.json")
DEBUG_LOG_FILE = os.path.join(DATA_DIR, "cursor_R2B_debug_log.txt")

# Complete default values shared by all scripts
DEFAULT_CONFIG = {
    "DataPath":       DATA_DIR,
    "ModelDir":       DATA_DIR,
    "LightLayer":     "R2B_LT_Points",
    "CameraFile":     "R2B_Camera_Sync.json",
    "LightFile":      "R2B_Light_Sync.json",
    "ModelFile":      "R2B.3dm",
    "BoxMapSize":     "500",
    "LastModelLayer": "",
    "ExportFormat":   "OBJ",
    "ExportCurves":   "False",
}

_FIELD_ORDER = [
    "DataPath",
    "ModelDir",
    "LightLayer",
    "CameraFile",
    "LightFile",
    "ModelFile",
    "BoxMapSize",
    "LastModelLayer",
    "ExportFormat",
    "ExportCurves",
]

def load_r2b_config():
    config = DEFAULT_CONFIG.copy()
    if not os.path.exists(CONFIG_FILE):
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
        save_r2b_config(config)
    else:
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    if ":" in line:
                        parts = line.split(":", 1)
                        key = parts[0].strip()
                        val = parts[1].strip()
                        if key in config:
                            config[key] = val
        except Exception:
            pass

    if not os.path.exists(config["DataPath"]):
        try:
            os.makedirs(config["DataPath"])
        except Exception:
            pass

    return config

def save_r2b_config(config):
    if not os.path.exists(DATA_DIR):
        try:
            os.makedirs(DATA_DIR)
        except Exception:
            pass
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            for key in _FIELD_ORDER:
                f.write("{}: {}\n".format(key, config.get(key, DEFAULT_CONFIG.get(key, ""))))
    except Exception:
        pass

def save_r2b_sync_metadata(meta_dict):
    """Save multi-session sync metadata to R2B_Sync.json with smart delta tracking."""
    if not os.path.exists(DATA_DIR):
        try:
            os.makedirs(DATA_DIR)
        except Exception:
            pass

    prev_meta = load_r2b_sync_metadata()
    curr_objs = meta_dict.get("object_manifest", {})
    prev_objs = prev_meta.get("object_manifest", {})

    curr_layers = meta_dict.get("layers", {})
    prev_layers = prev_meta.get("layers", {})

    if prev_objs and curr_objs:
        prev_keys = set(prev_objs.keys())
        curr_keys = set(curr_objs.keys())

        added = list(curr_keys - prev_keys)
        removed = list(prev_keys - curr_keys)
        
        # Check ONLY runtime_sn (geometry serial number) for geometry modifications!
        modified_geom = [
            k for k in (curr_keys & prev_keys) 
            if curr_objs[k].get("runtime_sn") != prev_objs[k].get("runtime_sn")
        ]
        
        geom_changed = bool(added or removed or modified_geom)
        modified = [k for k in (curr_keys & prev_keys) if curr_objs[k] != prev_objs[k]]
    else:
        added, removed, modified = [], [], []
        geom_changed = True

    layers_changed = (curr_layers != prev_layers)

    meta_dict["timestamp"] = time.time()
    meta_dict["geometry_changed"] = geom_changed
    meta_dict["layers_changed"] = layers_changed
    meta_dict["added_obj_guids"] = added
    meta_dict["removed_obj_guids"] = removed
    meta_dict["modified_obj_guids"] = modified

    try:
        with open(SYNC_JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(meta_dict, f, indent=2, ensure_ascii=False)

        act_file = meta_dict.get("active_filepath", "")
        if act_file:
            stem = os.path.splitext(os.path.basename(act_file))[0]
            # Write R2B_Sync_<file_stem>.json to DATA_DIR
            named_json_data = os.path.join(DATA_DIR, "R2B_Sync_{}.json".format(stem))
            with open(named_json_data, 'w', encoding='utf-8') as f:
                json.dump(meta_dict, f, indent=2, ensure_ascii=False)

            # Write R2B_Sync.json and R2B_Sync_<file_stem>.json to model directory
            act_dir = os.path.dirname(act_file)
            if act_dir and os.path.exists(act_dir):
                local_json = os.path.join(act_dir, "R2B_Sync.json")
                with open(local_json, 'w', encoding='utf-8') as f:
                    json.dump(meta_dict, f, indent=2, ensure_ascii=False)

                local_named = os.path.join(act_dir, "R2B_Sync_{}.json".format(stem))
                with open(local_named, 'w', encoding='utf-8') as f:
                    json.dump(meta_dict, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print("LoopFlow Config Error saving R2B_Sync.json: {}".format(e))

def load_r2b_sync_metadata():
    """Load multi-session sync metadata from R2B_Sync.json."""
    if os.path.exists(SYNC_JSON_FILE):
        try:
            with open(SYNC_JSON_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

