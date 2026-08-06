# RFC-001: Instant Fast-Path Layer Visibility Synchronization & GUID Mapping

- **Status**: Implemented & Standardized
- **Author**: Ruslan F
- **Target Component**: `LoopFlow_import_3dm` / `read3dm.py` & `LiveLink_R2B_Fast.py`

## 1. Context & Motivation

In original LiveLink implementations, toggling layer visibility in Rhino required re-reading the entire 3DM model file and re-converting all objects in Blender. For large models (e.g. > 100 MB / 20,000+ objects), this resulted in 100+ second delays for a simple layer checkbox toggle.

## 2. Proposed Architecture

### A. Rhino Layer GUID Serialization
Rhino exports layer visibility metadata into `R2B_Sync.json` with multi-key indexing:
- `layer_manifest[layer.Id]` (Rhino Layer GUID)
- `layer_manifest[layer.FullPath]` (Hierarchy Path string)
- `layer_manifest[layer.Name]` (Leaf Name)

### B. Blender Collection Custom Properties
During collection creation, Blender stores:
- `lcol["rhid"] = str(l.Id)`
- `lcol["rhino_full_path"] = str(l.FullPath)`
- `lcol["rhino_layer_name"] = str(l.Name)`

### C. Fast-Path Bypass Loop (< 0.06s)
When `geometry_changed == False` or `has_geom_delta == False`:
1. `read3dm.py` bypasses file reading entirely.
2. Traverses `context.view_layer.layer_collection`.
3. Matches collection nodes by `rhid` GUID first.
4. Toggles `lc.exclude = not effective_visible`.

## 3. Results
Layer visibility update time reduced from **100+ seconds** to **0.05 seconds (50ms)**.
