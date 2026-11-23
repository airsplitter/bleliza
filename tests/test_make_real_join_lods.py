"""Run with Blender 3.6: blender --background --factory-startup --python tests/test_make_real_join_lods.py"""
import shutil
import sys
import tempfile
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bleliza_utilities

TRIANGLE = ([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])


def mesh_object(name, material, offset=(0, 0, 0)):
    mesh = bpy.data.meshes.new(name)
    verts, edges, faces = TRIANGLE
    mesh.from_pydata([Vector(v) + Vector(offset) for v in verts], edges, faces)
    mesh.materials.append(material)
    return bpy.data.objects.new(name, mesh)


def clear_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    for data in (bpy.data.collections, bpy.data.meshes, bpy.data.materials, bpy.data.images):
        for datablock in list(data):
            if datablock.library is None:
                data.remove(datablock)


def run_in(collection, **kwargs):
    layer_collection = bpy.context.view_layer.layer_collection.children[collection.name]
    bpy.context.view_layer.active_layer_collection = layer_collection
    return bpy.ops.object.bleliza_make_real_join_lods(**kwargs)


root = Path(tempfile.mkdtemp(prefix="bleliza_join_"))
try:
    # Library: two LOD collections of one sign; LOD0 has two parts, LOD1 one.
    # Materials "Mat" and "Glass"; "Glass" uses an image.
    source = root / "sign.blend"
    mat = bpy.data.materials.new("Mat")
    glass = bpy.data.materials.new("Glass")
    glass.use_nodes = True
    image = bpy.data.images.new("GlassTex", 4, 4)
    image.filepath_raw = str(root / "glass.png")
    image.file_format = 'PNG'
    image.save()
    glass.node_tree.nodes.new("ShaderNodeTexImage").image = image
    lod0 = bpy.data.collections.new("Sign_LOD0")
    lod0.objects.link(mesh_object("Pole", mat))                    # no suffix: collection name
    lod0.objects.link(mesh_object("Panel_LOD0", glass, (0, 0, 2)))
    lod1 = bpy.data.collections.new("Sign_LOD1")
    lod1.objects.link(mesh_object("Sign_lod1", mat))               # case-insensitive suffix
    bpy.data.libraries.write(str(source), {lod0, lod1})
    clear_scene()

    bleliza_utilities.register()
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)

    # Local scene: an existing "Mat" that must be reused, two linked placements.
    local_mat = bpy.data.materials.new("Mat")
    airport = bpy.data.collections.new("Airport")
    bpy.context.scene.collection.children.link(airport)
    run_in(airport)  # nothing to do yet -> cancelled with a warning, no exception
    bpy.context.view_layer.active_layer_collection = \
        bpy.context.view_layer.layer_collection.children["Airport"]
    assert bpy.ops.object.bleliza_lod_collections_to_empties(
        filepath=str(source), link=True) == {'FINISHED'}
    sign = bpy.data.objects["Sign"]
    sign.location = (10, 0, 0)
    # A second placement of LOD0 and a plain local mesh with a suffix.
    second = bpy.data.objects.new("Second", None)
    second.instance_type = 'COLLECTION'
    second.instance_collection = bpy.data.collections["Sign_LOD0"]
    second.location = (0, 20, 0)
    airport.objects.link(second)
    airport.objects.link(mesh_object("Ground_LOD1", bpy.data.materials.new("Mat.001")))
    bpy.context.view_layer.update()

    assert run_in(airport) == {'FINISHED'}
    names = sorted(o.name for o in airport.objects)
    assert names == ["Airport_LOD0", "Airport_LOD1"], names
    lod0_obj, lod1_obj = bpy.data.objects["Airport_LOD0"], bpy.data.objects["Airport_LOD1"]
    assert lod0_obj.matrix_world == lod0_obj.matrix_world.Identity(4)
    assert len(lod0_obj.data.polygons) == 4 and len(lod1_obj.data.polygons) == 2
    xs = sorted({round(v.co.x) for v in lod0_obj.data.vertices})
    ys = sorted({round(v.co.y) for v in lod0_obj.data.vertices})
    assert 10 in xs and 20 in ys, (xs, ys)
    assert lod0_obj.data.library is None and lod0_obj.data.users == 1
    print("PASS: instances made real, joined per LOD suffix, transforms kept")

    used = {m for o in (lod0_obj, lod1_obj) for m in o.data.materials}
    assert all(m.library is None for m in used), used
    assert {m.name for m in used} == {"Mat", "Glass"}, {m.name for m in used}
    assert bpy.data.materials.get("Mat.001") is None
    assert [m for m in bpy.data.materials if m.library is None and m.name == "Mat"] == [local_mat]
    assert len([m for m in bpy.data.materials if m.library is None and m.name == "Glass"]) == 1
    glass_local = next(m for m in used if m.name == "Glass")
    tex = next(n for n in glass_local.node_tree.nodes if n.type == 'TEX_IMAGE')
    assert tex.image.library is None and tex.image.name == "GlassTex"
    print("PASS: existing material reused, linked material and image made local once, duplicate removed")

    assert not [o for o in bpy.data.objects if o.type == 'EMPTY' and o.library is None]
    print("PASS: instance empties and their parent empty removed")

    # Appended LODs (no link): "Mat" arrives as "Mat.001" and must be reused.
    clear_scene()
    bpy.ops.outliner.orphans_purge(do_recursive=True)
    local_mat = bpy.data.materials.new("Mat")
    props = bpy.data.collections.new("Props")
    bpy.context.scene.collection.children.link(props)
    bpy.context.view_layer.active_layer_collection = \
        bpy.context.view_layer.layer_collection.children["Props"]
    assert bpy.ops.object.bleliza_lod_collections_to_empties(
        filepath=str(source), link=False) == {'FINISHED'}
    assert bpy.data.materials.get("Mat.001") is not None
    keep = bpy.data.objects.new("Light", bpy.data.lights.new("Light", 'POINT'))
    props.objects.link(keep)
    assert run_in(props, remove_empties=False) == {'FINISHED'}
    used = {m for o in props.objects if o.type == 'MESH' for m in o.data.materials}
    assert {m.name for m in used} == {"Mat", "Glass"}
    assert local_mat in used and bpy.data.materials.get("Mat.001") is None
    assert {o.name for o in props.objects if o.type == 'MESH'} == {"Props_LOD0", "Props_LOD1"}
    assert bpy.data.objects.get("Sign") is not None and keep.name in props.objects
    print("PASS: appended duplicate materials reused, empties kept when asked, other objects untouched")

    try:
        run_in(props, lod_pattern="(unclosed")
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected an error for an invalid pattern")
    print("PASS: invalid pattern")

    bleliza_utilities.unregister()
    print("PASS: registration and unregistration")
finally:
    shutil.rmtree(root, ignore_errors=True)
