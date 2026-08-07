"""Test PLY with array module for C-level binary speed"""
import os, sys, time, tempfile, struct
from array import array
sys.path.insert(0, os.path.expanduser('~/Library/Application Support/Blender/5.2/scripts/addons'))
import rhino3dm as r3d, bpy

mp = os.path.expanduser('~/Desktop/B1M 9.2.3dm')
print(f'Loading...')
t0 = time.perf_counter()
model = r3d.File3dm.Read(mp)
print(f'Loaded in {time.perf_counter()-t0:.2f}s')

# Extract all meshes
t0 = time.perf_counter()
meshes = []
for ob in model.Objects:
    og = ob.Geometry
    if not og: continue
    ot = og.ObjectType
    msh = None
    if ot == r3d.ObjectType.Brep:
        combined = r3d.Mesh()
        for fi in range(len(og.Faces)):
            fm = og.Faces[fi].GetMesh(r3d.MeshType.Any)
            if fm: combined.Append(fm)
        msh = combined
    elif ot == r3d.ObjectType.Mesh:
        msh = og
    elif ot == r3d.ObjectType.Extrusion:
        msh = og.GetMesh(r3d.MeshType.Any)
    if msh and len(msh.Vertices) > 0:
        meshes.append(msh)
dt_extract = time.perf_counter() - t0
total_verts = sum(len(m.Vertices) for m in meshes)
total_faces = sum(len(m.Faces) for m in meshes)
print(f'Extracted {len(meshes)} meshes ({total_verts:,}v, {total_faces:,}f) in {dt_extract:.2f}s')

# Write PLY using array module (C-level binary packing)
tmp = tempfile.NamedTemporaryFile(suffix='.ply', delete=False)
tmp.close()

t0 = time.perf_counter()

# Use array('f') for vertex data - C-level float packing
verts_arr = array('f')
face_counts = array('B')  # uchar
face_indices = array('I')  # uint

for m in meshes:
    for v in m.Vertices:
        verts_arr.extend((v.X, v.Y, v.Z))
    for face in m.Faces:
        f0,f1,f2,f3 = face[0], face[1], face[2], face[3]
        if f3 == f2:
            face_counts.append(3)
            face_indices.extend((f0, f1, f2))
        else:
            face_counts.append(4)
            face_indices.extend((f0, f1, f2, f3))

# Write header
header = f"""ply
format binary_little_endian 1.0
element vertex {total_verts}
property float x
property float y
property float z
element face {total_faces}
property list uchar int vertex_indices
end_header
"""

with open(tmp.name, 'wb') as f:
    f.write(header.encode())
    # Write vertex array directly (C-level bulk write via memoryview)
    f.write(verts_arr.tobytes())
    # Write face data: for each face, count byte + indices
    idx_pos = 0
    for count in face_counts:
        f.write(bytes([count]))
        f.write(face_indices[idx_pos:idx_pos+count].tobytes())
        idx_pos += count

dt_write = time.perf_counter() - t0
ply_size = os.path.getsize(tmp.name)/1024/1024
print(f'PLY array write: {dt_write:.2f}s ({ply_size:.0f}MB)')

# Import PLY
bpy.ops.wm.read_factory_settings(use_empty=True)
t0 = time.perf_counter()
bpy.ops.wm.ply_import(filepath=tmp.name)
dt_import = time.perf_counter() - t0
print(f'PLY import: {dt_import:.2f}s')
print(f'Total: {dt_write+dt_import:.2f}s | Objects: {len(bpy.data.objects)}, Meshes: {len(bpy.data.meshes)}')
os.unlink(tmp.name)
