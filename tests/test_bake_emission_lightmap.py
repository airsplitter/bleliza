"""Run with Blender 3.6: blender --background --factory-startup --python tests/test_bake_emission_lightmap.py"""
import sys
import tempfile
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bleliza_utilities


def brightness(image):
    pixels = image.pixels[:]
    return max(sum(pixels[i:i + 3]) / 3 for i in range(0, len(pixels), 4))


bleliza_utilities.register()
scene = bpy.context.scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
scene.render.engine = 'BLENDER_EEVEE'
world = scene.world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (1, 1, 1, 1)

bpy.ops.mesh.primitive_plane_add(size=4)
ground = bpy.context.object
ground.name = "Ground"
ground_mat = bpy.data.materials.new("Ground")
ground_mat.use_nodes = True
ground.data.materials.append(ground_mat)

bpy.ops.mesh.primitive_cube_add(size=0.5, location=(0, 0, 0.5))
lamp_box = bpy.context.object
glow = bpy.data.materials.new("Glow")
glow.use_nodes = True
bsdf = glow.node_tree.nodes["Principled BSDF"]
(bsdf.inputs.get("Emission Color") or bsdf.inputs["Emission"]).default_value = (1, 0.5, 0.2, 1)
bsdf.inputs["Emission Strength"].default_value = 20.0
lamp_box.data.materials.append(glow)

sun_data = bpy.data.lights.new("Sun", 'SUN')
sun = bpy.data.objects.new("Sun", sun_data)
scene.collection.objects.link(sun)
bpy.context.view_layer.objects.active = lamp_box
lamp_box.select_set(True)

op = bpy.ops.object.bleliza_bake_emission_lightmap
assert not op.poll()
scene.bleliza_lightmap_target = ground
assert op.poll()

common = dict(resolution=32, samples=8, margin=2)
assert op(**common) == {'FINISHED'}
image = bpy.data.images["Ground_Lightmap"]
assert image.packed_file is not None
lit = brightness(image)
assert lit > 0.05, lit
assert scene.render.engine == 'BLENDER_EEVEE' and scene.world == world
assert not sun.hide_render and bsdf.inputs["Emission Strength"].default_value == 20.0
assert bpy.context.view_layer.objects.active == lamp_box
assert set(bpy.context.selected_objects) == {lamp_box}
assert all(n.name != "BleLIZA Lightmap Bake" for n in ground_mat.node_tree.nodes)
print("PASS: emission bake, packed image, scene restored")

# A material that shows the lightmap keeps showing it after a re-bake.
show = ground_mat.node_tree.nodes.new("ShaderNodeTexImage")
show.image = image
assert op(emission_scale=0.0, **common) == {'FINISHED'}
assert show.image.name == "Ground_Lightmap"
assert brightness(show.image) < 1e-4, brightness(show.image)
assert bsdf.inputs["Emission Strength"].default_value == 20.0
print("PASS: emission only ignores world and sun, re-bake replaces image")

assert op(emission_only=False, emission_scale=0.0, **common) == {'FINISHED'}
assert brightness(bpy.data.images["Ground_Lightmap"]) > 0.05
print("PASS: world and lamps included when Emission Only is off")

with tempfile.TemporaryDirectory() as tmp:
    out = Path(tmp) / "ground_lm"
    assert op(filepath=str(out), float_buffer=True, image_name="GroundLM", **common) == {'FINISHED'}
    saved = bpy.data.images["GroundLM"]
    assert (Path(tmp) / "ground_lm.exr").exists() and saved.source == 'FILE' and saved.is_float
    print("PASS: float lightmap saved as OpenEXR")

empty_target = bpy.data.objects.new("NoUV", bpy.data.meshes.new("NoUV"))
scene.collection.objects.link(empty_target)
scene.bleliza_lightmap_target = empty_target
try:
    op(**common)
except RuntimeError as exc:
    assert "no UV map" in str(exc), exc
else:
    raise AssertionError("target without UV map was baked")
print("PASS: target without UV map is refused")

bleliza_utilities.unregister()
print("PASS: registration and unregistration")
