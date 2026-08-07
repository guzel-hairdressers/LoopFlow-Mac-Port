"""Microbenchmark: isolate bpy.data.objects.new() slowdown"""
import bpy, time, gc
bpy.ops.wm.read_factory_settings(use_empty=True)

N = 67000
batch = 7659
gc.collect()
gc.disable()

print(f"\nCreating {N} empty objects in batches of {batch}...")
t0 = time.perf_counter()

for i in range(N):
    name = f"OBJ_{i:08d}"
    bpy.data.objects.new(name=name, object_data=None)

    if (i + 1) % batch == 0 or i == N - 1:
        dt = time.perf_counter() - t0
        ms_per = (dt / (i + 1)) * 1000
        print(f"  {i+1:6d}/{N} | {dt:7.2f}s total | {ms_per:.4f} ms/obj avg | objs: {len(bpy.data.objects)}")

print(f"\nFinal: {len(bpy.data.objects)} objects in {time.perf_counter()-t0:.2f}s")
