# MIT License

# Copyright (c) 2018-2024 Nathan Letwory, Joel Putnam, Tom Svilans, Lukas Fertig

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import rhino3dm as r3d
from . import utils
import bpy
import bmesh
import time
import math
from collections import defaultdict

def _dist(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2 + (p1[2]-p2[2])**2)

def _point_on_segment(p, a, b, tol=1e-3):
    ab_len = _dist(a, b)
    if ab_len < tol:
        return _dist(p, a) < tol
    ap_len = _dist(a, p)
    pb_len = _dist(p, b)
    return abs((ap_len + pb_len) - ab_len) < tol

def extract_subd_creases(og, scale, tol=1e-3):
    """
    Safely extract SubD edge crease segments and vertex creases.
    Uses native C++ iterator First() / Next() bounded by Count to prevent array offset crashes on Rhino 8 SubDs.
    Vertex creases only include explicit Corner vertices (SubDVertexTag.Corner).
    """
    subd_vert_pos = {}
    subd_vert_creases = {}

    if not hasattr(og, "Vertices") or not hasattr(og, "Edges"):
        return [], {}

    # Extract vertex positions using vit.First() / vit.Next()
    try:
        vit = og.Vertices
        v_count = vit.Count
        v = vit.First()
        for _ in range(v_count):
            if not v:
                break
            try:
                pt = v.ControlNetPoint
                p = (pt.X * scale, pt.Y * scale, pt.Z * scale)
                subd_vert_pos[v.Id] = p
                if hasattr(r3d, "SubDVertexTag"):
                    # Only Corner vertices are explicit vertex creases in Blender
                    if v.Tag == r3d.SubDVertexTag.Corner:
                        subd_vert_creases[p] = 1.0
            except Exception:
                pass
            v = vit.Next()
    except Exception:
        pass

    # Extract edge crease segments using eit.First() / eit.Next()
    subd_crease_segments = []
    try:
        eit = og.Edges
        e_count = eit.Count
        e = eit.First()
        for _ in range(e_count):
            if not e:
                break
            try:
                if e.VertexCount >= 2:
                    v0_id = e.VertexId(0)
                    v1_id = e.VertexId(1)
                    if v0_id in subd_vert_pos and v1_id in subd_vert_pos:
                        val = 0.0
                        if e.IsCrease or e.IsHardCrease or e.IsDartCrease:
                            val = 1.0
                        elif e.IsSharp:
                            s0 = e.EndSharpness(0)
                            s1 = e.EndSharpness(1)
                            val = min(1.0, max(0.0, ((s0 + s1) / 2.0) / 4.0))

                        if val > 0:
                            a = subd_vert_pos[v0_id]
                            b = subd_vert_pos[v1_id]
                            min_x = min(a[0], b[0]) - tol
                            max_x = max(a[0], b[0]) + tol
                            min_y = min(a[1], b[1]) - tol
                            max_y = max(a[1], b[1]) + tol
                            min_z = min(a[2], b[2]) - tol
                            max_z = max(a[2], b[2]) + tol
                            subd_crease_segments.append((min_x, max_x, min_y, max_y, min_z, max_z, a, b, val))
            except Exception:
                pass
            e = eit.Next()
    except Exception:
        pass

    return subd_crease_segments, subd_vert_creases

def import_render_mesh(context, ob, name, scale, options):
    og = ob.Geometry
    oa = ob.Attributes
    is_subd = (og.ObjectType == r3d.ObjectType.SubD)

    # Extract SubD crease edges and vertices if SubD
    subd_crease_segments = []
    subd_vert_creases = {}
    if is_subd:
        try:
            subd_crease_segments, subd_vert_creases = extract_subd_creases(og, scale)
        except Exception as e:
            print(f"LoopFlow: Error extracting SubD creases: {e}")

    # SubD objects are ALWAYS welded, even when weld_meshes checkbox is False
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
                if fm:
                    combined.Append(fm)
            except Exception:
                pass
        msh = [combined] if len(combined.Vertices) > 0 else []
    elif og.ObjectType == r3d.ObjectType.Surface:
        try:
            brep = og.ToBrep()
            if brep and hasattr(brep, "Faces"):
                combined = r3d.Mesh()
                b_faces = brep.Faces
                for f in range(len(b_faces)):
                    fm = b_faces[f].GetMesh(r3d.MeshType.Any)
                    if fm:
                        combined.Append(fm)
                msh = [combined] if len(combined.Vertices) > 0 else []
        except Exception:
            msh = []
    
    fidx = 0
    faces = []
    vertices = []
    coords = []
    vcls = []
    n_tris = 0
    n_quads = 0

    for m in msh:
        if not m:
            continue

        m_faces = m.Faces
        m_verts = m.Vertices
        m_tc = m.TextureCoordinates
        m_vc = m.VertexColors

        if fidx:
            for face in m_faces:
                f0, f1, f2, f3 = face[0], face[1], face[2], face[3]
                if f3 == f2:
                    faces.append((f0 + fidx, f1 + fidx, f2 + fidx))
                    n_tris += 1
                else:
                    faces.append((f0 + fidx, f1 + fidx, f2 + fidx, f3 + fidx))
                    n_quads += 1
        else:
            for face in m_faces:
                f0, f1, f2, f3 = face[0], face[1], face[2], face[3]
                if f3 == f2:
                    faces.append((f0, f1, f2))
                    n_tris += 1
                else:
                    faces.append((f0, f1, f2, f3))
                    n_quads += 1

        fidx += len(m_verts)
        if scale == 1.0:
            vertices.extend([(v.X, v.Y, v.Z) for v in m_verts])
        else:
            vertices.extend([(v.X * scale, v.Y * scale, v.Z * scale) for v in m_verts])

        if len(m_tc) > 0:
            coords.extend([(uv.X, uv.Y) for uv in m_tc])
        if len(m_vc) > 0:
            for c in m_vc:
                vcls.extend((c[0] / 255.0, c[1] / 255.0, c[2] / 255.0, c[3] / 255.0))

    # Compute bbox from vertices for dedup signature (one fast Python pass)
    nv = len(vertices)
    nf = len(faces)
    bb_min_x = bb_min_y = bb_min_z = float('inf')
    bb_max_x = bb_max_y = bb_max_z = float('-inf')
    for x, y, z in vertices:
        if x < bb_min_x: bb_min_x = x
        elif x > bb_max_x: bb_max_x = x
        if y < bb_min_y: bb_min_y = y
        elif y > bb_max_y: bb_max_y = y
        if z < bb_min_z: bb_min_z = z
        elif z > bb_max_z: bb_max_z = z

    # --- Mesh Deduplication ---
    nv = len(vertices)
    nf = len(faces)
    sig = utils.compute_mesh_signature_from_precomputed(
        nv, nf, bb_min_x, bb_min_y, bb_min_z,
        bb_max_x, bb_max_y, bb_max_z,
        n_tris, n_quads, nf - n_tris - n_quads
    ) if (nv > 0 and nf > 0) else None
    pre_key, full_hash = sig if sig else (None, None)

    mesh_cache = options.get("mesh_sig_cache")
    if mesh_cache is None:
        mesh_cache = {}
        options["mesh_sig_cache"] = mesh_cache

    if pre_key is not None and pre_key in mesh_cache:
        bucket = mesh_cache[pre_key]
        if full_hash in bucket:
            options.setdefault("_shared_mesh_names", set()).add(bucket[full_hash].name)
            return bucket[full_hash]

    mesh_name = oa.Name if oa.Name else f"LFM_{oa.Id}"
    tags = utils.create_tag_dict(oa.Id, mesh_name)
    mesh = utils.get_or_create_iddata(context.blend_data.meshes, tags, None)
    mesh.clear_geometry()
    mesh.from_pydata(vertices, [], faces, shade_flat=False)

    if pre_key is not None and full_hash is not None:
        mesh_cache.setdefault(pre_key, {})[full_hash] = mesh

    # UV: foreach_set with foreach_get for fast C-level transfer
    if mesh.loops and len(coords) == nv:
        if "RhinoUVMap" not in mesh.uv_layers:
            mesh.uv_layers.new(name="RhinoUVMap")
        uvl = mesh.uv_layers["RhinoUVMap"].data
        loop_count = len(mesh.loops)
        if len(uvl) == loop_count:
            vert_indices = [0] * loop_count
            mesh.loops.foreach_get("vertex_index", vert_indices)
            uv_flat = [0.0] * (loop_count * 2)
            for i in range(loop_count):
                c = coords[vert_indices[i]]
                uv_flat[i * 2] = c[0]
                uv_flat[i * 2 + 1] = c[1]
            uvl.foreach_set("uv", uv_flat)
        else:
            mesh.uv_layers.remove(mesh.uv_layers["RhinoUVMap"])

    # Vertex colors: pre-normalized during extraction, single foreach_set
    if len(vcls) == nv * 4:
        mesh.attributes.new("RhinoColor", "FLOAT_COLOR", "POINT")
        rcl = mesh.attributes["RhinoColor"]
        rcl.data.foreach_set("color", vcls)

    is_single_mesh = (len(msh) == 1 and (og.ObjectType == r3d.ObjectType.Mesh or og.ObjectType == r3d.ObjectType.Brep))
    should_weld = is_subd or (len(msh) > 1 and not (og.ObjectType == r3d.ObjectType.Brep)) or (needs_welding and not is_single_mesh)

    if should_weld:
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.001)

        # Transfer SubD creases onto welded bmesh edges and vertices with bounding-box optimization
        if is_subd and (subd_crease_segments or subd_vert_creases):
            crease_e_layer = bm.edges.layers.float.get("crease_edge")
            if not crease_e_layer and subd_crease_segments:
                crease_e_layer = bm.edges.layers.float.new("crease_edge")

            crease_v_layer = bm.verts.layers.float.get("crease_vert")
            if not crease_v_layer and subd_vert_creases:
                crease_v_layer = bm.verts.layers.float.new("crease_vert")

            dist_sq = lambda p1, p2: (p1.x-p2[0])**2 + (p1.y-p2[1])**2 + (p1.z-p2[2])**2
            sq_tol = 1e-4

            if subd_crease_segments and crease_e_layer:
                for edge in bm.edges:
                    p1 = edge.verts[0].co
                    p2 = edge.verts[1].co

                    e_min_x = min(p1.x, p2.x) - 1e-3
                    e_max_x = max(p1.x, p2.x) + 1e-3
                    e_min_y = min(p1.y, p2.y) - 1e-3
                    e_max_y = max(p1.y, p2.y) + 1e-3
                    e_min_z = min(p1.z, p2.z) - 1e-3
                    e_max_z = max(p1.z, p2.z) + 1e-3

                    for (min_x, max_x, min_y, max_y, min_z, max_z, a, b, val) in subd_crease_segments:
                        if e_max_x < min_x or e_min_x > max_x:
                            continue
                        if e_max_y < min_y or e_min_y > max_y:
                            continue
                        if e_max_z < min_z or e_min_z > max_z:
                            continue

                        if (dist_sq(p1, a) < sq_tol and dist_sq(p2, b) < sq_tol) or \
                           (dist_sq(p1, b) < sq_tol and dist_sq(p2, a) < sq_tol):
                            edge[crease_e_layer] = max(edge[crease_e_layer], val)
                            break

            if subd_vert_creases and crease_v_layer:
                for vert in bm.verts:
                    v_co = vert.co
                    for (p, val) in subd_vert_creases.items():
                        if dist_sq(v_co, p) < sq_tol:
                            vert[crease_v_layer] = max(vert[crease_v_layer], val)
                            break

        sharp_edge_indices = []
        if is_subd and (subd_crease_segments and crease_e_layer):
            for idx, edge in enumerate(bm.edges):
                if edge[crease_e_layer] > 0:
                    sharp_edge_indices.append(idx)

        bm.to_mesh(mesh)
        bm.free()

        if sharp_edge_indices:
            for idx in sharp_edge_indices:
                if idx < len(mesh.edges):
                    mesh.edges[idx].use_edge_sharp = True

        if not is_subd:
            if bpy.app.version >= (4, 1):
                mesh.set_sharp_from_angle(angle=0.523599) # 30deg
            else:
                mesh.use_auto_smooth = True
                mesh.auto_smooth_angle = 0.523599

    # done, now add object to blender
    return mesh
