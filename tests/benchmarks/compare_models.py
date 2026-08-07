import os, sys, time
sys.path.insert(0, os.path.expanduser('~/Library/Application Support/Blender/5.2/scripts/addons'))
import rhino3dm as r3d
from collections import Counter
import bpy

for fname in ['B1M 9.2.3dm', 'Game Center Roof.3dm', 'Roof Link.3dm']:
    fp = os.path.expanduser(f'~/Desktop/{fname}')
    if not os.path.exists(fp): continue
    sz = os.path.getsize(fp)/1024/1024
    m = r3d.File3dm.Read(fp)
    types = Counter()
    for ob in m.Objects:
        if ob.Geometry:
            types[ob.Geometry.ObjectType] += 1
    n = len(m.Objects)
    del m
    nb = types.get(r3d.ObjectType.Brep, 0)
    nm = types.get(r3d.ObjectType.Mesh, 0)
    ni = types.get(r3d.ObjectType.InstanceReference, 0)
    nc = types.get(r3d.ObjectType.Curve, 0)
    nmo = nb + nm
    pct = nmo/max(1,n)*100
    print(f'{fname}: {sz:.0f}MB | {n:,} objs | {nb:,}Brep + {nm:,}Mesh = {nmo:,} ({pct:.0f}%) | {ni:,}Ref + {nc:,}Curve')
