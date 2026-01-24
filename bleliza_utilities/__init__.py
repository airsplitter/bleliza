bl_info = {
    "name": "BleLIZA",
    "author": "Christoph Maschowski",
    "version": (1, 10),
    "blender": (2, 80, 0),
    "location": "Material Properties > My Material Tools",
    "description": "Adds image texture slots, materials generation and generates a node preset layout for ALIZA",
    "category": "Node",
}

import bpy
import importlib
from . import operators
from . import ui

# Force reload of submodules to ensure new classes are picked up
importlib.reload(operators)
importlib.reload(ui)

classes = (
    operators.NODE_OT_create_preset_2020,
    operators.NODE_OT_create_preset_2024,
    operators.NODE_OT_replace_textures_script,
    operators.NODE_OT_remove_empty_textures_nodes_script,
    operators.NODE_OT_create_and_assign_materials,
    operators.NODE_OT_snap_islands_to_terrain,
    operators.NODE_OT_select_flat_islands,
    operators.OBJECT_OT_bleliza_set_custom_property,
    operators.NODE_OT_set_texture_extend,
    operators.NODE_OT_assign_random_materials_islands,
    ui.BLELIZA_MATERIAL_PT_parent,
    ui.MATERIAL_PT_texture_preset_panel,
    ui.MATERIAL_PT_create_materials_panel,
    ui.BLELIZA_PT_object_tools,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.bleliza_rows = bpy.props.IntProperty(
        name="Rows",
        description="Number of rows for the grid",
        default=10,
        min=1
    )
    bpy.types.Scene.bleliza_cols = bpy.props.IntProperty(
        name="Columns",
        description="Number of columns for the grid",
        default=10,
        min=1
    )
    
    bpy.types.Scene.bleliza_mat_prefix = bpy.props.StringProperty(
        name="Material Prefix",
        description="Prefix for the created material names",
        default="zrhGroundSwisstopo2022-8k_"
    )
    
    bpy.types.Scene.bleliza_tex_folder = bpy.props.StringProperty(
        name="Texture Folder",
        description="Folder containing the textures",
        default="//../dds/",
        subtype='DIR_PATH'
    )
    
    bpy.types.Scene.bleliza_tex_ext = bpy.props.StringProperty(
        name="Extension",
        description="File extension (e.g. .dds)",
        default=".dds"
    )
    
    bpy.types.Scene.bleliza_tex_name_prefix = bpy.props.StringProperty(
        name="Filename Prefix",
        description="Prefix before coordinates in filename",
        default=""
    )
    
    bpy.types.Scene.bleliza_tex_name_suffix = bpy.props.StringProperty(
        name="Filename Suffix",
        description="Suffix after coordinates but before extension",
        default=""
    )
    
    bpy.types.Scene.bleliza_terrain_obj = bpy.props.PointerProperty(
        name="Terrain Object",
        type=bpy.types.Object,
        description="Terrain object to snap to"
    )
    
    bpy.types.Scene.bleliza_flat_threshold = bpy.props.FloatProperty(
        name="Flat Threshold",
        description="Max Z difference for an island to be selected",
        default=1.0,
        min=0.0
    )

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    del bpy.types.Scene.bleliza_rows
    del bpy.types.Scene.bleliza_cols
    del bpy.types.Scene.bleliza_mat_prefix
    del bpy.types.Scene.bleliza_tex_folder
    del bpy.types.Scene.bleliza_tex_ext
    del bpy.types.Scene.bleliza_tex_name_prefix
    del bpy.types.Scene.bleliza_tex_name_suffix
    del bpy.types.Scene.bleliza_terrain_obj
    del bpy.types.Scene.bleliza_flat_threshold

if __name__ == "__main__":
    register()
