"""Test OBJ export/import path performance"""
import os, sys, time, tempfile
sys.path.insert(0, os.path.expanduser('~/Library/Application Support/Blender/5.2/scripts/addons'))
import bpy, rhino3dm as r3d

bpy.ops.wm.read_factory_settings(use_empty=True)

mp = os.path.expanduser('~/Desktop/B1M 9.2.3dm')
print(f'Loading {os.path.getsize(mp)/1024/1024:.0f}MB model...')
t0 = time.perf_counter()
model = r3d.File3dm.Read(mp)
print(f'Loaded in {time.perf_counter()-t0:.2f}s')

# Write OBJ
tmp = tempfile.NamedTemporaryFile(suffix='.obj', delete=False)
tmp.close()
print(f'Writing OBJ...')
t0 = time.perf_counter()
with open(tmp.name, 'w') as f:
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
                fm = og.Faces[fi].GetMesh(r3d.MeshType.Any)
                if fm: combined.Append(fm)
            msh = combined
        elif ot == r3d.ObjectType.Mesh:
            msh = og
        elif ot == r3d.ObjectType.Extrusion:
            msh = og.GetMesh(r3d.MeshType.Any)
        elif ot == r3d.ObjectType.SubD:
            msh = r3d.Mesh.CreateFromSubDControlNet(og, False)
        if msh and len(msh.Vertices) > 0:
            for v in msh.Vertices:
                f.write(f'v {v.X} {v.Y} {v.Z}\n')
            for face in msh.Faces:
                f0,f1,f2,f3 = face[0]+1, face[1]+1, face[2]+1, face[3]+1
                if f3 == f2:
                    f.write(f'f {f0} {f1} {f2}\n')
                else:
                    f.write(f'f {f0} {f1} {f2} {f3}\n')
dt_write = time.perf_counter() - t0
print(f'OBJ written: {dt_write:.2f}s ({os.path.getsize(tmp.name)/1024/1024:.0f}MB)')

# Import via Blender C importer
t0 = time.perf_counter()
bpy.ops.wm.obj_import(filepath=tmp.name)
dt_import = time.perf_counter() - t0
print(f'OBJ imported: {dt_import:.2f}s')
print(f'Total: {dt_write+dt_import:.2f}s | Objects: {len(bpy.data.objects)} | Meshes: {len(bpy.data.meshes)}')
os.unlink(tmp.name)
