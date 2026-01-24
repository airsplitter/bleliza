import bpy

# Custom parent panel to group our tools
class BLELIZA_MATERIAL_PT_parent(bpy.types.Panel):
    bl_label = "BleLiza Material Parameters"
    bl_idname = "BLELIZA_MATERIAL_PT_parent"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "material"
    
    def draw(self, context):
        layout = self.layout
        layout.label(text="Material Tools:")

# Panel nested inside our custom parent panel
class MATERIAL_PT_texture_preset_panel(bpy.types.Panel):
    bl_label = "Texture Preset"
    bl_idname = "MATERIAL_PT_texture_preset_panel"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "material"
    bl_parent_id = "BLELIZA_MATERIAL_PT_parent"  # Nest under our custom panel

    def draw(self, context):
        layout = self.layout
        layout.operator("node.create_preset_2020", text="Generate ALIZA Texture Preset from MSFS2020 Shader Mess ;-)")
        layout.operator("node.create_preset_2024", text="Generate ALIZA Texture Preset from MSFS2024 Shader Mess ;-)")
        layout.operator("object.replace_textures_with_dds", text="Replace Texures")
        layout.operator("object.remove_empty_textures_nodes", text="Remove empty textures nodes")
        layout.operator("object.create_and_assign_materials", text="Create & Assign Materials (10x10)")
