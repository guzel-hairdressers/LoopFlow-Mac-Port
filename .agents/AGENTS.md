# Workspace Behavioral Rules & Customizations

## Rhino 8 macOS Toolbar (.rhc / .rui) Rules

1. **Dockbar Metadata & Container Header Requirement**:
   - Rhino 8 Mac requires the exact `dock_bar guid="171011a9-a956-41ee-853e-3ccc0c0db1d8"` and `name="Standard Toolbars"` container placement metadata in `.rhc` files for drag-and-drop floating window placement to function.
   - When updating RHC files, preserve the active scheme's container dockbar GUID (`171011a9-a956-41ee-853e-3ccc0c0db1d8`) and source group (`c7da84fc-2991-4824-832a-4f2509bd0ede`).

2. **GUID Caching & Active Scheme Synchronization**:
   - Rhino 8 Mac caches toolbars by GUID in `~/Library/Application Support/McNeel/Rhinoceros/8.0/settings/Scheme__Default/`.
   - When modifying `.rhc` files, ensure both the release `.rhc` and Rhino 8's active scheme file `Rhino.UI.Resources.rui.default_*.xml` are updated to force Rhino 8 to reload fresh toolbars and icons.

3. **Mac SVG Icon Specifications**:
   - Rhino 8 Mac SVG parser **only supports pure vector elements** (`<path>`, `<rect>`, `<circle>`, `<polygon>`, `<g>`).
   - Do NOT use `<defs>`, `<use>`, `xlink:href`, or embedded Base64 PNG data (`data:image/png;base64,...`).
   - Every `<g>` tag inside `<light_svg>` and `<dark_svg>` MUST explicitly include `xmlns="http://www.w3.org/2000/svg"`.
   - RHC files MUST start with a UTF-8 BOM (`ï»¿`) and use single-level XML entity escaping (`&lt;`, `&gt;`, `&quot;`, `&amp;`).

4. **Rhino Script Command Options Bar**:
   - Use `Rhino.Input.Custom.GetOption()` for Left Command Options Bar workflows.
   - Call `go.AcceptString(False)` to hide the empty string prompt field at the top of the command options panel.
