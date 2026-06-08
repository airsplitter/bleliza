#!/usr/bin/env python3
"""
Script to modify the operators to work on all materials instead of just active material
"""

def fix_create_preset_2020(lines):
    """Fix the NODE_OT_create_preset_2020 operator"""
    # Find the execute method
    for i, line in enumerate(lines):
        if 'class NODE_OT_create_preset_2020' in line:
            # Find the execute method
            for j in range(i, min(i+20, len(lines))):
                if 'def execute(self, context):' in lines[j]:
                    # Replace the material selection logic
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
                    
                    # Now indent all lines from j+15 until we hit the return statement at the end
                    # Find the final return statement
                    for k in range(j+15, len(lines)):
                        if lines[k].strip() == 'return {\'FINISHED\'}' and lines[k].startswith('        '):
                            # Found the end - update the report line before it
                            if 'self.report' in lines[k-1]:
                                lines[k-1] = '        self.report({\'INFO\'}, f"Node preset layout created for {materials_processed} material(s)")\n'
                            break
                        # Indent this line by 12 spaces (3 levels)
                        if lines[k].strip():  # Only indent non-empty lines
                            lines[k] = '            ' + lines[k].lstrip()
                    break
            break
    
    # Update description
    for i, line in enumerate(lines):
        if 'class NODE_OT_create_preset_2020' in line:
            for j in range(i, min(i+10, len(lines))):
                if 'bl_description' in lines[j]:
                    lines[j] = '    bl_description = "Creates image texture nodes with existing image values and arranges nodes in a preset layout for all materials"\n'
                    break
            break
    
    return lines

def fix_create_preset_2024(lines):
    """Fix the NODE_OT_create_preset_2024 operator - similar to 2020"""
    for i, line in enumerate(lines):
        if 'class NODE_OT_create_preset_2024' in line:
            # Find the execute method
            for j in range(i, min(i+20, len(lines))):
                if 'def execute(self, context):' in lines[j]:
                    # Replace the material selection logic
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
                    
                    # Indent all lines until return statement
                    for k in range(j+15, len(lines)):
                        if lines[k].strip() == 'return {\'FINISHED\'}' and lines[k].startswith('        '):
                            if 'self.report' in lines[k-1]:
                                lines[k-1] = '        self.report({\'INFO\'}, f"Node preset layout created for {materials_processed} material(s)")\n'
                            break
                        if lines[k].strip():
                            lines[k] = '            ' + lines[k].lstrip()
                    break
            break
    
    # Update description
    for i, line in enumerate(lines):
        if 'class NODE_OT_create_preset_2024' in line:
            for j in range(i, min(i+10, len(lines))):
                if 'bl_description' in lines[j]:
                    lines[j] = '    bl_description = "Creates image texture nodes with existing image values and arranges nodes in a preset layout for all materials"\n'
                    break
            break
    
    return lines

def fix_remove_empty_textures(lines):
    """Fix the NODE_OT_remove_empty_textures_nodes_script operator"""
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
                    # Add object validation
                    lines[j+1] = '        obj = context.object\n'
                    lines[j+2] = '        if not obj or not obj.data.materials:\n'
                    lines[j+3] = '            self.report({\'WARNING\'}, "Active object must have materials")\n'
                    lines[j+4] = '            return {\'CANCELLED\'}\n'
                    lines[j+5] = '        \n'
                    lines[j+6] = '        removed_nodes_count = 0\n'
                    lines[j+7] = '\n'
                    lines[j+8] = '        for mat in obj.data.materials:\n'
                    
                    # Find and replace the old for loop
                    for k in range(j+9, len(lines)):
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

# Apply fixes
lines = fix_create_preset_2020(lines)
lines = fix_create_preset_2024(lines)
lines = fix_remove_empty_textures(lines)

# Write back
with open('bleliza_utilities/operators.py', 'w') as f:
    f.writelines(lines)

print("Operators fixed successfully!")
