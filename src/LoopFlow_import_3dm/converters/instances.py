# MIT License
# Copyright (c) 2018-2024 Nathan Letwory, Joel Putnam, Tom Svilans, Lukas Fertig

import bpy
import rhino3dm as r3d
from mathutils import Matrix, Vector
from math import sqrt
from . import utils

def handle_instance_definitions(context, model, toplayer, layername):
    """
    Import instance definitions from rhino model as empty collections inside 'Instance Definitions'.
    """
    if not layername in context.blend_data.collections:
        instance_col = context.blend_data.collections.new(name=layername)
        instance_col.hide_render = True
        instance_col.hide_viewport = True
        try:
            toplayer.children.link(instance_col)
        except Exception:
            pass
    else:
        instance_col = context.blend_data.collections[layername]

    for idef in model.InstanceDefinitions:
        block_name = f"[Block] {idef.Name}" if idef.Name else f"Block {idef.Id}"
        tags = utils.create_tag_dict(idef.Id, block_name, None, None, True)
        idef_col = utils.get_or_create_iddata(context.blend_data.collections, tags, None)
        try:
            if idef_col.name not in instance_col.children:
                instance_col.children.link(idef_col)
        except Exception:
            pass

def import_instance_reference(context: bpy.types.Context, ob: r3d.File3dmObject, iref: bpy.types.Object, name: str, scale: float, options):
    """
    Convert a Rhino InstanceReference to a Blender Collection Instance Empty.
    """
    parent_id = ob.Geometry.ParentIdefId
    model = options.get("rh_model", None)
    block_name = ""
    if model and hasattr(model, "InstanceDefinitions"):
        for idef in model.InstanceDefinitions:
            if idef.Id == parent_id:
                block_name = f"[Block] {idef.Name}" if idef.Name else f"Block {idef.Id}"
                break
    if not block_name:
        block_name = f"Block {parent_id}"

    tags = utils.create_tag_dict(parent_id, block_name, None, None, True)
    idef_col = utils.get_or_create_iddata(context.blend_data.collections, tags, None)

    iref.empty_display_type = 'PLAIN_AXES'
    iref.instance_type = 'COLLECTION'
    iref.instance_collection = idef_col

    xform = list(ob.Geometry.Xform.ToFloatArray(1))
    xform_matrix = [
        [xform[0], xform[1], xform[2], xform[3] * scale],
        [xform[4], xform[5], xform[6], xform[7] * scale],
        [xform[8], xform[9], xform[10], xform[11] * scale],
        [xform[12], xform[13], xform[14], xform[15]]
    ]
    iref.matrix_world = Matrix(xform_matrix)

def populate_instance_definitions(context, model, toplayer, layername, options, scale):
    import_as_grid = options.get("import_instances_grid_layout", False)

    if import_as_grid and len(model.InstanceDefinitions) > 0:
        count = 0
        columns = int(sqrt(len(model.InstanceDefinitions)))
        grid = options.get("import_instances_grid", 10.0) * scale

    for idef in model.InstanceDefinitions:
        block_name = f"[Block] {idef.Name}" if idef.Name else f"Block {idef.Id}"
        tags = utils.create_tag_dict(idef.Id, block_name, None, None, True)
        parent = utils.get_or_create_iddata(context.blend_data.collections, tags, None)
        objectids = idef.GetObjectIds()

        if import_as_grid:
            offset = Vector((count % columns * grid, (count - count % columns) / columns * grid, 0))
            parent.instance_offset = offset
            count += 1

        for ob in context.blend_data.objects:
            for guid in objectids:
                if ob.get('rhid', None) == str(guid):
                    try:
                        if ob.name not in parent.objects:
                            parent.objects.link(ob)
                    except Exception:
                        pass
