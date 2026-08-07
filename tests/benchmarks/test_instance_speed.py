"""Profile what's slow about instance creation"""
import bpy, time
bpy.ops.wm.read_factory_settings(use_empty=True)

N = 12000
print(f"Creating {N} empties with collection instances...")

# Pre-create a collection for instancing
col = bpy.data.collections.new("TestBlock")
bpy.context.scene.collection.children.link(col)

# Test 1: Just new()
t0 = time.perf_counter()
empties = []
for i in range(N):
    e = bpy.data.objects.new(name=f"E_{i:08d}", object_data=None)
    empties.append(e)
print(f"Test 1 (new only): {time.perf_counter()-t0:.3f}s")

# Clean up
for e in empties:
    bpy.data.objects.remove(e)
empties.clear()

# Test 2: new + instance_collection
t0 = time.perf_counter()
for i in range(N):
    e = bpy.data.objects.new(name=f"E_{i:08d}", object_data=None)
    e.empty_display_type = 'PLAIN_AXES'
    e.instance_type = 'COLLECTION'
    e.instance_collection = col
    empties.append(e)
print(f"Test 2 (new + instance_collection): {time.perf_counter()-t0:.3f}s")

for e in empties:
    bpy.data.objects.remove(e)
empties.clear()

# Test 3: new + instance_collection + matrix
from mathutils import Matrix
mat = Matrix.Identity(4)
t0 = time.perf_counter()
for i in range(N):
    e = bpy.data.objects.new(name=f"E_{i:08d}", object_data=None)
    e.empty_display_type = 'PLAIN_AXES'
    e.instance_type = 'COLLECTION'
    e.instance_collection = col
    e.matrix_world = mat
    empties.append(e)
print(f"Test 3 (new + inst_col + matrix): {time.perf_counter()-t0:.3f}s")

for e in empties:
    bpy.data.objects.remove(e)
empties.clear()

# Test 4: new + inst_col + matrix + rhid
t0 = time.perf_counter()
for i in range(N):
    e = bpy.data.objects.new(name=f"E_{i:08d}", object_data=None)
    e['rhid'] = f"guid_{i}"
    e.empty_display_type = 'PLAIN_AXES'
    e.instance_type = 'COLLECTION'
    e.instance_collection = col
    e.matrix_world = mat
    empties.append(e)
print(f"Test 4 (all): {time.perf_counter()-t0:.3f}s")
