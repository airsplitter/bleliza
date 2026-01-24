bl_info = {
    "name": "BleLiza",
    "author": "Christoph Maschowski",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "Material Properties > My Material Tools",
    "description": "Adds image texture slots and generates a node preset layout for ALIZA",
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
    ui.BLELIZA_MATERIAL_PT_parent,
    ui.MATERIAL_PT_texture_preset_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
