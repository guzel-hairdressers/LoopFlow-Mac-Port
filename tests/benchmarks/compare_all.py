"""Compare Legacy vs OBJ on all 3 models with 5-min kill switch"""
import os, sys, subprocess, tempfile, time

BLENDER = "/Applications/Blender.app/Contents/MacOS/Blender"
ADDON = os.path.expanduser("~/Library/Application Support/Blender/5.2/scripts/addons")

# Sync latest code
SRC = "/Users/ruslan_faz/Desktop/Work/Job/LoopFlow Mac Port/src/LoopFlow_import_3dm"
for f in ["__init__.py", "read3dm.py"]:
    subprocess.run(["cp", os.path.join(SRC, f), os.path.join(ADDON, "LoopFlow_import_3dm", f)])
for f in ["__init__.py", "utils.py", "render_mesh.py", "instances.py", "material.py"]:
    subprocess.run(["cp", os.path.join(SRC, "converters", f), os.path.join(ADDON, "LoopFlow_import_3dm", "converters", f)])

MODELS = {
    "B1M 9.2": os.path.expanduser("~/Desktop/B1M 9.2.3dm"),
    "Game Center Roof": os.path.expanduser("~/Desktop/Game Center Roof.3dm"),
    "Roof Link": os.path.expanduser("~/Desktop/Roof Link.3dm"),
}

TIMEOUT = 300

def run_test(name, path, use_fast):
    mode = "OBJ" if use_fast else "LEGACY"
    sz = os.path.getsize(path)/(1024*1024)
    print(f"\n{'='*60}")
    print(f"{name} ({sz:.0f}MB) — {mode}")
    print(f"{'='*60}")

    script = f"""import os,sys,time,gc
sys.path.insert(0,'{ADDON}')
import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.preferences.addon_enable(module='LoopFlow_import_3dm')
from LoopFlow_import_3dm.read3dm import read_3dm
mp=r'{path}'
opts={{'filepath':mp,'is_update':False,'import_instances':True,'import_curves':False,'import_meshes':True,'weld_meshes':True,'nurbs_density':0.5,'subd_subsurf_level':3,'update_materials':False,'import_mode':'SYNC','link_materials_to':'PREFERENCES','use_fast_import':{str(use_fast)}}}
gc.disable()
t0=time.perf_counter();read_3dm(bpy.context,opts);dt=time.perf_counter()-t0
o=len(bpy.data.objects);m=len(bpy.data.meshes)
v=sum(len(x.data.vertices) for x in bpy.data.objects if x.type=='MESH')
f=sum(len(x.data.polygons) for x in bpy.data.objects if x.type=='MESH')
print(f'RESULT:{{dt:.1f}}s|{{o}}objs|{{m}}meshes|{{v}}v|{{f}}f')
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(script)
        tmp = f.name

    try:
        proc = subprocess.Popen([BLENDER, "--background", "--python", tmp], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            stdout, stderr = proc.communicate(timeout=TIMEOUT)
            found = False
            for line in stdout.split('\n'):
                if 'RESULT:' in line:
                    print(f"  {mode}: {line.split('RESULT:')[1]}")
                    found = True
            if not found:
                print(f"  {mode}: NO RESULT (crashed?)")
                for line in stderr.strip().split('\n')[-2:]:
                    if line.strip(): print(f"  ERR: {line.strip()[:120]}")
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            print(f"  {mode}: TIMEOUT (>5 min)")
    finally:
        try: os.unlink(tmp)
        except: pass

for name, path in MODELS.items():
    if not os.path.exists(path):
        print(f"\nSKIP {name}: not found")
        continue
    run_test(name, path, False)  # Legacy
    run_test(name, path, True)   # OBJ

print("\nDone!")
