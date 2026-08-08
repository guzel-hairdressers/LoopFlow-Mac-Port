# Known Issues & Backlog

## 1. Elevator / Escalator Block Instance Missing Faces
- **Status**: Root Cause Diagnosed / Pending Fix (Deferred per user request)
- **Occurrence**: Both OBJ Fast-Path and Legacy import modes.
- **Root Cause**:
  In Rhino 3DM models (e.g. `B1M 9.3.3dm`), over **50.5% (830 out of 1,645 faces)** of Brep faces in the Elevator and Escalator block definitions have `face.OrientationIsReversed == True`.
  When `rhino3dm` extracts render meshes via `face.GetMesh()`, the resulting mesh triangle winding orders and vertex normals point **inward** toward the interior of the solid. In Blender, backface culling / single-sided shading makes these inverted outer faces appear completely transparent / missing when viewed from the outside.
- **Proposed Future Fix**:
  Check `face.OrientationIsReversed` when iterating Brep faces in `read3dm.py` / `render_mesh.py`. If `True`, flip mesh face triangle winding orders ($v_0, v_1, v_2 \to v_0, v_2, v_1$) and invert vertex normals (`mesh.Flip(True, True, True)`).
