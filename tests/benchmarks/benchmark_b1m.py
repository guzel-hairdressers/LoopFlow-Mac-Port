import os, sys, time, gc
sys.path.insert(0, os.path.expanduser('~/Library/Application Support/Blender/5.2/scripts/addons'))
import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.preferences.addon_enable(module='LoopFlow_import_3dm')
from LoopFlow_import_3dm.read3dm import read_3dm

mp = os.path.expanduser('~/Desktop/B1M 9.2.3dm')
gc.disable()
opts = {'filepath': mp, 'is_update': False, 'import_instances': True, 'import_curves': False,
        'import_meshes': True, 'weld_meshes': True, 'nurbs_density': 0.5, 'subd_subsurf_level': 3,
        'update_materials': False, 'import_mode': 'SYNC', 'link_materials_to': 'PREFERENCES'}
t0 = time.perf_counter()
r = read_3dm(bpy.context, opts)
dt = time.perf_counter() - t0
print(f'B1M: {dt:.2f}s | {len(bpy.data.objects)} objs | {len(bpy.data.meshes)} meshes')
