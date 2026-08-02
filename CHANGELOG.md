# Changelog

## [2.0.0] - 2026-08-01

### Cross-Platform macOS & Windows Support
- Added native macOS Rhino 8 toolbar (`LoopFlow_R2B_Mac.rhc`) and auto-installer (`install_LoopFlow_R2B.command`).
- Retained Windows Rhino 8 toolbar (`LoopFlow_R2B.rhc`) and auto-installer (`install_LoopFlow_R2B.bat`).

### Pure Vector SVG Toolbar Icons
- Refactored all 5 core toolbar icons (`Fast Link`, `Advanced Link`, `Camera Sync`, `Light Sync`, `Config`) into pure vector SVG graphics compatible with Rhino 8 Mac's parser.
- Added pure vector `Blender Test` toolbar button.
- Embedded dual Light Mode (`<light_svg>`) and Dark Mode (`<dark_svg>`) vector renders.

### Advanced Link & Command Options Bar
- Implemented Rhino's Left Command Options Bar workflow (`Rhino.Input.Custom.GetOption()`).
- Added toggleable `ExportCurves=Yes/No` and `ExportAllLayers=Yes/No` sidebar controls.
- Integrated native layer tree picker (`rs.GetLayer()`) for selective model layer export.
- Tracked hidden layer (`hidden_layers`) and hidden object (`hidden_objects`) metadata so Blender automatically excludes hidden layers and hides hidden objects in the viewport.

---

## [1.0.0] - 2026-04-28

First public release.

### Rhino-Side Scripts
- **LiveLink_R2B_Models** — One-click 3DM export with auto scene cleanup, material standardisation, and Box Mapping
- **LiveLink_R2B_Camera** — Toggle-based live camera sync; writes viewport data to JSON on every rotation/zoom
- **LiveLink_R2B_Light** — Scans Point objects and exports light position data for Blender auto-alignment
- **LiveLink_R2B_Open** — Quick open utility for config file, data folder, and debug log

### Blender Side — LoopFlow_import_3dm (Required)
- **Import Models / Update Models** — First-time import and seamless geometry updates preserving all layer, hide, exclude, and Bounds states
- **Start / Stop Camera Sync** — Background polling of `R2B_Camera_Sync.json` for real-time viewport sync
- **Sync Rhino Lights** — One-click fixture alignment from `R2B_Light_Sync.json` with orphan cleanup

### Blender Side — LoopFlow Toolkit (Optional)
- **Export Tools** — Batch and selective USDZ export for Collections
- **Rename Tools** — Sequential naming for Collections and Objects with instance dual-counter
- **Selection Tools** — Group, Un-Group, Re-Group, Select All in Group, Delete From Group, Material Isolator
