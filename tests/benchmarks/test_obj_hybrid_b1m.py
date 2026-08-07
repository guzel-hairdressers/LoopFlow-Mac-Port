"""OBJ Hybrid: extract mesh data → write OBJ → import via Blender C → reconcile metadata"""
import os, sys, time, tempfile, gc
sys.path.insert(0, os.path.expanduser('~/Library/Application Support/Blender/5.2/scripts/addons'))
import bpy, rhino3dm as r3d

bpy.ops.wm.read_factory_settings(use_empty=True)

# Load model
mp = os.path.expanduser('~/Desktop/B1M 9.2.3dm')
print(f'Loading {os.path.getsize(mp)/1024/1024:.0f}MB...')
t0 = time.perf_counter()
model = r3d.File3dm.Read(mp)
print(f'Loaded in {time.perf_counter()-t0:.2f}s')

gc.disable()

# --- Phase 1: Accumulate OBJ data ---
print('Phase 1: Building OBJ...')
t0 = time.perf_counter()

# Pre-build layer/material structures (same as current import)
from LoopFlow_import_3dm.converters import handle_materials, handle_layers, handle_instance_definitions, utils
from LoopFlow_import_3dm.read3dm import create_or_get_top_layer

scale = r3d.UnitSystem.UnitScale(model.Settings.ModelUnitSystem, r3d.UnitSystem.Meters) / bpy.context.scene.unit_settings.scale_length
layerids, materials = {}, {}
handle_materials(bpy.context, model, materials, False)
layer_visibility = handle_layers(bpy.context, model, create_or_get_top_layer(bpy.context, mp), layerids, materials, False, True)

import_instances = True
if import_instances and hasattr(model, "InstanceDefinitions") and len(model.InstanceDefinitions) > 0:
    handle_instance_definitions(bpy.context, model, create_or_get_top_layer(bpy.context, mp), "Instance Definitions")

# Map: obj_index → (rhino_guid, rhino_name, layer_collection, material, color, is_idef)
obj_map = []
lines = []
for idx, ob in enumerate(model.Objects):
    og = ob.Geometry
    if not og: continue
    ot = og.ObjectType
    if ot not in (r3d.ObjectType.Brep, r3d.ObjectType.Extrusion, r3d.ObjectType.Mesh, r3d.ObjectType.SubD):
        continue

    oa = ob.Attributes
    is_idef = oa.IsInstanceDefinitionObject if hasattr(oa, "IsInstanceDefinitionObject") else False

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

    if not msh or len(msh.Vertices) == 0:
        continue

    obj_map.append((oa.Id, oa.Name, layerids.get(oa.LayerIndex), materials.get(oa.MaterialIndex, materials.get(-1)), oa.ObjectColor if hasattr(oa, "ObjectColor") else (200,200,200,255), is_idef))

    # Write OBJ entry
    lines.append(f'o obj_{len(obj_map)-1}')
    for v in msh.Vertices:
        lines.append(f'v {v.X*scale:.6f} {v.Y*scale:.6f} {v.Z*scale:.6f}')
    for uv in msh.TextureCoordinates:
        lines.append(f'vt {uv.X:.6f} {uv.Y:.6f}')
    for face in msh.Faces:
        f0,f1,f2,f3 = face[0]+1, face[1]+1, face[2]+1, face[3]+1
        if f3 == f2:
            lines.append(f'f {f0}/{f0} {f1}/{f1} {f2}/{f2}')
        else:
            lines.append(f'f {f0}/{f0} {f1}/{f1} {f2}/{f2} {f3}/{f3}')

dt_build = time.perf_counter() - t0
obj_text = '\n'.join(lines)
dt_total = time.perf_counter() - t0
print(f'Phase 1 done: {dt_build:.1f}s build + {dt_total-dt_build:.1f}s join = {dt_total:.1f}s | {len(obj_map)} objects')

# --- Phase 2: Write OBJ to temp file and import ---
print('Phase 2: Writing and importing OBJ...')
tmp = tempfile.NamedTemporaryFile(suffix='.obj', delete=False)
tmp.close()
t0 = time.perf_counter()
with open(tmp.name, 'w') as f:
    f.write(obj_text)
dt_write = time.perf_counter() - t0
print(f'  Write: {dt_write:.1f}s ({os.path.getsize(tmp.name)/1024/1024:.0f}MB)')

t0 = time.perf_counter()
bpy.ops.wm.obj_import(filepath=tmp.name)
dt_import = time.perf_counter() - t0
print(f'  Import: {dt_import:.1f}s')
print(f'Phase 2 total: {dt_write+dt_import:.1f}s | Objects: {len(bpy.data.objects)}, Meshes: {len(bpy.data.meshes)}')
os.unlink(tmp.name)

# --- Phase 3: Reconcile metadata ---
print('Phase 3: Reconciling metadata...')
t0 = time.perf_counter()
imported_objs = [o for o in bpy.data.objects if o.name.startswith('obj_') and o.type == 'MESH']
print(f'  Found {len(imported_objs)} imported mesh objects')

# Match imported objects to model objects by index
for i, ob in enumerate(imported_objs):
    if i >= len(obj_map): break
    guid, name, layer_col, mat, color, is_idef = obj_map[i]
    ob['rhid'] = str(guid)
    if name: ob['rhname'] = name; ob.name = name
    if mat and mat.name not in ob.material_slots:
        ob.data.materials.append(mat)
    ob.color = (color[0]/255.0, color[1]/255.0, color[2]/255.0, color[3]/255.0)
    if layer_col and ob.name not in layer_col.objects:
        layer_col.objects.link(ob)
dt_reconcile = time.perf_counter() - t0
print(f'Phase 3 done: {dt_reconcile:.1f}s')

total = dt_total + dt_write + dt_import + dt_reconcile
print(f'\nTOTAL: {total:.1f}s | Objects: {len(bpy.data.objects)}, Meshes: {len(bpy.data.meshes)}')
