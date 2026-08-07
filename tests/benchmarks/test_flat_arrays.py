"""Test: flat float list vs tuple list for from_pydata"""
import bpy, time, random
bpy.ops.wm.read_factory_settings(use_empty=True)

N = 3000
nv = 500  # realistic vertex count
nf = 500  # realistic face count

# Generate test data
verts_tuples = [(random.random(), random.random(), random.random()) for _ in range(nv)]
verts_flat = [random.random() for _ in range(nv * 3)]
faces_tuples = [(i, i+1, i+2, i+3) for i in range(0, nf*4, 4)]

print(f"Testing {N} meshes with {nv} verts, {nf} faces each...")

# Test 1: tuple list
t0 = time.perf_counter()
for i in range(N):
    m = bpy.data.meshes.new(name=f"TT_{i:08d}")
    m.from_pydata(verts_tuples, [], faces_tuples)
dt1 = time.perf_counter() - t0
print(f"  Tuple lists: {dt1:.3f}s ({dt1/N*1000:.3f}ms/mesh)")
# Clean up
for m in list(bpy.data.meshes):
    if m.name.startswith("TT_"):
        bpy.data.meshes.remove(m)

# Test 2: flat float list
t0 = time.perf_counter()
for i in range(N):
    m = bpy.data.meshes.new(name=f"TF_{i:08d}")
    m.from_pydata(verts_flat, [], faces_tuples)
dt2 = time.perf_counter() - t0
print(f"  Flat floats: {dt2:.3f}s ({dt2/N*1000:.3f}ms/mesh)")

# Test 3: foreach_set for vertex coords (skip from_pydata for verts)
t0 = time.perf_counter()
for i in range(N):
    m = bpy.data.meshes.new(name=f"FS_{i:08d}")
    m.vertices.add(nv)
    m.vertices.foreach_set("co", verts_flat)
    # Still need from_pydata for faces
    m.from_pydata([], [], faces_tuples)
dt3 = time.perf_counter() - t0
print(f"  foreach_set co: {dt3:.3f}s ({dt3/N*1000:.3f}ms/mesh)")

# Test 4: combined - flat verts + foreach_set for faces
t0 = time.perf_counter()
for i in range(N):
    m = bpy.data.meshes.new(name=f"CB_{i:08d}")
    m.from_pydata(verts_flat, [], faces_tuples)
    # UV would be done via foreach_set separately
dt4 = time.perf_counter() - t0
print(f"  Combined flat: {dt4:.3f}s ({dt4/N*1000:.3f}ms/mesh)")

print(f"\nBest vs worst: {min(dt1,dt2,dt3,dt4):.3f}s vs {max(dt1,dt2,dt3,dt4):.3f}s ({(1-min(dt1,dt2,dt3,dt4)/max(dt1,dt2,dt3,dt4))*100:.0f}% improvement)")
