"""Run with Blender 3.6: blender --background --factory-startup --python tests/test_lod_collections_to_empties.py"""
import shutil
import sys
import tempfile
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bleliza_utilities


def children(empty):
    return {child.name: child.instance_collection.name for child in empty.children}


root = Path(tempfile.mkdtemp(prefix="bleliza_lod_"))
try:
    # Source file: container "Signs" holding three LODs of one sign, plus "Misc".
    source = root / "signs.blend"
    signs = bpy.data.collections.new("Signs")
    written = {signs}
    for lod in (0, 1, 10):
        lod_collection = bpy.data.collections.new(f"ENGM_TaxiSigns_268_LOD{lod}")
        lod_collection.objects.link(bpy.data.objects.new(f"Sign_LOD{lod}", None))
        signs.children.link(lod_collection)
        written.add(lod_collection)
    misc = bpy.data.collections.new("Misc")
    misc.objects.link(bpy.data.objects.new("Pole", None))
    written.add(misc)
    bpy.data.libraries.write(str(source), written)
    for collection in written:
        for obj in list(collection.objects):
            bpy.data.objects.remove(obj)
        bpy.data.collections.remove(collection)

    bleliza_utilities.register()
    op = bpy.ops.object.bleliza_lod_collections_to_empties

    assert op(filepath=str(source)) == {'FINISHED'}
    parent = bpy.data.objects["ENGM_TaxiSigns_268"]
    assert parent.instance_type == 'NONE' and parent.parent is None
    assert children(parent) == {f"ENGM_TaxiSigns_268_LOD{n}": f"ENGM_TaxiSigns_268_LOD{n}"
                                for n in (0, 1, 10)}, children(parent)
    assert all(c.instance_type == 'COLLECTION' and c.instance_collection.library
               for c in parent.children)
    assert children(bpy.data.objects["Misc"]) == {"Misc.001": "Misc"}
    assert "Signs" not in bpy.data.objects
    assert bpy.context.scene.collection.children.get("ENGM_TaxiSigns_268_LOD0") is None
    print("PASS: linked LOD grouping, collection without suffix, container skipped")

    assert op(filepath=str(source), link=False, target_collection="LODs",
              skip_container_collections=False, empty_size=2.0) == {'FINISHED'}
    lods = bpy.data.collections["LODs"]
    parent = bpy.data.objects["ENGM_TaxiSigns_268.001"]
    assert lods.objects.get(parent.name) is not None and parent.empty_display_size == 2.0
    assert all(c.instance_collection.library is None for c in parent.children)
    assert "Signs" in {o.name for o in lods.objects}
    print("PASS: append, target collection, empty size, container collections included")

    for kwargs in ({"filepath": str(root / "missing.blend")},
                   {"filepath": str(source), "lod_pattern": "(unclosed"},
                   {"filepath": str(source), "lod_pattern": r"_LOD\d+$"}):
        try:
            op(**kwargs)
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"expected an error for {kwargs}")
    print("PASS: missing file, invalid pattern, pattern without base group")

    bleliza_utilities.unregister()
    print("PASS: registration and unregistration")
finally:
    shutil.rmtree(root, ignore_errors=True)
