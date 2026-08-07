"""Test binary PLY write + import performance (no string formatting overhead)"""
import os, sys, time, tempfile, struct
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
dt = time.perf_counter() - t0
total_verts = sum(len(m.Vertices) for m in meshes)
total_faces = sum(len(m.Faces) for m in meshes)
print(f'Extracted {len(meshes)} meshes ({total_verts:,}v, {total_faces:,}f) in {dt:.2f}s')

# Write binary PLY (much faster than text OBJ)
tmp = tempfile.NamedTemporaryFile(suffix='.ply', delete=False)
tmp.close()
t0 = time.perf_counter()

# Collect all vertex/face data first (one SWIG pass per mesh)
all_verts = []
all_faces = []
vert_counts = []
face_counts = []
for m in meshes:
    nv = len(m.Vertices)
    nf = len(m.Faces)
    vert_counts.append(nv)
    face_counts.append(nf)
    # Flatten vertex data for bulk binary write
    for v in m.Vertices:
        all_verts.extend((v.X, v.Y, v.Z))
    for face in m.Faces:
        f0,f1,f2,f3 = face[0], face[1], face[2], face[3]
        if f3 == f2:
            all_faces.extend((3, f0, f1, f2))  # triangle
        else:
            all_faces.extend((4, f0, f1, f2, f3))  # quad

# Write PLY header + binary data
with open(tmp.name, 'wb') as f:
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
    f.write(header.encode())
    # Write vertices as binary floats
    f.write(struct.pack(f'{total_verts*3}f', *all_verts))
    # Write faces as binary ints
    for i in range(total_faces):
        # Each face entry: count (1 byte) + indices (count * 4 bytes)
        # We're packing tri and quad faces
        pass
    # Actually use a flat array approach for faces too
    # Build face binary data
    face_data = []
    for m in meshes:
        for face in m.Faces:
            f0,f1,f2,f3 = face[0], face[1], face[2], face[3]
            if f3 == f2:
                face_data.append(b'\x03' + struct.pack('III', f0, f1, f2))
            else:
                face_data.append(b'\x04' + struct.pack('IIII', f0, f1, f2, f3))
    f.write(b''.join(face_data))

dt_write = time.perf_counter() - t0
ply_size = os.path.getsize(tmp.name)/1024/1024
print(f'PLY written: {dt_write:.2f}s ({ply_size:.0f}MB)')

# Import PLY via Blender
bpy.ops.wm.read_factory_settings(use_empty=True)
t0 = time.perf_counter()
bpy.ops.wm.ply_import(filepath=tmp.name)
dt_import = time.perf_counter() - t0
print(f'PLY imported: {dt_import:.2f}s')
print(f'Total PLY path: {dt_write+dt_import:.2f}s')
print(f'Objects: {len(bpy.data.objects)}, Meshes: {len(bpy.data.meshes)}')
os.unlink(tmp.name)
