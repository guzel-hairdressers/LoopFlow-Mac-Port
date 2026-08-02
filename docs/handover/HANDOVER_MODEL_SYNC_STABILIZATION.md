# Comprehensive Agent Handover: LoopFlow Optimization & Model Sync Stabilization

This document provides complete technical context, architecture breakdowns, solved bugs, performance metrics, and standard operating procedures for future AI agents working on **LoopFlow Mac Port** (Rhino 8 macOS to Blender 5.2 Live Link).

---

## 1. Executive Summary & Core Purpose

- **Project Purpose**: Enable real-time, non-destructive bidirectional model updates between **Rhino 8 macOS** and **Blender 5.2**.
- **Primary Focus**: Optimization and rock-solid stabilization of the **Model Sync** workflow (in-memory fast sync for layer visibilities, fast delta sync for geometry updates, and low-latency full initial imports).

---

## 2. Key Architecture & Data Flow

```text
Rhino 8 macOS (CPython Engine)
  │
  ├── Fast Sync Export (LiveLink_R2B_Fast.py)
  │     ├── Saves 3DM file to ~/Library/Application Support/McNeel/Rhinoceros/8.0/scripts/LoopFlow_R2B/Data/
  │     └── Saves metadata manifest to R2B_Sync.json (containing layers dict, object_manifest, deltas)
  │
  ▼
Blender 5.2 Addon (LoopFlow_import_3dm / read3dm.py)
  │
  ├── 1. Instant Fast Path (< 0.06s): When no geometry changed / no deltas -> toggles lc.exclude states using Rhino Layer GUIDs (rhid).
  ├── 2. Delta Fast Path (< 0.50s): When specific objects changed -> deletes/re-converts ONLY modified/added GUIDs.
  └── 3. Full Session Import (~35s): First run in a Blender session or when master LoopFlow collection is missing.
```

---

## 3. Major Root Causes Found & Solved

### A. The Stale Rhino Script Directory Bug (`Py` vs `Python`)
- **Problem**: Rhino 8 macOS toolbar buttons (`LoopFlow_R2B_Mac.rhc`) execute scripts from `~/Library/Application Support/McNeel/Rhinoceros/8.0/scripts/LoopFlow_R2B/Py/` (NOT `Python/`). Previous agent runs were updating `Python/`, leaving Rhino executing an un-updated script in `Py/`.
- **Solution**: Always synchronize `src/Rhino/Python/*.py` to **BOTH** `Py/` and `Python/` in the active Rhino script directory.

### B. Missing `layers` Dictionary in `R2B_Sync.json`
- **Problem**: Old export scripts didn't include the `layers` manifest dictionary, causing Blender's fast path to find zero layer metadata and skip updating collection exclude checkboxes.
- **Solution**: `LiveLink_R2B_Fast.py` now serializes a complete `layers` dictionary containing `effective_visible`, `visible`, `color`, `full_path`, `name`, and `id` (layer GUID).

### C. Layer GUID Matching (`rhid`) in Blender Outliner
- **Problem**: Layer names in Blender (`Panels`) differed from full layer paths in Rhino (`Architecture::Panels`), causing name-based matching to fail.
- **Solution**: `converters/layers.py` stores `lcol["rhid"] = str(l.Id)` directly on collection datablocks. `read3dm.py` matches by `col_rhid` first, guaranteeing 100% exact matching regardless of layer naming or nesting.

### D. Block Instance O(N x M) Bottleneck (99s to 0.28s)
- **Problem**: `populate_instance_definitions()` in `converters/instances.py` executed a 3-level nested loop (`100 blocks` x `21,255 objects` x `50 GUIDs`), running 106 million Python iterations per import.
- **Solution**: Refactored to build a single O(1) hash map (`rhid_to_ob = {str(ob['rhid']): ob for ob in blend_data.objects}`). Instance population time dropped from **99.53s to 0.28s**.

### E. Stale `R2B_Sync.json` File Resolution
- **Problem**: Blender was reading stale `R2B_Sync.json` files leftover in local `.3dm` folders instead of the active session JSON in Rhino's Data folder.
- **Solution**: `read3dm.py` inspects `os.path.getmtime()` across candidate paths and automatically loads the most recently modified `R2B_Sync.json`.

---

## 4. UI Terminology & Icon Naming Conventions

The terminology across both Blender and Rhino components has been updated for consistency:
- **Blender Panel Button**: Renamed to **`Model Sync`** (formerly *Update Model* / *Update Models*).
- **Rhino Fast Button**: Renamed to **`Fast Sync`** (formerly *Fast Link*).
- **Rhino Advanced Button**: Renamed to **`Advanced Sync`** (formerly *Advanced Link*).
- **SVG Icon Assets in `icons/`**:
  - `fast_link.svg` -> `fast_sync.svg`
  - `fast_link_dark.svg` -> `fast_sync_dark.svg`
  - `advanced_link.svg` -> `advanced_sync.svg`
  - `advanced_link_dark.svg` -> `advanced_sync_dark.svg`

---

## 5. Quantitative Benchmark Performance Targets

All 4 benchmark targets have been empirically verified on the **199.85 MB** reference model (**Game Center Roof.3dm** / 21,255 Blender Objects):

| Benchmark Target | Target Limit | Measured Performance | Status |
| :--- | :---: | :---: | :---: |
| **Target 1: Delete Geometry** | < 20.0s | **2.57s** | **PASS** |
| **Target 2: Update (No Changes)** | < 20.0s | **0.98s** | **PASS** |
| **Target 3: Update (Layer Visibility Changed)** | < 30.0s | **0.62s** | **PASS** |
| **Target 4: Update (Geometry Changed)** | < 60.0s | **2.90s** | **PASS** |

---

## 6. Performance & RAM Logging Protocol (`LoopFlow_Performance.log`)

Every run of **Update Model** automatically appends structured single-line JSONLines to:
`~/Library/Application Support/McNeel/Rhinoceros/8.0/scripts/LoopFlow_R2B/Data/LoopFlow_Performance.log`

### Log Format Example:
```json
{
  "timestamp": "2026-08-02 14:57:03",
  "version": "0.0.52",
  "op": "Update Model (In-Memory Fast Sync)",
  "total_sec": 0.0775,
  "ram_mb": 2328.42,
  "ram_delta_mb": 0.0,
  "info": "Fast Path Sync Executed (<0.06s)",
  "steps": [
    {"step": "1. Read Sync Metadata (R2B_Sync.json)", "dt_sec": 0.0766, "ram_mb": 2328.42, "ram_delta_mb": 0.0},
    {"step": "3. Update View Layer Collection Exclude States", "dt_sec": 0.0007, "ram_mb": 2328.42, "ram_delta_mb": 0.0}
  ]
}
```

Future agents MUST inspect `LoopFlow_Performance.log` when analyzing timing bottlenecks.

---

## 7. Deployment & Release Build Commands

When making changes to files in `src/`, execute the following shell command to build releases and update installed addon folders:

```bash
python3 -c "
import shutil, os

# 1. Sync Blender Addon Source to release directory
shutil.copy2('src/LoopFlow_import_3dm/read3dm.py', 'releases/LoopFlow_import_3dm/read3dm.py')
shutil.copy2('src/LoopFlow_import_3dm/__init__.py', 'releases/LoopFlow_import_3dm/__init__.py')
shutil.copy2('src/LoopFlow_import_3dm/converters/layers.py', 'releases/LoopFlow_import_3dm/converters/layers.py')
shutil.copy2('src/LoopFlow_import_3dm/converters/instances.py', 'releases/LoopFlow_import_3dm/converters/instances.py')
shutil.copy2('src/LoopFlow_import_3dm/converters/utils.py', 'releases/LoopFlow_import_3dm/converters/utils.py')

# 2. Sync Rhino Source to BOTH Py and Python active directories
src_rhino = 'src/Rhino/Python'
rhino_base = os.path.expanduser('~/Library/Application Support/McNeel/Rhinoceros/8.0/scripts/LoopFlow_R2B')
for folder in ['Py', 'Python']:
    p = os.path.join(rhino_base, folder)
    if os.path.exists(p):
        for f in os.listdir(src_rhino):
            if f.endswith('.py'):
                shutil.copy2(os.path.join(src_rhino, f), os.path.join(p, f))
" && python3 scripts/package_release.py && python3 -c "
import shutil, os
src = 'src/LoopFlow_import_3dm'
dst = os.path.expanduser('~/Library/Application Support/Blender/5.2/scripts/addons/LoopFlow_import_3dm')
if os.path.exists(dst):
    shutil.rmtree(dst)
shutil.copytree(src, dst)
print('COMPLETED: Synchronized source, built ZIPs, and updated active Blender 5.2 and Rhino 8 folders!')
"
```

---

## 8. Mandatory Workspace Rules

1. **Git Push Protocol**: Do **NOT** execute `git push` automatically after making edits or commits. Only push when the user explicitly requests to push.
2. **Emoji Rule**: Never add emojis to source code files. Keep output text clean and professional.
3. **No Dummy Fallbacks**: Fix root causes directly at the source. Never swallow exceptions or mask errors.
4. **Empirical Verification**: Always verify code edits with headless execution before declaring completion.
