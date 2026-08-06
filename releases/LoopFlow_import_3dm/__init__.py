# -*- coding: utf-8 -*-
"""
====================================
Import Rhinoceros 3D (R2B Pro)
====================================
Version            : v5.2
Date               : 2026-07-31
Author             : Cursor + Claude Sonnet 4.6
Environment        : Blender 5.1.0+ / Python 3.13
Location           : 3D Viewport sidebar (N-Panel > LoopFlow 3dm > Rhino Live Link)

"""

bl_info = {
    "name": "Import Rhinoceros 3D (R2B Pro)",
    "author": "Ruslan F, Chihyu Tsai, Nathan 'jesterKing' Letwory, Joel Putnam, Tom Svilans",
    "version": (0, 0, 52),
    "blender": (5, 1, 0),
    "location": "N-Panel > LoopFlow 3dm",
    "description": "R2B Dual-JSON performance build with Auto Sync & Purge into top-level LoopFlow Collection",
    "category": "Import-Export",
}

import bpy
import os
import sys

# Add addon directory to sys.path for bundled rhino3dm module
addon_dir = os.path.dirname(os.path.abspath(__file__))
if addon_dir not in sys.path:
    sys.path.insert(0, addon_dir)

import re
import json
import mathutils
from pathlib import Path
from .read3dm import read_3dm
from bpy_extras.io_utils import ImportHelper

# Central Data Directory
DATA_DIR = os.path.expanduser("~/Library/Application Support/McNeel/Rhinoceros/8.0/scripts/LoopFlow_R2B/Data")
if not os.path.exists(DATA_DIR):
    DATA_DIR = os.path.expanduser("~/Desktop")

DEFAULT_R2B_MODEL = os.path.join(DATA_DIR, "R2B.obj")
SYNC_JSON_FILE    = os.path.join(DATA_DIR, "R2B_Sync.json")

# -------------------------------------------------------------------
# Module-level constants
# -------------------------------------------------------------------

CAMERA_SYNC_FILE   = "R2B_Camera_Sync.json"
LIGHT_SYNC_FILE    = "R2B_Light_Sync.json"

COL_FIXTURES       = "Lighting Fixtures"
COL_LIGHTING       = "Lighting"
COL_LIGHT_POINTS   = "R2B Lighting Points"
COL_MATERIALS      = "Materials"

MAT_PRESET_LT_K    = "Preset_Lighting_K"
LAYER_SUFFIX_LT    = "5_LT"
MAT_AUTO_5LT       = "Auto_5LT_Light"

CAMERA_POLL_INTERVAL = 0.03
DEFAULT_LENS         = 50.0
EMPTY_DISPLAY_SIZE   = 0.3

# -------------------------------------------------------------------
# View Layer Collection Un-Exclude State Sync Engine
# -------------------------------------------------------------------
_last_layer_col_excludes = {}
_is_syncing_layers = False

def _on_depsgraph_update_layer_collections(scene, depsgraph):
    global _is_syncing_layers
    if _is_syncing_layers:
        return
    
    vl = bpy.context.view_layer
    if not vl:
        return

    _is_syncing_layers = True
    try:
        def _sync_tree(lc, parent_was_excluded=False, parent_just_unexcluded=False):
            col = lc.collection
            col_name = col.name
            
            own_vis = col.get("rhino_own_visible", True)
            prev_ex = _last_layer_col_excludes.get(col_name, lc.exclude)
            curr_ex = lc.exclude

            child_parent_unexcluded = False
            curr_is_excluded = curr_ex

            if parent_just_unexcluded:
                if not own_vis:
                    lc.exclude = True
                    curr_is_excluded = True
                else:
                    lc.exclude = False
                    curr_is_excluded = False
                child_parent_unexcluded = True

            elif prev_ex and not curr_ex:
                col["rhino_own_visible"] = True
                child_parent_unexcluded = True
                curr_is_excluded = False

            elif not prev_ex and curr_ex:
                if not parent_was_excluded:
                    col["rhino_own_visible"] = False
                child_parent_unexcluded = False
                curr_is_excluded = True

            _last_layer_col_excludes[col_name] = curr_is_excluded

            for child in lc.children:
                _sync_tree(child, parent_was_excluded=(parent_was_excluded or curr_is_excluded), parent_just_unexcluded=child_parent_unexcluded)

        _sync_tree(vl.layer_collection)
    except Exception:
        pass
    finally:
        _is_syncing_layers = False

# -------------------------------------------------------------------
# 1. Core helper functions
# -------------------------------------------------------------------
def merge_duplicate_materials():
    count = 0
    for mat in list(bpy.data.materials):
        match = re.match(r"(.*)\.\d{3}$", mat.name)
        if match:
            base_name = match.group(1)
            base_mat = bpy.data.materials.get(base_name)
            if base_mat and base_mat != mat:
                mat.user_remap(base_mat)
                bpy.data.materials.remove(mat)
                count += 1
    return count

def get_template_objects(type_name):
    templates = []
    clean_type = type_name.strip()
    for col_name in [COL_FIXTURES, COL_LIGHTING]:
        col = bpy.data.collections.get(col_name)
        if col:
            for obj in col.objects:
                base_name = re.sub(r'\.\d{3}$', '', obj.name).strip()
                if base_name == clean_type:
                    templates.append(obj)
                    break
    return templates

def get_all_objects_in_collection(collection):
    objs = set(collection.objects)
    for child in collection.children:
        objs.update(get_all_objects_in_collection(child))
    return objs

# -------------------------------------------------------------------
# 2. Viewport sync engine (camera only)
# -------------------------------------------------------------------
def update_viewport_from_json():
    wm = bpy.context.window_manager
    scene = bpy.context.scene
    if wm.get("livelink_viewport_active", 0) == 0:
        return None

    json_dir = bpy.path.abspath(scene.rhino_json_dir)
    json_path = os.path.join(json_dir, CAMERA_SYNC_FILE)

    scale_factor = scene.rhino_cam_scale
    lens_mult = scene.rhino_cam_lens_mult

    if not os.path.exists(json_path):
        return CAMERA_POLL_INTERVAL

    try:
        current_mtime = os.path.getmtime(json_path)
        last_mtime = wm.get("livelink_last_mtime", 0.0)

        if current_mtime == last_mtime:
            return CAMERA_POLL_INTERVAL
        wm["livelink_last_mtime"] = current_mtime

        with open(json_path, 'r') as f:
            data = json.load(f)

        raw_x = data["location"]["x"] * scale_factor
        raw_y = data["location"]["y"] * scale_factor
        raw_z = data["location"]["z"] * scale_factor
        loc = mathutils.Vector((raw_x, raw_y, raw_z))

        dir_vec = mathutils.Vector((data["direction"]["x"], data["direction"]["y"], data["direction"]["z"])).normalized()
        up_vec  = mathutils.Vector((data["up"]["x"], data["up"]["y"], data["up"]["z"])).normalized()

        base_lens = data.get("lens", DEFAULT_LENS)
        final_lens = base_lens * lens_mult

        z_axis = -dir_vec
        x_axis = up_vec.cross(z_axis).normalized()
        y_axis = z_axis.cross(x_axis).normalized()

        mat = mathutils.Matrix((x_axis, y_axis, z_axis)).transposed()

        for window in wm.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    for space in area.spaces:
                        if space.type == 'VIEW_3D':
                            region_3d = space.region_3d
                            if region_3d.view_perspective == 'PERSP':
                                region_3d.view_location = loc
                                region_3d.view_rotation = mat.to_quaternion()
                                space.lens = final_lens
    except Exception:
        pass

    return CAMERA_POLL_INTERVAL

# -------------------------------------------------------------------
# Operators & Panel
# -------------------------------------------------------------------

class RHINO_OT_SyncLights(bpy.types.Operator):
    bl_idname = "import_3dm.sync_lights"
    bl_label = "Sync Lights from Rhino"
    bl_description = "Sync point positions from Rhino to instantiate fixtures or 5LT lights"

    def execute(self, context):
        scene = context.scene
        json_dir = bpy.path.abspath(scene.rhino_json_dir)
        json_path = os.path.join(json_dir, LIGHT_SYNC_FILE)

        if not os.path.exists(json_path):
            self.report({'ERROR'}, f"Light sync JSON not found: {json_path}")
            return {'CANCELLED'}

        try:
            with open(json_path, 'r') as f:
                data = json.load(f)

            light_col = bpy.data.collections.get(COL_LIGHT_POINTS)
            if not light_col:
                light_col = bpy.data.collections.new(COL_LIGHT_POINTS)
                context.scene.collection.children.link(light_col)

            active_guids = set()

            for pt in data.get("points", []):
                guid = pt["guid"]
                active_guids.add(guid)

                name = pt.get("name", "LightPoint")
                layer = pt.get("layer", "")

                pos = mathutils.Vector((
                    pt["location"]["x"] * scene.rhino_cam_scale,
                    pt["location"]["y"] * scene.rhino_cam_scale,
                    pt["location"]["z"] * scene.rhino_cam_scale
                ))

                empty = None
                for obj in light_col.objects:
                    if obj.get("rhino_guid") == guid:
                        empty = obj
                        break

                if not empty:
                    empty = bpy.data.objects.new(f"Empty_{name}", None)
                    empty.empty_display_type = 'PLAIN_AXES'
                    empty.empty_display_size = EMPTY_DISPLAY_SIZE
                    empty["rhino_guid"] = guid
                    light_col.objects.link(empty)

                empty.location = pos
                empty.name = f"Empty_{name}_{guid[:5]}"

            self.report({'INFO'}, f"Light sync complete! Processed {len(data.get('points', []))} point(s).")
        except Exception as e:
            self.report({'ERROR'}, f"Light sync failed: {e}")

        return {'FINISHED'}

class RHINO_OT_ResetProp(bpy.types.Operator):
    bl_idname = "import_3dm.reset_prop"
    bl_label = "Reset Property"
    bl_description = "Reset to default value"
    target: bpy.props.StringProperty()

    def execute(self, context):
        if self.target == "scale":
            context.scene.rhino_cam_scale = 0.01
            self.report({'INFO'}, "Scale Factor reset to default (0.01)")
        elif self.target == "lens":
            context.scene.rhino_cam_lens_mult = 1.80
            self.report({'INFO'}, "Lens Multiplier reset to default (1.80)")
        return {'FINISHED'}

class RHINO_OT_ToggleCamSync(bpy.types.Operator):
    bl_idname = "import_3dm.toggle_cam_sync"
    bl_label = "Toggle Camera Sync"
    bl_description = "Start or stop camera viewport sync with Rhino"

    def execute(self, context):
        wm = context.window_manager
        current_state = wm.get("livelink_viewport_active", 0)

        if current_state == 1:
            wm["livelink_viewport_active"] = 0
            self.report({'INFO'}, "Camera sync: stopped")
        else:
            wm["livelink_viewport_active"] = 1
            wm["livelink_last_mtime"] = 0.0
            bpy.app.timers.register(update_viewport_from_json)
            self.report({'INFO'}, "Camera sync: started")

        return {'FINISHED'}

class RHINO_OT_ShowHelp(bpy.types.Operator):
    bl_idname = "import_3dm.show_help"
    bl_label = "Rhino Live Link Quick Guide"
    bl_description = "Show the R2B workflow steps and notes"

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text="[Model Sync]", icon='MESH_DATA')
        box.label(text="1. Rhino: Click Fast Sync or Advanced Sync")
        box.label(text="2. Blender: Click 'Model Sync' in LoopFlow sidebar panel")
        layout.separator()
        box2 = layout.box()
        box2.label(text="[Auto Material & Lights]", icon='LIGHT')
        box2.label(text="1. Place prototype objects in Materials collection")
        box2.label(text="2. Toggle Camera Sync for real-time viewport alignment")

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=450)

class RHINO_OT_ResetPath(bpy.types.Operator):
    bl_idname = "import_3dm.reset_path"
    bl_label = "Auto-Detect Paths"
    bl_description = "Auto-detect model path and sync directory"

    def execute(self, context):
        candidates = [
            os.path.join(DATA_DIR, "R2B.obj"),
            os.path.join(DATA_DIR, "R2B.3dm"),
            DEFAULT_R2B_MODEL,
        ]
        
        found_model = candidates[0]
        for cand in candidates:
            if cand and os.path.exists(cand):
                found_model = cand
                break
                
        context.scene.rhino_update_path = found_model
        context.scene.rhino_json_dir = DATA_DIR

        self.report({'INFO'}, f"Paths auto-configured: {found_model}")
        return {'FINISHED'}

class RHINO_OT_QuickSync(bpy.types.Operator):
    bl_idname = "import_3dm.quick_sync"
    bl_label = "Rhino Quick Sync"

    @classmethod
    def description(cls, context, properties):
        mode = getattr(properties, 'import_mode', 'SYNC')
        if mode == 'OVERRIDE':
            return "Import 3DM model, replacing existing LoopFlow collection objects"
        elif mode == 'APPEND':
            return "Import 3DM model, appending geometry to existing layers and merging materials"
        return "Synchronize model updates with active Rhino session"

    import_mode: bpy.props.StringProperty(default='SYNC')
    update_mats: bpy.props.BoolProperty(default=False)

    def execute(self, context):
        is_standalone = (self.import_mode in ('OVERRIDE', 'APPEND')) or self.update_mats
        is_override = (self.import_mode == 'OVERRIDE')
        is_append = (self.import_mode == 'APPEND')

        raw_path = context.scene.rhino_update_path
        path = bpy.path.abspath(raw_path) if raw_path else ""

        target_path = ""

        if is_standalone:
            if path and os.path.exists(path) and path.endswith(".3dm"):
                target_path = path
            else:
                return bpy.ops.import_3dm.some_data('INVOKE_DEFAULT', update_materials=True, is_update=(not is_override), import_mode=self.import_mode)
        else:
            sync_meta = {}
            if os.path.exists(SYNC_JSON_FILE):
                try:
                    with open(SYNC_JSON_FILE, 'r', encoding='utf-8') as f:
                        sync_meta = json.load(f)
                except Exception:
                    pass

            active_filepath = sync_meta.get("active_filepath", "")
            fallback_filepath = sync_meta.get("fallback_filepath", "")

            if active_filepath and os.path.exists(active_filepath):
                target_path = active_filepath
            elif path and os.path.exists(path) and path.endswith(".3dm"):
                target_path = path
            elif fallback_filepath and os.path.exists(fallback_filepath):
                target_path = fallback_filepath

        if not target_path or not os.path.exists(target_path):
            if not is_standalone:
                self.report({'ERROR'}, f"No active sync file found in {DATA_DIR}. Please run Fast Sync or Advanced Sync in Rhino first!")
                return {'CANCELLED'}
            return bpy.ops.import_3dm.some_data('INVOKE_DEFAULT', update_materials=True, is_update=(not is_override), import_mode=self.import_mode)

        context.scene.rhino_update_path = target_path

        # If OVERRIDE mode, clear existing LoopFlow collection objects first
        if is_override:
            master_col = bpy.data.collections.get("LoopFlow")
            if master_col:
                objs_to_delete = get_all_objects_in_collection(master_col)
                for obj in objs_to_delete:
                    try:
                        bpy.data.objects.remove(obj, do_unlink=True)
                    except Exception:
                        pass

        # 1. Ensure master top-level 'LoopFlow' collection exists in Scene Collection
        master_col_name = "LoopFlow"
        master_col = bpy.data.collections.get(master_col_name)
        if not master_col:
            master_col = bpy.data.collections.new(name=master_col_name)
        if master_col.name not in context.scene.collection.children:
            try:
                context.scene.collection.children.link(master_col)
            except Exception:
                pass

        col_states = {}
        def capture_col_states(lc):
            col_states[lc.collection.name] = {
                'exclude': lc.exclude,
                'hide_viewport_eye': lc.hide_viewport,
                'hide_viewport_screen': lc.collection.hide_viewport,
                'hide_render': lc.collection.hide_render
            }
            for child in lc.children:
                capture_col_states(child)

        if not is_standalone:
            capture_col_states(context.view_layer.layer_collection)

        three_dm_path = target_path if target_path.endswith(".3dm") else os.path.splitext(target_path)[0] + ".3dm"

        bpy.ops.import_3dm.some_data(
            filepath=three_dm_path,
            import_curves=getattr(context.scene, "rhino_import_curves", False),
            import_meshes=getattr(context.scene, "rhino_import_meshes", True),
            weld_meshes=getattr(context.scene, "rhino_weld_meshes", True),
            nurbs_density=getattr(context.scene, "rhino_nurbs_density", 0.5),
            subd_subsurf_level=getattr(context.scene, "rhino_subd_subsurf_level", 1),
            update_materials=is_standalone,
            is_update=(not is_override),
            import_mode=self.import_mode
        )

        merged_count = merge_duplicate_materials()

        if not is_standalone and col_states:
            def restore_col_states(lc):
                if lc.collection.name in col_states:
                    state = col_states[lc.collection.name]
                    lc.hide_viewport = state['hide_viewport_eye']
                    lc.collection.hide_viewport = state['hide_viewport_screen']
                    lc.collection.hide_render = state['hide_render']
                for child in lc.children:
                    restore_col_states(child)

            restore_col_states(context.view_layer.layer_collection)

        if is_override:
            msg = f"Imported & Replaced LoopFlow model ({os.path.basename(three_dm_path)})."
        elif is_append:
            msg = f"Appended model ({os.path.basename(three_dm_path)}). Merged {merged_count} duplicate materials."
        else:
            msg = f"Model synchronized cleanly ({os.path.basename(three_dm_path)})."

        self.report({'INFO'}, msg)
        return {'FINISHED'}

# -------------------------------------------------------------------
# Panel Layout
# -------------------------------------------------------------------
class Import3dm(bpy.types.Operator, ImportHelper):
    bl_idname = "import_3dm.some_data"
    bl_label = "Import Rhinoceros 3D"
    filename_ext = ".3dm"
    filter_glob: bpy.props.StringProperty(default="*.3dm", options={'HIDDEN'})
    import_curves: bpy.props.BoolProperty(name="Curves", default=False)
    import_meshes: bpy.props.BoolProperty(name="Meshes", default=True)
    weld_meshes: bpy.props.BoolProperty(name="Weld Meshes", default=True)
    nurbs_density: bpy.props.FloatProperty(name="NURBS Density", default=0.5, min=0.0, max=1.0)
    subd_subsurf_level: bpy.props.IntProperty(name="SubD Subdivisions", default=1, min=0, max=5)
    import_mode: bpy.props.StringProperty(default='SYNC')
    update_materials: bpy.props.BoolProperty(name="Update Materials", default=False)
    is_update: bpy.props.BoolProperty(name="Is Update", default=False)

    def execute(self, context):
        options = self.as_keywords(ignore=("filter_glob",))
        return read_3dm(context, options)

class RHINO_PT_QuickUpdate(bpy.types.Panel):
    bl_label = "Rhino Live Link"
    bl_idname = "RHINO_PT_QuickUpdate"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'LoopFlow 3dm'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        wm = context.window_manager

        layout.label(text="Model Sync", icon='MESH_DATA')
        box_model = layout.box()

        col_upd = box_model.column()
        col_upd.scale_y = 1.3
        col_upd.operator("import_3dm.quick_sync", text="Model Sync", icon='FILE_REFRESH').import_mode = 'SYNC'

        row_import = box_model.row(align=True)
        row_import.scale_y = 1.2
        op_ovr = row_import.operator("import_3dm.quick_sync", text="Import (Override)", icon='IMPORT')
        op_ovr.import_mode = 'OVERRIDE'
        
        op_app = row_import.operator("import_3dm.quick_sync", text="Import (Append)", icon='ADD')
        op_app.import_mode = 'APPEND'

        row_opts = box_model.row(align=True)
        row_opts.prop(scene, "rhino_weld_meshes", text="Weld Meshes")
        row_opts.prop(scene, "rhino_import_curves", text="Import Curves")

        col_mesh = box_model.column(align=True)
        col_mesh.prop(scene, "rhino_nurbs_density", text="NURBS Density", slider=True)
        col_mesh.prop(scene, "rhino_subd_subsurf_level", text="SubD Subdivisions")

        row_model_path = box_model.row(align=True)
        row_model_path.prop(scene, "rhino_update_path", text="")
        row_model_path.operator("import_3dm.reset_path", text="", icon='VIEWZOOM')

        layout.separator()

        layout.label(text="Camera & Light Sync", icon='OUTLINER_OB_CAMERA')
        box_cam = layout.box()

        is_active = wm.get("livelink_viewport_active", 0) == 1
        col_sync = box_cam.column()
        col_sync.scale_y = 1.2
        if is_active:
            col_sync.operator("import_3dm.toggle_cam_sync", text="Stop Camera Sync", icon='CANCEL')
        else:
            col_sync.operator("import_3dm.toggle_cam_sync", text="Start Camera Sync", icon='PLAY')

        col_light = box_cam.column()
        col_light.scale_y = 1.1
        col_light.operator("import_3dm.sync_lights", text="Sync Light Points", icon='LIGHT_POINT')

        box_cam.operator("import_3dm.show_help", text="Help / Workflow Guide", icon='QUESTION')

classes = (
    RHINO_OT_SyncLights,
    RHINO_OT_ResetProp,
    RHINO_OT_ToggleCamSync,
    RHINO_OT_ShowHelp,
    RHINO_OT_ResetPath,
    RHINO_OT_QuickSync,
    Import3dm,
    RHINO_PT_QuickUpdate,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.rhino_update_path = bpy.props.StringProperty(
        name="Model File",
        description="Path to sync model file",
        default=os.path.join(DATA_DIR, "R2B.obj"),
        subtype='FILE_PATH'
    )
    bpy.types.Scene.rhino_json_dir = bpy.props.StringProperty(
        name="JSON Directory",
        description="Directory containing LiveLink sync JSON files",
        default=DATA_DIR,
        subtype='DIR_PATH'
    )
    bpy.types.Scene.rhino_import_curves = bpy.props.BoolProperty(
        name="Import Curves",
        description="Import CAD curves",
        default=False
    )
    bpy.types.Scene.rhino_import_meshes = bpy.props.BoolProperty(
        name="Import Meshes",
        description="Import mesh geometry",
        default=True
    )
    bpy.types.Scene.rhino_weld_meshes = bpy.props.BoolProperty(
        name="Weld Meshes",
        description="Weld mesh vertices",
        default=True
    )
    bpy.types.Scene.rhino_nurbs_density = bpy.props.FloatProperty(
        name="NURBS Density",
        description="NURBS render mesh polygonization resolution slider (0.0 = Fewer Polygons / Fast, 1.0 = More Polygons / Smooth)",
        default=0.5,
        min=0.0,
        max=1.0,
        subtype='FACTOR'
    )
    bpy.types.Scene.rhino_subd_subsurf_level = bpy.props.IntProperty(
        name="SubD Subdivisions",
        description="Number of subdivisions for SubD objects (Blender Subdivision Surface modifier level)",
        default=1,
        min=0,
        max=5
    )
    bpy.types.Scene.rhino_cam_scale = bpy.props.FloatProperty(
        name="Scale Factor",
        description="Scale factor from Rhino units to Blender meters",
        default=0.01
    )
    bpy.types.Scene.rhino_cam_lens_mult = bpy.props.FloatProperty(
        name="Lens Multiplier",
        description="Focal length multiplier",
        default=1.80
    )

    try:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph_update_layer_collections)
    except Exception:
        pass

def unregister():
    try:
        if _on_depsgraph_update_layer_collections in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph_update_layer_collections)
    except Exception:
        pass

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.rhino_update_path
    del bpy.types.Scene.rhino_json_dir
    del bpy.types.Scene.rhino_import_curves
    del bpy.types.Scene.rhino_import_meshes
    del bpy.types.Scene.rhino_weld_meshes
    del bpy.types.Scene.rhino_nurbs_density
    del bpy.types.Scene.rhino_subd_subsurf_level
    del bpy.types.Scene.rhino_cam_scale
    del bpy.types.Scene.rhino_cam_lens_mult

if __name__ == "__main__":
    register()
