# LoopFlow Master Agent Handover & Architecture Specification

This document serves as the permanent master reference for developers and AI agents working on **LoopFlow Mac Port** (Rhino 8 macOS to Blender 5.2 Live Sync Engine).

---

## 1. Directory & Code Base Organization

```text
LoopFlow-Mac-Port/
├── src/                          # Extension Core Source Code
│   ├── LoopFlow_import_3dm/      # Blender 3DM Importer & LiveSync Engine
│   ├── LoopFlow_Toolkit/         # Blender Auxiliary Utility Toolkit
│   └── Rhino/                    # Rhino 8 Toolbars (.rhc) & Python Script Engines
├── releases/                     # Pre-packaged Production ZIPs & Toolbars
├── icons/                        # Pure Vector SVG Artboard Icons
├── scripts/                      # Developer Build & Packaging Utilities
│   └── package_release.py        # Automated ZIP packaging script
├── tests/                        # Comprehensive Testing Framework
│   ├── unit/                     # Standard Unit Tests
│   ├── integration/              # Live Sync Integration Tests
│   ├── benchmarks/               # Performance Benchmarking Suite
│   │   └── verify_all_targets.py # 4-Target Benchmark Verifier
│   └── temp/                     # Temporary Tests, Scratch Scripts & Temp Trackers
├── docs/                         # Architecture, Guides & Specifications
│   ├── proposals/                # Architectural RFCs & Long-Term Proposals
│   ├── tracking/                 # Long-Term Issue Trackers & Milestones
│   ├── USER_GUIDE.md             # End User Guide
│   └── HANDOVER.md               # Master Project Handover Reference (This File)
└── .agents/                      # Workspace Behavioral Rules & Customizations
    └── AGENTS.md
```

---

## 2. Core Functional Workflow

### A. Rhino 8 Side
- **Fast Sync (`LiveLink_R2B_Fast.py`)**: One-click export of 3DM file and JSON sync metadata to `~/Library/Application Support/McNeel/Rhinoceros/8.0/scripts/LoopFlow_R2B/Data/R2B_Sync.json`.
- **Active Directory Dual Sync**: Rhino toolbar macros execute scripts from `LoopFlow_R2B/Py/`. Developer build scripts MUST synchronize source edits to **both** `Py/` and `Python/` subdirectories.

### B. Blender 5.2 Side
- **Unified Model Sync Button (`RHINO_OT_QuickSync`, `import_mode='SYNC'`)**: Consolidates smart sync and file override logic!
  - **Multi-File Persistence**: Syncing `model1.3dm` stores objects inside `LoopFlow/model1`. Syncing `model2.3dm` creates `LoopFlow/model2`, preserving `model1` 100%.
  - **Smart Delta Sync (JSON Manifest)**: If `R2B_Sync.json` is present for the file (in `Data/` or model directory), performs instant layer visibility update ($< 0.06\text{s}$) or delta geometry conversion ($< 0.5\text{s}$).
  - **File Signature Change Detection**: For standalone `.3dm` files without JSON manifests, compares file timestamp (`mtime`) and size. If the file has not changed, skips re-sync instantly; if changed, performs a file-level override on ONLY that file's collection.
- **Material Merge Modes (`rhino_material_merge_mode`)**:
  - `Merge (Keep Existing)`: Remaps objects to existing Blender materials, keeping existing material settings intact.
  - `Merge (Overwrite Existing)`: Remaps materials and updates existing Blender shader node inputs with newly imported material properties.
  - `Keep Unique`: Keeps imported materials unique (`Material.001`, `Material.002`) without merging.
- **SubD Subdivision Level Control (`0` to `5`)**: Imports SubD objects as pure 1:1 control nets (`r3d.Mesh.CreateFromSubDControlNet(og, False)`). Verified against `subd_test.3dm` to yield exact 20 faces and 18 vertices (no baked rigid texture-coord quad splitting). Applies a single `Subdivision` modifier default to **3** subdivisions for smooth Catmull-Clark viewport and render geometry.

---

## 3. Quantitative Performance Benchmark Targets

All 4 benchmark targets have been verified on the 199.85 MB reference model (**Game Center Roof.3dm** / 21,255 Blender Objects):

| Target | Description | Target Limit | Status |
| :--- | :--- | :---: | :---: |
| **Target 1** | Geometry Deletion | $< 20.0\text{s}$ | **2.57s** ✅ |
| **Target 2** | Update Model (No Changes) | $< 20.0\text{s}$ | **0.98s** ✅ |
| **Target 3** | Update Model (Layer Visibility Changed) | $< 30.0\text{s}$ | **0.62s** ✅ |
| **Target 4** | Update Model (Geometry Changed) | $< 60.0\text{s}$ | **2.90s** ✅ |

---

## 4. Developer Deployment Command

To compile release ZIPs, synchronize Rhino scripts to both `Py/` and `Python/` folders, and update installed Blender/Rhino extension directories in one step:

```bash
python3 -c "
import shutil, os

shutil.copy2('src/LoopFlow_import_3dm/read3dm.py', 'releases/LoopFlow_import_3dm/read3dm.py')
shutil.copy2('src/LoopFlow_import_3dm/__init__.py', 'releases/LoopFlow_import_3dm/__init__.py')
shutil.copy2('src/LoopFlow_import_3dm/converters/layers.py', 'releases/LoopFlow_import_3dm/converters/layers.py')
shutil.copy2('src/LoopFlow_import_3dm/converters/instances.py', 'releases/LoopFlow_import_3dm/converters/instances.py')
shutil.copy2('src/LoopFlow_import_3dm/converters/utils.py', 'releases/LoopFlow_import_3dm/converters/utils.py')
shutil.copy2('src/Rhino/Python/LiveLink_R2B_Fast.py', 'releases/LoopFlow_Rhino-to-Blender-Sync/Python/LiveLink_R2B_Fast.py')
shutil.copy2('src/Rhino/Python/LiveLink_R2B__Config.py', 'releases/LoopFlow_Rhino-to-Blender-Sync/Python/LiveLink_R2B__Config.py')
shutil.copy2('src/Rhino/LoopFlow_R2B_Mac.rhc', 'releases/LoopFlow_R2B_Mac.rhc')
shutil.copy2('src/Rhino/LoopFlow_R2B.rhc', 'releases/LoopFlow_R2B.rhc')

rhino_base = os.path.expanduser('~/Library/Application Support/McNeel/Rhinoceros/8.0/scripts/LoopFlow_R2B')
for folder in ['Py', 'Python']:
    p = os.path.join(rhino_base, folder)
    if os.path.exists(p):
        for f in os.listdir('src/Rhino/Python'):
            if f.endswith('.py'):
                shutil.copy2(os.path.join('src/Rhino/Python', f), os.path.join(p, f))
" && python3 scripts/package_release.py && python3 -c "
import shutil, os
src = 'src/LoopFlow_import_3dm'
dst = os.path.expanduser('~/Library/Application Support/Blender/5.2/scripts/addons/LoopFlow_import_3dm')
if os.path.exists(dst):
    shutil.rmtree(dst)
shutil.copytree(src, dst)
print('DEPLOYMENT SUCCESSFUL!')
"
```
