"""Test if multithreading speeds up mesh extraction (SWIG GIL behavior)"""
import os, sys, time, threading
from array import array
sys.path.insert(0, os.path.expanduser('~/Library/Application Support/Blender/5.2/scripts/addons'))
import rhino3dm as r3d

mp = os.path.expanduser('~/Desktop/B1M 9.2.3dm')
print(f'Loading...')
t0 = time.perf_counter()
model = r3d.File3dm.Read(mp)
print(f'Loaded in {time.perf_counter()-t0:.2f}s')

# Collect all mesh-creating objects
mesh_objs = []
for ob in model.Objects:
    og = ob.Geometry
    if not og: continue
    ot = og.ObjectType
    if ot in (r3d.ObjectType.Brep, r3d.ObjectType.Mesh, r3d.ObjectType.Extrusion):
        mesh_objs.append(ob)

print(f'{len(mesh_objs)} mesh objects to extract')

# Test 1: Single-threaded extraction
def extract_range(start, end, result_list, idx):
    verts = array('f')
    counts = array('B')
    indices = array('I')
    for i in range(start, end):
        ob = mesh_objs[i]
        og = ob.Geometry
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
            for v in msh.Vertices:
                verts.extend((v.X, v.Y, v.Z))
            for face in msh.Faces:
                f0,f1,f2,f3 = face[0], face[1], face[2], face[3]
                if f3 == f2:
                    counts.append(3); indices.extend((f0,f1,f2))
                else:
                    counts.append(4); indices.extend((f0,f1,f2,f3))
    result_list[idx] = (verts, counts, indices)

N = len(mesh_objs)
results_single = [None]
t0 = time.perf_counter()
extract_range(0, N, results_single, 0)
dt_single = time.perf_counter() - t0
v = results_single[0][0]
print(f'Single-thread: {dt_single:.2f}s | {len(v)//3:,} verts')

# Test 2: Two-threaded extraction
results_multi = [None, None]
mid = N // 2
t0 = time.perf_counter()
t1 = threading.Thread(target=extract_range, args=(0, mid, results_multi, 0))
t2 = threading.Thread(target=extract_range, args=(mid, N, results_multi, 1))
t1.start(); t2.start()
t1.join(); t2.join()
dt_multi = time.perf_counter() - t0
v0 = results_multi[0][0] if results_multi[0] else array('f')
v1 = results_multi[1][0] if results_multi[1] else array('f')
print(f'Two-thread:   {dt_multi:.2f}s ({dt_single/dt_multi:.1f}x speedup) | {len(v0)//3 + len(v1)//3:,} verts')

# Test 3: Four-threaded
results_4 = [None]*4
chunk = N // 4
t0 = time.perf_counter()
threads = []
for i in range(4):
    start = i * chunk
    end = start + chunk if i < 3 else N
    t = threading.Thread(target=extract_range, args=(start, end, results_4, i))
    threads.append(t)
    t.start()
for t in threads: t.join()
dt_4 = time.perf_counter() - t0
total_v = sum(len(r[0])//3 for r in results_4 if r)
print(f'Four-thread:  {dt_4:.2f}s ({dt_single/dt_4:.1f}x speedup) | {total_v:,} verts')
