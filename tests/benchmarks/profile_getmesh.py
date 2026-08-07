"""Profile Brep GetMesh tessellation time"""
import os, sys, time
addons_dir = os.path.expanduser("~/Library/Application Support/Blender/5.2/scripts/addons")
sys.path.insert(0, addons_dir)
import rhino3dm as r3d
import bpy

model_path = os.path.expanduser("~/Desktop/Roof Link.3dm")
print("Loading model...")
t0 = time.perf_counter()
model = r3d.File3dm.Read(model_path)
print(f"Loaded in {time.perf_counter()-t0:.2f}s")

# Collect all Breps with face counts
breps = []
for ob in model.Objects:
    og = ob.Geometry
    if not og or og.ObjectType != r3d.ObjectType.Brep:
        continue
    nf = len(og.Faces)
    breps.append((ob, nf))

print(f"Total Breps: {len(breps)}")

# Categorize by face count
from collections import Counter
fc_dist = Counter(nf for _, nf in breps)
print("Face count distribution:")
for fc in sorted(fc_dist)[:20]:
    print(f"  {fc} faces: {fc_dist[fc]} Breps")

# Sample GetMesh time for different face counts
print("\nProfiling GetMesh time by face count...")
for fc in [1, 2, 5, 10, 20, 50, 100]:
    samples = [(ob, nf) for ob, nf in breps if nf == fc][:20]
    if not samples:
        continue
    total_verts = 0
    t0 = time.perf_counter()
    for ob, nf in samples:
        og = ob.Geometry
        for f_idx in range(nf):
            fm = og.Faces[f_idx].GetMesh(r3d.MeshType.Any)
            if fm:
                total_verts += len(fm.Vertices)
    dt = time.perf_counter() - t0
    n_samples = len(samples) * fc
    print(f"  {fc}-face Brep x{len(samples)}: {dt:.3f}s total, {dt/n_samples*1000:.3f}ms/face, avg verts={total_verts/max(1,n_samples):.0f}")

# Profile: single-face Brep with combined mesh vs direct
print("\nProfiling 1-face Brep: combined mesh vs direct...")
samples_1f = [(ob, nf) for ob, nf in breps if nf == 1][:500]
t_combined = 0
t_direct = 0
for ob, nf in samples_1f:
    og = ob.Geometry
    # Combined approach
    t0 = time.perf_counter()
    combined = r3d.Mesh()
    fm = og.Faces[0].GetMesh(r3d.MeshType.Any)
    if fm:
        combined.Append(fm)
    t_combined += time.perf_counter() - t0

    # Direct approach
    t0 = time.perf_counter()
    fm2 = og.Faces[0].GetMesh(r3d.MeshType.Any)
    t_direct += time.perf_counter() - t0

print(f"  Combined (Mesh+Append): {t_combined:.4f}s ({t_combined/len(samples_1f)*1000:.4f}ms/obj)")
print(f"  Direct (GetMesh only):  {t_direct:.4f}s ({t_direct/len(samples_1f)*1000:.4f}ms/obj)")
print(f"  Overhead of Mesh+Append: {(t_combined-t_direct)/len(samples_1f)*1000:.4f}ms/obj")

# Profile: multi-face Brep with Append overhead
print("\nProfiling multi-face Brep Append...")
for fc in [5, 10, 20]:
    samples = [(ob, nf) for ob, nf in breps if nf == fc][:10]
    if not samples:
        continue
    t0 = time.perf_counter()
    total_face_ops = 0
    for ob, nf in samples:
        og = ob.Geometry
        combined = r3d.Mesh()
        for f_idx in range(nf):
            fm = og.Faces[f_idx].GetMesh(r3d.MeshType.Any)
            if fm:
                combined.Append(fm)
                total_face_ops += 1
    dt = time.perf_counter() - t0
    print(f"  {fc}-face Brep x{len(samples)}: {dt:.3f}s, {dt/total_face_ops*1000:.3f}ms/(GetMesh+Append)")
