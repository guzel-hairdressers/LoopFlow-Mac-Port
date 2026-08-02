# LoopFlow｜Rhino to Blender Sync (Pro macOS & Windows Edition)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Blender](https://img.shields.io/badge/Blender-5.1%2B%20%7C%205.2%2B-orange.svg)](https://www.blender.org/)
[![Rhino](https://img.shields.io/badge/Rhino-8%20(macOS%20%26%20Windows)-blue.svg)](https://www.rhino3d.com/)

[▶ How it works (YouTube)](https://www.youtube.com/playlist?list=PLiJmu8T_uzJJTnDl6HLSOFZ3DimkI9bV8) · [▶ User Guide](./docs/USER_GUIDE.md) · [▶ Download Releases](./releases)

LoopFlow is an ultra-high-performance **Rhino 8 to Blender LiveSync Engine** built for macOS (Apple Silicon & Intel) and Windows. It provides zero-overhead geometry synchronization, instant layer visibility updates ($< 0.06\text{s}$), camera viewport mirroring, and light alignment.

---

## 👨‍💻 Authors & Credits

- **Ruslan F** ([@guzel-hairdressers](https://github.com/guzel-hairdressers)) — MacOS Port Creator
- **Chihyu Tsai** ([@ChihyuTsai-Oli](https://github.com/ChihyuTsai-Oli)) — Original LoopFlow Creator & Concept Lead
- **Nathan Letwory** ([@jesterKing](https://github.com/jesterKing)) — Original `import_3dm` Importer Foundation (MIT License)

---

## ⚡️ Key Features & Performance

- **Instant Fast Path Sync ($< 0.06\text{s}$)**: Pure metadata & layer visibility updates execute in under $60\text{ms}$ without re-reading 3DM geometry or re-welding meshes.
- **Native C++ Teardown ($< 2.5\text{s}$)**: Full scene reset of 20,000+ objects runs in native C++ via collection unlinking, bypassing Python $O(N^2)$ Dependency Graph rebuilds.
- **Pure Vector SVG Toolbars**: Cross-platform `.rhc` toolbars with native light/dark mode vector icons.
- **Camera Sync & Light Alignment**: Real-time camera matching and automatic point light placement.

---

## 📁 Repository Structure

```text
LoopFlow-Mac-Port/
├── src/                          # 📦 Core Extension Source Code
│   ├── LoopFlow_import_3dm/      # Blender 3DM Importer & LiveSync Engine
│   ├── LoopFlow_Toolkit/         # Blender Auxiliary Utility Toolkit
│   └── Rhino/                    # Rhino 8 Toolbars (.rhc) & Python Engines
├── releases/                     # 🚀 Pre-packaged Release ZIPs & Installers
│   ├── LoopFlow_import_3dm.zip
│   ├── LoopFlow_Toolkit.zip
│   ├── LoopFlow_R2B_Mac.rhc
│   ├── LoopFlow_R2B.rhc
│   └── install_LoopFlow_R2B.command
├── docs/                         # 📖 Guides, Manuals & Diagrams
├── icons/                        # 🎨 Pure Vector SVG Artboard Icons
├── scripts/                      # 🛠 Developer Build & Packaging Utilities
│   └── package_release.py        # Automated ZIP packaging script
├── .gitignore                    # Clean Git ignore rules
├── LICENSE                       # MIT License
├── README.md                     # Documentation (English)
├── CHANGELOG.md                  # Release Version History
└── CREDITS.md                    # Attribution
```

---

## 🚀 Quick Setup Instructions

### 1. Blender Setup
1. Download `releases/LoopFlow_import_3dm.zip` and `releases/LoopFlow_Toolkit.zip`.
2. Open Blender 5.1/5.2 $\rightarrow$ **Edit** $\rightarrow$ **Preferences** $\rightarrow$ **Add-ons** $\rightarrow$ **Install from Disk**.
3. Enable **Import Rhinoceros 3D (R2B Pro)** and **LoopFlow Toolkit**.

### 2. Rhino 8 Setup (macOS & Windows)
1. **macOS**: Double-click `releases/install_LoopFlow_R2B.command` or drag `releases/LoopFlow_R2B_Mac.rhc` into Rhino 8.
2. **Windows**: Double-click `releases/install_LoopFlow_R2B.bat` or drag `releases/LoopFlow_R2B.rhc` into Rhino 8.

---

## 📜 License

Distributed under the [MIT License](LICENSE). Copyright (c) 2026 Ruslan F & Chihyu Tsai.
