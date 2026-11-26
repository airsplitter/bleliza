"""Run with Blender: blender --background --factory-startup --python tests/test_select_lod_objects.py"""
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bleliza_utilities


def new_collection(name, parent, objects=()):
    collection = bpy.data.collections.new(name)
    parent.children.link(collection)
    for obj_name in objects:
        collection.objects.link(bpy.data.objects.new(obj_name, None))
    return collection


def layer_collection(collection, root=None):
    root = root or bpy.context.view_layer.layer_collection
    if root.collection == collection:
        return root
    for child in root.children:
        found = layer_collection(collection, child)
        if found:
            return found


def selected():
    return {o.name for o in bpy.context.view_layer.objects if o.select_get()}


scene = bpy.context.scene
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj)

bleliza_utilities.register()
op = bpy.ops.object.bleliza_select_lod_objects

# Scene/  Outside_LOD0(OutA)  Group/ { Sign_LOD0(A0) Sign_LOD1(A1) Sign_LOD10(A10)
#                                      Sub/ { Tree_lod0.001(B0) Nested_LOD0/ { Inner/(C0) } } }
new_collection("Outside_LOD0", scene.collection, ["OutA"])
group = new_collection("Group", scene.collection)
new_collection("Sign_LOD0", group, ["A0"])
new_collection("Sign_LOD1", group, ["A1"])
new_collection("Sign_LOD10", group, ["A10"])
sub = new_collection("Sub", group)
new_collection("Tree_lod0.001", sub, ["B0"])
nested = new_collection("Nested_LOD0", sub)
new_collection("Inner", nested, ["C0"])

bpy.context.view_layer.active_layer_collection = layer_collection(group)

assert op(lod=0) == {'FINISHED'}
assert selected() == {"A0", "B0", "C0"}, selected()
print("PASS: LOD0 recursive, case-insensitive, .001 tail, nested objects, outside ignored")

assert op(lod=1) == {'FINISHED'}
assert selected() == {"A1"}, selected()
print("PASS: LOD1 replaces selection and does not match LOD10")

assert op(lod=0, extend=True) == {'FINISHED'}
assert selected() == {"A0", "A1", "B0", "C0"}, selected()
print("PASS: extend keeps selection")

assert op(lod=4) == {'CANCELLED'}
print("PASS: no matching collections")

bpy.context.view_layer.active_layer_collection = layer_collection(sub)
assert op(lod=0) == {'FINISHED'}
assert selected() == {"B0", "C0"}, selected()
print("PASS: only sub collections of the active collection")

bleliza_utilities.unregister()
print("ALL PASS")
