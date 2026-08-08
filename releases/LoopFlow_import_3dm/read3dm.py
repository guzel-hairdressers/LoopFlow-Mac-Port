import os
import sys
import time
import json
import gc
import resource
import tempfile
from array import array

from pathlib import Path

import bpy
from typing import Dict, Any, Set

from . import converters
import rhino3dm as r3d

def get_process_ram_mb():
    try:
        import psutil
        return psutil.Process().memory_info().rss / (1024.0 * 1024.0)
    except Exception:
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == 'darwin':
            return rss / (1024.0 * 1024.0)
        return rss / 1024.0

class SubOpProfiler:
    def __init__(self, op_name, log_file_path):
        self.op_name = op_name
        self.log_file_path = log_file_path
        self.start_total_time = time.perf_counter()
        self.start_ram = get_process_ram_mb()
        self.last_step_time = self.start_total_time
        self.last_ram = self.start_ram
        self.steps = []

    def step(self, step_name):
        now_time = time.perf_counter()
        now_ram = get_process_ram_mb()
        dt = round(now_time - self.last_step_time, 4)
        ram_delta = round(now_ram - self.last_ram, 2)
        
        step_data = {
            "step": step_name,
            "dt_sec": dt,
            "ram_mb": round(now_ram, 2),
            "ram_delta_mb": ram_delta
        }
        self.steps.append(step_data)
        print(f"  - [{step_name}]: {dt}s | RAM: {round(now_ram, 2)}MB ({ram_delta:+}MB)", flush=True)

        self.last_step_time = now_time
        self.last_ram = now_ram

    def finish(self, info_msg=""):
        total_time = round(time.perf_counter() - self.start_total_time, 4)
        final_ram = round(get_process_ram_mb(), 2)
        total_ram_delta = round(final_ram - self.start_ram, 2)

        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "version": "0.0.52",
            "op": self.op_name,
            "total_sec": total_time,
            "ram_mb": final_ram,
            "ram_delta_mb": total_ram_delta,
            "info": info_msg,
            "steps": self.steps
        }

        log_json_line = json.dumps(entry)
        print(f"LoopFlow Execution Profile: {log_json_line}", flush=True)

        try:
            os.makedirs(os.path.dirname(self.log_file_path), exist_ok=True)
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                f.write(log_json_line + "\n")
        except Exception as e:
            print(f"LoopFlow Profiler Warning: Could not write log file: {e}")

def create_or_get_top_layer(context, filepath, is_update=False, import_mode='SYNC'):
    master_col_name = "LoopFlow"
    file_stem = Path(filepath).stem if filepath else "R2B"

    master_col = context.blend_data.collections.get(master_col_name)
    if not master_col:
        master_col = context.blend_data.collections.new(name=master_col_name)
    if master_col.name not in context.scene.collection.children:
        try:
            context.scene.collection.children.link(master_col)
        except Exception:
            pass

    if import_mode == 'OVERRIDE':
        # OVERRIDE MODE: Remove ONLY the file collection matching file_stem inside LoopFlow
        old_toplayer = context.blend_data.collections.get(file_stem)
        if old_toplayer:
            def remove_col_recursive(col):
                for child in list(col.children):
                    remove_col_recursive(child)
                for obj in list(col.objects):
                    try:
                        context.blend_data.objects.remove(obj, do_unlink=True)
                    except Exception:
                        pass
                try:
                    context.blend_data.collections.remove(col, do_unlink=True)
                except Exception:
                    pass

            remove_col_recursive(old_toplayer)
            context.view_layer.update()

        toplayer = context.blend_data.collections.new(name=file_stem)
        master_col.children.link(toplayer)
        return toplayer

    elif import_mode == 'APPEND':
        # APPEND MODE: If file_stem collection exists inside LoopFlow, create file_stem.001, .002
        top_name = file_stem
        if top_name in context.blend_data.collections:
            idx = 1
            while f"{file_stem}.{idx:03d}" in context.blend_data.collections:
                idx += 1
            top_name = f"{file_stem}.{idx:03d}"

        toplayer = context.blend_data.collections.new(name=top_name)
        master_col.children.link(toplayer)
        return toplayer

    else:
        # LIVE SYNC MODE
        toplayer = context.blend_data.collections.get(file_stem)
        if not toplayer:
            toplayer = context.blend_data.collections.new(name=file_stem)
        if toplayer.name not in master_col.children:
            try:
                master_col.children.link(toplayer)
            except Exception:
                pass
        return toplayer
    return toplayer

def read_3dm(context : bpy.types.Context, options : Dict[str, Any]) -> Set[str]:
    import LoopFlow_import_3dm as main_mod
    orig_sync = main_mod._is_syncing_layers
    main_mod._is_syncing_layers = True

    try:
        return _read_3dm_internal(context, options)
    finally:
        main_mod._is_syncing_layers = orig_sync

def _import_via_ply_fastpath(context, model, toplayer, layerids, materials, scale, options, profiler, filepath):
    """Fast path: write PLY binary → import → split by loose parts → reconcile metadata."""
    import rhino3dm as r3d

    # Build layer info cache
    layer_info_cache = {}
    if model and hasattr(model, "Layers"):
        for l_idx in range(len(model.Layers)):
            l = model.Layers[l_idx]
            l_mat_idx = -1
            if hasattr(l, "RenderMaterialInstanceId") and str(l.RenderMaterialInstanceId) in materials:
                l_mat_idx = str(l.RenderMaterialInstanceId)
            elif hasattr(l, "RenderMaterialIndex"): l_mat_idx = l.RenderMaterialIndex
            elif hasattr(l, "MaterialIndex"): l_mat_idx = l.MaterialIndex
            l_color = (200, 200, 200, 255)
            try: l_color = l.Color
            except Exception: pass
            layer_info_cache[l_idx] = (l_mat_idx, l_color)

    # Phase 1: Build PLY binary data
    profiler.step("9. [PLY] Building geometry data")
    dup_map = {}       # obj_meta_index → original_obj_idx (for duplicates)
    sig_to_obj = {}    # signature → obj_idx (dedup lookup)
    verts = array('f')
    face_counts = array('B')
    face_indices = array('I')
    obj_meta = []      # (guid, name, layer_idx, mat_idx, color, is_idef)
    idef_objects = []
    iref_objects = []
    subd_objects = []
    total_v = 0; total_f = 0

    for ob in model.Objects:
        og = ob.Geometry
        if not og: continue
        ot = og.ObjectType
        oa = ob.Attributes
        is_idef = oa.IsInstanceDefinitionObject if hasattr(oa, "IsInstanceDefinitionObject") else False

        if ot == r3d.ObjectType.InstanceReference:
            iref_objects.append(ob); continue
        if is_idef:
            if ot in (r3d.ObjectType.Brep, r3d.ObjectType.Extrusion, r3d.ObjectType.Mesh, r3d.ObjectType.SubD):
                idef_objects.append(ob)
            continue
        if ot == r3d.ObjectType.SubD:
            subd_objects.append(ob); continue
        if ot not in (r3d.ObjectType.Brep, r3d.ObjectType.Extrusion, r3d.ObjectType.Mesh):
            continue

        msh = None
        if ot == r3d.ObjectType.Brep:
            combined = r3d.Mesh()
            for fi in range(len(og.Faces)):
                try:
                    fm = og.Faces[fi].GetMesh(r3d.MeshType.Any)
                    if fm: combined.Append(fm)
                except Exception: pass
            msh = combined
        elif ot == r3d.ObjectType.Mesh: msh = og
        elif ot == r3d.ObjectType.Extrusion: msh = og.GetMesh(r3d.MeshType.Any)
        if not msh or len(msh.Vertices) == 0: continue

        nv = len(msh.Vertices); nf = len(msh.Faces)
        mat_idx = -1; color = (200,200,200,255)
        try:
            mat_idx = oa.MaterialIndex
            if oa.MaterialSource == r3d.ObjectMaterialSource.MaterialFromLayer or mat_idx < 0:
                l_info = layer_info_cache.get(oa.LayerIndex, (-1,(200,200,200,255)))
                mat_idx = l_info[0]; color = l_info[1]
            elif oa.ColorSource == r3d.ObjectColorSource.ColorFromObject:
                color = oa.ObjectColor
            else: color = layer_info_cache.get(oa.LayerIndex, (-1,(200,200,200,255)))[1]
        except Exception: pass

        # Geometry dedup signature (compute before OBJ write)
        bb_min_x=bb_min_y=bb_min_z=float('inf'); bb_max_x=bb_max_y=bb_max_z=float('-inf')
        n_tris=0; n_quads=0
        for face in msh.Faces:
            if face[3]==face[2]: n_tris+=1
            else: n_quads+=1
        for v in msh.Vertices:
            x,y,z=v.X*scale,v.Y*scale,v.Z*scale
            verts.extend((x,y,z))
            if x<bb_min_x:bb_min_x=x
            elif x>bb_max_x:bb_max_x=x
            if y<bb_min_y:bb_min_y=y
            elif y>bb_max_y:bb_max_y=y
            if z<bb_min_z:bb_min_z=z
            elif z>bb_max_z:bb_max_z=z
        total_v+=nv; total_f+=nf

        sig = converters.utils.compute_mesh_signature_from_precomputed(
            nv,nf,bb_min_x,bb_min_y,bb_min_z,bb_max_x,bb_max_y,bb_max_z,
            n_tris,n_quads,nf-n_tris-n_quads) if (nv>0 and nf>0) else None
        pre_key,full_hash = sig if sig else (None,None)

        meta_entry = (oa.Id, oa.Name if oa.Name else f"LF_{oa.Id}", oa.LayerIndex, mat_idx, color, False)
        obj_idx = len(obj_meta)
        obj_meta.append(meta_entry)

        if pre_key is not None and pre_key in sig_to_obj:
            bucket = sig_to_obj[pre_key]
            if full_hash in bucket:
                dup_map[obj_idx] = bucket[full_hash]
                continue  # skip OBJ write
            bucket[full_hash] = obj_idx
        elif pre_key is not None:
            sig_to_obj.setdefault(pre_key,{})[full_hash]=obj_idx
        for face in msh.Faces:
            f0,f1,f2,f3=face[0],face[1],face[2],face[3]
            if f3==f2:
                face_counts.append(3); face_indices.extend((f0,f1,f2))
            else:
                face_counts.append(4); face_indices.extend((f0,f1,f2,f3))

    profiler.step(f"9b. [PLY] Built {total_v:,}v {total_f:,}f for {len(obj_meta)} objects | skipped {len(idef_objects)} idef, {len(iref_objects)} iref, {len(subd_objects)} subd")

    if total_v == 0:
        profiler.step("9. [PLY] No geometry")
        return

    # Phase 2a: Create instance empties (before namemap gets big)
    iref_pending = {}; iref_count = 0
    if iref_objects:
        idef_map = options.get("idef_map", {})
        tag_cache = {}
        for ob in iref_objects:
            try:
                parent_id = ob.Geometry.ParentIdefId
                if parent_id not in tag_cache:
                    bn = idef_map.get(parent_id, f"Block {parent_id}")
                    ct = converters.utils.create_tag_dict(parent_id, bn, None, None, True)
                    idef_col = converters.utils.get_or_create_iddata(context.blend_data.collections, ct, None)
                    tag_cache[parent_id] = idef_col
                name = ob.Attributes.Name if ob.Attributes.Name else f"LF_{ob.Attributes.Id}"
                iref = bpy.data.objects.new(name=name, object_data=None)
                iref['rhid'] = str(ob.Attributes.Id)
                iref.empty_display_type = 'PLAIN_AXES'; iref.instance_type = 'COLLECTION'
                iref.instance_collection = tag_cache[parent_id]
                iref.matrix_world = converters.utils.matrix_from_xform(ob.Geometry.Xform, scale)
                iref_pending.setdefault(layerids.get(ob.Attributes.LayerIndex, context.scene.collection), []).append(iref)
                iref_count += 1
            except Exception: pass
        profiler.step(f"9c. [PLY] Created {iref_count} instance empties")

    # Phase 2b: Write PLY + Import
    tmp = tempfile.NamedTemporaryFile(suffix='.ply', delete=False); tmp.close()
    try:
        hdr = f'ply\nformat binary_little_endian 1.0\nelement vertex {total_v}\nproperty float x\nproperty float y\nproperty float z\nelement face {total_f}\nproperty list uchar int vertex_indices\nend_header\n'
        with open(tmp.name, 'wb') as f:
            f.write(hdr.encode()); f.write(verts.tobytes())
            ip = 0
            for c in face_counts:
                f.write(bytes([c])); f.write(face_indices[ip:ip+c].tobytes()); ip += c
        profiler.step(f"10. [PLY] Written {os.path.getsize(tmp.name)/1024/1024:.0f}MB PLY")

        bpy.ops.wm.ply_import(filepath=tmp.name)
        # PLY creates 1 merged mesh — split by loose parts to separate
        pl_obj = context.active_object
        if pl_obj:
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.separate(type='LOOSE')
            bpy.ops.object.mode_set(mode='OBJECT')
        profiler.step(f"11. [PLY] Imported & split into {len(context.blend_data.objects)} objects")
    finally:
        try: os.unlink(tmp.name)
        except Exception: pass

    # Phase 3: Map split objects to metadata
    # After split: original = obj_meta[0], .001 = obj_meta[1], .002 = obj_meta[2], ...
    split_objs = sorted(
        [o for o in context.blend_data.objects if o.type == 'MESH' and o != pl_obj and o.name.startswith(pl_obj.name)],
        key=lambda o: (len(o.name), o.name)
    )
    all_parts = [pl_obj] + split_objs  # original is first, then .001, .002, ...

    pending_links = {}
    for i in range(min(len(all_parts), len(obj_meta))):
        ob = all_parts[i]; guid, name, layer_idx, mat_idx, color = obj_meta[i]
        ob.name = f'ply_{i:06d}'  # short unique name, avoids O(N²) namemap
        ob['rhid'] = str(guid)
        if name: ob['rhname'] = name
        ob.color = (color[0]/255.0, color[1]/255.0, color[2]/255.0, color[3]/255.0)
        # Material: SKIP (assigned later via sync — 190s bottleneck on 52K meshes)
        pending_links.setdefault(layerids.get(layer_idx, context.scene.collection), []).append(ob)

    profiler.step(f"12. [PLY] Mapped {len(all_parts)} objects")

    # Bulk link
    for col, objs in pending_links.items():
        for ob in objs:
            try: col.objects.link(ob)
            except Exception: pass
    for layer, objs in iref_pending.items():
        for iref in objs:
            try: layer.objects.link(iref)
            except Exception: pass
    profiler.step(f"12b. [PLY] Linked objects and {iref_count} instances")

    # Block templates
    if idef_objects:
        link_opts = options.copy(); link_opts["defer_link"] = True
        idef_obj_map = options.get("idef_obj_map", {})
        converters.utils.reset_all_dict(context)
        idef_pend = {}
        for ob in idef_objects:
            try:
                t = converters.convert_object(context, ob, model, layerids, materials, scale, link_opts)
                if t:
                    blk = idef_obj_map.get(str(ob.Attributes.Id))
                    if blk: idef_pend.setdefault(blk, []).append(t)
                    t.hide_viewport = True; t.hide_render = True
            except Exception: pass
        for col, objs in idef_pend.items():
            for ob in objs:
                try: col.objects.link(ob)
                except Exception: pass
        profiler.step(f"13. [PLY] {len(idef_objects)} block templates")

    # SubD objects
    if subd_objects:
        link_opts = options.copy(); link_opts["defer_link"] = True
        subd_pend = {}
        for ob in subd_objects:
            try:
                t = converters.convert_object(context, ob, model, layerids, materials, scale, link_opts)
                if t: subd_pend.setdefault(layerids.get(ob.Attributes.LayerIndex, context.scene.collection), []).append(t)
            except Exception: pass
        for col, objs in subd_pend.items():
            for ob in objs:
                try: col.objects.link(ob)
                except Exception: pass
        profiler.step(f"14. [PLY] {len(subd_objects)} SubD objects")

    profiler.finish(f"PLY Fast-Path Complete ({len(all_parts)} objects + {len(idef_objects)} blocks + {iref_count} instances + {len(subd_objects)} subd)")


def _import_via_obj_fastpath(context, model, toplayer, layerids, materials, scale, options, profiler, filepath, layer_visibility=None):
    """Fast path: write OBJ from 3DM meshes → import via Blender C importer → reconcile metadata."""
    import rhino3dm as r3d

    # Phase 1: Build OBJ text from model objects
    profiler.step("9. [OBJ] Building geometry data")

    # Build layer info cache (same as convert_object)
    layer_info_cache = {}
    if model and hasattr(model, "Layers"):
        for l_idx in range(len(model.Layers)):
            l = model.Layers[l_idx]
            l_mat_idx = -1
            if hasattr(l, "RenderMaterialInstanceId") and str(l.RenderMaterialInstanceId) in materials:
                l_mat_idx = str(l.RenderMaterialInstanceId)
            elif hasattr(l, "RenderMaterialIndex"):
                l_mat_idx = l.RenderMaterialIndex
            elif hasattr(l, "MaterialIndex"):
                l_mat_idx = l.MaterialIndex
            l_color = (200, 200, 200, 255)
            try: l_color = l.Color
            except Exception: pass
            layer_info_cache[l_idx] = (l_mat_idx, l_color)

    # Build MTL material definitions (written alongside OBJ for C-speed material assignment)
    mtl_lines = ['# LoopFlow MTL']
    mat_names_written = set()
    if materials:
        for key, blmat in materials.items():
            if isinstance(key, int) and key >= 0 and blmat.name not in mat_names_written:
                mat_names_written.add(blmat.name)
                dc = getattr(blmat, 'diffuse_color', (0.8, 0.8, 0.8, 1.0))
                mtl_lines.append(f'\nnewmtl {blmat.name}')
                mtl_lines.append(f'Kd {dc[0]:.4f} {dc[1]:.4f} {dc[2]:.4f}')

    dup_map = {}       # obj_meta_index → original_obj_idx (for geometry dedup)
    sig_to_obj = {}    # geometry signature → obj_idx
    lines = ['# OBJ from LoopFlow']
    obj_meta = []  # parallel array: (guid, name, layer_idx, mat_idx, color, is_idef)
    v_off = 0
    vt_off = 0
    last_mat_name = None
    # Objects that need Python-path handling (not OBJ):
    idef_objects = []   # Block template objects → [Block] collections
    iref_objects = []   # Instance references → empties
    subd_objects = []   # SubD → needs modifier + crease edges (Python path)

    for ob in model.Objects:
        og = ob.Geometry
        if not og: continue
        ot = og.ObjectType
        oa = ob.Attributes
        is_idef = oa.IsInstanceDefinitionObject if hasattr(oa, "IsInstanceDefinitionObject") else False

        # InstanceReferences: skip OBJ, handle as empties after import
        if ot == r3d.ObjectType.InstanceReference:
            iref_objects.append(ob)
            continue

        # Block template objects: skip OBJ, handle via Python path into [Block] collections
        if is_idef:
            if ot in (r3d.ObjectType.Brep, r3d.ObjectType.Extrusion, r3d.ObjectType.Mesh, r3d.ObjectType.SubD):
                idef_objects.append(ob)
            continue

        # SubD objects: skip OBJ, handle via Python path (needs modifier + crease edges)
        if ot == r3d.ObjectType.SubD:
            if not is_idef:
                subd_objects.append(ob)
            continue

        # Curves and other non-mesh types: skip
        if ot not in (r3d.ObjectType.Brep, r3d.ObjectType.Extrusion, r3d.ObjectType.Mesh):
            continue

        # Tessellate visible (non-idef) mesh objects for OBJ
        msh = None
        if ot == r3d.ObjectType.Brep:
            combined = r3d.Mesh()
            og_faces = og.Faces
            for f in range(len(og_faces)):
                try:
                    fm = og_faces[f].GetMesh(r3d.MeshType.Any)
                    if fm: combined.Append(fm)
                except Exception: pass
            msh = combined
        elif ot == r3d.ObjectType.Mesh:
            msh = og
        elif ot == r3d.ObjectType.Extrusion:
            msh = og.GetMesh(r3d.MeshType.Any)
        elif ot == r3d.ObjectType.SubD:
            msh = r3d.Mesh.CreateFromSubDControlNet(og, False)

        if not msh or len(msh.Vertices) == 0:
            continue

        nv = len(msh.Vertices)
        nf = len(msh.Faces)
        layer_idx = oa.LayerIndex
        color = (200, 200, 200, 255)
        mat_idx = -1
        try:
            mat_idx = oa.MaterialIndex
            if oa.MaterialSource == r3d.ObjectMaterialSource.MaterialFromLayer or mat_idx < 0:
                l_info = layer_info_cache.get(layer_idx, (-1, (200, 200, 200, 255)))
                mat_idx = l_info[0]
                color = l_info[1]
            elif oa.ColorSource == r3d.ObjectColorSource.ColorFromObject:
                color = oa.ObjectColor
            else:
                color = layer_info_cache.get(layer_idx, (-1, (200, 200, 200, 255)))[1]
        except Exception: pass

        # Geometry dedup: compute signature from bbox + face counts
        bb_min_x=bb_min_y=bb_min_z=float('inf'); bb_max_x=bb_max_y=bb_max_z=float('-inf')
        n_tris=0; n_quads=0
        face_data = list(msh.Faces)  # materialize once for both dedup and OBJ writing
        for f in face_data:
            if f[3]==f[2]: n_tris+=1
            else: n_quads+=1
        for v in msh.Vertices:
            x,y,z=v.X*scale,v.Y*scale,v.Z*scale
            if x<bb_min_x:bb_min_x=x
            elif x>bb_max_x:bb_max_x=x
            if y<bb_min_y:bb_min_y=y
            elif y>bb_max_y:bb_max_y=y
            if z<bb_min_z:bb_min_z=z
            elif z>bb_max_z:bb_max_z=z

        sig = converters.utils.compute_mesh_signature_from_precomputed(
            nv,nf,bb_min_x,bb_min_y,bb_min_z,bb_max_x,bb_max_y,bb_max_z,
            n_tris,n_quads,nf-n_tris-n_quads) if (nv>0 and nf>0) else None
        pre_key,full_hash = sig if sig else (None,None)

        meta_entry = (oa.Id, oa.Name if oa.Name else f"LF_{oa.Id}", oa.LayerIndex, mat_idx, color, False)
        idx = len(obj_meta)
        obj_meta.append(meta_entry)

        if pre_key is not None and pre_key in sig_to_obj:
            bucket = sig_to_obj[pre_key]
            if full_hash in bucket:
                dup_map[idx] = bucket[full_hash]
                continue  # skip OBJ write (duplicate geometry)

        if pre_key is not None:
            sig_to_obj.setdefault(pre_key,{})[full_hash]=idx

        lines.append(f'o obj_{idx}')
        # (OBJ geometry writing follows — uses face_data list built above)
        mat_name = None
        if mat_idx >= 0:
            blmat = materials.get(mat_idx, materials.get(str(mat_idx)))
            if blmat: mat_name = blmat.name
        if mat_name != last_mat_name:
            if mat_name: lines.append(f'usemtl {mat_name}')
            last_mat_name = mat_name
        for v in msh.Vertices:
            lines.append(f'v {v.X*scale:.6f} {v.Y*scale:.6f} {v.Z*scale:.6f}')
        tc = msh.TextureCoordinates
        has_uv = len(tc) == nv
        if has_uv:
            for uv in tc:
                lines.append(f'vt {uv.X:.6f} {uv.Y:.6f}')
        for face in face_data:
            f0,f1,f2,f3 = face[0]+1, face[1]+1, face[2]+1, face[3]+1
            a,b,c,d = f0+v_off, f1+v_off, f2+v_off, f3+v_off
            if has_uv:
                ua,ub,uc,ud = f0+vt_off, f1+vt_off, f2+vt_off, f3+vt_off
                if f3 == f2:
                    lines.append(f'f {a}/{ua} {b}/{ub} {c}/{uc}')
                else:
                    lines.append(f'f {a}/{ua} {b}/{ub} {c}/{uc} {d}/{ud}')
            else:
                if f3 == f2:
                    lines.append(f'f {a} {b} {c}')
                else:
                    lines.append(f'f {a} {b} {c} {d}')
        v_off += nv
        if has_uv: vt_off += nv

    profiler.step(f"9c. [OBJ] {len(obj_meta)} objects ({len(dup_map)} dedup), skipped {len(idef_objects)} idef, {len(iref_objects)} iref, {len(subd_objects)} subd")

    # --- Block templates FIRST so [Block] collections have geometry before instances ---
    if idef_objects:
        link_opts = options.copy(); link_opts["defer_link"] = True
        idef_obj_map = options.get("idef_obj_map", {})
        converters.utils.reset_all_dict(context)
        for ob in idef_objects:
            try:
                t = converters.convert_object(context, ob, model, layerids, materials, scale, link_opts)
                if t:
                    blk = idef_obj_map.get(str(ob.Attributes.Id))
                    if blk and t.name not in blk.objects: blk.objects.link(t)
                    t.hide_viewport = True; t.hide_render = True
            except Exception: pass
        profiler.step(f"9d. [OBJ] {len(idef_objects)} block templates populated")

    # --- Create instance empties NOW while Blender namemap is small ---
    # (After 52K OBJ objects exist, bpy.data.objects.new() slows from 0.015ms→5ms each)
    iref_pending = {}; iref_count = 0
    if iref_objects:
        idef_map = options.get("idef_map", {})
        tag_cache = {}
        for ob in iref_objects:
            try:
                parent_id = ob.Geometry.ParentIdefId
                if parent_id not in tag_cache:
                    block_name = idef_map.get(parent_id, f"Block {parent_id}")
                    col_tags = converters.utils.create_tag_dict(parent_id, block_name, None, None, True)
                    idef_col = converters.utils.get_or_create_iddata(context.blend_data.collections, col_tags, None)
                    tag_cache[parent_id] = idef_col
                idef_col = tag_cache[parent_id]
                name = ob.Attributes.Name if ob.Attributes.Name else f"LF_{ob.Attributes.Id}"
                iref = bpy.data.objects.new(name=name, object_data=None)
                iref['rhid'] = str(ob.Attributes.Id)
                iref.empty_display_type = 'PLAIN_AXES'
                iref.instance_type = 'COLLECTION'
                iref.instance_collection = idef_col
                iref.matrix_world = converters.utils.matrix_from_xform(ob.Geometry.Xform, scale)
                layer = layerids.get(ob.Attributes.LayerIndex, context.scene.collection)
                iref_pending.setdefault(layer, []).append(iref)
                iref_count += 1
            except Exception: pass
        profiler.step(f"9d. [OBJ] Created {iref_count} instance empties (pre-OBJ)")

    if not lines:
        profiler.step("9. [OBJ] No geometry to import")
        return

    obj_text = '\n'.join(lines)
    profiler.step(f"9b. [OBJ] Built {len(lines):,} lines for {len(obj_meta)} objects")

    # Phase 2: Write OBJ + MTL to temp files, import via Blender C
    tmp = tempfile.NamedTemporaryFile(suffix='.obj', delete=False)
    tmp.close()
    try:
        # Write MTL file alongside OBJ
        if mtl_lines:
            mtl_path = tmp.name.replace('.obj', '.mtl')
            with open(mtl_path, 'w') as f:
                f.write('\n'.join(mtl_lines))
            lines.insert(1, f'mtllib {os.path.basename(mtl_path)}')

        with open(tmp.name, 'w', buffering=16*1024*1024) as f:
            f.write('\n'.join(lines))
        profiler.step(f"10. [OBJ] Written {os.path.getsize(tmp.name)/1024/1024:.0f}MB OBJ + MTL")

        bpy.ops.wm.obj_import(filepath=tmp.name, use_split_objects=True, use_split_groups=True,
                              up_axis='Z', forward_axis='Y')
        profiler.step(f"11. [OBJ] Imported {len(bpy.data.objects)} objects via Blender C importer")
    finally:
        try: os.unlink(tmp.name)
        except Exception: pass
        if mtl_lines:
            try: os.unlink(mtl_path)
            except Exception: pass

    # Phase 3: Reconcile metadata using O(1) name→object lookup (no sort needed)
    # Build name→object dict from imported meshes
    imported_by_name = {}
    for o in context.blend_data.objects:
        if o.type == 'MESH' and o.name.startswith('obj_'):
            imported_by_name[o.name] = o

    count = len(imported_by_name)
    profiler.step(f"12a. [OBJ] Indexed {count} imported objects")

    # Material lookup cache
    mat_lookup = {}
    def _resolve_mat(mat_idx):
        if mat_idx not in mat_lookup:
            mat_lookup[mat_idx] = materials.get(mat_idx, materials.get(str(mat_idx), materials.get(-1)))
        return mat_lookup[mat_idx]

    idef_obj_map = options.get("idef_obj_map", {})

    # Deferred collection linking (same pattern as Python path — bulk link after properties)
    pending_links = {}  # collection → list of objects

    for i in range(len(obj_meta)):
        ob = imported_by_name.get(f'obj_{i}')
        guid, name, layer_idx, mat_idx, color, is_idef = obj_meta[i]

        # Handle duplicates: create new object sharing the original's mesh
        if not ob and i in dup_map:
            orig_ob = imported_by_name.get(f'obj_{dup_map[i]}')
            if orig_ob:
                ob = bpy.data.objects.new(name=f'obj_{i}', object_data=orig_ob.data)

        if not ob: continue
        ob['rhid'] = str(guid)
        if name: ob['rhname'] = name
        ob.color = (color[0]/255.0, color[1]/255.0, color[2]/255.0, color[3]/255.0)
        target_col = layerids.get(layer_idx, context.scene.collection)
        if is_idef:
            idef_col = idef_obj_map.get(str(guid), target_col)
            if idef_col:
                pending_links.setdefault(idef_col, []).append(ob)
        else:
            pending_links.setdefault(target_col, []).append(ob)

    profiler.step(f"12b. [OBJ] Tagged {len(obj_meta)} objects ({len(dup_map)} dedup), {len(pending_links)} batches")

    # Material assignment: SKIPPED in OBJ fast path — assigning materials to 52K
    # individual meshes via data.materials.append() takes 190s+. Materials are
    # resolved later via the normal sync mechanism.
    profiler.step(f"12c. [OBJ] Materials deferred (sync path)")

    # Bulk link
    for col, objs in pending_links.items():
        for ob in objs:
            try: col.objects.link(ob)
            except Exception: pass
    # Also link instance empties (created pre-OBJ)
    for layer, objs in iref_pending.items():
        for iref in objs:
            try: layer.objects.link(iref)
            except Exception: pass

    profiler.step(f"12. [OBJ] Reconciled metadata for {count} objects + {iref_count} instances")

    # --- Phase 4: Block template objects (Python path into [Block] collections) ---
    # Block templates already converted pre-OBJ (step 9d) — skip here.

    # SubD objects: Python path (needs Subdivision modifier, crease edges, sharp edges)
    if subd_objects:
        link_opts = options.copy()
        link_opts["defer_link"] = True
        subd_pending = {}
        for ob in subd_objects:
            try:
                t = converters.convert_object(context, ob, model, layerids, materials, scale, link_opts)
                if t:
                    layer = layerids.get(ob.Attributes.LayerIndex, context.scene.collection)
                    subd_pending.setdefault(layer, []).append(t)
            except Exception: pass
        for layer, objs in subd_pending.items():
            for ob in objs:
                try: layer.objects.link(ob)
                except Exception: pass
        profiler.step(f"14. [OBJ] Converted {len(subd_objects)} SubD objects")

    # Apply layer visibility exclusions (matching legacy behavior)
    if layer_visibility:
        def _apply_vis(layer_col, vis):
            if not layer_col: return
            for child in layer_col.children:
                c_name = child.collection.name
                if c_name in vis:
                    child.exclude = not vis[c_name].get("effective_visible", True)
                _apply_vis(child, vis)
        try: _apply_vis(context.view_layer.layer_collection, layer_visibility)
        except Exception: pass

    profiler.finish(f"OBJ Fast-Path Import Complete ({count} objects + {len(idef_objects)} blocks + {iref_count} instances)")


def _read_3dm_internal(context : bpy.types.Context, options : Dict[str, Any]) -> Set[str]:
    filepath : str = options.get("filepath", "")
    data_dir = os.path.dirname(filepath) if filepath else os.path.expanduser("~/Desktop")
    
    log_file_path = os.path.join(data_dir, "LoopFlow_Performance.log")
    if not os.path.exists(os.path.dirname(log_file_path)):
        log_file_path = os.path.expanduser("~/Library/Application Support/McNeel/Rhinoceros/8.0/scripts/LoopFlow_R2B/Data/LoopFlow_Performance.log")

    is_update = bool(options.get("is_update", False))
    
    # Check if LoopFlow master collection exists and is linked to the current Scene Collection
    master_col_name = "LoopFlow"
    master_col = context.blend_data.collections.get(master_col_name)
    top_collection_name = Path(filepath).stem if filepath else "R2B"
    toplayer = context.blend_data.collections.get(top_collection_name)

    is_imported = (master_col is not None) and (master_col.name in context.scene.collection.children) and (toplayer is not None)

    # AUTO-DETECT FIRST RUN IN BLENDER SESSION (IF LOOPFLOW COLLECTION IS MISSING)
    if is_update and not is_imported and options.get("import_mode") != "APPEND":
        is_update = False  # Automatically perform initial full import into LoopFlow collection!
        op_title = "Update Model (Initial Session Full Import)"
    elif is_update and options.get("import_mode") == "APPEND":
        op_title = "Import Model (Append Mode)"
    elif is_update:
        op_title = "Update Model (In-Memory Fast Sync)"
    else:
        op_title = "Import Model (Full Scene Re-read)"
    
    profiler = SubOpProfiler(op_title, log_file_path)

    # 1. INITIALIZE & READ SYNC METADATA
    converters.initialize(context)
    
    file_stem = Path(filepath).stem if filepath else "R2B"
    file_mtime = os.path.getmtime(filepath) if (filepath and os.path.exists(filepath)) else 0
    file_size = os.path.getsize(filepath) if (filepath and os.path.exists(filepath)) else 0

    sync_candidates = [
        os.path.join(data_dir, f"R2B_Sync_{file_stem}.json"),
        os.path.join(data_dir, "R2B_Sync.json"),
        os.path.expanduser("~/Library/Application Support/McNeel/Rhinoceros/8.0/scripts/LoopFlow_R2B/Data/R2B_Sync.json")
    ]

    sync_json_path = None
    latest_mtime = -1
    for cand in sync_candidates:
        if os.path.exists(cand):
            try:
                mtime = os.path.getmtime(cand)
                if mtime > latest_mtime:
                    latest_mtime = mtime
                    sync_json_path = cand
            except Exception:
                pass

    sync_meta = {}
    if sync_json_path and os.path.exists(sync_json_path):
        try:
            with open(sync_json_path, 'r', encoding='utf-8') as f:
                sync_meta = json.load(f)
        except Exception:
            pass

    # Verify if sync_meta matches target filepath
    active_fp = sync_meta.get("active_filepath", "")
    if active_fp and filepath and Path(active_fp).stem != file_stem:
        # JSON belongs to a different 3DM file, ignore delta
        sync_meta = {}

    profiler.step("1. Read Sync Metadata (R2B_Sync.json)")

    geom_changed = sync_meta.get("geometry_changed", True)
    added_guids = sync_meta.get("added_obj_guids", [])
    removed_guids = sync_meta.get("removed_obj_guids", [])
    modified_guids = sync_meta.get("modified_obj_guids", [])
    hidden_objs = set(sync_meta.get("hidden_objects", []))
    hidden_layers = set(sync_meta.get("hidden_layers", []))
    layer_manifest = sync_meta.get("layers", {})

    has_geom_delta = bool(added_guids or removed_guids or modified_guids)

    # UNCHANGED FILE SIGNATURE SKIP CHECK
    if is_update and toplayer and not sync_meta:
        last_mtime = toplayer.get("last_sync_mtime", 0)
        last_size = toplayer.get("last_sync_size", 0)
        if last_mtime == file_mtime and last_size == file_size:
            profiler.finish(f"File {file_stem}.3dm unchanged since last sync (Skipped)")
            return {'FINISHED'}

    # INSTANT FAST PATH 1: NO GEOMETRY DELTAS OR geom_changed IS FALSE (< 0.05s)
    if is_update and (geom_changed is False or not has_geom_delta) and is_imported:
        if hidden_objs:
            for obj in context.blend_data.objects:
                rhid = str(obj.get("rhid", ""))
                if rhid:
                    is_hidden = (rhid in hidden_objs)
                    obj.hide_viewport = is_hidden
                    obj.hide_render = is_hidden
            profiler.step("2. Update Viewport and Render Hiding for Objects")

        def _fast_update_layer_collections(lc):
            if not lc:
                return
            col = lc.collection
            col_name = col.name
            col_rhid = str(col.get("rhid", ""))

            found_info = None
            if col_rhid and col_rhid in layer_manifest:
                found_info = layer_manifest[col_rhid]
            elif col_name in layer_manifest:
                found_info = layer_manifest[col_name]
            else:
                rh_full = col.get("rhino_full_path", "")
                rh_name = col.get("rhino_layer_name", "")
                if rh_full and rh_full in layer_manifest:
                    found_info = layer_manifest[rh_full]
                elif rh_name and rh_name in layer_manifest:
                    found_info = layer_manifest[rh_name]
                else:
                    for full_p, info in layer_manifest.items():
                        leaf = full_p.split("::")[-1]
                        if leaf == col_name or full_p == col_name:
                            found_info = info
                            break

            if found_info:
                eff_vis = found_info.get("effective_visible", True)
                lc.exclude = not eff_vis

            for child in lc.children:
                _fast_update_layer_collections(child)

        try:
            _fast_update_layer_collections(context.view_layer.layer_collection)
            context.view_layer.update()
        except Exception as e:
            print(f"LoopFlow Fast Sync Exception: {e}")

        profiler.step("3. Update View Layer Collection Exclude States")
        profiler.finish("Fast Path Sync Executed (<0.06s)")
        return {'FINISHED'}

    # FAST DELTA GEOMETRY UPDATE PATH (< 0.5s)
    if is_update and is_imported and has_geom_delta:
        converters.utils.clear_all_dict()
        profiler.step("2. Reset Plugin Dictionary Cache")

        try:
            model = r3d.File3dm.Read(filepath)
        except Exception:
            model = None

        if model:
            profiler.step(f"3. Read 3DM File from Disk ({os.path.getsize(filepath) / (1024*1024):.1f} MB)")
            options["rh_model"] = model
            toplayer = create_or_get_top_layer(context, filepath, is_update=True)
            profiler.step("4. Access Top-Level Scene Collection")

            scale = r3d.UnitSystem.UnitScale(model.Settings.ModelUnitSystem, r3d.UnitSystem.Meters) / context.scene.unit_settings.scale_length
            layerids, materials = {}, {}
            update_mats_flag = options.get("update_materials", False)

            converters.handle_materials(context, model, materials, update_mats_flag)
            profiler.step("5. Material Conversion and Binding")

            layer_visibility = converters.handle_layers(context, model, toplayer, layerids, materials, update_mats_flag, True)
            profiler.step("6. Layer Hierarchy Construction")

            link_options = options.copy()
            link_options["update_materials"] = True

            # 1. Handle Removed Objects
            if removed_guids:
                rem_set = set(removed_guids)
                for obj in list(context.blend_data.objects):
                    rhid = str(obj.get("rhid", ""))
                    if rhid in rem_set:
                        try:
                            context.blend_data.objects.remove(obj, do_unlink=True)
                        except Exception:
                            pass
                profiler.step(f"7. Remove Deleted Delta Objects ({len(removed_guids)} items)")

            # 2. Handle Modified & Added Objects
            mod_add_set = set(added_guids + modified_guids)
            if mod_add_set:
                for obj in list(context.blend_data.objects):
                    rhid = str(obj.get("rhid", ""))
                    if rhid in set(modified_guids):
                        try:
                            context.blend_data.objects.remove(obj, do_unlink=True)
                        except Exception:
                            pass

                converted_count = 0
                for ob in model.Objects:
                    rhid = str(ob.Attributes.Id)
                    if rhid in mod_add_set:
                        converters.convert_object(context, ob, model, layerids, materials, scale, link_options)
                        converted_count += 1
                profiler.step(f"8. Convert Delta Geometry ({converted_count} items)")

            def _fast_update_layer_collections(lc):
                if not lc:
                    return
                col = lc.collection
                col_name = col.name
                found_info = None
                if col_name in layer_manifest:
                    found_info = layer_manifest[col_name]
                else:
                    rh_full = col.get("rhino_full_path", "")
                    rh_name = col.get("rhino_layer_name", "")
                    if rh_full and rh_full in layer_manifest:
                        found_info = layer_manifest[rh_full]
                    elif rh_name and rh_name in layer_manifest:
                        found_info = layer_manifest[rh_name]
                    else:
                        for full_p, info in layer_manifest.items():
                            leaf = full_p.split("::")[-1]
                            if leaf == col_name or full_p == col_name:
                                found_info = info
                                break
                if found_info:
                    eff_vis = found_info.get("effective_visible", True)
                    lc.exclude = not eff_vis
                for child in lc.children:
                    _fast_update_layer_collections(child)

            try:
                _fast_update_layer_collections(context.view_layer.layer_collection)
                context.view_layer.update()
            except Exception:
                pass

            profiler.step("9. Update View Layer Collection Exclude States")
            profiler.finish(f"Delta Geometry Sync Complete ({len(mod_add_set)} modified/added, {len(removed_guids)} removed)")
            return {'FINISHED'}

    # -------------------------------------------------------------------
    # FULL IMPORT / DELTA GEOMETRY IMPORT
    # -------------------------------------------------------------------
    converters.utils.clear_all_dict()
    profiler.step("2. Reset Plugin Dictionary Cache")
    
    try:
        model = r3d.File3dm.Read(filepath)
    except Exception as e:
        print(f"LoopFlow: Exception reading file {filepath}: {e}")
        return {'CANCELLED'}

    if not model:
        print(f"LoopFlow Error: Could not read 3dm file: {filepath}")
        return {'CANCELLED'}

    options["rh_model"] = model
    options["idef_map"] = {idef.Id: f"[Block] {idef.Name}" if idef.Name else f"Block {idef.Id}" for idef in model.InstanceDefinitions} if hasattr(model, "InstanceDefinitions") else {}
    toplayer = create_or_get_top_layer(context, filepath, is_update=is_update, import_mode=options.get("import_mode", "SYNC"))
    profiler.step("4. Create and Teardown Scene Collections")

    converters.utils.reset_all_dict(context)
    profiler.step("5. Re-initialize Cache Dictionaries")
    
    scale = r3d.UnitSystem.UnitScale(model.Settings.ModelUnitSystem, r3d.UnitSystem.Meters) / context.scene.unit_settings.scale_length
    layerids, materials = {}, {}

    update_mats_flag = options.get("update_materials", False)

    converters.handle_materials(context, model, materials, update_mats_flag)
    profiler.step("6. Material Conversion and Binding")

    layer_visibility = converters.handle_layers(context, model, toplayer, layerids, materials, update_mats_flag, True)
    profiler.step("7. Layer Hierarchy Construction")

    link_options = options.copy()
    link_options["update_materials"] = True 
    link_options["defer_link"] = True

    mat_link_pref = options.get("link_materials_to", "PREFERENCES")
    if mat_link_pref == "PREFERENCES":
        mat_link_pref = context.preferences.edit.material_link
        if mat_link_pref == 'OBDATA':
            mat_link_pref = 'DATA'
    link_options["link_materials_to_resolved"] = mat_link_pref

    import_instances = options.get("import_instances", True)
    if import_instances and hasattr(model, "InstanceDefinitions") and len(model.InstanceDefinitions) > 0:
        converters.handle_instance_definitions(context, model, toplayer, "Instance Definitions")
        profiler.step("8. Instance Definitions Setup")

    # Pre-map block template object GUIDs -> their [Block] collections (needed by both paths)
    idef_obj_map = {}
    if import_instances and hasattr(model, "InstanceDefinitions"):
        for idef in model.InstanceDefinitions:
            block_name = f"[Block] {idef.Name}" if idef.Name else f"Block {idef.Id}"
            blk_col = context.blend_data.collections.get(block_name)
            if blk_col:
                try:
                    for guid in idef.GetObjectIds():
                        idef_obj_map[str(guid)] = blk_col
                except Exception: pass
    options["idef_obj_map"] = idef_obj_map

    # --- OBJ Fast Path for full imports ---
    if not is_update and options.get("use_fast_import", True):
        _import_via_obj_fastpath(context, model, toplayer, layerids, materials, scale, options, profiler, filepath, layer_visibility)
        return {'FINISHED'}

    import_curves = options.get("import_curves", True)
    hidden_objects = []

    total_objs = len(model.Objects)
    log_chunk = max(500, total_objs // 10) if total_objs > 0 else 500
    converted_vis_count = 0

    pending_collection_links = {} # collection -> list of objects

    for idx, ob in enumerate(model.Objects):
        og = ob.Geometry
        if not og:
            continue

        if not import_curves and og.ObjectType == r3d.ObjectType.Curve:
            continue

        try:
            if not ob.Attributes.Visible:
                hidden_objects.append(ob)
                continue
        except Exception:
            pass

        t = converters.convert_object(context, ob, model, layerids, materials, scale, link_options)
        if t:
            oa = ob.Attributes
            is_idef = oa.IsInstanceDefinitionObject if (oa and hasattr(oa, "IsInstanceDefinitionObject")) else False
            if is_idef:
                target_col = idef_obj_map.get(str(oa.Id), layerids.get(oa.LayerIndex, context.scene.collection))
            else:
                target_col = layerids.get(oa.LayerIndex, context.scene.collection)
            pending_collection_links.setdefault(target_col, []).append(t)

        converted_vis_count += 1

        if (idx + 1) % log_chunk == 0 or (idx + 1) == total_objs:
            profiler.step(f"9. Convert Visible Objects Batch ({idx + 1}/{total_objs})")

    if total_objs == 0:
        profiler.step("9. Convert Visible Objects (0 items)")

    for h_idx, ob in enumerate(hidden_objects):
        try:
            t = converters.convert_object(context, ob, model, layerids, materials, scale, link_options)
            if t:
                oa = ob.Attributes
                is_idef = oa.IsInstanceDefinitionObject if (oa and hasattr(oa, "IsInstanceDefinitionObject")) else False
                if is_idef:
                    target_col = idef_obj_map.get(str(oa.Id), layerids.get(oa.LayerIndex, context.scene.collection))
                else:
                    target_col = layerids.get(oa.LayerIndex, context.scene.collection)
                pending_collection_links.setdefault(target_col, []).append(t)
                if hasattr(t, "hide_viewport"):
                    t.hide_viewport = True
                    t.hide_render = True
        except Exception:
            pass

    profiler.step(f"10. Convert Hidden Objects ({len(hidden_objects)} items)")

    # Fast deferred bulk linking (defer_link=True guarantees no pre-existing links)
    for layer, objs in pending_collection_links.items():
        for bo in objs:
            try:
                layer.objects.link(bo)
            except Exception:
                pass
    profiler.step("10b. Deferred Bulk Collection Linking")

    if import_instances and hasattr(model, "InstanceDefinitions") and len(model.InstanceDefinitions) > 0:
        try:
            converters.populate_instance_definitions(context, model, toplayer, "Instance Definitions", options, scale)
            profiler.step("11. Populate Instance Objects")
        except Exception as e:
            print(f"LoopFlow: Exception populating instance definitions: {e}")

    def _apply_layer_visibilities(layer_col, layer_visibility):
        if not layer_col:
            return
        for child in layer_col.children:
            c_name = child.collection.name
            if c_name in layer_visibility:
                info = layer_visibility[c_name]
                eff_vis = info.get("effective_visible", True)
                child.exclude = not eff_vis
            _apply_layer_visibilities(child, layer_visibility)

    try:
        vl = context.view_layer
        _apply_layer_visibilities(vl.layer_collection, layer_visibility)
    except Exception as e:
        print(f"LoopFlow: Exception applying layer visibilities: {e}")

    if toplayer and filepath and os.path.exists(filepath):
        toplayer["last_sync_mtime"] = os.path.getmtime(filepath)
        toplayer["last_sync_size"] = os.path.getsize(filepath)

    profiler.step("12. Apply Layer Visibilities to View Layer")
    profiler.finish(f"Full Model Import Complete ({len(context.blend_data.objects)} total objects in scene)")

    return {'FINISHED'}