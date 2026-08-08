"""Test PLY import + separate by loose parts speed"""
import bpy, time, tempfile, os
from array import array

bpy.ops.wm.read_factory_settings(use_empty=True)

# Create test PLY with 5000 separate cubes (simulating building parts)
N = 5000
print(f'Creating test PLY with {N} separate cube meshes...')
verts = array('f'); face_counts = array('B'); indices = array('I')
cube_verts = [(0,0,0),(1,0,0),(1,1,0),(0,1,0),(0,0,1),(1,0,1),(1,1,1),(0,1,1)]
cube_faces = [(0,1,2,3),(4,5,6,7),(0,1,5,4),(2,3,7,6),(0,4,7,3),(1,2,6,5)]

for i in range(N):
    x = (i % 100) * 2; y = (i // 100) * 2
    base = len(verts) // 3
    for v in cube_verts:
        verts.extend((v[0]+x, v[1]+y, v[2]))
    for f in cube_faces:
        face_counts.append(4)
        indices.extend((f[0]+base, f[1]+base, f[2]+base, f[3]+base))

tmp = tempfile.NamedTemporaryFile(suffix='.ply', delete=False); tmp.close()
nv = len(verts)//3; nf = len(face_counts)
hdr = f'ply\nformat binary_little_endian 1.0\nelement vertex {nv}\nproperty float x\nproperty float y\nproperty float z\nelement face {nf}\nproperty list uchar int vertex_indices\nend_header\n'
with open(tmp.name, 'wb') as f:
    f.write(hdr.encode()); f.write(verts.tobytes())
    ip = 0
    for c in face_counts:
        f.write(bytes([c])); f.write(indices[ip:ip+c].tobytes()); ip += c

# Import
t0 = time.perf_counter()
bpy.ops.wm.ply_import(filepath=tmp.name)
dt_import = time.perf_counter() - t0
print(f'Import: {dt_import:.2f}s | {len(bpy.data.objects)} object')

# Split by loose parts
obj = bpy.context.active_object
bpy.ops.object.mode_set(mode='EDIT')
t0 = time.perf_counter()
bpy.ops.mesh.separate(type='LOOSE')
dt_split = time.perf_counter() - t0
bpy.ops.object.mode_set(mode='OBJECT')
print(f'Split: {dt_split:.2f}s | {len(bpy.data.objects)} objects')

os.unlink(tmp.name)
