"""Microbenchmark: test mesh+object creation slowdown"""
import bpy, time, gc
bpy.ops.wm.read_factory_settings(use_empty=True)

N = 36000  # match unique mesh count
batch = 7000
gc.collect()
gc.disable()

print(f"\n=== Test 1: Create {N} MESHES with vertices/faces ===")
t0 = time.perf_counter()
for i in range(N):
    name = f"MESH_{i:08d}"
    m = bpy.data.meshes.new(name=name)
    # Small mesh: 4 verts, 1 quad
    m.from_pydata([(0,0,0),(1,0,0),(1,1,0),(0,1,0)], [], [(0,1,2,3)])
    if (i + 1) % batch == 0:
        dt = time.perf_counter() - t0
        print(f"  {i+1:6d}/{N} | {dt:7.2f}s | {dt/(i+1)*1000:.4f} ms/mesh")

print(f"Meshes: {len(bpy.data.meshes)} in {time.perf_counter()-t0:.2f}s\n")

print(f"=== Test 2: Create {N} objects WITH mesh data ===")
t0 = time.perf_counter()
meshes = list(bpy.data.meshes)
for i in range(N):
    name = f"OBJ_{i:08d}"
    bpy.data.objects.new(name=name, object_data=meshes[i])
    if (i + 1) % batch == 0:
        dt = time.perf_counter() - t0
        print(f"  {i+1:6d}/{N} | {dt:7.2f}s | {dt/(i+1)*1000:.4f} ms/obj")

print(f"Objects: {len(bpy.data.objects)} in {time.perf_counter()-t0:.2f}s")

print(f"\n=== Test 3: Create BOTH mesh+obj interleaved ===")
bpy.ops.wm.read_factory_settings(use_empty=True)
gc.collect()
t0 = time.perf_counter()
for i in range(N):
    m = bpy.data.meshes.new(name=f"M_{i:08d}")
    m.from_pydata([(0,0,0),(1,0,0),(1,1,0),(0,1,0)], [], [(0,1,2,3)])
    bpy.data.objects.new(name=f"O_{i:08d}", object_data=m)
    if (i + 1) % batch == 0:
        dt = time.perf_counter() - t0
        print(f"  {i+1:6d}/{N} | {dt:7.2f}s | {dt/(i+1)*1000:.4f} ms/pair")

print(f"Total interleaved: {time.perf_counter()-t0:.2f}s")
