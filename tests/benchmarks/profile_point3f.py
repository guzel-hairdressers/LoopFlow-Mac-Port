import sys, time
sys.path.insert(0, '/Users/ruslan_faz/Library/Application Support/Blender/5.2/scripts/addons/LoopFlow_import_3dm')
import rhino3dm as r3d

m = r3d.Mesh()
m.Vertices.Add(1.5, 2.5, 3.5)
v = m.Vertices[0]

# Time Point3f.XYZ
N = 500000
t0 = time.perf_counter()
for _ in range(N):
    x = v.X; y = v.Y; z = v.Z
dt = time.perf_counter() - t0
print(f'{N}x Point3f.XYZ access: {dt:.4f}s ({dt/N*1e9:.1f} ns per XYZ triplet)')

# Check Encode
enc = v.Encode()
print(f'Encode result: {enc}, type: {type(enc).__name__}')

# Check vertex list count
print(f'Vertices.Count: {m.Vertices.Count}')
