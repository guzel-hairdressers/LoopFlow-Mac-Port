"""Profile: determine where time is spent during Brep/Mesh conversion"""
import os, sys, time
addons_dir = os.path.expanduser("~/Library/Application Support/Blender/5.2/scripts/addons")
sys.path.insert(0, addons_dir)
import bpy, rhino3dm as r3d
bpy.ops.wm.read_factory_settings(use_empty=True)

model_path = os.path.expanduser("~/Desktop/Roof Link.3dm")
print(f"Loading {model_path}...")
t0 = time.perf_counter()
model = r3d.File3dm.Read(model_path)
print(f"Loaded in {time.perf_counter()-t0:.2f}s | {len(model.Objects)} objects")

# Profile: Brep face tessellation
breps = [ob for ob in model.Objects if ob.Geometry.ObjectType == r3d.ObjectType.Brep]
meshes_raw = [ob for ob in model.Objects if ob.Geometry.ObjectType == r3d.ObjectType.Mesh]
print(f"Breps: {len(breps)}, Meshes: {len(meshes_raw)}")

# Test 1: Brep tessellation with combined mesh
print("\n=== Test: Brep combined mesh tessellation (first 2000) ===")
N = min(2000, len(breps))
t_tess = 0
t_append = 0
t_vert = 0
t_face = 0
total_verts = 0
total_faces = 0
for i in range(N):
    og = breps[i].Geometry
    t1 = time.perf_counter()
    combined = r3d.Mesh()
    og_faces = og.Faces
    for f in range(len(og_faces)):
        try:
            fm = og_faces[f].GetMesh(r3d.MeshType.Any)
            if fm:
                t2 = time.perf_counter()
                combined.Append(fm)
                t_append += time.perf_counter() - t2
        except Exception:
            pass
    t_tess += time.perf_counter() - t1

    # Extract vertices
    t2 = time.perf_counter()
    if len(combined.Vertices) > 0:
        verts = [(v.X, v.Y, v.Z) for v in combined.Vertices]
        total_verts += len(verts)
        t_vert += time.perf_counter() - t2

        t2 = time.perf_counter()
        faces = []
        for face in combined.Faces:
            f0, f1, f2, f3 = face[0], face[1], face[2], face[3]
            if f3 == f2:
                faces.append((f0, f1, f2))
            else:
                faces.append((f0, f1, f2, f3))
        total_faces += len(faces)
        t_face += time.perf_counter() - t2

    if (i+1) % 500 == 0:
        dt = time.perf_counter() - t0
        print(f"  Brep {i+1}/{N} | {dt:.2f}s | tess={t_tess:.2f}s append={t_append:.2f}s vert={t_vert:.2f}s face={t_face:.2f}s | v={total_verts} f={total_faces}")

print(f"\nTotals: tess={t_tess:.2f}s append={t_append:.2f}s vert={t_vert:.2f}s face={t_face:.2f}s")

# Test 2: Simple mesh conversion
print(f"\n=== Test: Mesh vertex/face extraction (first 2000) ===")
N2 = min(2000, len(meshes_raw))
t_mesh = 0
for i in range(N2):
    og = meshes_raw[i].Geometry
    t1 = time.perf_counter()
    verts = [(v.X, v.Y, v.Z) for v in og.Vertices]
    faces = []
    for face in og.Faces:
        f0, f1, f2, f3 = face[0], face[1], face[2], face[3]
        if f3 == f2:
            faces.append((f0, f1, f2))
        else:
            faces.append((f0, f1, f2, f3))
    t_mesh += time.perf_counter() - t1
    if (i+1) % 500 == 0:
        print(f"  Mesh {i+1}/{N2} | mesh_extract={t_mesh:.2f}s")

print(f"Total mesh extraction: {t_mesh:.2f}s")

# Test 3: Blender mesh.from_pydata with realistic sizes
print(f"\n=== Test: Blender from_pydata + foreach_set with realistic sizes ===")
N3 = min(1000, len(breps))
t_pydata = 0
t_uv = 0
t_vcol = 0
t_newmesh = 0
t_newobj = 0

for i in range(N3):
    og = breps[i].Geometry
    # Quick tessellation
    combined = r3d.Mesh()
    for f in range(len(og.Faces)):
        try:
            fm = og.Faces[f].GetMesh(r3d.MeshType.Any)
            if fm: combined.Append(fm)
        except: pass
    if len(combined.Vertices) == 0: continue

    verts = [(v.X, v.Y, v.Z) for v in combined.Vertices]
    faces_data = []
    for face in combined.Faces:
        f0,f1,f2,f3 = face[0],face[1],face[2],face[3]
        faces_data.append((f0,f1,f2) if f3==f2 else (f0,f1,f2,f3))

    t1 = time.perf_counter()
    m = bpy.data.meshes.new(name=f"TST_{i:08d}")
    t_newmesh += time.perf_counter() - t1

    t1 = time.perf_counter()
    m.from_pydata(verts, [], faces_data)
    t_pydata += time.perf_counter() - t1

    # UVs
    tc = combined.TextureCoordinates
    if len(tc) == len(verts):
        t1 = time.perf_counter()
        m.uv_layers.new(name="RhinoUVMap")
        uvl = m.uv_layers["RhinoUVMap"].data
        uv_flat = []
        for l in m.loops:
            c = tc[l.vertex_index]
            uv_flat.extend((c.X, c.Y))
        uvl.foreach_set("uv", uv_flat)
        t_uv += time.perf_counter() - t1

    t1 = time.perf_counter()
    bpy.data.objects.new(name=f"OBJT_{i:08d}", object_data=m)
    t_newobj += time.perf_counter() - t1

    if (i+1) % 200 == 0:
        dt = time.perf_counter() - t0
        print(f"  {i+1}/{N3} | new_mesh={t_newmesh:.2f}s pydata={t_pydata:.2f}s uv={t_uv:.2f}s new_obj={t_newobj:.2f}s | objs:{len(bpy.data.objects)} meshes:{len(bpy.data.meshes)}")

print(f"\nFinal: new_mesh={t_newmesh:.2f}s pydata={t_pydata:.2f}s uv={t_uv:.2f}s new_obj={t_newobj:.2f}s")
print(f"Total: {t_newmesh+t_pydata+t_uv+t_newobj:.2f}s")
