import bpy
import os
import re
import bmesh
from mathutils import Vector

# Operator to add image texture nodes and create a node preset layout,
# filling them with images from existing nodes if available.
class NODE_OT_create_preset_2020(bpy.types.Operator):
    bl_idname = "node.create_preset_2020"
    bl_label = "Create Node Preset 2020"
    bl_description = "Creates image texture nodes with existing image values and arranges nodes in a preset layout"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        mat = context.object.active_material
        if not mat or not mat.use_nodes:
            self.report({'WARNING'}, "Active object must have a material with nodes")
            return {'CANCELLED'}
        
        node_tree = mat.node_tree
        
        # Retrieve values from nodes that might exist before clearing.
        base_color_value = None
        metallic_value = None
        roughness_value = None
        emissive_value = None
        detail_scale_value = None
        
        base_color_node = node_tree.nodes.get("Base Color RGB")
        base_color_alpha_node = node_tree.nodes.get("Base Color A")

        # Check if the node exists and has valid outputs
        if base_color_node and hasattr(base_color_node, "outputs") and base_color_node.outputs:
            base_color_value = base_color_node.outputs[0].default_value
        else:
            base_color_value = (1.0, 1.0, 1.0)  # Fallback to white
            
        # Check if the node exists and has valid outputs
        if base_color_alpha_node and hasattr(base_color_node, "outputs") and base_color_node.outputs:
            base_color_alpha_value = base_color_alpha_node.outputs[0].default_value
        else:
            base_color_alpha_value = (1)  # Fallback to white
        
        # Ensure base_color_value has an RGBA format by adding an alpha channel
        if len(base_color_value) == 3:
            base_color_rgba = (*base_color_value, *base_color_alpha_value)  # Adds the alpha value
        elif len(base_color_value) == 4:
            base_color_rgba = base_color_value  # It already has 4 sequences (RGBA)
        
        metallic_node = node_tree.nodes.get("Metallic Scale")
        if metallic_node and hasattr(metallic_node, "outputs") and metallic_node.outputs:
            metallic_value = metallic_node.outputs[0].default_value

        roughness_node = node_tree.nodes.get("Roughness Scale")
        if roughness_node and hasattr(roughness_node, "outputs") and roughness_node.outputs:
            roughness_value = roughness_node.outputs[0].default_value

        emissive_node = node_tree.nodes.get("Emissive Scale")
        if emissive_node and hasattr(emissive_node, "outputs") and emissive_node.outputs:
            emissive_value = emissive_node.outputs[0].default_value
            
        detail_scale_node = node_tree.nodes.get("Detail UV Scale")
        if detail_scale_node and hasattr(detail_scale_node, "outputs") and detail_scale_node.outputs:
            detail_scale_value = detail_scale_node.outputs[0].default_value

        # Try to find existing nodes (if any) before clearing the node tree.
        existing_base = node_tree.nodes.get("Base Color Texture")
        existing_detail = node_tree.nodes.get("Detail Color(RGBA)")
        existing_base_mat = node_tree.nodes.get("Occlusion(R) Roughness(G) Metallic(B)")
        existing_detail_mat = node_tree.nodes.get("Detail Occlusion(R) Roughness(G) Metallic(B)")
        existing_normal = node_tree.nodes.get("Normal Texture")
        existing_normal_map_node = node_tree.nodes.get("Normal Map Sampler")
        
        base_image = existing_base.image if existing_base and existing_base.image else None
        detail_image = existing_detail.image if existing_detail and existing_detail.image else None
        base_mat_image = existing_base_mat.image if existing_base_mat and existing_base_mat.image else None
        detail_mat_image = existing_detail_mat.image if existing_detail_mat and existing_detail_mat.image else None
        normal_image = existing_normal.image if existing_normal and existing_normal.image else None
        # Get the 'Strength' value from the existing node if it has the input
        if "Strength" in existing_normal_map_node.inputs:
            strength_value_to_apply = existing_normal_map_node.inputs["Strength"].default_value
        
        # Clear existing nodes (optional – here we rebuild the node tree)
        for node in list(node_tree.nodes):
            node_tree.nodes.remove(node)
        
        # Create Material Output node
        output_node = node_tree.nodes.new(type="ShaderNodeOutputMaterial")
        output_node.location = (500, 0)
        
        # Create Principled BSDF node
        bsdf_node = node_tree.nodes.new(type="ShaderNodeBsdfPrincipled")
        bsdf_node.location = (200, 0)
        node_tree.links.new(bsdf_node.outputs["BSDF"], output_node.inputs["Surface"])
        
        # Transfer value from "Base Color" to BSDF input "Base Color"
        if base_color_value is not None:
            bsdf_node.inputs["Base Color"].default_value = base_color_rgba
        
        # Transfer value from "Metallic Factor" to BSDF input "Metallic"
        if metallic_value is not None:
            bsdf_node.inputs["Metallic"].default_value = metallic_value
        
        # Transfer value from "Roughness Factor" to BSDF input "Roughness"
        if roughness_value is not None:
            bsdf_node.inputs["Roughness"].default_value = roughness_value

        # For emission, assume there is a custom input called "Emission Strength" in the shader.
        if emissive_value is not None and "Emission Strength" in bsdf_node.inputs:
            bsdf_node.inputs["Emission Strength"].default_value = emissive_value
        
        # Create Image Texture node for Base Color and assign image from existing node if available
        base_color_node = node_tree.nodes.new(type="ShaderNodeTexImage")
        base_color_node.location = (-500, 100)
        base_color_node.name = "Base Color Texture"  # set name for clarity
        if base_image:
            base_color_node.image = base_image
            base_color_node.image.colorspace_settings.name = 'sRGB'
        
        # Create another Image Texture node for Detail Color and assign image from existing node if available
        detail_color_node = node_tree.nodes.new(type="ShaderNodeTexImage")
        detail_color_node.location = (-500, -200)
        detail_color_node.name = "Detail Color"
        if detail_image:
            detail_color_node.image = detail_image
            detail_color_node.image.colorspace_settings.name = 'sRGB'
            
        # Create Image Texture node for Base Color Material and assign image from existing node if available
        base_mat_color_node = node_tree.nodes.new(type="ShaderNodeTexImage")
        base_mat_color_node.location = (-800, 0)
        base_mat_color_node.name = "Base Color Material Texture"  # set name for clarity
        if base_mat_image:
            base_mat_color_node.image = base_mat_image
            base_mat_color_node.image.colorspace_settings.name = 'Non-Color'
        
        # Create another Image Texture node for Detail Color Material and assign image from existing node if available
        detail_mat_color_node = node_tree.nodes.new(type="ShaderNodeTexImage")
        detail_mat_color_node.location = (-800, -300)
        detail_mat_color_node.name = "Detail Color"
        if detail_mat_image:
            detail_mat_color_node.image = detail_mat_image
            detail_mat_color_node.image.colorspace_settings.name = 'Non-Color'
            
        # Create another Image Texture node for Normal Map and assign image from existing node if available
        normal_color_node = node_tree.nodes.new(type="ShaderNodeTexImage")
        normal_color_node.location = (-500, -500)
        normal_color_node.name = "Normal Image"
        if normal_image:
            normal_color_node.image = normal_image
            normal_color_node.image.colorspace_settings.name = 'Non-Color'
        
        # Create a Normal Map node
        if existing_normal_map_node:
            normal_map_node = node_tree.nodes.new(type="ShaderNodeNormalMap")
            normal_map_node.inputs["Strength"].default_value = strength_value_to_apply
            normal_map_node.location = (-200, -500)
        else:
            normal_map_node = node_tree.nodes.new(type="ShaderNodeNormalMap")
            normal_map_node.location = (-200, -500)
        
        # Connect the Normal Map node to the Principled BSDF node's Normal input
        node_tree.links.new(normal_map_node.outputs["Normal"], bsdf_node.inputs["Normal"])
        
        # Link the normal image texture node into the Normal Map node's "Color" input
        node_tree.links.new(normal_color_node.outputs["Color"], normal_map_node.inputs["Color"])
        
        # Check if base and detail textures have images
        has_base_image = base_color_node.image is not None
        has_detail_image = detail_color_node.image is not None
        
        if has_base_image and has_detail_image:
            # Create a Mix Color node for albedo images
            mix_node = node_tree.nodes.new(type="ShaderNodeMixRGB")
            mix_node.location = (-200, 100)
            mix_node.blend_type = 'MIX'  # Use MIX mode (default)
            mix_node.inputs["Fac"].default_value = 0.5  # Adjust the factor as needed
            # Link the two albedo image texture nodes into the MixRGB node
            node_tree.links.new(base_color_node.outputs["Color"], mix_node.inputs[1])
            node_tree.links.new(detail_color_node.outputs["Color"], mix_node.inputs[2])
            # Link the output of the Mix Color node to the Principled BSDF's Base Color input
            node_tree.links.new(mix_node.outputs["Color"], bsdf_node.inputs["Base Color"])
        elif has_base_image:
            node_tree.links.new(base_color_node.outputs["Color"], bsdf_node.inputs["Base Color"])
        elif has_detail_image:
            # Create a Mix Color node for albedo images
            mix_node = node_tree.nodes.new(type="ShaderNodeMixRGB")
            mix_node.location = (0, 100)
            mix_node.blend_type = 'MIX'  # Use MIX mode (default)
            mix_node.inputs["Fac"].default_value = 0.5  # Adjust the factor as needed
            color_input = node_tree.nodes.new(type="ShaderNodeRGB")
            color_input.location = (-200, 100)
            color_input.label = "Base Color Input"  # Name it for clarity
            # Set the color value (RGBA format: (R, G, B, Alpha))
            color_input.outputs[0].default_value = base_color_rgba  # Must be a tuple (R, G, B, A)
            node_tree.links.new(color_input.outputs["Color"], mix_node.inputs[1])  # Connect to input 1
            node_tree.links.new(detail_color_node.outputs["Color"], mix_node.inputs[2])
            # Link the output of the Mix Color node to the Principled BSDF's Base Color input
            node_tree.links.new(mix_node.outputs["Color"], bsdf_node.inputs["Base Color"])
        else:
            color_input = node_tree.nodes.new(type="ShaderNodeRGB")
            color_input.label = "Base Color Input"  # Name it for clarity
            color_input.outputs[0].default_value = base_color_rgba  # Must be a tuple (R, G, B, A)
            node_tree.links.new(color_input.outputs["Color"], bsdf_node.inputs["Base Color"])
        
        # Check if base and detail material textures have images
        has_base_mat_image = base_mat_color_node.image is not None
        has_detail_mat_image = detail_mat_color_node.image is not None
        
        if has_base_mat_image and has_detail_mat_image:
            # Create a Mix Color node for material images
            mix_mat_node = node_tree.nodes.new(type="ShaderNodeMixRGB")
            mix_mat_node.location = (-200, -150)
            mix_mat_node.blend_type = 'MIX'  # Use MIX mode (default)
            mix_mat_node.inputs["Fac"].default_value = 0.5  # Adjust the factor as needed
        
            # Link the two material image texture nodes into the MixRGB node
            node_tree.links.new(base_mat_color_node.outputs["Color"], mix_mat_node.inputs[1])
            node_tree.links.new(detail_mat_color_node.outputs["Color"], mix_mat_node.inputs[2])
            
            # Create a Separate Color node
            separate_node = node_tree.nodes.new("ShaderNodeSeparateColor")
            separate_node.location = (0, -150)  # adjust the location as needed
            
            # Link the output of the Mix Color material node to the Separate Color node input
            node_tree.links.new(mix_mat_node.outputs["Color"], separate_node.inputs["Color"])
            
            # Connect the Green channel from the Separate Color node to the Metallic input.
            node_tree.links.new(separate_node.outputs["Green"], bsdf_node.inputs["Metallic"])
            
            # Connect the Red channel from the Separate Color node to the Roughness input.
            node_tree.links.new(separate_node.outputs["Red"], bsdf_node.inputs["Roughness"])
        elif has_base_mat_image:
            # Create a Separate Color node
            separate_node = node_tree.nodes.new("ShaderNodeSeparateColor")
            separate_node.location = (0, -150)  # adjust the location as needed
            
            # Link the output of the Base Color material node to the Separate Color node input
            node_tree.links.new(base_mat_color_node.outputs["Color"], separate_node.inputs["Color"])
            
            # Connect the Green channel from the Separate Color node to the Metallic input.
            node_tree.links.new(separate_node.outputs["Green"], bsdf_node.inputs["Metallic"])
            
            # Connect the Red channel from the Separate Color node to the Roughness input.
            node_tree.links.new(separate_node.outputs["Red"], bsdf_node.inputs["Roughness"])
        elif has_detail_mat_image:
            # Create a Separate Color node
            separate_node = node_tree.nodes.new("ShaderNodeSeparateColor")
            separate_node.location = (0, -150)  # adjust the location as needed
            
            # Link the output of the Detail Color material node to the Separate Color node input
            node_tree.links.new(detail_mat_color_node.outputs["Color"], separate_node.inputs["Color"])
            
            # Connect the Green channel from the Separate Color node to the Metallic input.
            node_tree.links.new(separate_node.outputs["Green"], bsdf_node.inputs["Metallic"])
            
            # Connect the Red channel from the Separate Color node to the Roughness input.
            node_tree.links.new(separate_node.outputs["Red"], bsdf_node.inputs["Roughness"])
        
        # Create a UV Map node
        obj = context.object
        if hasattr(obj.data, "uv_layers") and obj.data.uv_layers:
            first_uv = obj.data.uv_layers[0].name
        else:
            first_uv = "UVMap"  # fallback if no UV maps exist
        uv_map_node = node_tree.nodes.new(type="ShaderNodeUVMap")
        uv_map_node.location = (-1200, 0)  # adjust location as needed
        uv_map_node.uv_map = first_uv  # use the first UV map name from the object
        
        # Connect the UV Map node output to the Vector input of each image texture node
        node_tree.links.new(uv_map_node.outputs["UV"], base_color_node.inputs["Vector"])
        
        node_tree.links.new(uv_map_node.outputs["UV"], base_mat_color_node.inputs["Vector"])
        node_tree.links.new(uv_map_node.outputs["UV"], detail_mat_color_node.inputs["Vector"])
        node_tree.links.new(uv_map_node.outputs["UV"], normal_color_node.inputs["Vector"])
        
        # --- START OF ADJUSTED CODE ---
        
        # Create a Mapping node
        mapping_node = node_tree.nodes.new(type="ShaderNodeMapping")
        mapping_node.location = (-1000, -300)  # Adjust location as needed
        mapping_node.vector_type = 'TEXTURE' # Set to texture to expose scale
        
        # Set the scale values
        if detail_scale_value is not None:
            mapping_node.inputs["Scale"].default_value = (detail_scale_value, detail_scale_value, 1.0) # X, Y, Z
        else:
            mapping_node.inputs["Scale"].default_value = (1.0, 1.0, 1.0) # Fallback value
        
        # Connect the UV Map node output to the Mapping node's Vector input
        node_tree.links.new(uv_map_node.outputs["UV"], mapping_node.inputs["Vector"])
        
        # Connect the output of the Mapping node to the Detail Image node's Vector input
        node_tree.links.new(mapping_node.outputs["Vector"], detail_color_node.inputs["Vector"])
        node_tree.links.new(mapping_node.outputs["Vector"], detail_mat_color_node.inputs["Vector"])
        
        self.report({'INFO'}, "Node preset layout created with existing texture values (if available)")
        return {'FINISHED'}
        
# Operator to add image texture nodes and create a node preset layout,
# filling them with images from existing nodes if available.
class NODE_OT_create_preset_2024(bpy.types.Operator):
    bl_idname = "node.create_preset_2024"
    bl_label = "Create Node Preset 2024"
    bl_description = "Creates image texture nodes with existing image values and arranges nodes in a preset layout"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        mat = context.object.active_material
        if not mat or not mat.use_nodes:
            self.report({'WARNING'}, "Active object must have a material with nodes")
            return {'CANCELLED'}
        
        node_tree = mat.node_tree
        
        # Retrieve values from nodes that might exist before clearing.
        base_color_value = None
        metallic_value = None
        roughness_value = None
        emissive_value = None
        detail_scale_value = None
        
        base_color_node = node_tree.nodes.get("Base Color")

        # Check if the node exists and has valid outputs
        if base_color_node and hasattr(base_color_node, "outputs") and base_color_node.outputs:
            base_color_value = base_color_node.outputs[0].default_value
        else:
            base_color_value = (1.0, 1.0, 1.0)  # Fallback to white
        
        # Ensure base_color_value has an RGBA format by adding an alpha channel
        if len(base_color_value) == 3:
            base_color_rgba = (*base_color_value, 1.0)  # Adds 1.0 as the alpha value
        elif len(base_color_value) == 4:
            base_color_rgba = base_color_value  # It already has 4 sequences (RGBA)
        
        metallic_node = node_tree.nodes.get("Metallic Factor")
        if metallic_node and hasattr(metallic_node, "outputs") and metallic_node.outputs:
            metallic_value = metallic_node.outputs[0].default_value

        roughness_node = node_tree.nodes.get("Roughness Factor")
        if roughness_node and hasattr(roughness_node, "outputs") and roughness_node.outputs:
            roughness_value = roughness_node.outputs[0].default_value

        emissive_node = node_tree.nodes.get("Emissive Scale")
        if emissive_node and hasattr(emissive_node, "outputs") and emissive_node.outputs:
            emissive_value = emissive_node.outputs[0].default_value
            
        detail_scale_node = node_tree.nodes.get("Detail UV Scale")
        if detail_scale_node and hasattr(detail_scale_node, "outputs") and detail_scale_node.outputs:
            detail_scale_value = detail_scale_node.outputs[0].default_value
        
        # Retrieve the normal scale value from an existing node named "Normal Scale"
        normal_scale_value = None
        normal_scale_node = node_tree.nodes.get("Normal Scale")
        if normal_scale_node and hasattr(normal_scale_node, "outputs") and normal_scale_node.outputs:
            normal_scale_value = normal_scale_node.outputs[0].default_value
        
        # Try to find existing nodes (if any) before clearing the node tree.
        existing_base = node_tree.nodes.get("Base Color Texture (RGBA)")
        existing_detail = node_tree.nodes.get("Detail Color (RGB), Alpha (A)")
        existing_base_mat = node_tree.nodes.get("Occlusion (R), Roughness (G), Metallic (B)")
        existing_detail_mat = node_tree.nodes.get("Detail Occlusion (R), Roughness (G), Metallic (B)")
        existing_normal = node_tree.nodes.get("Normal Texture (RGB)")
        
        base_image = existing_base.image if existing_base and existing_base.image else None
        detail_image = existing_detail.image if existing_detail and existing_detail.image else None
        base_mat_image = existing_base_mat.image if existing_base_mat and existing_base_mat.image else None
        detail_mat_image = existing_detail_mat.image if existing_detail_mat and existing_detail_mat.image else None
        normal_image = existing_normal.image if existing_normal and existing_normal.image else None
        
        # Clear existing nodes (optional – here we rebuild the node tree)
        for node in list(node_tree.nodes):
            node_tree.nodes.remove(node)
        
        # Create Material Output node
        output_node = node_tree.nodes.new(type="ShaderNodeOutputMaterial")
        output_node.location = (500, 0)
        
        # Create Principled BSDF node
        bsdf_node = node_tree.nodes.new(type="ShaderNodeBsdfPrincipled")
        bsdf_node.location = (200, 0)
        node_tree.links.new(bsdf_node.outputs["BSDF"], output_node.inputs["Surface"])
        
        # Transfer value from "Base Color" to BSDF input "Base Color"
        if base_color_value is not None:
            bsdf_node.inputs["Base Color"].default_value = base_color_rgba
        
        # Transfer value from "Metallic Factor" to BSDF input "Metallic"
        if metallic_value is not None:
            bsdf_node.inputs["Metallic"].default_value = metallic_value
        
        # Transfer value from "Roughness Factor" to BSDF input "Roughness"
        if roughness_value is not None:
            bsdf_node.inputs["Roughness"].default_value = roughness_value

        # For emission, assume there is a custom input called "Emission Strength" in the shader.
        if emissive_value is not None and "Emission Strength" in bsdf_node.inputs:
            bsdf_node.inputs["Emission Strength"].default_value = emissive_value
        
        # Create Image Texture node for Base Color and assign image from existing node if available
        base_color_node = node_tree.nodes.new(type="ShaderNodeTexImage")
        base_color_node.location = (-500, 100)
        base_color_node.name = "Base Color Texture"  # set name for clarity
        if base_image:
            base_color_node.image = base_image
            base_color_node.image.colorspace_settings.name = 'sRGB'
        
        # Create another Image Texture node for Detail Color and assign image from existing node if available
        detail_color_node = node_tree.nodes.new(type="ShaderNodeTexImage")
        detail_color_node.location = (-500, -200)
        detail_color_node.name = "Detail Color"
        if detail_image:
            detail_color_node.image = detail_image
            detail_color_node.image.colorspace_settings.name = 'sRGB'
            
        # Create Image Texture node for Base Color Material and assign image from existing node if available
        base_mat_color_node = node_tree.nodes.new(type="ShaderNodeTexImage")
        base_mat_color_node.location = (-800, 0)
        base_mat_color_node.name = "Base Color Material Texture"  # set name for clarity
        if base_mat_image:
            base_mat_color_node.image = base_mat_image
            base_mat_color_node.image.colorspace_settings.name = 'Non-Color'
        
        # Create another Image Texture node for Detail Color Material and assign image from existing node if available
        detail_mat_color_node = node_tree.nodes.new(type="ShaderNodeTexImage")
        detail_mat_color_node.location = (-800, -300)
        detail_mat_color_node.name = "Detail Color"
        if detail_mat_image:
            detail_mat_color_node.image = detail_mat_image
            detail_mat_color_node.image.colorspace_settings.name = 'Non-Color'
            
        # Create another Image Texture node for Normal Map and assign image from existing node if available
        normal_color_node = node_tree.nodes.new(type="ShaderNodeTexImage")
        normal_color_node.location = (-500, -500)
        normal_color_node.name = "Normal Image"
        if normal_image:
            normal_color_node.image = normal_image
            normal_color_node.image.colorspace_settings.name = 'Non-Color'
        
        # Create a Normal Map node
        normal_map_node = node_tree.nodes.new(type="ShaderNodeNormalMap")
        normal_map_node.location = (-200, -500)
        if normal_scale_value is not None:
            normal_map_node.inputs["Strength"].default_value = normal_scale_value
        
        # Connect the Normal Map node to the Principled BSDF node's Normal input
        node_tree.links.new(normal_map_node.outputs["Normal"], bsdf_node.inputs["Normal"])
        
        # Link the normal image texture node into the Normal Map node's "Color" input
        node_tree.links.new(normal_color_node.outputs["Color"], normal_map_node.inputs["Color"])
        
        # Check if base and detail textures have images
        has_base_image = base_color_node.image is not None
        has_detail_image = detail_color_node.image is not None
        
        if has_base_image and has_detail_image:
            # Create a Mix Color node for albedo images
            mix_node = node_tree.nodes.new(type="ShaderNodeMixRGB")
            mix_node.location = (-200, 100)
            mix_node.blend_type = 'MIX'  # Use MIX mode (default)
            mix_node.inputs["Fac"].default_value = 0.5  # Adjust the factor as needed
            # Link the two albedo image texture nodes into the MixRGB node
            node_tree.links.new(base_color_node.outputs["Color"], mix_node.inputs[1])
            node_tree.links.new(detail_color_node.outputs["Color"], mix_node.inputs[2])
            # Link the output of the Mix Color node to the Principled BSDF's Base Color input
            node_tree.links.new(mix_node.outputs["Color"], bsdf_node.inputs["Base Color"])
        elif has_base_image:
            node_tree.links.new(base_color_node.outputs["Color"], bsdf_node.inputs["Base Color"])
        elif has_detail_image:
            # Create a Mix Color node for albedo images
            mix_node = node_tree.nodes.new(type="ShaderNodeMixRGB")
            mix_node.location = (0, 100)
            mix_node.blend_type = 'MIX'  # Use MIX mode (default)
            mix_node.inputs["Fac"].default_value = 0.5  # Adjust the factor as needed
            color_input = node_tree.nodes.new(type="ShaderNodeRGB")
            color_input.location = (-200, 100)
            color_input.label = "Base Color Input"  # Name it for clarity
            # Set the color value (RGBA format: (R, G, B, Alpha))
            color_input.outputs[0].default_value = base_color_rgba  # Must be a tuple (R, G, B, A)
            node_tree.links.new(color_input.outputs["Color"], mix_node.inputs[1])  # Connect to input 1
            node_tree.links.new(detail_color_node.outputs["Color"], mix_node.inputs[2])
            # Link the output of the Mix Color node to the Principled BSDF's Base Color input
            node_tree.links.new(mix_node.outputs["Color"], bsdf_node.inputs["Base Color"])
        else:
            color_input = node_tree.nodes.new(type="ShaderNodeRGB")
            color_input.label = "Base Color Input"  # Name it for clarity
            color_input.outputs[0].default_value = base_color_rgba  # Must be a tuple (R, G, B, A)
            node_tree.links.new(color_input.outputs["Color"], bsdf_node.inputs["Base Color"])
        
        # Check if base and detail material textures have images
        has_base_mat_image = base_mat_color_node.image is not None
        has_detail_mat_image = detail_mat_color_node.image is not None
        
        if has_base_mat_image and has_detail_mat_image:
            # Create a Mix Color node for material images
            mix_mat_node = node_tree.nodes.new(type="ShaderNodeMixRGB")
            mix_mat_node.location = (-200, -150)
            mix_mat_node.blend_type = 'MIX'  # Use MIX mode (default)
            mix_mat_node.inputs["Fac"].default_value = 0.5  # Adjust the factor as needed
        
            # Link the two material image texture nodes into the MixRGB node
            node_tree.links.new(base_mat_color_node.outputs["Color"], mix_mat_node.inputs[1])
            node_tree.links.new(detail_mat_color_node.outputs["Color"], mix_mat_node.inputs[2])
            
            # Create a Separate Color node
            separate_node = node_tree.nodes.new("ShaderNodeSeparateColor")
            separate_node.location = (0, -150)  # adjust the location as needed
            
            # Link the output of the Mix Color material node to the Separate Color node input
            node_tree.links.new(mix_mat_node.outputs["Color"], separate_node.inputs["Color"])
            
            # Connect the Green channel from the Separate Color node to the Metallic input.
            node_tree.links.new(separate_node.outputs["Green"], bsdf_node.inputs["Metallic"])
            
            # Connect the Red channel from the Separate Color node to the Roughness input.
            node_tree.links.new(separate_node.outputs["Red"], bsdf_node.inputs["Roughness"])
        elif has_base_mat_image:
            # Create a Separate Color node
            separate_node = node_tree.nodes.new("ShaderNodeSeparateColor")
            separate_node.location = (0, -150)  # adjust the location as needed
            
            # Link the output of the Base Color material node to the Separate Color node input
            node_tree.links.new(base_mat_color_node.outputs["Color"], separate_node.inputs["Color"])
            
            # Connect the Green channel from the Separate Color node to the Metallic input.
            node_tree.links.new(separate_node.outputs["Green"], bsdf_node.inputs["Metallic"])
            
            # Connect the Red channel from the Separate Color node to the Roughness input.
            node_tree.links.new(separate_node.outputs["Red"], bsdf_node.inputs["Roughness"])
        elif has_detail_mat_image:
            # Create a Separate Color node
            separate_node = node_tree.nodes.new("ShaderNodeSeparateColor")
            separate_node.location = (0, -150)  # adjust the location as needed
            
            # Link the output of the Detail Color material node to the Separate Color node input
            node_tree.links.new(detail_mat_color_node.outputs["Color"], separate_node.inputs["Color"])
            
            # Connect the Green channel from the Separate Color node to the Metallic input.
            node_tree.links.new(separate_node.outputs["Green"], bsdf_node.inputs["Metallic"])
            
            # Connect the Red channel from the Separate Color node to the Roughness input.
            node_tree.links.new(separate_node.outputs["Red"], bsdf_node.inputs["Roughness"])
        
        # Create a UV Map node
        obj = context.object
        if hasattr(obj.data, "uv_layers") and obj.data.uv_layers:
            first_uv = obj.data.uv_layers[0].name
        else:
            first_uv = "UVMap"  # fallback if no UV maps exist
        uv_map_node = node_tree.nodes.new(type="ShaderNodeUVMap")
        uv_map_node.location = (-1200, 0)  # adjust location as needed
        uv_map_node.uv_map = first_uv  # use the first UV map name from the object
        
        # Connect the UV Map node output to the Vector input of each image texture node
        node_tree.links.new(uv_map_node.outputs["UV"], base_color_node.inputs["Vector"])
        
        node_tree.links.new(uv_map_node.outputs["UV"], base_mat_color_node.inputs["Vector"])
        node_tree.links.new(uv_map_node.outputs["UV"], detail_mat_color_node.inputs["Vector"])
        node_tree.links.new(uv_map_node.outputs["UV"], normal_color_node.inputs["Vector"])
        
        # --- START OF ADJUSTED CODE ---
        
        # Create a Mapping node
        mapping_node = node_tree.nodes.new(type="ShaderNodeMapping")
        mapping_node.location = (-1000, -300)  # Adjust location as needed
        mapping_node.vector_type = 'TEXTURE' # Set to texture to expose scale
        
        # Set the scale values
        if detail_scale_value is not None:
            mapping_node.inputs["Scale"].default_value = (detail_scale_value, detail_scale_value, 1.0) # X, Y, Z
        else:
            mapping_node.inputs["Scale"].default_value = (1.0, 1.0, 1.0) # Fallback value
        
        # Connect the UV Map node output to the Mapping node's Vector input
        node_tree.links.new(uv_map_node.outputs["UV"], mapping_node.inputs["Vector"])
        
        # Connect the output of the Mapping node to the Detail Image node's Vector input
        node_tree.links.new(mapping_node.outputs["Vector"], detail_color_node.inputs["Vector"])
        node_tree.links.new(mapping_node.outputs["Vector"], detail_mat_color_node.inputs["Vector"])
        
        self.report({'INFO'}, "Node preset layout created with existing texture values (if available)")
        return {'FINISHED'}

class NODE_OT_replace_textures_script(bpy.types.Operator):
    bl_idname = "object.replace_textures_with_dds"
    bl_label = "Replace Textures with DDS"
    bl_description = "Replaces all PNG/JPG image textures with corresponding DDS files"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        blend_file_dir = bpy.path.abspath('//')
        parent_dir = os.path.abspath(os.path.join(blend_file_dir, os.pardir))
        path_to_dds_files = os.path.join(parent_dir, 'dds')

        # Regular expression to find base names ending in common image extensions,
        # followed by an optional numeric or other suffix.
        # It handles names like "texture.png", "texture.png.001", "texture.jpg.other_suffix".
        regex = re.compile(r'(.+?)\.(png|jpg|jpeg)\b(.*)', re.IGNORECASE)

        # Iterate through all images in the .blend file
        for image in bpy.data.images:
            if image is None or not image.name:
                continue

            # Check if the image name matches our pattern
            match = regex.match(image.name)
            if match:
                # The base name is the first captured group
                base_name = match.group(1)
                dds_filename = base_name + ".dds"
                dds_file_path = os.path.join(path_to_dds_files, dds_filename)

                # Check if the DDS file exists on the disk
                if os.path.exists(dds_file_path):
                    try:
                        # Load the new DDS image and replace the old one
                        new_image = bpy.data.images.load(filepath=dds_file_path, check_existing=True)

                        # Update the image in all materials that use it
                        for material in bpy.data.materials:
                            if material.use_nodes:
                                for node in material.node_tree.nodes:
                                    if node.type == 'TEX_IMAGE' and node.image == image:
                                        node.image = new_image
                                        print(f"Replaced {image.name} with {dds_filename} in material: {material.name}")
                        
                        # Update the image in any old-style textures
                        for texture in bpy.data.textures:
                            if texture.type == 'IMAGE' and texture.image == image:
                                texture.image = new_image
                                print(f"Replaced {image.name} with {dds_filename} in texture: {texture.name}")

                    except Exception as e:
                        print(f"Error loading {dds_filename}: {e}")
                else:
                    print(f"DDS file not found for {image.name}: {dds_file_path}")
        
        self.report({'INFO'}, "Texture images successfully changed to .dds!")
        return {'FINISHED'}

class NODE_OT_remove_empty_textures_nodes_script(bpy.types.Operator):
    bl_idname = "object.remove_empty_textures_nodes"
    bl_label = "Remove empty textures nodes"
    bl_description = "Removes all unused image texture nodes"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        removed_nodes_count = 0

        for mat in bpy.data.materials:
            if not mat.use_nodes:
                continue

            nodes = mat.node_tree.nodes
            links = mat.node_tree.links
            nodes_to_remove = set()

            for node in nodes:
                # Check for unused image texture nodes
                if node.type == 'TEX_IMAGE':
                    has_outputs = any(link.from_node == node for link in links)
                    if not has_outputs:
                        nodes_to_remove.add(node)
                        continue

                    # Check if the image is empty or None and it's connected to a normal map node
                    if node.image is None:
                        for link in node.outputs[0].links:
                            if link.to_node.type == 'NORMAL_MAP':
                                nodes_to_remove.add(link.to_node)
                                nodes_to_remove.add(node)

                # Optional: remove NORMAL_MAP nodes with no input
                elif node.type == 'NORMAL_MAP':
                    if not node.inputs['Color'].is_linked:
                        nodes_to_remove.add(node)

            for node in nodes_to_remove:
                nodes.remove(node)
                removed_nodes_count += 1

        self.report({'INFO'}, f"Removed {removed_nodes_count} empty or unused nodes.")
        return {'FINISHED'}

class NODE_OT_create_and_assign_materials(bpy.types.Operator):
    bl_idname = "object.create_and_assign_materials"
    bl_label = "Create and Assign Materials"
    bl_description = "Creates materials and assigns them to the faces of a grid from DDS textures"
    bl_options = {'REGISTER', 'UNDO'}

    grid_columns: bpy.props.IntProperty(
        name="Columns",
        default=10,
        min=1,
        description="Number of columns in the grid"
    )
    
    grid_rows: bpy.props.IntProperty(
        name="Rows",
        default=10,
        min=1,
        description="Number of rows in the grid"
    )

    mat_prefix: bpy.props.StringProperty(
        name="Material Prefix",
        default="zrhGroundSwisstopo2022-8k_"
    )
    
    tex_folder: bpy.props.StringProperty(
        name="Texture Folder",
        default="//../dds/",
        subtype='DIR_PATH'
    )
    
    tex_ext: bpy.props.StringProperty(
        name="Extension",
        default=".dds"
    )
    
    tex_name_prefix: bpy.props.StringProperty(
        name="Filename Prefix",
        default=""
    )
    
    tex_name_suffix: bpy.props.StringProperty(
        name="Filename Suffix",
        default=""
    )

    def execute(self, context):
        # --- Configuration ---
        columns = self.grid_columns
        rows = self.grid_rows
        TOTAL_FACES = columns * rows
        TEXTURE_FOLDER = self.tex_folder
        TEXTURE_SUFFIX = ".dds"
        MATERIAL_PREFIX = "zrhGroundSwisstopo2022-8k_"

        # 1. Check for a selected object
        obj = context.object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a MESH object (the subdivided plane).")
            return {'CANCELLED'}

        # Check if we are in Edit mode, switch to Object mode temporarily
        if context.view_layer.objects.active and context.view_layer.objects.active.mode == 'EDIT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # Check the number of faces
        if len(obj.data.polygons) != TOTAL_FACES:
            self.report({'ERROR'}, f"Selected object must have exactly {TOTAL_FACES} faces (a {columns}x{rows} grid). It has {len(obj.data.polygons)}.")
            return {'CANCELLED'}

        print(f"Starting material creation and assignment for {TOTAL_FACES} faces...")

        # Clear existing materials slots on the object
        # We can't iterate and remove directly efficiently, so we use the operator
        bpy.ops.object.material_slot_remove_unused() # Optional cleanup
        
        # More robust way to remove all slots
        while obj.material_slots:
            bpy.context.object.active_material_index = 0
            bpy.ops.object.material_slot_remove()

        # Create and assign materials
        for face_index in range(TOTAL_FACES):
            # Calculate (column, row) coordinates (1-based index)
            # This assumes the faces are indexed in a row-major order:
            # 0..cols-1 (row 1), cols..2*cols-1 (row 2), ...
            # Row index 'y' (1 to rows)
            # Column index 'x' (1 to columns)
            row = (face_index // columns) + 1
            col = (face_index % columns) + 1

            # Determine file and material names
            # File name format: "{prefix}{col}_{row}{suffix}{ext}"
            file_name = f"{self.tex_name_prefix}{col}_{row}{self.tex_name_suffix}{self.tex_ext}"
            material_name = f"{self.mat_prefix}{col}-{row}"

            # 2. Create New Material
            mat = bpy.data.materials.get(material_name)
            if mat is None:
                mat = bpy.data.materials.new(name=material_name)
                mat.use_nodes = True
                print(f"  Created material: {material_name}")
            else:
                print(f"  Reusing existing material: {material_name}")


            # 3. Add Material Slot and Assign to Face
            obj.data.materials.append(mat)
            
            # Get the index of the newly added material slot
            slot_index = len(obj.material_slots) - 1
            
            # Assign the material slot index to the current face
            obj.data.polygons[face_index].material_index = slot_index
            

            # 4. Configure Material Nodes (Albedo Texture)
            nodes = mat.node_tree.nodes
            links = mat.node_tree.links
            
            # Clear existing nodes for a clean slate (optional, but safer)
            for node in nodes:
                if node.name != 'Material Output' and node.name != 'Principled BSDF':
                    nodes.remove(node)

            principled_bsdf = nodes.get("Principled BSDF")
            if not principled_bsdf:
                # If Principled BSDF was removed, re-add it (shouldn't happen with the clear above)
                principled_bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
                principled_bsdf.location = (-200, 0)
                output_node = nodes.get("Material Output")
                if output_node:
                    links.new(principled_bsdf.outputs['BSDF'], output_node.inputs['Surface'])
            
            # Create Image Texture node
            tex_image = nodes.new('ShaderNodeTexImage')
            tex_image.location = (-400, 0)
            
            # Set image path (relative path)
            image_path = os.path.join(TEXTURE_FOLDER, file_name)
            
            # Blender's relative path handling starts with '//'
            # The os.path.join will need to be careful with the leading '//'
            if not image_path.startswith('//'):
                image_path = '//' + image_path

            # Load Image
            # Check if image is already loaded
            img = bpy.data.images.get(file_name)
            if img is None:
                try:
                    # Use bpy.path.abspath to resolve the path relative to the .blend file
                    abs_path = bpy.path.abspath(image_path)
                    # We only load if it exists to avoid errors spamming
                    if os.path.exists(abs_path):
                         img = bpy.data.images.load(abs_path, check_existing=True)
                    else:
                         print(f"  Warning: File not found {abs_path}")
                         img = None
                except RuntimeError as e:
                    print(f"  Warning: Could not load image {image_path}. Error: {e}")
                    img = None # Ensure img is None if loading fails

            tex_image.image = img
            
            # Connect Image Texture to Principled BSDF Base Color
            links.new(tex_image.outputs['Color'], principled_bsdf.inputs['Base Color'])
            
            # Set image texture color space to Non-Color for DDS (often used for non-albedo data)
            # However, for an "albedo image texture", it is usually sRGB.
            # I will keep it as the default which is usually sRGB unless you specify otherwise.
            # If the DDS is raw data, uncomment the line below:
            # tex_image.image.colorspace_settings.name = 'Non-Color'

        self.report({'INFO'}, "Materials created and assigned successfully.")
        return {'FINISHED'}

class NODE_OT_snap_islands_to_terrain(bpy.types.Operator):
    bl_idname = "object.snap_islands_to_terrain"
    bl_label = "Snap Islands to Terrain"
    bl_description = "Snaps mesh islands vertically to a terrain object"
    bl_options = {'REGISTER', 'UNDO'}

    terrain_name: bpy.props.StringProperty(
        name="Terrain Object",
        default="groundMiddle",
        description="Name of the terrain object to snap to"
    )

    def execute(self, context):
        terrain_name = self.terrain_name
        
        terrain = bpy.data.objects.get(terrain_name)
        obj = context.active_object

        if not terrain:
            self.report({'ERROR'}, f"Object '{terrain_name}' not found!")
            return {'CANCELLED'}
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select your merged mesh object.")
            return {'CANCELLED'}

        # Go to Object Mode to safely handle mesh data
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        bm = bmesh.new()
        bm.from_mesh(obj.data)
        
        world_mat = obj.matrix_world
        inv_world_mat = world_mat.inverted()
        terr_inv_mat = terrain.matrix_world.inverted()

        # --- ROBUST ISLAND DETECTION ---
        processed_verts = set()
        islands = []

        for v in bm.verts:
            if v not in processed_verts:
                island_verts = []
                stack = [v]
                processed_verts.add(v)
                
                while stack:
                    curr_v = stack.pop()
                    island_verts.append(curr_v)
                    for edge in curr_v.link_edges:
                        other_v = edge.other_vert(curr_v)
                        if other_v not in processed_verts:
                            processed_verts.add(other_v)
                            stack.append(other_v)
                islands.append(island_verts)

        if not islands:
            self.report({'WARNING'}, "No geometry found in object.")
            bm.free()
            return {'CANCELLED'}

        count = 0
        for island_verts in islands:
            # 1. Calculate world-space bottom center of this island
            world_coords = [world_mat @ v.co for v in island_verts]
            
            min_z = min(co.z for co in world_coords)
            avg_x = sum(co.x for co in world_coords) / len(world_coords)
            avg_y = sum(co.y for co in world_coords) / len(world_coords)
            
            island_bottom_center = Vector((avg_x, avg_y, min_z))

            # 2. Raycast from 1000 units above the island
            ray_origin_world = island_bottom_center + Vector((0, 0, 1000))
            
            # Convert world ray to terrain-local space
            local_start = terr_inv_mat @ ray_origin_world
            local_dir = terr_inv_mat.to_quaternion() @ Vector((0, 0, -1))

            success, hit_loc, hit_normal, face_index = terrain.ray_cast(local_start, local_dir)

            if success:
                world_hit_loc = terrain.matrix_world @ hit_loc
                
                # 3. Move the island
                # The vertical distance to move:
                z_offset_world = world_hit_loc.z - island_bottom_center.z
                
                # Convert world Z offset to object-local vector
                # (Works even if the object is rotated)
                local_offset = inv_world_mat.to_quaternion() @ Vector((0, 0, z_offset_world))
                
                for v in island_verts:
                    v.co += local_offset
                count += 1

        # Update the mesh and viewport
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        
        self.report({'INFO'}, f"Successfully snapped {count} islands to {terrain_name}")
        return {'FINISHED'}
