"""Run with Blender 3.6: blender --background --factory-startup --python tests/test_import_collections.py"""
import shutil
import sys
import tempfile
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bleliza_utilities

TRIANGLE = "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"


def scene_collections():
    return {c.name: c for c in bpy.context.scene.collection.children}


root = Path(tempfile.mkdtemp(prefix="bleliza_import_"))
try:
    # Source .blend with a parent/child pair that is not linked to any scene.
    mesh = bpy.data.meshes.new("ChairMesh")
    parent = bpy.data.objects.new("Seat", mesh)
    child = bpy.data.objects.new("Leg", None)
    child.parent = parent
    bpy.data.libraries.write(str(root / "chair.blend"), {parent, child})
    bpy.data.objects.remove(child)
    bpy.data.objects.remove(parent)
    bpy.data.meshes.remove(mesh)

    (root / "table.obj").write_text("o Top\n" + TRIANGLE)
    (root / "broken.fbx").write_text("not an fbx file")
    (root / "notes.txt").write_text("ignored")
    (root / "sub").mkdir()
    (root / "sub" / "lamp.obj").write_text("o Lamp\n" + TRIANGLE)

    bleliza_utilities.register()
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)

    op = bpy.ops.object.bleliza_import_files_to_collections
    assert op(directory=str(root)) == {'FINISHED'}
    cols = scene_collections()
    assert set(cols) == {"Collection", "chair", "table"}, set(cols)
    assert {o.name for o in cols["chair"].objects} == {"Seat", "Leg"}
    assert bpy.data.objects["Leg"].parent == bpy.data.objects["Seat"]
    assert [o.name for o in cols["table"].objects] == ["Top"]
    assert not cols["Collection"].objects
    assert "broken" not in bpy.data.collections
    assert all(len(o.users_collection) == 1 for o in bpy.data.objects)
    print("PASS: .blend append with parenting, OBJ import, failed file skipped, other files ignored")

    assert op(directory=str(root), recursive=True, keep_extension=True,
              file_types={'OBJ'}) == {'FINISHED'}
    cols = scene_collections()
    assert [o.name for o in cols["lamp.obj"].objects] == ["Lamp"]
    assert [o.name for o in cols["table.obj"].objects] == ["Top.001"]
    assert "chair.blend" not in cols
    print("PASS: subdirectories, kept extensions, file type filter")

    empty = root / "empty"
    empty.mkdir()
    assert op(directory=str(empty)) == {'CANCELLED'}
    try:
        op(directory=str(root / "missing"))
    except RuntimeError:
        pass
    else:
        raise AssertionError("missing directory must report an error")
    print("PASS: empty and missing directories")

    # Two source files use material "Paint", which already exists in the scene.
    shared = root / "materials"
    shared.mkdir()
    paint = bpy.data.materials.new("Paint")
    paint.use_nodes = True
    texture = paint.node_tree.nodes.new('ShaderNodeTexImage')
    texture.image = bpy.data.images.new("PaintTex", 4, 4)
    for name in ("SignA", "SignB"):
        sign_mesh = bpy.data.meshes.new(name + "Mesh")
        sign_mesh.materials.append(paint)
        sign = bpy.data.objects.new(name, sign_mesh)
        bpy.data.libraries.write(str(shared / f"{name.lower()}.blend"), {sign})
        bpy.data.objects.remove(sign)
        bpy.data.meshes.remove(sign_mesh)

    assert op(directory=str(shared)) == {'FINISHED'}
    for name in ("SignA", "SignB"):
        assert bpy.data.objects[name].material_slots[0].material == paint, name
    assert "Paint.001" not in bpy.data.materials
    assert [i.name for i in bpy.data.images] == ["PaintTex"]
    print("PASS: existing material reused, duplicate material and image removed")

    assert op(directory=str(shared), reuse_materials=False) == {'FINISHED'}
    assert bpy.data.objects["SignA.001"].material_slots[0].material.name == "Paint.001"
    print("PASS: material reuse can be turned off")

    bleliza_utilities.unregister()
    print("PASS: registration and unregistration")
finally:
    shutil.rmtree(root, ignore_errors=True)
