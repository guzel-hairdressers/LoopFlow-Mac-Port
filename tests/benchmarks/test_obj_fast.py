"""Test fast OBJ write using bulk string building vs per-line f.write"""
import os, sys, time, tempfile, io
sys.path.insert(0, os.path.expanduser('~/Library/Application Support/Blender/5.2/scripts/addons'))
import rhino3dm as r3d

mp = os.path.expanduser('~/Desktop/B1M 9.2.3dm')
print(f'Loading...')
t0 = time.perf_counter()
model = r3d.File3dm.Read(mp)
print(f'Loaded in {time.perf_counter()-t0:.2f}s')

# Pre-extract all meshes (same work as our import, no Blender calls)
def extract_meshes(model):
    meshes = []
    for ob in model.Objects:
        og = ob.Geometry
        if not og: continue
        ot = og.ObjectType
        if ot not in (r3d.ObjectType.Brep, r3d.ObjectType.Extrusion, r3d.ObjectType.Mesh):
            continue
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
    return meshes

t0 = time.perf_counter()
meshes = extract_meshes(model)
dt_extract = time.perf_counter() - t0
total_verts = sum(len(m.Vertices) for m in meshes)
total_faces = sum(len(m.Faces) for m in meshes)
print(f'Extracted {len(meshes)} meshes ({total_verts:,} verts, {total_faces:,} faces) in {dt_extract:.2f}s')

# Test 1: Traditional per-line write
tmp1 = tempfile.NamedTemporaryFile(suffix='.obj', delete=False)
tmp1.close()
t0 = time.perf_counter()
with open(tmp1.name, 'w') as f:
    for m in meshes:
        f.write(f'o mesh\n')
        for v in m.Vertices:
            f.write(f'v {v.X:.6f} {v.Y:.6f} {v.Z:.6f}\n')
        for face in m.Faces:
            f0,f1,f2,f3 = face[0]+1, face[1]+1, face[2]+1, face[3]+1
            if f3 == f2:
                f.write(f'f {f0} {f1} {f2}\n')
            else:
                f.write(f'f {f0} {f1} {f2} {f3}\n')
dt1 = time.perf_counter() - t0
print(f'Per-line write: {dt1:.2f}s ({os.path.getsize(tmp1.name)/1024/1024:.0f}MB)')
os.unlink(tmp1.name)

# Test 2: Bulk string building with StringIO
tmp2 = tempfile.NamedTemporaryFile(suffix='.obj', delete=False)
tmp2.close()
t0 = time.perf_counter()
buf = io.StringIO()
for m in meshes:
    buf.write('o mesh\n')
    for v in m.Vertices:
        buf.write(f'v {v.X:.6f} {v.Y:.6f} {v.Z:.6f}\n')
    for face in m.Faces:
        f0,f1,f2,f3 = face[0]+1, face[1]+1, face[2]+1, face[3]+1
        if f3 == f2:
            buf.write(f'f {f0} {f1} {f2}\n')
        else:
            buf.write(f'f {f0} {f1} {f2} {f3}\n')
with open(tmp2.name, 'w') as f:
    f.write(buf.getvalue())
dt2 = time.perf_counter() - t0
print(f'StringIO write: {dt2:.2f}s ({os.path.getsize(tmp2.name)/1024/1024:.0f}MB)')
os.unlink(tmp2.name)

# Test 3: Bulk write with joined strings (build all lines, join, write once)
tmp3 = tempfile.NamedTemporaryFile(suffix='.obj', delete=False)
tmp3.close()
t0 = time.perf_counter()
lines = []
for m in meshes:
    lines.append('o mesh')
    for v in m.Vertices:
        lines.append(f'v {v.X:.6f} {v.Y:.6f} {v.Z:.6f}')
    for face in m.Faces:
        f0,f1,f2,f3 = face[0]+1, face[1]+1, face[2]+1, face[3]+1
        if f3 == f2:
            lines.append(f'f {f0} {f1} {f2}')
        else:
            lines.append(f'f {f0} {f1} {f2} {f3}')
with open(tmp3.name, 'w') as f:
    f.write('\n'.join(lines))
dt3 = time.perf_counter() - t0
print(f'Join+batch write: {dt3:.2f}s ({os.path.getsize(tmp3.name)/1024/1024:.0f}MB)')
os.unlink(tmp3.name)

# Test 4: Import the OBJ via Blender
# Rewrite with 'o' lines for separate objects
tmp4 = tempfile.NamedTemporaryFile(suffix='.obj', delete=False)
tmp4.close()
t0 = time.perf_counter()
lines = []
for i, m in enumerate(meshes):
    lines.append(f'o Mesh_{i}')
    for v in m.Vertices:
        lines.append(f'v {v.X:.6f} {v.Y:.6f} {v.Z:.6f}')
    for face in m.Faces:
        f0,f1,f2,f3 = face[0]+1, face[1]+1, face[2]+1, face[3]+1
        if f3 == f2:
            lines.append(f'f {f0} {f1} {f2}')
        else:
            lines.append(f'f {f0} {f1} {f2} {f3}')
with open(tmp4.name, 'w') as f:
    f.write('\n'.join(lines))
dt_write = time.perf_counter() - t0

import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
t0 = time.perf_counter()
bpy.ops.wm.obj_import(filepath=tmp4.name)
dt_import = time.perf_counter() - t0
print(f'\nFast OBJ: write={dt_write:.2f}s + import={dt_import:.2f}s = {dt_write+dt_import:.2f}s total')
print(f'Objects: {len(bpy.data.objects)}, Meshes: {len(bpy.data.meshes)}')
os.unlink(tmp4.name)
