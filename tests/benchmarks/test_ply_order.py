"""Test if PLY split preserves object order"""
import bpy, time, tempfile, os
from array import array

bpy.ops.wm.read_factory_settings(use_empty=True)

# Create PLY with 10 objects of different sizes (v1=100v, v2=200v, ..., v10=1000v)
# Each object is a different-sized cube. Check order after split.
N = 10
verts = array('f'); face_counts = array('B'); indices = array('I')
expected_sizes = []

for i in range(N):
    size = (i + 1) * 0.5
    base = len(verts) // 3
    # Create a cube of this size offset by i*2 in X
    x_off = i * 3.0
    vdata = [(0+x_off,0,0),(size+x_off,0,0),(size+x_off,size,0),(0+x_off,size,0),
             (0+x_off,0,size),(size+x_off,0,size),(size+x_off,size,size),(0+x_off,size,size)]
    for v in vdata: verts.extend(v)
    for f in [(0,1,2,3),(4,5,6,7),(0,1,5,4),(2,3,7,6),(0,4,7,3),(1,2,6,5)]:
        face_counts.append(4)
        indices.extend((f[0]+base, f[1]+base, f[2]+base, f[3]+base))
    expected_sizes.append((f'obj_{i}', 8, 6))  # name, verts, faces

tmp = tempfile.NamedTemporaryFile(suffix='.ply', delete=False); tmp.close()
nv = len(verts)//3; nf = len(face_counts)
hdr = f'ply\nformat binary_little_endian 1.0\nelement vertex {nv}\nproperty float x\nproperty float y\nproperty float z\nelement face {nf}\nproperty list uchar int vertex_indices\nend_header\n'
with open(tmp.name, 'wb') as f:
    f.write(hdr.encode()); f.write(verts.tobytes())
    ip = 0
    for c in face_counts:
        f.write(bytes([c])); f.write(indices[ip:ip+c].tobytes()); ip += c

bpy.ops.wm.ply_import(filepath=tmp.name)
obj = bpy.context.active_object
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.separate(type='LOOSE')
bpy.ops.object.mode_set(mode='OBJECT')
os.unlink(tmp.name)

# Check order: split objects get names based on vertex count order?
# Blender names: Object, Object.001, Object.002, ...
objects = sorted([o for o in bpy.data.objects if o.type == 'MESH' and o != obj],
                 key=lambda o: o.name)  # Blender naming order

print(f'Split into {len(objects)} objects:')
for i, o in enumerate(objects):
    nv = len(o.data.vertices)
    nf = len(o.data.polygons)
    print(f'  [{i}] {o.name}: {nv}v {nf}f (expected {expected_sizes[i][0]}: {expected_sizes[i][1]}v {expected_sizes[i][2]}f)')

# Check if original merged object still exists (it shouldn't after split)
print(f'Original obj: {obj.name} has {len(obj.data.vertices)}v (should be 0 after split)')
