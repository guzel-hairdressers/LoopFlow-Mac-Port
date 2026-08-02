import os
import shutil
import zipfile

def package_all():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src_dir = os.path.join(root, "src")
    releases_dir = os.path.join(root, "releases")
    os.makedirs(releases_dir, exist_ok=True)

    # 1. Package LoopFlow_import_3dm.zip from src/LoopFlow_import_3dm
    src_3dm = os.path.join(src_dir, "LoopFlow_import_3dm")
    zip_3dm_root = os.path.join(releases_dir, "LoopFlow_import_3dm.zip")
    
    with zipfile.ZipFile(zip_3dm_root, 'w', zipfile.ZIP_DEFLATED) as z:
        for folder, _, filenames in os.walk(src_3dm):
            for filename in filenames:
                if filename.endswith(('.pyc', '.DS_Store', '.pyo')):
                    continue
                filepath = os.path.join(folder, filename)
                arcname = os.path.relpath(filepath, os.path.dirname(src_3dm))
                z.write(filepath, arcname)
    print(f"Created ZIP archive: releases/LoopFlow_import_3dm.zip")

    # 2. Package LoopFlow_Toolkit.zip from src/LoopFlow_Toolkit
    src_tk = os.path.join(src_dir, "LoopFlow_Toolkit")
    zip_tk_root = os.path.join(releases_dir, "LoopFlow_Toolkit.zip")

    with zipfile.ZipFile(zip_tk_root, 'w', zipfile.ZIP_DEFLATED) as z:
        for folder, _, filenames in os.walk(src_tk):
            for filename in filenames:
                if filename.endswith(('.pyc', '.DS_Store', '.pyo')):
                    continue
                filepath = os.path.join(folder, filename)
                arcname = os.path.relpath(filepath, os.path.dirname(src_tk))
                z.write(filepath, arcname)
    print(f"Created ZIP archive: releases/LoopFlow_Toolkit.zip")

    # 3. Sync Rhino assets to releases/
    src_rh = os.path.join(src_dir, "Rhino")
    for item in os.listdir(src_rh):
        s_item = os.path.join(src_rh, item)
        d_item = os.path.join(releases_dir, item)
        if os.path.isdir(s_item):
            if os.path.exists(d_item):
                shutil.rmtree(d_item)
            shutil.copytree(s_item, d_item)
        else:
            shutil.copy2(s_item, d_item)
            
    # Also mirror zip copies to releases/Rhino if expected
    rh_releases = os.path.join(releases_dir, "LoopFlow_Rhino-to-Blender-Sync")
    if os.path.exists(rh_releases):
        shutil.copy2(zip_3dm_root, os.path.join(rh_releases, "LoopFlow_import_3dm.zip"))
        shutil.copy2(zip_tk_root, os.path.join(rh_releases, "LoopFlow_Toolkit.zip"))

    print("ALL RELEASE PACKAGES COMPILED & SYNCHRONIZED SUCCESSFULLY!")

if __name__ == "__main__":
    package_all()
