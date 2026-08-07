"""A/B test: measure UV and vertex color impact on B1M"""
import os, sys, time, gc
sys.path.insert(0, os.path.expanduser('~/Library/Application Support/Blender/5.2/scripts/addons'))

# Patch render_mesh to skip UV and VC
import LoopFlow_import_3dm.converters.render_mesh as rm_mod
original_fn = rm_mod.import_render_mesh

def no_uv_vc_import(context, ob, name, scale, options):
    """Skip UV and vertex color processing entirely"""
    og = ob.Geometry
    oa = ob.Attributes
    is_subd = (og.ObjectType == r3d.ObjectType.SubD)

    # ... same mesh extraction but skip UV assignment and vertex colors
    import rhino3dm as r3d
    from LoopFlow_import_3dm.converters import utils

    subd_crease_segments = []
    subd_vert_creases = {}
    if is_subd:
        try:
            subd_crease_segments, subd_vert_creases = rm_mod.extract_subd_creases(og, scale)
        except: pass

    needs_welding = options.get("weld_meshes", True) or is_subd
    msh = []
    if og.ObjectType == r3d.ObjectType.Extrusion:
        msh = [og.GetMesh(r3d.MeshType.Any)]
    elif og.ObjectType == r3d.ObjectType.Mesh:
        msh = [og]
    elif is_subd:
        msh = [r3d.Mesh.CreateFromSubDControlNet(og, False)]
    elif og.ObjectType == r3d.ObjectType.Brep:
        combined = r3d.Mesh()
        og_faces = og.Faces
        for f in range(len(og_faces)):
            try:
                fm = og_faces[f].GetMesh(r3d.MeshType.Any)
                if fm: combined.Append(fm)
            except: pass
        msh = [combined] if len(combined.Vertices) > 0 else []
    elif og.ObjectType == r3d.ObjectType.Surface:
        try:
            brep = og.ToBrep()
            if brep and hasattr(brep, "Faces"):
                combined = r3d.Mesh()
                for f in range(len(brep.Faces)):
                    fm = brep.Faces[f].GetMesh(r3d.MeshType.Any)
                    if fm: combined.Append(fm)
                msh = [combined] if len(combined.Vertices) > 0 else []
        except: msh = []

    fidx = 0
    faces = []
    vertices = []
    bb_min_x = bb_min_y = bb_min_z = float('inf')
    bb_max_x = bb_max_y = bb_max_z = float('-inf')
    n_tris = n_quads = 0

    for m in msh:
        if not m: continue
        m_faces = m.Faces
        m_verts = m.Vertices
        nv = len(m_verts)

        if fidx:
            for face in m_faces:
                f0,f1,f2,f3 = face
                if f3 == f2:
                    faces.append((f0+fidx, f1+fidx, f2+fidx)); n_tris += 1
                else:
                    faces.append((f0+fidx, f1+fidx, f2+fidx, f3+fidx)); n_quads += 1
        else:
            for face in m_faces:
                f0,f1,f2,f3 = face
                if f3 == f2:
                    faces.append((f0,f1,f2)); n_tris += 1
                else:
                    faces.append((f0,f1,f2,f3)); n_quads += 1

        fidx += nv
        if scale == 1.0:
            for v in m_verts:
                x,y,z = v.X, v.Y, v.Z
                vertices.append((x,y,z))
                if x < bb_min_x: bb_min_x = x
                elif x > bb_max_x: bb_max_x = x
                if y < bb_min_y: bb_min_y = y
                elif y > bb_max_y: bb_max_y = y
                if z < bb_min_z: bb_min_z = z
                elif z > bb_max_z: bb_max_z = z
        else:
            for v in m_verts:
                x,y,z = v.X*scale, v.Y*scale, v.Z*scale
                vertices.append((x,y,z))
                if x < bb_min_x: bb_min_x = x
                elif x > bb_max_x: bb_max_x = x
                if y < bb_min_y: bb_min_y = y
                elif y > bb_max_y: bb_max_y = y
                if z < bb_min_z: bb_min_z = z
                elif z > bb_max_z: bb_max_z = z

    # Signature and cache lookup
    nv = len(vertices); nf = len(faces)
    sig = utils.compute_mesh_signature_from_precomputed(nv,nf,bb_min_x,bb_min_y,bb_min_z,bb_max_x,bb_max_y,bb_max_z,n_tris,n_quads,nf-n_tris-n_quads) if (nv>0 and nf>0) else None
    pre_key, full_hash = sig if sig else (None, None)

    mesh_cache = options.get("mesh_sig_cache")
    if mesh_cache is None:
        mesh_cache = {}; options["mesh_sig_cache"] = mesh_cache

    if pre_key is not None and pre_key in mesh_cache:
        bucket = mesh_cache[pre_key]
        if full_hash in bucket:
            cached = bucket[full_hash]
            options.setdefault("_shared_mesh_names", set()).add(cached.name)
            options.setdefault("_mesh_sharing_hits", 0)
            options["_mesh_sharing_hits"] += 1
            return cached

    mesh_name = oa.Name if oa.Name else f"LFM_{oa.Id}"
    tags = utils.create_tag_dict(oa.Id, mesh_name)
    mesh = utils.get_or_create_iddata(bpy.context.blend_data.meshes, tags, None)
    mesh.clear_geometry()
    mesh.from_pydata(vertices, [], faces, shade_flat=False)

    if pre_key is not None and full_hash is not None:
        bucket = mesh_cache.setdefault(pre_key, {})
        bucket[full_hash] = mesh

    # SKIP UV and vertex color processing
    # (The UV and vertex color code is omitted entirely)

    is_single_mesh = (len(msh)==1 and (og.ObjectType==r3d.ObjectType.Mesh or og.ObjectType==r3d.ObjectType.Brep))
    should_weld = is_subd or (len(msh)>1 and not(og.ObjectType==r3d.ObjectType.Brep)) or (needs_welding and not is_single_mesh)
    if should_weld:
        import bmesh
        bm = bmesh.new(); bm.from_mesh(mesh)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.001)
        bm.to_mesh(mesh); bm.free()
        if not is_subd and bpy.app.version >= (4,1):
            mesh.set_sharp_from_angle(angle=0.523599)
    return mesh

# Run test
rm_mod.import_render_mesh = no_uv_vc_import

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
print(f'B1M NO UV/VC: {dt:.2f}s | {len(bpy.data.objects)} objs | {len(bpy.data.meshes)} meshes')
print(f'Savings vs baseline (19.80s): {19.80-dt:.2f}s ({(19.80-dt)/19.80*100:.0f}%)')
