"""OBJ Hybrid v2: extract to arrays, bulk OBJ write, import via Blender C"""
import os, sys, time, tempfile, gc
from array import array
sys.path.insert(0, os.path.expanduser('~/Library/Application Support/Blender/5.2/scripts/addons'))
import bpy, rhino3dm as r3d

bpy.ops.wm.read_factory_settings(use_empty=True)

mp = os.path.expanduser('~/Desktop/B1M 9.2.3dm')
print(f'Loading {os.path.getsize(mp)/1024/1024:.0f}MB...')
t0 = time.perf_counter()
model = r3d.File3dm.Read(mp)
print(f'Loaded in {time.perf_counter()-t0:.2f}s')
gc.disable()

# --- Phase 1: Extract to arrays ---
print('Phase 1: Extracting mesh data...')
t0 = time.perf_counter()
obj_meta = []  # (name, guid, layer_idx, mat_idx, color, is_idef)
all_verts = array('d')    # double for precision, avoid f-string float conversion
all_faces = array('I')    # unsigned ints for face indices
all_vt = array('d')       # UV coords
vert_counts = array('I')  # vertex count per object
face_counts = array('I')  # face count per object
vt_counts = array('I')    # UV count per object

for ob in model.Objects:
    og = ob.Geometry
    if not og: continue
    ot = og.ObjectType
    if ot not in (r3d.ObjectType.Brep, r3d.ObjectType.Extrusion, r3d.ObjectType.Mesh, r3d.ObjectType.SubD):
        continue
    oa = ob.Attributes
    is_idef = oa.IsInstanceDefinitionObject if hasattr(oa, "IsInstanceDefinitionObject") else False

    msh = None
    if ot == r3d.ObjectType.Brep:
        combined = r3d.Mesh()
        for fi in range(len(og.Faces)):
            try:
                fm = og.Faces[fi].GetMesh(r3d.MeshType.Any)
                if fm: combined.Append(fm)
            except: pass
        msh = combined
    elif ot == r3d.ObjectType.Mesh:
        msh = og
    elif ot == r3d.ObjectType.Extrusion:
        msh = og.GetMesh(r3d.MeshType.Any)
    elif ot == r3d.ObjectType.SubD:
        msh = r3d.Mesh.CreateFromSubDControlNet(og, False)

    if not msh or len(msh.Vertices) == 0:
        continue

    nv = len(msh.Vertices)
    nf = len(msh.Faces)
    nvt = len(msh.TextureCoordinates)

    obj_meta.append((oa.Id, oa.Name, oa.LayerIndex, oa.MaterialIndex, oa.ObjectColor if hasattr(oa, "ObjectColor") else (200,200,200,255), is_idef, oa.MaterialSource if hasattr(oa, "MaterialSource") else 0))

    vert_counts.append(nv)
    face_counts.append(nf)
    vt_counts.append(nvt)

    for v in msh.Vertices:
        all_verts.extend((v.X, v.Y, v.Z))
    for uv in msh.TextureCoordinates:
        all_vt.extend((uv.X, uv.Y))
    for face in msh.Faces:
        f0,f1,f2,f3 = face[0], face[1], face[2], face[3]
        if f3 == f2:
            all_faces.extend((3, f0, f1, f2))
        else:
            all_faces.extend((4, f0, f1, f2, f3))

dt_extract = time.perf_counter() - t0
total_verts = sum(vert_counts)
total_faces = sum(face_counts)
print(f'Extracted {len(obj_meta)} objects ({total_verts:,}v, {total_faces:,}f) in {dt_extract:.2f}s')

# --- Phase 2: Bulk OBJ write ---
print('Phase 2: Writing OBJ...')
tmp = tempfile.NamedTemporaryFile(suffix='.obj', delete=False)
tmp.close()
t0 = time.perf_counter()

with open(tmp.name, 'w', buffering=1024*1024) as f:
    v_offset = 0
    vt_offset = 0
    f_idx = 0
    for obj_i in range(len(obj_meta)):
        nv = vert_counts[obj_i]
        nf = face_counts[obj_i]
        nvt = vt_counts[obj_i]
        f.write(f'o obj_{obj_i}\n')

        # Write vertices in bulk chunks
        for vi in range(v_offset*3, (v_offset+nv)*3, 3):
            f.write(f'v {all_verts[vi]:.6f} {all_verts[vi+1]:.6f} {all_verts[vi+2]:.6f}\n')

        # Write UVs
        for vi in range(vt_offset*2, (vt_offset+nvt)*2, 2):
            f.write(f'vt {all_vt[vi]:.6f} {all_vt[vi+1]:.6f}\n')

        # Write faces (with UV refs if available)
        for fi in range(f_idx, f_idx + nf*...):
            # face data: count + indices
            pass

        v_offset += nv
        vt_offset += nvt
        f_idx += nf

# Actually the above is still per-vertex f-strings. Let me use a different approach:
# Build all lines as a single string using extend on a list
# But the join approach was 13.28s — let me just do that

# Let me rewrite this more cleanly...
# Actually I realize I should just verify: does the bulk join approach work well enough?

# Let me use the proven 13.28s approach from earlier test
lines = []
v_off = 0; vt_off = 0; f_ptr = 0
for obj_i in range(len(obj_meta)):
    nv = vert_counts[obj_i]; nf = face_counts[obj_i]; nvt = vt_counts[obj_i]
    lines.append(f'o obj_{obj_i}')
    for vi in range(v_off*3, (v_off+nv)*3, 3):
        lines.append(f'v {all_verts[vi]:.6f} {all_verts[vi+1]:.6f} {all_verts[vi+2]:.6f}')
    for vi in range(vt_off*2, (vt_off+nvt)*2, 2):
        lines.append(f'vt {all_vt[vi]:.6f} {all_vt[vi+1]:.6f}')
    # Faces: need to read count-prefixed indices from all_faces
    for fi in range(f_ptr, f_ptr + sum(1 for _ in range(nf) if ...)):
        pass  # complex, skip for now

    v_off += nv; vt_off += nvt

# Since face processing is complex with the count-prefixed array,
# let me just use a simpler face representation
