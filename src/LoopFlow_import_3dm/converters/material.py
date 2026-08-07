# [material.py full source]

import binascii
import struct
import bpy
import rhino3dm as r3d
from bpy_extras.node_shader_utils import ShaderWrapper, PrincipledBSDFWrapper
from . import utils
from . import rdk_manager
from pathlib import Path, PureWindowsPath, PurePosixPath
import base64
import tempfile
import uuid
from typing import Any, Tuple

DEFAULT_RHINO_MATERIAL = "Rhino Default Material"
DEFAULT_TEXT_MATERIAL = "Rhino Default Text"
DEFAULT_RHINO_MATERIAL_ID = uuid.UUID("00000000-ABCD-EF01-2345-000000000000")
DEFAULT_RHINO_TEXT_MATERIAL_ID = uuid.UUID("00000000-ABCD-EF01-6789-000000000000")

_white = (0.8, 0.8, 0.8, 1.0) # Corrected to off-white

def tobytes(d):
    t = type(d)
    if t is bool: return struct.pack("?", d)
    if t is float: return struct.pack("f", d)
    if t is tuple and len(d) == 4: return struct.pack("IIII", *d)
    return b''

def srgb_eotf(srgb_color):
    def cc(v): return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return tuple(cc(x) for x in srgb_color)

def get_color_field(rm, field_name):
    colstr = rm.GetParameter(field_name)
    if not colstr: return _white
    return srgb_eotf(tuple(float(f) for f in colstr.split(",")))

def get_float_field(rm, field_name):
    fl = rm.GetParameter(field_name)
    return float(fl) if fl else 0.0

def material_name(m): return m.Name if m and m.Name else DEFAULT_RHINO_MATERIAL
def rendermaterial_name(m): return m.Name if m and m.Name else DEFAULT_RHINO_MATERIAL

# --- Material conversion handlers (all routed to Principled BSDF) ---

def paint_material(rm, bm):
    p = PrincipledBSDFWrapper(bm, is_readonly=False)
    p.base_color = get_color_field(rm, "color")[0:3]
    p.roughness = 1.0 - get_float_field(rm, "reflectivity")

def plaster_material(rm, bm):
    p = PrincipledBSDFWrapper(bm, is_readonly=False)
    p.base_color = get_color_field(rm, "color")[0:3]
    p.roughness = 1.0

def default_material(bm):
    p = PrincipledBSDFWrapper(bm, is_readonly=False)
    p.base_color = (0.8, 0.8, 0.8)
    p.roughness = 1.0

def default_text_material(bm):
    p = PrincipledBSDFWrapper(bm, is_readonly=False)
    p.base_color = (0.05, 0.05, 0.05)
    p.roughness = 1.0

def metal_material(rm, bm):
    p = PrincipledBSDFWrapper(bm, is_readonly=False)
    p.base_color = get_color_field(rm, "color")[0:3]
    p.metallic = 1.0
    p.roughness = get_float_field(rm, "polish-amount")

def glass_material(rm, bm):
    p = PrincipledBSDFWrapper(bm, is_readonly=False)
    col = get_color_field(rm, "color")[0:3]
    p.base_color = col
    p.transmission = 1.0
    p.roughness = 0.0
    ior = get_float_field(rm, "ior")
    p.ior = ior if ior > 0 else 1.52
    
    # 10% opacity in Viewport Display (Solid mode)
    bm.diffuse_color = (col[0], col[1], col[2], 0.1)

def pbr_material(rm, bm):
    p = PrincipledBSDFWrapper(bm, is_readonly=False)
    col = get_color_field(rm, "pbr-base-color")[0:3]
    p.base_color = col
    p.metallic = get_float_field(rm, "pbr-metallic")
    p.transmission = 1.0 - get_float_field(rm, "pbr-opacity")
    p.ior = get_float_field(rm, "pbr-opacity-ior")

    if p.transmission > 0.5:
        p.roughness = 0.0
        bm.diffuse_color = (col[0], col[1], col[2], 0.1)
    else:
        p.roughness = get_float_field(rm, "pbr-roughness")

material_handlers = {
    'rdk-paint-material': paint_material, 'rdk-plaster-material': plaster_material,
    'rdk-metal-material': metal_material, 'rdk-glass-material': glass_material,
    '5a8d7b9b-cdc9-49de-8c16-2ef64fb097ab': pbr_material,
}

def harvest_from_rendercontent(model, mat, bm):
    bm.use_nodes = True
    handler = material_handlers.get(mat.TypeName, plaster_material)
    handler(mat, bm)

def harvest_from_rhino_material(mat, bm):
    bm.use_nodes = True
    p = PrincipledBSDFWrapper(bm, is_readonly=False)

    # 1. Check Rhino 8 PhysicallyBased PBR properties
    if hasattr(mat, "PhysicallyBased") and mat.PhysicallyBased and mat.PhysicallyBased.Supported:
        pb = mat.PhysicallyBased
        bc = pb.BaseColor
        col = (bc[0], bc[1], bc[2])
        p.base_color = col
        p.metallic = float(pb.Metallic)
        p.transmission = float(1.0 - pb.Opacity)
        ior = float(pb.OpacityIOR)
        p.ior = ior if ior > 0 else 1.52

        if p.transmission > 0.5:
            p.roughness = 0.0
            bm.diffuse_color = (col[0], col[1], col[2], 0.1)
        else:
            p.roughness = float(pb.Roughness)
        return

    # 2. Fallback for standard Rhino materials
    col = (0.8, 0.8, 0.8)
    if hasattr(mat, "DiffuseColor"):
        dc = mat.DiffuseColor
        col = srgb_eotf((dc[0] / 255.0, dc[1] / 255.0, dc[2] / 255.0))
    p.base_color = col[0:3]

    if hasattr(mat, "Reflectivity") and mat.Reflectivity > 0:
        p.metallic = float(mat.Reflectivity)

    if hasattr(mat, "Transparency") and mat.Transparency > 0:
        p.transmission = float(mat.Transparency)
        if mat.Transparency > 0.5:
            p.roughness = 0.0
            bm.diffuse_color = (col[0], col[1], col[2], 0.1)
        else:
            if hasattr(mat, "Shine"):
                p.roughness = max(0.05, 1.0 - (float(mat.Shine) / 255.0))
    elif hasattr(mat, "Shine"):
        p.roughness = max(0.05, 1.0 - (float(mat.Shine) / 255.0))

def handle_embedded_files(model):
    pass

def handle_materials(context, model : r3d.File3dm, materials, update):
    """Smart material sync logic."""
    handle_embedded_files(model)

    # Handle default materials
    for d_name, d_id, d_handler in [(DEFAULT_RHINO_MATERIAL, DEFAULT_RHINO_MATERIAL_ID, default_material), (DEFAULT_TEXT_MATERIAL, DEFAULT_RHINO_TEXT_MATERIAL_ID, default_text_material)]:
        if d_name not in materials:
            tags = utils.create_tag_dict(d_id, d_name)
            blmat = utils.get_or_create_iddata(context.blend_data.materials, tags, None)
            is_harvested = blmat.get("rh_harvested", False)
            if update or not is_harvested:
                d_handler(blmat)
                blmat["rh_harvested"] = True
            materials[d_name] = blmat
            materials[-1] = blmat

    # Handle Rhino model materials
    for mid, mat in enumerate(model.Materials):
        matname = mat.Name if mat.Name else f"Material_{mid}"
        m = None
        if hasattr(model, "RenderContent") and model.RenderContent:
            try:
                m = model.RenderContent.FindId(mat.RenderMaterialInstanceId)
            except Exception:
                m = None
        
        mat_guid = m.Id if m else (mat.Id if hasattr(mat, "Id") else uuid.uuid1())
        blmat = context.blend_data.materials.get(matname)
        if not blmat:
            tags = utils.create_tag_dict(mat_guid, matname)
            blmat = utils.get_or_create_iddata(context.blend_data.materials, tags, None)
        
        is_harvested = blmat.get("rh_harvested", False)
        if update or not is_harvested:
            if m:
                harvest_from_rendercontent(model, m, blmat)
            else:
                harvest_from_rhino_material(mat, blmat)
            blmat["rh_harvested"] = True
            
        materials[mid] = blmat
        materials[str(mat_guid)] = blmat
        materials[matname] = blmat