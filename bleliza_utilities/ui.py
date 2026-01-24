import bpy

# Custom parent panel to group our tools
class BLELIZA_MATERIAL_PT_parent(bpy.types.Panel):
    bl_label = "BleLIZA Material Parameters"
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

# Panel for creating materials
class MATERIAL_PT_create_materials_panel(bpy.types.Panel):
    bl_label = "Create Materials"
    bl_idname = "MATERIAL_PT_create_materials_panel"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "material"
    bl_parent_id = "BLELIZA_MATERIAL_PT_parent"  # Nest under our custom panel

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        col = layout.column()
        col.prop(scene, "bleliza_cols", text="Columns")
        col.prop(scene, "bleliza_rows", text="Rows")
        
        col.separator()
        col.label(text="Naming:")
        col.prop(scene, "bleliza_mat_prefix", text="Mat Prefix")
        col.prop(scene, "bleliza_tex_folder", text="Folder")
        col.prop(scene, "bleliza_tex_name_prefix", text="File Prefix")
        col.prop(scene, "bleliza_tex_name_suffix", text="File Suffix")
        col.prop(scene, "bleliza_tex_ext", text="Extension")
        
        col.separator()
        op = col.operator("object.create_and_assign_materials", text="Create & Assign Materials")
        op.grid_columns = scene.bleliza_cols
        op.grid_rows = scene.bleliza_rows
        op.mat_prefix = scene.bleliza_mat_prefix
        op.tex_folder = scene.bleliza_tex_folder
        op.tex_ext = scene.bleliza_tex_ext
        op.tex_name_prefix = scene.bleliza_tex_name_prefix
        op.tex_name_suffix = scene.bleliza_tex_name_suffix

# Panel for object tools
class BLELIZA_PT_object_tools(bpy.types.Panel):
    bl_label = "BleLIZA Object Tools"
    bl_idname = "BLELIZA_PT_object_tools"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        layout.label(text="Snap Islands:")
        layout.prop(scene, "bleliza_terrain_obj")
        
        op = layout.operator("object.snap_islands_to_terrain", text="Snap Islands to Terrain")
        if scene.bleliza_terrain_obj:
            op.terrain_name = scene.bleliza_terrain_obj.name
            
        layout.separator()
        layout.label(text="Selection:")
        layout.prop(scene, "bleliza_flat_threshold")
        
        op_sel = layout.operator("mesh.select_flat_islands", text="Select Flat Z Islands")
        op_sel.threshold = scene.bleliza_flat_threshold
        
        layout.separator()
        layout.label(text="Custom Properties:")
        
        # 1. Add shadow=0 to all
        op = layout.operator("object.bleliza_set_custom_property", text="Add Shadow=0 (All)")
        op.prop_name = "aliza_cast_shadow"
        op.prop_value = 0
        op.target = 'ALL'
        op.overwrite = False
        
        # 2. Set shadow=1 to selected
        op = layout.operator("object.bleliza_set_custom_property", text="Set Shadow=1 (Selected)")
        op.prop_name = "aliza_cast_shadow"
        op.prop_value = 1
        op.target = 'SELECTED'
        op.overwrite = True
        
        # 3. Set marking=1 to selected
        op = layout.operator("object.bleliza_set_custom_property", text="Set Marking=1 (Selected)")
        op.prop_name = "aliza_marking"
        op.prop_value = 1
        op.target = 'SELECTED'
        op.overwrite = True
        
        # 4. Set tree=1 to selected
        op = layout.operator("object.bleliza_set_custom_property", text="Set Tree=1 (Selected)")
        op.prop_name = "aliza_tree"
        op.prop_value = 1
        op.target = 'SELECTED'
        op.overwrite = True
        
        # 5. Set layer=0 to selected
        op = layout.operator("object.bleliza_set_custom_property", text="Set Layer=0 (Selected)")
        op.prop_name = "aliza_layer"
        op.prop_value = 0
        op.target = 'SELECTED'
        op.overwrite = True
