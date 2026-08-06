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
import bpy
from bpy import context

import uuid

from typing import Any, Dict

from .material import handle_materials, material_name, DEFAULT_RHINO_MATERIAL
from .layers import handle_layers
from .render_mesh import import_render_mesh
from .curve import import_curve
from .views import handle_views
from .groups import handle_groups
from .instances import import_instance_reference, handle_instance_definitions, populate_instance_definitions
from .pointcloud import import_pointcloud
from .annotation import import_annotation

from . import utils

'''
Dictionary mapping between the Rhino file types and importer functions
'''

RHINO_TYPE_TO_IMPORT = {
    r3d.ObjectType.Brep : import_render_mesh,
    r3d.ObjectType.Extrusion : import_render_mesh,
    r3d.ObjectType.Mesh : import_render_mesh,
    r3d.ObjectType.SubD : import_render_mesh,
    r3d.ObjectType.Surface : import_render_mesh,
    r3d.ObjectType.Curve : import_curve,
    r3d.ObjectType.PointSet: import_pointcloud,
    r3d.ObjectType.Annotation: import_annotation,
}


def initialize(
        context     : bpy.types.Context
) -> None:
    utils.reset_all_dict(context)

def cleanup() -> None:
    utils.clear_all_dict()

# TODO: Decouple object data creation from object creation
#       and consolidate object-level conversion.

def convert_object(
        context     : bpy.types.Context,
        ob          : r3d.File3dmObject,
        model       : r3d.File3dm,
        layerids    : Dict[int, bpy.types.Collection],
        materials   : Dict[int, bpy.types.Material],
        scale       : float,
        options     : Dict[str, Any]):
    """
    Add a new object with given data, link to
    collection given by layer
    """

    name = ob.Attributes.Name if ob.Attributes.Name else str(ob.Attributes.Id)
    layer = layerids.get(ob.Attributes.LayerIndex, context.scene.collection)
    
    # Resolve material index/guid from object or layer
    mat_idx = ob.Attributes.MaterialIndex
    if (ob.Attributes.MaterialSource == r3d.ObjectMaterialSource.MaterialFromLayer or mat_idx < 0) and model and 0 <= ob.Attributes.LayerIndex < len(model.Layers):
        l = model.Layers[ob.Attributes.LayerIndex]
        if hasattr(l, "RenderMaterialInstanceId") and str(l.RenderMaterialInstanceId) in materials:
            mat_idx = str(l.RenderMaterialInstanceId)
        elif hasattr(l, "RenderMaterialIndex"):
            mat_idx = l.RenderMaterialIndex
        elif hasattr(l, "MaterialIndex"):
            mat_idx = l.MaterialIndex
        else:
            mat_idx = -1

    rhinomat = materials.get(mat_idx, materials.get(str(mat_idx), materials.get(-1)))

    view_color = (200, 200, 200, 255)
    try:
        if ob.Attributes.ColorSource == r3d.ObjectColorSource.ColorFromObject:
            view_color = ob.Attributes.ObjectColor
        elif model and 0 <= ob.Attributes.LayerIndex < len(model.Layers):
            view_color = model.Layers[ob.Attributes.LayerIndex].Color
    except Exception:
        pass

    update_materials = options.get("update_materials", False)
    link_materials_to = options.get("link_materials_to", "PREFERENCES")
    data = None
    blender_object = None

    # Text curve is created by annotation import.
    # this needs to be added as an extra object
    # and parented to the annotation main import object
    text_curve = None
    text_object = None
    if ob.Geometry.ObjectType in RHINO_TYPE_TO_IMPORT:
        data = RHINO_TYPE_TO_IMPORT[ob.Geometry.ObjectType](context, ob, name, scale, options)
        if ob.Geometry.ObjectType == r3d.ObjectType.Annotation:
            text_curve = data[1]
            data = data[0]

    mat_from_object = ob.Attributes.MaterialSource == r3d.ObjectMaterialSource.MaterialFromObject

    tags = utils.create_tag_dict(ob.Attributes.Id, ob.Attributes.Name)
    if data is not None:
        data.materials.clear()
        data.materials.append(rhinomat)
        blender_object = utils.get_or_create_iddata(context.blend_data.objects, tags, data)
        if link_materials_to == "PREFERENCES":
            link_materials_to = bpy.context.preferences.edit.material_link
            if link_materials_to == 'OBDATA':
                link_materials_to = 'DATA'
        for slot in blender_object.material_slots:
            slot.link = link_materials_to

        if text_curve:
            text_tags = utils.create_tag_dict(uuid.uuid1(), f"TXT{ob.Attributes.Name}")
            text_curve[0].materials.append(rhinomat)
            text_object = utils.get_or_create_iddata(context.blend_data.objects, text_tags, text_curve[0])
            text_object.material_slots[0].link = 'OBJECT'
            text_object.material_slots[0].material = rhinomat
            text_object.parent = blender_object
            texmatrix = text_curve[1]
            text_object.matrix_world = texmatrix
    else:
        blender_object = context.blend_data.objects.new(name+"_Instance", None)
        utils.tag_data(blender_object, tags)

    blender_object.color = [x/255. for x in view_color]

    # Ensure viewport restriction (hide_viewport) and render restriction (hide_render) are FALSE so objects are NEVER disabled.
    blender_object.hide_viewport = False
    blender_object.hide_render = False

    # 1. Apply single Subdivision Surface modifier based on user UI slider (default 3)
    if ob.Geometry.ObjectType == r3d.ObjectType.SubD and blender_object and type(blender_object) == bpy.types.Object:
        subd_level = options.get("subd_subsurf_level", 3)
        if subd_level > 0:
            mod = blender_object.modifiers.get("Subdivision")
            if not mod:
                mod = blender_object.modifiers.new("Subdivision", 'SUBSURF')
            mod.levels = subd_level
            mod.render_levels = subd_level
            mod.boundary_smooth = 'ALL'

    # 2. Apply NURBS resolution_u / resolution_v based on user UI density slider
    if data and hasattr(data, "resolution_u"):
        density = options.get("nurbs_density", 0.5)
        res = int(4 + round(density * 28))
        data.resolution_u = res
        if hasattr(data, "resolution_v"):
            data.resolution_v = res

    if ob.Geometry.ObjectType == r3d.ObjectType.InstanceReference and options.get("import_instances", True):
        import_instance_reference(context, ob, blender_object, name, scale, options)

    # Import Rhino user strings
    for pair in ob.Attributes.GetUserStrings():
        blender_object[pair[0]] = pair[1]

    for pair in ob.Geometry.GetUserStrings():
        blender_object[pair[0]] = pair[1]

    # Always assign material to object if empty, None, or update_materials is True
    if rhinomat and not ob.Attributes.IsInstanceDefinitionObject and ob.Geometry.ObjectType != r3d.ObjectType.InstanceReference:
        if hasattr(blender_object, "material_slots"):
            if len(blender_object.material_slots) == 0:
                if hasattr(blender_object, "data") and hasattr(blender_object.data, "materials"):
                    blender_object.data.materials.append(rhinomat)
            elif blender_object.material_slots[0].material is None or update_materials:
                blender_object.material_slots[0].link = 'OBJECT'
                blender_object.material_slots[0].material = rhinomat

    # Instance definition objects are linked within their definition collections
    if not ob.Attributes.IsInstanceDefinitionObject:
        try:
            layer.objects.link(blender_object)
            if text_object:
                layer.objects.link(text_object)
        except Exception:
            pass

    return blender_object
