"""Check if Breps later in the 3DM file have more faces"""
import os, sys, time
addons_dir = os.path.expanduser("~/Library/Application Support/Blender/5.2/scripts/addons")
sys.path.insert(0, addons_dir)
import rhino3dm as r3d

model_path = os.path.expanduser("~/Desktop/Roof Link.3dm")
print(f"Loading {os.path.getsize(model_path)/1024/1024:.0f}MB model...")
t0 = time.perf_counter()
model = r3d.File3dm.Read(model_path)
print(f"Loaded in {time.perf_counter()-t0:.2f}s\n")

# Collect face counts for all Breps by position in file
brep_faces = []
mesh_verts = []
iref_count = 0
curve_count = 0
for idx, ob in enumerate(model.Objects):
    og = ob.Geometry
    if not og: continue
    ot = og.ObjectType
    if ot == r3d.ObjectType.Brep:
        n_faces = len(og.Faces)
        brep_faces.append((idx, n_faces))
    elif ot == r3d.ObjectType.Mesh:
        n_verts = len(og.Vertices)
        mesh_verts.append((idx, n_verts))
    elif ot == r3d.ObjectType.InstanceReference:
        iref_count += 1
    elif ot == r3d.ObjectType.Curve:
        curve_count += 1

print(f"Breps: {len(brep_faces)}, Meshes: {len(mesh_verts)}, InstRefs: {iref_count}, Curves: {curve_count}")

# Group into 10 batches by index position
batch_size = len(model.Objects) // 10
for b in range(10):
    start = b * batch_size
    end = start + batch_size if b < 9 else len(model.Objects)
    b_breps = [(i,n) for i,n in brep_faces if start <= i < end]
    b_meshes = [(i,n) for i,n in mesh_verts if start <= i < end]
    avg_brep_faces = sum(n for _,n in b_breps) / max(1, len(b_breps))
    max_brep_faces = max((n for _,n in b_breps), default=0)
    avg_mesh_verts = sum(n for _,n in b_meshes) / max(1, len(b_meshes))
    print(f"  Batch {b+1} [{start}-{end}]: {len(b_breps)} breps (avg {avg_brep_faces:.0f} faces, max {max_brep_faces}) | {len(b_meshes)} meshes (avg {avg_mesh_verts:.0f} verts)")

# Total potential Append cost (sum of faces² per Brep = O(N²) per Brep)
total_append_cost = sum(n*n for _,n in brep_faces)
print(f"\nTotal Brep Append cost (Σ faces²): {total_append_cost:,}")
print(f"Avg faces² per Brep: {total_append_cost/len(brep_faces):,.0f}")
