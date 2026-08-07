"""OBJ Hybrid for Roof Link: extract → OBJ → import → metadata"""
import os, sys, time, tempfile, gc
sys.path.insert(0, os.path.expanduser('~/Library/Application Support/Blender/5.2/scripts/addons'))
import bpy, rhino3dm as r3d

bpy.ops.wm.read_factory_settings(use_empty=True)
mp = os.path.expanduser('~/Desktop/Roof Link.3dm')
sz = os.path.getsize(mp)/1024/1024
print(f'Loading {sz:.0f}MB model...')
t_load = time.perf_counter()
model = r3d.File3dm.Read(mp)
dt_load = time.perf_counter() - t_load
print(f'Loaded in {dt_load:.1f}s')
gc.disable()

scale = r3d.UnitSystem.UnitScale(model.Settings.ModelUnitSystem, r3d.UnitSystem.Meters) / bpy.context.scene.unit_settings.scale_length

# Phase 1: Extract all meshes
print('Phase 1: Tessellating...')
t0 = time.perf_counter()
meshes = []
for ob in model.Objects:
    og = ob.Geometry
    if not og: continue
    ot = og.ObjectType
    if ot not in (r3d.ObjectType.Brep, r3d.ObjectType.Extrusion, r3d.ObjectType.Mesh, r3d.ObjectType.SubD):
        continue
    msh = None
    if ot == r3d.ObjectType.Brep:
        combined = r3d.Mesh()
        for fi in range(len(og.Faces)):
            try:
                fm = og.Faces[fi].GetMesh(r3d.MeshType.Any)
                if fm: combined.Append(fm)
            except: pass
        msh = combined
    elif ot == r3d.ObjectType.Mesh: msh = og
    elif ot == r3d.ObjectType.Extrusion: msh = og.GetMesh(r3d.MeshType.Any)
    elif ot == r3d.ObjectType.SubD: msh = r3d.Mesh.CreateFromSubDControlNet(og, False)
    if msh and len(msh.Vertices) > 0:
        meshes.append(msh)
dt_tess = time.perf_counter() - t0
total_v = sum(len(m.Vertices) for m in meshes)
total_f = sum(len(m.Faces) for m in meshes)
print(f'Tessellated {len(meshes)} meshes ({total_v:,}v, {total_f:,}f) in {dt_tess:.1f}s')

# Phase 2: Build OBJ text
print('Phase 2: Building OBJ...')
t0 = time.perf_counter()
lines = []
v_off = 0  # cumulative vertex count
for i, m in enumerate(meshes):
    nv = len(m.Vertices)
    lines.append(f'o obj_{i}')
    for v in m.Vertices:
        lines.append(f'v {v.X*scale:.6f} {v.Y*scale:.6f} {v.Z*scale:.6f}')
    # UVs
    tc = m.TextureCoordinates
    has_uv = len(tc) == nv
    if has_uv:
        for uv in tc:
            lines.append(f'vt {uv.X:.6f} {uv.Y:.6f}')
    # Faces
    for face in m.Faces:
        f0,f1,f2,f3 = face[0]+1, face[1]+1, face[2]+1, face[3]+1
        a,b,c,d = f0+v_off, f1+v_off, f2+v_off, f3+v_off
        if has_uv:
            if f3 == f2:
                lines.append(f'f {a}/{a} {b}/{b} {c}/{c}')
            else:
                lines.append(f'f {a}/{a} {b}/{b} {c}/{c} {d}/{d}')
        else:
            if f3 == f2:
                lines.append(f'f {a} {b} {c}')
            else:
                lines.append(f'f {a} {b} {c} {d}')
    v_off += nv

obj_text = '\n'.join(lines)
dt_build = time.perf_counter() - t0
print(f'Built {len(lines):,} lines in {dt_build:.1f}s')

# Phase 3: Write + Import
print('Phase 3: Write & Import...')
tmp = tempfile.NamedTemporaryFile(suffix='.obj', delete=False)
tmp.close()
t0 = time.perf_counter()
with open(tmp.name, 'w', buffering=16*1024*1024) as f:
    f.write(obj_text)
dt_write = time.perf_counter() - t0
obj_mb = os.path.getsize(tmp.name)/1024/1024
print(f'  Written {obj_mb:.0f}MB in {dt_write:.1f}s')

t0 = time.perf_counter()
bpy.ops.wm.obj_import(filepath=tmp.name)
dt_import = time.perf_counter() - t0
print(f'  Imported in {dt_import:.1f}s | {len(bpy.data.objects)} objects')
os.unlink(tmp.name)

total = dt_load + dt_tess + dt_build + dt_write + dt_import
print(f'\nTOTAL: {total:.1f}s ({total/60:.1f}min)')
