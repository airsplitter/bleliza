"""Run with Blender 3.6: blender --background --factory-startup --python tests/test_mesh_cleanup.py"""
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bleliza_utilities


def mesh_object(name, near=0.00005, far=0.0002):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0),
                      (near, 0, 0), (far, 0, 0)], [], [(0, 1, 2)])
    mesh.use_auto_smooth = True
    mesh.polygons[0].use_smooth = True
    mesh.normals_split_custom_set([(1, 0, 0)] * len(mesh.loops))
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def select(*objects, active=None):
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = active or objects[0]


bleliza_utilities.register()
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
first = mesh_object('First')
second = mesh_object('Second')
untouched = mesh_object('Unselected')
empty = bpy.data.objects.new('Empty', None)
bpy.context.collection.objects.link(empty)
shared = bpy.data.objects.new('Shared', first.data)
bpy.context.collection.objects.link(shared)
select(first, second, shared, empty, active=empty)
assert bpy.ops.object.bleliza_cleanup_meshes() == {'FINISHED'}
assert bpy.context.mode == 'OBJECT'
assert bpy.context.view_layer.objects.active == empty
assert set(bpy.context.selected_objects) == {first, second, shared, empty}
for obj in (first, second):
    assert len(obj.data.vertices) == 4, obj.name
    obj.data.calc_normals_split()
    assert all(loop.normal.z > 0.999 for loop in obj.data.loops), obj.name
assert len(untouched.data.vertices) == 5
print('PASS: multiple meshes, shared data, skipped empty, preserved selection, normals reset')

# A centimeter scene must still merge vertices separated by 0.00005 m.
bpy.context.scene.unit_settings.system = 'METRIC'
bpy.context.scene.unit_settings.scale_length = 0.01
scaled = mesh_object('Centimeters', near=0.005, far=0.02)
select(scaled)
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='DESELECT')
assert bpy.ops.object.bleliza_cleanup_meshes() == {'FINISHED'}
assert bpy.context.mode == 'OBJECT'
assert len(scaled.data.vertices) == 4
print('PASS: scene units, Edit Mode entry, selecting all, Object Mode exit')

select(empty)
assert not bpy.ops.object.bleliza_cleanup_meshes.poll()
bleliza_utilities.unregister()
print('PASS: no mesh selection, registration and unregistration')
