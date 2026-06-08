#!/usr/bin/env python3
"""
Script to modify operators to work on all materials instead of just active material
"""

def get_indent(line):
    """Get the indentation level of a line"""
    return len(line) - len(line.lstrip())

def modify_operator_2020(lines):
    """Modify NODE_OT_create_preset_2020"""
    # Find the class
    for i, line in enumerate(lines):
        if 'class NODE_OT_create_preset_2020' in line:
            # Update description
            for j in range(i, min(i+10, len(lines))):
                if 'bl_description' in lines[j]:
                    lines[j] = '    bl_description = "Creates image texture nodes with existing image values and arranges nodes in a preset layout for all materials"\n'
                    break
            
            # Find execute method
            for j in range(i, min(i+20, len(lines))):
                if 'def execute(self, context):' in lines[j]:
                    # Replace lines after execute
                    lines[j+1] = '        obj = context.object\n'
                    lines[j+2] = '        if not obj or not obj.data.materials:\n'
                    lines[j+3] = '            self.report({\'WARNING\'}, "Active object must have materials")\n'
                    lines[j+4] = '            return {\'CANCELLED\'}\n'
                    lines[j+5] = '        \n'
                    lines[j+6] = '        materials_processed = 0\n'
                    lines[j+7] = '        \n'
                    lines[j+8] = '        for mat in obj.data.materials:\n'
                    lines[j+9] = '            if not mat or not mat.use_nodes:\n'
                    lines[j+10] = '                continue\n'
                    lines[j+11] = '            \n'
                    lines[j+12] = '            materials_processed += 1\n'
                    lines[j+13] = '            node_tree = mat.node_tree\n'
                    lines[j+14] = '            \n'
                    
                    # Now indent all lines from j+15 until we find the return statement
                    k = j + 15
                    while k < len(lines):
                        if lines[k].strip() == "return {'FINISHED'}":
                            # Update the report line before return
                            if k > 0 and 'self.report' in lines[k-1]:
                                lines[k-1] = '        self.report({\'INFO\'}, f"Node preset layout created for {materials_processed} material(s)")\n'
                            break
                        
                        # Indent this line by adding 12 spaces
                        if lines[k].strip():  # Non-empty line
                            current_indent = get_indent(lines[k])
                            lines[k] = ' ' * (current_indent + 12) + lines[k].lstrip()
                        k += 1
                    break
            break
    return lines

def modify_operator_2024(lines):
    """Modify NODE_OT_create_preset_2024"""
    # Find the class
    for i, line in enumerate(lines):
        if 'class NODE_OT_create_preset_2024' in line:
            # Update description
            for j in range(i, min(i+10, len(lines))):
                if 'bl_description' in lines[j]:
                    lines[j] = '    bl_description = "Creates image texture nodes with existing image values and arranges nodes in a preset layout for all materials"\n'
                    break
            
            # Find execute method
            for j in range(i, min(i+20, len(lines))):
                if 'def execute(self, context):' in lines[j]:
                    # Replace lines after execute
                    lines[j+1] = '        obj = context.object\n'
                    lines[j+2] = '        if not obj or not obj.data.materials:\n'
                    lines[j+3] = '            self.report({\'WARNING\'}, "Active object must have materials")\n'
                    lines[j+4] = '            return {\'CANCELLED\'}\n'
                    lines[j+5] = '        \n'
                    lines[j+6] = '        materials_processed = 0\n'
                    lines[j+7] = '        \n'
                    lines[j+8] = '        for mat in obj.data.materials:\n'
                    lines[j+9] = '            if not mat or not mat.use_nodes:\n'
                    lines[j+10] = '                continue\n'
                    lines[j+11] = '            \n'
                    lines[j+12] = '            materials_processed += 1\n'
                    lines[j+13] = '            node_tree = mat.node_tree\n'
                    lines[j+14] = '            \n'
                    
                    # Indent all lines from j+15 until return statement
                    k = j + 15
                    while k < len(lines):
                        if lines[k].strip() == "return {'FINISHED'}":
                            if k > 0 and 'self.report' in lines[k-1]:
                                lines[k-1] = '        self.report({\'INFO\'}, f"Node preset layout created for {materials_processed} material(s)")\n'
                            break
                        
                        if lines[k].strip():
                            current_indent = get_indent(lines[k])
                            lines[k] = ' ' * (current_indent + 12) + lines[k].lstrip()
                        k += 1
                    break
            break
    return lines

def modify_remove_empty_textures(lines):
    """Modify NODE_OT_remove_empty_textures_nodes_script"""
    for i, line in enumerate(lines):
        if 'class NODE_OT_remove_empty_textures_nodes_script' in line:
            # Update description
            for j in range(i, min(i+10, len(lines))):
                if 'bl_description' in lines[j]:
                    lines[j] = '    bl_description = "Removes all unused image texture nodes from all materials of the selected object"\n'
                    break
            
            # Find execute method
            for j in range(i, min(i+20, len(lines))):
                if 'def execute(self, context):' in lines[j]:
                    # Insert object validation at the beginning
                    lines[j+1] = '        obj = context.object\n'
                    lines[j+2] = '        if not obj or not obj.data.materials:\n'
                    lines[j+3] = '            self.report({\'WARNING\'}, "Active object must have materials")\n'
                    lines[j+4] = '            return {\'CANCELLED\'}\n'
                    lines[j+5] = '        \n'
                    lines[j+6] = '        removed_nodes_count = 0\n'
                    lines[j+7] = '\n'
                    lines[j+8] = '        for mat in obj.data.materials:\n'
                    
                    # Find and replace the old for loop
                    for k in range(j+9, min(j+30, len(lines))):
                        if 'for mat in bpy.data.materials:' in lines[k]:
                            lines[k] = '            if not mat or not mat.use_nodes:\n'
                            lines[k+1] = '                continue\n'
                            lines[k+2] = '\n'
                            break
                    
                    # Update the final report message
                    for k in range(j, len(lines)):
                        if 'self.report({\'INFO\'}' in lines[k] and 'removed_nodes_count' in lines[k]:
                            lines[k] = '        self.report({\'INFO\'}, f"Removed {removed_nodes_count} empty or unused nodes from selected object.")\n'
                            break
                    break
            break
    return lines

# Read the file
with open('bleliza_utilities/operators.py', 'r') as f:
    lines = f.readlines()

# Apply modifications
lines = modify_operator_2020(lines)
lines = modify_operator_2024(lines)
lines = modify_remove_empty_textures(lines)

# Write back
with open('bleliza_utilities/operators.py', 'w') as f:
    f.writelines(lines)

print("All modifications applied successfully!")
