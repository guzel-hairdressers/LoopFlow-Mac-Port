# LoopFlow Rhino-to-Blender Sync — Releases

[Watch on YouTube](https://www.youtube.com/@LoopFlow) · [Project Page](https://github.com/ChihyuTsai-Oli/LoopFlow_Rhino-to-Blender-Sync)

---

## Installation Instructions

### macOS Rhino 8
1. Extract the release files.
2. Run `install_LoopFlow_R2B.command` in Terminal to install the Python scripts to `~/Library/Application Support/McNeel/Rhinoceros/8.0/scripts/LoopFlow_R2B/`.
3. Drag **`LoopFlow_R2B_Mac.rhc`** into Rhino 8 to open the toolbar.

### Windows Rhino 8
1. Extract the release files.
2. Run `install_LoopFlow_R2B.bat` to install scripts to `%appdata%\McNeel\Rhinoceros\8.0\scripts\LoopFlow_R2B\`.
3. Drag **`LoopFlow_R2B.rhc`** into Rhino 8 to open the toolbar.

---

### Blender Side (Addons)
1. In Blender, go to **Edit > Preferences > Add-ons > Install**.
2. Install the following addons as ZIP files:
   - `LoopFlow_import_3dm.zip` — 3DM model importer (Required)
   - `LoopFlow_Toolkit.zip` — Export / Rename / Selection toolkit (Optional)

---

## Included Files & Structure

```
releases/
  LoopFlow_Rhino-to-Blender-Sync/
    Python/                            ← Rhino-side Python scripts
      LiveLink_R2B_Fast.py
      LiveLink_R2B_Advanced.py
      LiveLink_R2B_Camera.py
      LiveLink_R2B_Light.py
      LiveLink_R2B_Open.py
      LiveLink_R2B__Config.py
    LoopFlow_import_3dm/               ← Blender Addon source
    LoopFlow_Toolkit/                  ← Blender Addon source
    install_LoopFlow_R2B.command       ← macOS Installer
    install_LoopFlow_R2B.bat           ← Windows Installer
    LoopFlow_R2B_Mac.rhc               ← macOS Toolbar Definition
    LoopFlow_R2B.rhc                   ← Windows Toolbar Definition
    LoopFlow_import_3dm.zip            ← Pre-packaged Blender Addon
    LoopFlow_Toolkit.zip               ← Pre-packaged Blender Addon
  README.md
```

---

## Credits

- **LoopFlow_import_3dm** is a fork of [import_3dm](https://github.com/jesterKing/import_3dm) by [Nathan Letwory (jesterKing)](https://github.com/jesterKing), licensed under MIT
