# MIT License
# Copyright (c) 2018-2024 Nathan Letwory, Joel Putnam, Tom Svilans, Lukas Fertig

import bpy
import uuid
import rhino3dm as r3d
from mathutils import Matrix
from typing import Any, Dict

def tag_data(idblock : bpy.types.ID, tag_dict: Dict[str, Any]) -> None:
    """
    Write Rhino source data into Blender object custom properties.
    """
    if 'rhid' in tag_dict and tag_dict['rhid'] is not None:
        idblock['rhid'] = str(tag_dict['rhid'])
    if 'rhname' in tag_dict and tag_dict['rhname']:
        idblock['rhname'] = tag_dict['rhname']

def create_tag_dict(guid, name, matid=None, parentid=None, is_idef=False, mat_from_object=True):
    return {'rhid': guid, 'rhname': name}

all_dict = dict()

def clear_all_dict():
    """
    Compatibility shim: original cleanup function name from the base addon.
    """
    global all_dict
    all_dict = dict()

def reset_all_dict(context):
    """
    Run cleanup and reinitialise the cache dictionary.
    """
    clear_all_dict()
    all_dict["objects"] = {item['rhid']: item for item in context.blend_data.objects if 'rhid' in item}
    all_dict["meshes"] = {item['rhid']: item for item in context.blend_data.meshes if 'rhid' in item}
    all_dict["materials"] = {item['rhid']: item for item in context.blend_data.materials if 'rhid' in item}
    all_dict["collections"] = {item['rhid']: item for item in context.blend_data.collections if 'rhid' in item}

def get_dict_for_base(base):
    global all_dict
    bd = bpy.context.blend_data
    if base == bd.objects:
        return all_dict.setdefault("objects", dict())
    elif base == bd.meshes:
        return all_dict.setdefault("meshes", dict())
    elif base == bd.materials:
        return all_dict.setdefault("materials", dict())
    elif base == bd.collections:
        return all_dict.setdefault("collections", dict())
    try:
        t = repr(base).split(',')[1].strip()
    except Exception:
        t = str(type(base))
    return all_dict.setdefault(t, dict())

def get_or_create_iddata(base : bpy.types.bpy_prop_collection, tag_dict: Dict[str, Any], obdata : bpy.types.ID) -> bpy.types.ID:
    """
    Get or create a data block and sync its display name.
    """
    guid = tag_dict.get('rhid', None)
    name = tag_dict.get('rhname', None)
    dct = get_dict_for_base(base)

    strguid = str(guid) if guid is not None else None

    if strguid and strguid in dct:
        theitem = dct[strguid]
        if name and theitem.name != name:
            theitem.name = name
            theitem['rhname'] = name
        if obdata and hasattr(theitem, "data") and type(theitem.data) != type(obdata):
            theitem.data = obdata
    else:
        # Create new data block
        if not name and guid:
            name = f"LF_{guid}"
        dname = name if name else "LF_Obj"
        if base == bpy.context.blend_data.objects:
            theitem = base.new(name=dname, object_data=obdata)
        else:
            theitem = base.new(name=dname)
        
        if strguid:
            dct[strguid] = theitem
        tag_data(theitem, tag_dict)
        
    return theitem

def compute_mesh_signature_from_precomputed(nv, nf, bb_min_x, bb_min_y, bb_min_z,
                                              bb_max_x, bb_max_y, bb_max_z,
                                              n_tris, n_quads, n_ngons):
    """Build position-independent geometry signature from pre-computed bbox/face counts."""
    pre_key = (nv, nf)
    r = 3
    dx = round(bb_max_x - bb_min_x, r)
    dy = round(bb_max_y - bb_min_y, r)
    dz = round(bb_max_z - bb_min_z, r)
    full_hash = hash((nv, nf, dx, dy, dz, n_tris, n_quads, n_ngons))
    return (pre_key, full_hash)


def matrix_from_xform(xform : r3d.Transform, scale : float = 1.0):
    if scale == 1.0:
        return Matrix(
            ((xform.M00, xform.M01, xform.M02, xform.M03),
             (xform.M10, xform.M11, xform.M12, xform.M13),
             (xform.M20, xform.M21, xform.M22, xform.M23),
             (xform.M30, xform.M31, xform.M32, xform.M33))
        )
    return Matrix(
        ((xform.M00, xform.M01, xform.M02, xform.M03 * scale),
         (xform.M10, xform.M11, xform.M12, xform.M13 * scale),
         (xform.M20, xform.M21, xform.M22, xform.M23 * scale),
         (xform.M30, xform.M31, xform.M32, xform.M33))
    )