"""OBJ Hybrid v4: extract meshes→build lines→join→write→import→metadata (proven fast)"""
import os, sys, time, tempfile, gc
sys.path.insert(0, os.path.expanduser('~/Library/Application Support/Blender/5.2/scripts/addons'))
import bpy, rhino3dm as r3d

bpy.ops.wm.read_factory_settings(use_empty=True)
mp = os.path.expanduser('~/Desktop/B1M 9.2.3dm')
print(f'Loading {os.path.getsize(mp)/1024/1024:.0f}MB...')
t0 = time.perf_counter()
model = r3d.File3dm.Read(mp)
print(f'Loaded in {time.perf_counter()-t0:.2f}s')
gc.disable()

scale = r3d.UnitSystem.UnitScale(model.Settings.ModelUnitSystem, r3d.UnitSystem.Meters) / bpy.context.scene.unit_settings.scale_length

# --- Phase 1a: Extract meshes (GetMesh only, 0.2s for B1M) ---
print('Phase 1a: Tessellating meshes...')
t0 = time.perf_counter()
mesh_data = []  # (msh, guid, name, layer_idx, mat_idx, color, is_idef, mat_src)
for ob in model.Objects:
    og = ob.Geometry
    if not og: continue
    ot = og.ObjectType
    if ot not in (r3d.ObjectType.Brep, r3d.ObjectType.Extrusion, r3d.ObjectType.Mesh, r3d.ObjectType.SubD):
        continue
    oa = ob.Attributes
    msh = None
    if ot == r3d.ObjectType.Brep:
        combined = r3d.Mesh()
        for fi in range(len(og.Faces)):
            try:
                fm = og.Faces[fi].GetMesh(r3d.MeshType.Any)
                if fm: combined.Append(fm)
            except: pass
        msh = combined
    elif ot == r3d.ObjectType.Mesh:
        msh = og
    elif ot == r3d.ObjectType.Extrusion:
        msh = og.GetMesh(r3d.MeshType.Any)
    elif ot == r3d.ObjectType.SubD:
        msh = r3d.Mesh.CreateFromSubDControlNet(og, False)
    if msh and len(msh.Vertices) > 0:
        is_idef = oa.IsInstanceDefinitionObject if hasattr(oa, "IsInstanceDefinitionObject") else False
        mesh_data.append((msh, oa.Id, oa.Name, oa.LayerIndex, oa.MaterialIndex,
                          oa.ObjectColor if hasattr(oa, "ObjectColor") else (200,200,200,255),
                          is_idef, oa.MaterialSource if hasattr(oa, "MaterialSource") else 0))
dt_extract = time.perf_counter() - t0
print(f'Extracted {len(mesh_data)} meshes in {dt_extract:.2f}s')

# --- Phase 1b: Build OBJ lines from pre-extracted meshes ---
print('Phase 1b: Building OBJ lines...')
t0 = time.perf_counter()
lines = []
v_global = 0; vt_global = 0
for i, (msh, guid, name, layer_idx, mat_idx, color, is_idef, mat_src) in enumerate(mesh_data):
    has_uv = len(msh.TextureCoordinates) > 0
    nv = len(msh.Vertices)
    lines.append(f'o obj_{i}')
    for v in msh.Vertices:
        lines.append(f'v {v.X*scale:.6f} {v.Y*scale:.6f} {v.Z*scale:.6f}')
    if has_uv:
        for uv in msh.TextureCoordinates:
            lines.append(f'vt {uv.X:.6f} {uv.Y:.6f}')
    for face in msh.Faces:
        f0,f1,f2,f3 = face[0]+1, face[1]+1, face[2]+1, face[3]+1
        if has_uv:
            a,b,c,d = f0+v_global, f1+v_global, f2+v_global, f3+v_global
            if f3 == f2:
                lines.append(f'f {a}/{a} {b}/{b} {c}/{c}')
            else:
                lines.append(f'f {a}/{a} {b}/{b} {c}/{c} {d}/{d}')
        else:
            if f3 == f2:
                lines.append(f'f {f0+v_global} {f1+v_global} {f2+v_global}')
            else:
                lines.append(f'f {f0+v_global} {f1+v_global} {f2+v_global} {f3+v_global}')
    v_global += nv
    if has_uv: vt_global += nv

obj_text = '\n'.join(lines)
dt_build = time.perf_counter() - t0
print(f'Built {len(lines):,} lines in {dt_build:.2f}s')

# --- Phase 2: Write + Import ---
print('Phase 2: Writing & importing...')
tmp = tempfile.NamedTemporaryFile(suffix='.obj', delete=False)
tmp.close()
t0 = time.perf_counter()
with open(tmp.name, 'w', buffering=16*1024*1024) as f:
    f.write(obj_text)
dt_write = time.perf_counter() - t0
obj_mb = os.path.getsize(tmp.name)/1024/1024
print(f'  Write: {dt_write:.1f}s ({obj_mb:.0f}MB)')

t0 = time.perf_counter()
bpy.ops.wm.obj_import(filepath=tmp.name)
dt_import = time.perf_counter() - t0
print(f'  Import: {dt_import:.1f}s | Objs: {len(bpy.data.objects)} | Meshes: {len(bpy.data.meshes)}')
os.unlink(tmp.name)

# --- Phase 3: Metadata ---
print('Phase 3: Metadata...')
t0 = time.perf_counter()
imported = sorted([o for o in bpy.data.objects if o.type == 'MESH' and o.name.startswith('obj_')],
                  key=lambda x: int(x.name.split('_')[1]))
print(f'  Matching {len(imported)} imported objects to {len(mesh_data)} model entries')
for i, ob in enumerate(imported):
    if i >= len(mesh_data): break
    msh, guid, name, layer_idx, mat_idx, color, is_idef, mat_src = mesh_data[i]
    ob['rhid'] = str(guid)
    if name: ob.name = name; ob['rhname'] = name
    ob.color = (color[0]/255.0, color[1]/255.0, color[2]/255.0, color[3]/255.0)
dt_meta = time.perf_counter() - t0
print(f'  Metadata: {dt_meta:.1f}s')

total = dt_extract + dt_build + dt_write + dt_import + dt_meta
print(f'\nTOTAL: {total:.1f}s | {len(bpy.data.objects)} objs | {len(bpy.data.meshes)} meshes')
