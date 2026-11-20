"""Run with Blender 3.6: blender --background --factory-startup --python tests/test_place_from_scenery_xml.py"""
import math
import shutil
import sys
import tempfile
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bleliza_utilities

XML = """<?xml version="1.0"?>
<FSData version="9.0">
	<!--SceneryObject name: AtOrigin-->

	<SceneryObject lat="60.2" lon="11.1" alt="5.5" pitch="0" bank="0" heading="-90.0">
		<LibraryObject name="{B71C7557-DB8A-4BA3-A59D-ADD8AF99C85E}" scale="1.000000"/>
	</SceneryObject>
	<!--SceneryObject name: North-->
	<SceneryObject lat="60.201" lon="11.1" alt="0" heading="0"/>
	<Group groupID="36">
		<!--SceneryObject name: EastChild-->
		<SceneryObject lat="60.2" lon="11.102" alt="0" heading="45"/>
	</Group>
	<!--SceneryObject name: Outside-->
	<SceneryObject lat="60.201" lon="11.101" alt="0" heading="0"/>
	<!--SceneryObject name: Missing-->
	<SceneryObject lat="60.201" lon="11.101" alt="0" heading="0"/>
	<!--SceneryObject name: North-->
	<SceneryObject lat="61" lon="12" alt="0" heading="0"/>
	<SceneryObject lat="61" lon="12" alt="0" heading="0"/>
</FSData>
"""


def close(a, b, tolerance):
    return abs(a - b) <= tolerance


root = Path(tempfile.mkdtemp(prefix="bleliza_xml_"))
try:
    xml = root / "objects.xml"
    xml.write_text(XML)
    broken = root / "broken.xml"
    broken.write_text("<FSData><SceneryObject></FSData>")

    bleliza_utilities.register()
    scene = bpy.context.scene
    placed = bpy.data.collections.new("Placed")
    scene.collection.children.link(placed)
    sub = bpy.data.collections.new("Sub")
    placed.children.link(sub)
    objs = {}
    for name, collection in (("AtOrigin", placed), ("North", placed),
                             ("Parent", placed), ("EastChild", sub),
                             ("Outside", scene.collection)):
        objs[name] = bpy.data.objects.new(name, None)
        objs[name].location = (100.0, 100.0, 7.0)
        collection.objects.link(objs[name])
    objs["Parent"].location = (10.0, 0.0, 0.0)
    objs["EastChild"].parent = objs["Parent"]
    view_layer = bpy.context.view_layer
    view_layer.active_layer_collection = view_layer.layer_collection.children["Placed"]
    op = bpy.ops.object.bleliza_place_from_scenery_xml

    try:
        op(filepath=str(xml))
    except RuntimeError:
        pass
    else:
        raise AssertionError("missing origin must report an error")
    assert objs["North"].location.x == 100.0
    print("PASS: missing origin is an error")

    assert op(filepath=str(xml), origin_lat="60.2", origin_lon="11,1",
              set_altitude=True) == {'FINISHED'}
    view_layer.update()
    at_origin = objs["AtOrigin"].matrix_world
    assert at_origin.translation.length < 1e-3 and close(at_origin.translation.z, 5.5, 1e-4)
    assert close(objs["AtOrigin"].rotation_euler.z, math.radians(90.0), 1e-5)
    north = objs["North"].matrix_world.translation
    # 0.001° of latitude at 60° N is about 111.4 m.
    assert close(north.x, 0.0, 1e-3) and close(north.y, 111.4, 0.2), north
    east = objs["EastChild"].matrix_world.translation
    # 0.002° of longitude at 60.2° N is about 110.9 m.
    assert close(east.x, 110.9, 0.3) and close(east.y, 0.0, 0.05), east
    assert objs["Parent"].location.x == 10.0
    assert tuple(objs["Outside"].location) == (100.0, 100.0, 7.0)
    assert (scene["lat"], scene["lon"]) == (60.2, 11.1)
    print("PASS: origin from fields, nested group, child in world space, heading, altitude")

    objs["North"].location = (0.0, 0.0, 3.0)
    assert op(filepath=str(xml), apply_heading=False) == {'FINISHED'}
    assert close(objs["North"].location.y, 111.4, 0.2) and objs["North"].location.z == 3.0
    print("PASS: origin from scene properties, Z kept")

    for kwargs in ({"filepath": str(broken)},
                   {"filepath": str(root / "missing.xml")},
                   {"filepath": str(xml), "origin_lat": "north", "origin_lon": "11"}):
        try:
            op(**kwargs)
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"expected an error for {kwargs}")
    print("PASS: broken XML, missing file, invalid origin")

    bleliza_utilities.unregister()
    print("PASS: registration and unregistration")
finally:
    shutil.rmtree(root, ignore_errors=True)
