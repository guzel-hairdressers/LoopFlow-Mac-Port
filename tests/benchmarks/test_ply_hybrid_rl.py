"""PLY Hybrid for Roof Link"""
import os, sys, time, tempfile, gc
from array import array
sys.path.insert(0, os.path.expanduser('~/Library/Application Support/Blender/5.2/scripts/addons'))
import bpy, rhino3dm as r3d

bpy.ops.wm.read_factory_settings(use_empty=True)
mp = os.path.expanduser('~/Desktop/Roof Link.3dm')
print(f'Loading {os.path.getsize(mp)/1024/1024:.0f}MB...')
t0=time.perf_counter()
model=r3d.File3dm.Read(mp)
print(f'Loaded in {time.perf_counter()-t0:.1f}s')
gc.disable()

from LoopFlow_import_3dm.converters import handle_materials, handle_layers, handle_instance_definitions
from LoopFlow_import_3dm.read3dm import create_or_get_top_layer

scale = r3d.UnitSystem.UnitScale(model.Settings.ModelUnitSystem, r3d.UnitSystem.Meters) / bpy.context.scene.unit_settings.scale_length
layerids, materials = {}, {}
handle_materials(bpy.context, model, materials, False)
toplayer = create_or_get_top_layer(bpy.context, mp)
handle_layers(bpy.context, model, toplayer, layerids, materials, False, True)
if hasattr(model, "InstanceDefinitions") and len(model.InstanceDefinitions) > 0:
    handle_instance_definitions(bpy.context, model, toplayer, "Instance Definitions")

# Phase 1: Build PLY binary data (fast C-level arrays)
print('Phase 1: Building PLY...')
t0=time.perf_counter()
verts = array('f')
face_counts = array('B')
face_indices = array('I')
total_v = 0; total_f = 0
idef_count = 0; iref_count = 0; subd_count = 0

for ob in model.Objects:
    og = ob.Geometry
    if not og: continue
    ot = og.ObjectType
    oa = ob.Attributes
    is_idef = oa.IsInstanceDefinitionObject if hasattr(oa, "IsInstanceDefinitionObject") else False

    if ot == r3d.ObjectType.InstanceReference:
        iref_count += 1; continue
    if is_idef:
        idef_count += 1; continue
    if ot == r3d.ObjectType.SubD:
        subd_count += 1; continue
    if ot not in (r3d.ObjectType.Brep, r3d.ObjectType.Extrusion, r3d.ObjectType.Mesh):
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
    if not msh or len(msh.Vertices) == 0: continue

    nv = len(msh.Vertices); nf = len(msh.Faces)
    total_v += nv; total_f += nf
    for v in msh.Vertices:
        verts.extend((v.X*scale, v.Y*scale, v.Z*scale))
    for face in msh.Faces:
        f0,f1,f2,f3 = face[0], face[1], face[2], face[3]
        if f3 == f2:
            face_counts.append(3); face_indices.extend((f0,f1,f2))
        else:
            face_counts.append(4); face_indices.extend((f0,f1,f2,f3))

dt_build = time.perf_counter()-t0
print(f'Built PLY data: {total_v:,}v {total_f:,}f in {dt_build:.1f}s')

# Phase 2: Write + Import
print('Phase 2: Write & Import...')
tmp = tempfile.NamedTemporaryFile(suffix='.ply', delete=False)
tmp.close()
t0=time.perf_counter()
header = f"""ply
format binary_little_endian 1.0
element vertex {total_v}
property float x
property float y
property float z
element face {total_f}
property list uchar int vertex_indices
end_header
"""
with open(tmp.name, 'wb') as f:
    f.write(header.encode())
    f.write(verts.tobytes())
    idx_pos = 0
    for count in face_counts:
        f.write(bytes([count]))
        f.write(face_indices[idx_pos:idx_pos+count].tobytes())
        idx_pos += count
dt_write = time.perf_counter()-t0
print(f'  Written {os.path.getsize(tmp.name)/1024/1024:.0f}MB in {dt_write:.1f}s')

t0=time.perf_counter()
bpy.ops.wm.ply_import(filepath=tmp.name)
dt_import = time.perf_counter()-t0
print(f'  Imported in {dt_import:.1f}s | {len(bpy.data.objects)} obj, {len(bpy.data.meshes)} mesh')
os.unlink(tmp.name)

total = dt_build+dt_write+dt_import
print(f'\nPLY TOTAL: {total:.1f}s | Skipped: {idef_count} idef, {iref_count} iref, {subd_count} subd')
