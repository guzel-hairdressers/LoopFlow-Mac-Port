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
    idef_map = options.get("idef_map", None)
    if idef_map is None:
        model = options.get("rh_model", None)
        if model and hasattr(model, "InstanceDefinitions"):
            idef_map = {idef.Id: (f"[Block] {idef.Name}" if idef.Name else f"Block {idef.Id}") for idef in model.InstanceDefinitions}
        else:
            idef_map = {}
        options["idef_map"] = idef_map

    block_name = idef_map.get(parent_id, f"Block {parent_id}")

    tags = utils.create_tag_dict(parent_id, block_name, None, None, True)
    idef_col = utils.get_or_create_iddata(context.blend_data.collections, tags, None)

    iref.empty_display_type = 'PLAIN_AXES'
    iref.instance_type = 'COLLECTION'
    iref.instance_collection = idef_col

    iref.matrix_world = utils.matrix_from_xform(ob.Geometry.Xform, scale)

def populate_instance_definitions(context, model, toplayer, layername, options, scale):
    import_as_grid = options.get("import_instances_grid_layout", False)

    if import_as_grid and len(model.InstanceDefinitions) > 0:
        count = 0
        columns = int(sqrt(len(model.InstanceDefinitions)))
        grid = options.get("import_instances_grid", 10.0) * scale

    # Build O(1) hash table mapping rhid -> Blender object
    rhid_to_ob = {}
    for ob in context.blend_data.objects:
        rhid = ob.get('rhid', None)
        if rhid:
            rhid_to_ob[str(rhid)] = ob

    for idef in model.InstanceDefinitions:
        block_name = f"[Block] {idef.Name}" if idef.Name else f"Block {idef.Id}"
        tags = utils.create_tag_dict(idef.Id, block_name, None, None, True)
        parent = utils.get_or_create_iddata(context.blend_data.collections, tags, None)
        objectids = idef.GetObjectIds()

        if import_as_grid:
            offset = Vector((count % columns * grid, (count - count % columns) / columns * grid, 0))
            parent.instance_offset = offset
            count += 1

        for guid in objectids:
            str_guid = str(guid)
            if str_guid in rhid_to_ob:
                ob = rhid_to_ob[str_guid]
                try:
                    if ob.name not in parent.objects:
                        parent.objects.link(ob)
                except Exception:
                    pass

    if layername in context.blend_data.collections:
        instance_col = context.blend_data.collections[layername]
        try:
            if instance_col.name not in toplayer.children:
                toplayer.children.link(instance_col)
        except Exception:
            pass
