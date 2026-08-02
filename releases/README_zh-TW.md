# LoopFlow Rhino-to-Blender Sync — Releases

[▶ YouTube 影片教學](https://www.youtube.com/@LoopFlow) · [▶ 專案首頁](https://github.com/ChihyuTsai-Oli/LoopFlow_Rhino-to-Blender-Sync)

---

## 安裝說明

### 🍎 macOS Rhino 8
1. 下載並解壓縮發行包。
2. 在 Terminal 執行 `install_LoopFlow_R2B.command`，自動安裝腳本至 `~/Library/Application Support/McNeel/Rhinoceros/8.0/scripts/LoopFlow_R2B/`。
3. 將 **`LoopFlow_R2B_Mac.rhc`** 拖曳至 Rhino 視窗開啟工具列。

### 🪟 Windows Rhino 8
1. 下載並解壓縮發行包。
2. 執行 `install_LoopFlow_R2B.bat`，自動安裝腳本至 `%appdata%\McNeel\Rhinoceros\8.0\scripts\LoopFlow_R2B\`。
3. 將 **`LoopFlow_R2B.rhc`** 拖曳至 Rhino 視窗開啟工具列。

---

### 🎨 Blender 端（Addons）
1. 在 Blender 中選擇 **Edit > Preferences > Add-ons > Install**。
2. 安裝以下 Addon ZIP 檔：
   - `LoopFlow_import_3dm.zip`：3DM 模型匯入器（必需）
   - `LoopFlow_Toolkit.zip`：Export / Rename / Selection 工具包（選用）

---

## 檔案與資料夾結構

```
releases/
  LoopFlow_Rhino-to-Blender-Sync/
    Python/                            ← Rhino 端 Python 腳本
      LiveLink_R2B_Fast.py
      LiveLink_R2B_Advanced.py
      LiveLink_R2B_Camera.py
      LiveLink_R2B_Light.py
      LiveLink_R2B_Open.py
      LiveLink_R2B__Config.py
    LoopFlow_import_3dm/               ← Blender Addon 原始碼
    LoopFlow_Toolkit/                  ← Blender Addon 原始碼
    install_LoopFlow_R2B.command       ← macOS 自動安裝檔
    install_LoopFlow_R2B.bat           ← Windows 自動安裝檔
    LoopFlow_R2B_Mac.rhc               ← macOS 工具列定義檔
    LoopFlow_R2B.rhc                   ← Windows 工具列定義檔
    LoopFlow_import_3dm.zip            ← 打包好的 Blender Addon
    LoopFlow_Toolkit.zip               ← 打包好的 Blender Addon
  README.md
  README_zh-TW.md
```

---

## 致謝

- **LoopFlow_import_3dm** 是 [Nathan Letwory (jesterKing)](https://github.com/jesterKing) 開發之 [import_3dm](https://github.com/jesterKing/import_3dm) 的 Fork 版本，採用 MIT 授權。
