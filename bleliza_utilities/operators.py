import bpy
import os
import re
import math
import bmesh
import random
import xml.etree.ElementTree as ET
from pathlib import Path
from mathutils import Matrix, Quaternion, Vector


class OBJECT_OT_bleliza_cleanup_meshes(bpy.types.Operator):
    bl_idname = "object.bleliza_cleanup_meshes"
    bl_label = "Merge by Distance & Reset Vectors"
    bl_description = (
        "Select all visible geometry in selected meshes, merge vertices within "
        "0.0001 m and reset normal vectors, then return to Object Mode"
    )
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode in {'OBJECT', 'EDIT_MESH'} and any(
            obj.type == 'MESH' for obj in context.selected_editable_objects
        )

    def execute(self, context):
        selected = list(context.selected_objects)
        active = context.view_layer.objects.active
        meshes = [
            obj for obj in context.selected_editable_objects
            if obj.type == 'MESH' and obj.data.library is None
        ]
        if not meshes:
            self.report({'WARNING'}, "Select at least one editable mesh object.")
            return {'CANCELLED'}

        # Match entering 0.0001 m in Blender's Merge by Distance field.
        units = context.scene.unit_settings
        threshold = 0.0001 / (units.scale_length if units.system != 'NONE' else 1.0)
        counts = []
        error = None
        try:
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            for obj in selected:
                obj.select_set(False)
            for obj in meshes:
                obj.select_set(True)
            context.view_layer.objects.active = meshes[0]
            bpy.ops.object.mode_set(mode='EDIT')

            # Linked duplicates share one mesh: count and edit that mesh once.
            data = [obj.data for obj in context.objects_in_mode_unique_data]
            counts = [(mesh, len(bmesh.from_edit_mesh(mesh).verts)) for mesh in data]
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.remove_doubles(threshold=threshold)
            bpy.ops.mesh.normals_tools(mode='RESET')
        except RuntimeError as exc:
            error = str(exc)
        finally:
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            for obj in meshes:
                obj.select_set(False)
            for obj in selected:
                obj.select_set(True)
            context.view_layer.objects.active = active

        removed = sum(before - len(mesh.vertices) for mesh, before in counts)
        details = [
            f"{mesh.name}: {before} -> {len(mesh.vertices)} vertices "
            f"({before - len(mesh.vertices)} merged)"
            for mesh, before in counts
        ]
        summary = (
            f"{len(meshes)} mesh object(s), {len(counts)} unique mesh(es); "
            f"{removed} vertices merged at 0.0001 m; "
            + ("cleanup incomplete" if error else "normal vectors reset")
            + f"; {len(selected) - len(meshes)} object(s) skipped."
        )
        if error:
            summary += f" {error}. Undo to revert partial changes."
        self.report({'WARNING'} if error else {'INFO'}, summary)
        print("[BleLIZA Mesh Cleanup] " + summary)
        for detail in details:
            print("  " + detail)

        if not bpy.app.background:
            def draw_summary(menu, _context):
                menu.layout.label(text=summary)
                for detail in details:
                    menu.layout.label(text=detail)

            context.window_manager.popup_menu(
                draw_summary, title="Mesh cleanup summary", icon='INFO'
            )
        # Keep partial edits undoable if a Blender operator failed.
        return {'FINISHED'}


# ─────────────────────────────────────────────────────────────────────────────
# Import every file of a directory into its own collection
# ─────────────────────────────────────────────────────────────────────────────

# (enum id, label, extensions, importer operators in order of preference).
# Blender 3.6 ships new built-in OBJ/STL/PLY importers next to the legacy
# add-ons; the first operator that exists is used.
_IMPORT_FORMATS = (
    ('BLEND', ".blend", {'.blend'}, ()),
    ('FBX', "FBX", {'.fbx'}, (('import_scene', 'fbx'),)),
    ('OBJ', "OBJ", {'.obj'}, (('wm', 'obj_import'), ('import_scene', 'obj'))),
    ('GLTF', "glTF", {'.gltf', '.glb'}, (('import_scene', 'gltf'),)),
    ('STL', "STL", {'.stl'}, (('wm', 'stl_import'), ('import_mesh', 'stl'))),
    ('PLY', "PLY", {'.ply'}, (('wm', 'ply_import'), ('import_mesh', 'ply'))),
)
_IMPORTERS_BY_EXTENSION = {
    ext: importers for _id, _label, exts, importers in _IMPORT_FORMATS for ext in exts
}


def _append_blend_objects(filepath):
    """Append every object stored in a .blend file."""
    with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
        data_to.objects = list(data_from.objects)


def _import_with_operator(filepath, importers):
    """Run the first available importer operator for a non-.blend file."""
    for module, name in importers:
        try:
            result = getattr(getattr(bpy.ops, module), name)(filepath=filepath)
        except AttributeError:
            continue  # Operator not available (add-on disabled or not shipped).
        if 'FINISHED' not in result:
            raise RuntimeError(f"importer returned {sorted(result)}")
        return
    raise RuntimeError("no importer available; enable the matching import add-on")


# Blender's duplicate-name suffix: "Name.001", "Name.002", ...
_NUMBER_SUFFIX = re.compile(r"^(?P<base>.+)\.\d{3,}$")


def _reuse_existing_materials(materials_before, images_before):
    """Replace new "Name.001" materials with the "Name" material that existed
    before the import, then delete the copies and the new images only they
    used. Returns the number of reused materials."""
    new_materials = [m for m in bpy.data.materials if m.as_pointer() not in materials_before]
    reused = 0
    for material in new_materials:
        match = _NUMBER_SUFFIX.match(material.name)
        existing = bpy.data.materials.get(match.group("base")) if match else None
        if existing is None or existing.as_pointer() not in materials_before:
            continue
        material.user_remap(existing)
        bpy.data.materials.remove(material)
        reused += 1

    if reused:
        for image in [i for i in bpy.data.images if i.as_pointer() not in images_before]:
            if image.users == 0:
                bpy.data.images.remove(image)
    return reused


class OBJECT_OT_bleliza_import_files_to_collections(bpy.types.Operator):
    bl_idname = "object.bleliza_import_files_to_collections"
    bl_label = "Import Files to Collections"
    bl_description = (
        "Import every supported file in a directory into a new collection "
        "named after the file"
    )
    bl_options = {'REGISTER', 'UNDO'}

    directory: bpy.props.StringProperty(
        name="Directory",
        description="Directory to search for files",
        subtype='DIR_PATH',
    )
    filter_folder: bpy.props.BoolProperty(default=True, options={'HIDDEN'})
    recursive: bpy.props.BoolProperty(
        name="Include Subdirectories",
        description="Also search all subdirectories",
        default=False,
    )
    keep_extension: bpy.props.BoolProperty(
        name="Keep File Extension",
        description="Name collections like 'chair.fbx' instead of 'chair'",
        default=False,
    )
    reuse_materials: bpy.props.BoolProperty(
        name="Reuse Existing Materials",
        description=(
            "Use an existing material with the same name instead of importing "
            "it again as 'Name.001'"
        ),
        default=True,
    )
    file_types: bpy.props.EnumProperty(
        name="File Types",
        description="File types to import",
        items=[(fid, label, f"Import {label} files") for fid, label, _e, _i in _IMPORT_FORMATS],
        options={'ENUM_FLAG'},
        default={fid for fid, _l, _e, _i in _IMPORT_FORMATS},
    )

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "recursive")
        layout.prop(self, "keep_extension")
        layout.prop(self, "reuse_materials")
        layout.label(text="File Types:")
        layout.column(align=True).prop(self, "file_types")

    def _find_files(self, directory):
        extensions = set()
        for fid, _label, exts, _importers in _IMPORT_FORMATS:
            if fid in self.file_types:
                extensions |= exts
        current = Path(bpy.data.filepath).resolve() if bpy.data.filepath else None
        return [
            path for path in sorted(directory.glob("**/*" if self.recursive else "*"))
            if path.is_file()
            and not path.name.startswith(".")
            and path.suffix.lower() in extensions
            and path.resolve() != current
        ]

    def execute(self, context):
        directory = Path(bpy.path.abspath(self.directory)) if self.directory else None
        if directory is None or not directory.is_dir():
            self.report({'ERROR'}, f"Not a directory: {self.directory or '(none)'}")
            return {'CANCELLED'}
        files = self._find_files(directory)
        if not files:
            self.report({'WARNING'}, f"No supported files found in {directory}")
            return {'CANCELLED'}

        imported, failed = [], []
        changed = False
        reused_total = 0
        for path in files:
            label = str(path.relative_to(directory))
            collection = bpy.data.collections.new(
                path.name if self.keep_extension else path.stem
            )
            context.scene.collection.children.link(collection)
            before = {obj.as_pointer() for obj in bpy.data.objects}
            materials_before = {m.as_pointer() for m in bpy.data.materials}
            images_before = {i.as_pointer() for i in bpy.data.images}
            error = None
            try:
                if path.suffix.lower() == '.blend':
                    _append_blend_objects(str(path))
                else:
                    _import_with_operator(
                        str(path), _IMPORTERS_BY_EXTENSION[path.suffix.lower()]
                    )
            except Exception as exc:  # Importers raise many exception types.
                lines = str(exc).strip().splitlines()
                error = lines[-1] if lines else repr(exc)

            # Move everything the file created into its collection only, even
            # after a partial failure, so nothing lands in the active collection.
            objects = [o for o in bpy.data.objects if o.as_pointer() not in before]
            for obj in objects:
                for old in list(obj.users_collection):
                    old.objects.unlink(obj)
                collection.objects.link(obj)
            reused = (_reuse_existing_materials(materials_before, images_before)
                      if self.reuse_materials else 0)
            reused_total += reused

            if error and not objects:
                bpy.data.collections.remove(collection)
                failed.append(f"{label}: {error}")
            elif error:
                changed = True
                failed.append(f"{label}: partially imported "
                              f"({len(objects)} object(s) in '{collection.name}'): {error}")
            else:
                changed = True
                imported.append(f"{label}: {len(objects)} object(s) -> '{collection.name}'"
                                + (f", {reused} material(s) reused" if reused else ""))

        summary = (f"Imported {len(imported)} of {len(files)} file(s) into collections"
                   + (f"; {reused_total} existing material(s) reused" if reused_total else "")
                   + (f"; {len(failed)} failed" if failed else "") + ".")
        details = imported + [f"FAILED {line}" for line in failed]
        self.report({'WARNING'} if failed else {'INFO'}, summary)
        print("[BleLIZA Import to Collections] " + summary)
        for line in details:
            print("  " + line)

        if not bpy.app.background:
            def draw_summary(menu, _context):
                menu.layout.label(text=summary)
                for line in details:
                    menu.layout.label(text=line)

            context.window_manager.popup_menu(
                draw_summary, title="Import summary",
                icon='ERROR' if failed else 'INFO',
            )
        return {'FINISHED'} if changed else {'CANCELLED'}


def menu_func_import_to_collections(self, context):
    self.layout.operator(
        OBJECT_OT_bleliza_import_files_to_collections.bl_idname,
        text="Directory to Collections (BleLIZA)",
    )
    self.layout.operator(
        OBJECT_OT_bleliza_lod_collections_to_empties.bl_idname,
        text="LOD Collections to Empties (BleLIZA)",
    )
    self.layout.operator(
        OBJECT_OT_bleliza_place_from_scenery_xml.bl_idname,
        text="Scenery XML Positions (BleLIZA)",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Group the collections of a .blend file under one empty per LOD base name
# ─────────────────────────────────────────────────────────────────────────────

def _load_collections(filepath, link):
    """Link or append every collection; return (name in source file, collection)."""
    with bpy.data.libraries.load(filepath, link=link) as (data_from, data_to):
        names = [str(name) for name in data_from.collections]
        # Blender replaces the entries of this list with the loaded collections,
        # so it must be a separate list from `names`.
        data_to.collections = list(names)
    # Appended collections may be renamed ("X.001"), so keep the source names.
    return [(n, c) for n, c in zip(names, data_to.collections) if c is not None]


class OBJECT_OT_bleliza_lod_collections_to_empties(bpy.types.Operator):
    bl_idname = "object.bleliza_lod_collections_to_empties"
    bl_label = "LOD Collections to Empties"
    bl_description = (
        "Load all collections from a .blend file and group them as collection "
        "instances under one empty per name without the _LOD<n> suffix"
    )
    bl_options = {'REGISTER', 'UNDO'}

    filepath: bpy.props.StringProperty(
        name="Blend File",
        description="Blend file to read the collections from",
        subtype='FILE_PATH',
    )
    filter_glob: bpy.props.StringProperty(default="*.blend", options={'HIDDEN'})
    filter_blender: bpy.props.BoolProperty(default=True, options={'HIDDEN'})
    filter_folder: bpy.props.BoolProperty(default=True, options={'HIDDEN'})
    link: bpy.props.BoolProperty(
        name="Link",
        description=(
            "Link the collections (read-only, follows changes to the source "
            "file); turn off to append editable copies"
        ),
        default=True,
    )
    lod_pattern: bpy.props.StringProperty(
        name="LOD Pattern",
        description=(
            "Regular expression (case-insensitive) for LOD collection names. "
            "Group 'base' names the parent empty, optional group 'lod' sorts the LODs"
        ),
        default=r"^(?P<base>.+?)_LOD(?P<lod>\d+)$",
    )
    skip_container_collections: bpy.props.BoolProperty(
        name="Skip Container Collections",
        description="Skip collections that hold only other collections and no objects",
        default=True,
    )
    target_collection: bpy.props.StringProperty(
        name="Target Collection",
        description="Collection for the new empties, created if missing; empty = active collection",
        default="",
    )
    empty_size: bpy.props.FloatProperty(
        name="Empty Size",
        description="Display size of the new empties",
        default=1.0,
        min=0.001,
    )

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "link")
        layout.prop(self, "skip_container_collections")
        layout.prop(self, "lod_pattern")
        layout.prop(self, "target_collection")
        layout.prop(self, "empty_size")

    def _target(self, context):
        if not self.target_collection:
            return context.collection
        collection = bpy.data.collections.get(self.target_collection)
        if collection is None:
            collection = bpy.data.collections.new(self.target_collection)
            context.scene.collection.children.link(collection)
        return collection

    def _new_empty(self, name, target, parent=None, instance=None):
        empty = bpy.data.objects.new(name, None)
        empty.empty_display_size = self.empty_size
        if instance is not None:
            empty.instance_type = 'COLLECTION'
            empty.instance_collection = instance
        target.objects.link(empty)
        empty.parent = parent
        return empty

    def execute(self, context):
        filepath = Path(bpy.path.abspath(self.filepath)) if self.filepath else None
        if filepath is None or not filepath.is_file():
            self.report({'ERROR'}, f"Blend file not found: {self.filepath or '(none)'}")
            return {'CANCELLED'}
        if bpy.data.filepath and filepath.resolve() == Path(bpy.data.filepath).resolve():
            self.report({'ERROR'}, "Choose a different .blend file than the one that is open")
            return {'CANCELLED'}
        try:
            lod_re = re.compile(self.lod_pattern, re.IGNORECASE)
        except re.error as exc:
            self.report({'ERROR'}, f"Invalid LOD pattern: {exc}")
            return {'CANCELLED'}
        if "base" not in lod_re.groupindex:
            self.report({'ERROR'}, "LOD pattern needs a named group (?P<base>...)")
            return {'CANCELLED'}

        def sort_key(item):
            """Order by LOD number, so LOD10 comes after LOD2."""
            match = lod_re.match(item[0])
            lod = match.group("lod") if match and "lod" in lod_re.groupindex else None
            return (int(lod) if lod and lod.isdigit() else -1, item[0])

        try:
            loaded = _load_collections(str(filepath), self.link)
        except OSError as exc:
            self.report({'ERROR'}, f"Could not read {filepath.name}: {exc}")
            return {'CANCELLED'}

        groups, skipped = {}, []
        for name, collection in loaded:
            if (self.skip_container_collections
                    and collection.children and not collection.objects):
                skipped.append(name)
                continue
            match = lod_re.match(name)
            base = match.group("base") if match and match.group("base") else name
            groups.setdefault(base, []).append((name, collection))
        if not groups:
            self.report({'WARNING'}, f"No collections to group in {filepath.name}")
            return {'CANCELLED'}

        target = self._target(context)
        details = []
        for base in sorted(groups):
            parent = self._new_empty(base, target)
            members = sorted(groups[base], key=sort_key)
            for name, collection in members:
                self._new_empty(name, target, parent=parent, instance=collection)
            details.append(f"{parent.name}: {', '.join(n for n, _ in members)}")
        details += [f"Skipped {name}: contains only other collections" for name in skipped]

        summary = (f"Created {len(groups)} parent empties for "
                   f"{sum(len(m) for m in groups.values())} collection(s) from "
                   f"{filepath.name} in '{target.name}'"
                   + (f"; {len(skipped)} container collection(s) skipped" if skipped else "")
                   + ".")
        self.report({'INFO'}, summary)
        print("[BleLIZA LOD Collections to Empties] " + summary)
        for line in details:
            print("  " + line)

        if not bpy.app.background:
            def draw_summary(menu, _context):
                menu.layout.label(text=summary)
                for line in details:
                    menu.layout.label(text=line)

            context.window_manager.popup_menu(
                draw_summary, title="LOD collections summary", icon='INFO'
            )
        return {'FINISHED'}


# ─────────────────────────────────────────────────────────────────────────────
# Move objects to the lat/lon positions of an MSFS scenery XML file
# ─────────────────────────────────────────────────────────────────────────────

_WGS84_A = 6378137.0
_WGS84_E2 = 6.69437999014e-3
_SCENERY_NAME = re.compile(r"^\s*SceneryObject name:\s*(?P<name>.*?)\s*$")


def _parse_float(value):
    """Return value as a finite float, or None. Accepts a decimal comma."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(str(value).strip().replace(",", "."))
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _ecef(lat, lon):
    lat, lon = math.radians(lat), math.radians(lon)
    n = _WGS84_A / math.sqrt(1.0 - _WGS84_E2 * math.sin(lat) ** 2)
    return (n * math.cos(lat) * math.cos(lon),
            n * math.cos(lat) * math.sin(lon),
            n * (1.0 - _WGS84_E2) * math.sin(lat))


def _east_north(lat, lon, origin_lat, origin_lon):
    """Metres east and north of the origin in its local tangent plane (WGS84)."""
    x, y, z = _ecef(lat, lon)
    x0, y0, z0 = _ecef(origin_lat, origin_lon)
    dx, dy, dz = x - x0, y - y0, z - z0
    lat0, lon0 = math.radians(origin_lat), math.radians(origin_lon)
    east = -math.sin(lon0) * dx + math.cos(lon0) * dy
    north = (-math.sin(lat0) * math.cos(lon0) * dx
             - math.sin(lat0) * math.sin(lon0) * dy
             + math.cos(lat0) * dz)
    return east, north


def _read_scenery_objects(filepath):
    """Return ([(name, attributes)], unnamed count) for the SceneryObjects of a file.

    The name comes from the comment "<!--SceneryObject name: X-->" directly
    before a SceneryObject element, at any nesting depth.
    """
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    root = ET.parse(filepath, parser=parser).getroot()
    found, unnamed = [], 0
    for parent in root.iter():
        name = None
        for child in parent:
            if child.tag is ET.Comment:
                match = _SCENERY_NAME.match(child.text or "")
                if match:
                    name = match.group("name")
                continue
            if child.tag == "SceneryObject":
                if name:
                    found.append((name, dict(child.attrib)))
                else:
                    unnamed += 1
            name = None
    return found, unnamed


def _origin_from_scene(scene):
    lat, lon = _parse_float(scene.get("lat")), _parse_float(scene.get("lon"))
    if lat is None or lon is None:
        return None
    return lat, lon


class OBJECT_OT_bleliza_place_from_scenery_xml(bpy.types.Operator):
    bl_idname = "object.bleliza_place_from_scenery_xml"
    bl_label = "Place Objects from Scenery XML"
    bl_description = (
        "Move objects of the active collection to the lat/lon position of the "
        "SceneryObject with the same name in an MSFS scenery XML file"
    )
    bl_options = {'REGISTER', 'UNDO'}

    filepath: bpy.props.StringProperty(
        name="XML File",
        description="Scenery XML file with SceneryObject positions",
        subtype='FILE_PATH',
    )
    filter_glob: bpy.props.StringProperty(default="*.xml", options={'HIDDEN'})
    filter_folder: bpy.props.BoolProperty(default=True, options={'HIDDEN'})
    # Strings, because a FloatProperty is single precision: about 0.4 m at 60° latitude.
    origin_lat: bpy.props.StringProperty(
        name="Origin Latitude",
        description=(
            "Latitude of the scene origin in decimal degrees, north positive. "
            "Empty = scene custom property 'lat'"
        ),
        options={'SKIP_SAVE'},
    )
    origin_lon: bpy.props.StringProperty(
        name="Origin Longitude",
        description=(
            "Longitude of the scene origin in decimal degrees, east positive. "
            "Empty = scene custom property 'lon'"
        ),
        options={'SKIP_SAVE'},
    )
    store_origin: bpy.props.BoolProperty(
        name="Save Origin in Scene",
        description="Write the origin to the scene custom properties 'lat' and 'lon'",
        default=True,
    )
    apply_heading: bpy.props.BoolProperty(
        name="Apply Heading",
        description=(
            "Set the rotation to the heading of the file (clockwise from north "
            "around Z; pitch and bank are ignored). Off = keep the current rotation"
        ),
        default=True,
    )
    set_altitude: bpy.props.BoolProperty(
        name="Set Altitude",
        description="Set Z to the alt value of the file in metres. Off = keep the current Z",
        default=False,
    )

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def invoke(self, context, event):
        origin = _origin_from_scene(context.scene)
        if origin is not None:
            self.origin_lat, self.origin_lon = (repr(value) for value in origin)
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text="Scene Origin (WGS84 degrees):")
        if not (self.origin_lat.strip() and self.origin_lon.strip()):
            if _origin_from_scene(context.scene) is None:
                row = box.row()
                row.alert = True
                row.label(text="Scene has no lat/lon: enter the origin", icon='ERROR')
        box.prop(self, "origin_lat", text="Latitude")
        box.prop(self, "origin_lon", text="Longitude")
        box.prop(self, "store_origin")
        layout.prop(self, "apply_heading")
        layout.prop(self, "set_altitude")

    def _origin(self, scene):
        """Return ((lat, lon), None) or (None, error message)."""
        if self.origin_lat.strip() or self.origin_lon.strip():
            origin = (_parse_float(self.origin_lat), _parse_float(self.origin_lon))
            source = "Origin Latitude/Longitude"
        else:
            origin = (_parse_float(scene.get("lat")), _parse_float(scene.get("lon")))
            source = "scene custom properties lat/lon"
            if origin == (None, None):
                return None, ("Scene origin unknown: enter Origin Latitude/Longitude "
                              "or add scene custom properties 'lat' and 'lon'")
        lat, lon = origin
        if lat is None or lon is None or not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            return None, f"Invalid {source}: expected decimal degrees"
        return origin, None

    @staticmethod
    def _place(context, obj, east, north, alt, heading):
        if obj.parent is not None:
            # The parent may have been moved in this run; refresh matrix_world.
            context.view_layer.update()
        location, rotation, scale = obj.matrix_world.decompose()
        location = Vector((east, north, location.z if alt is None else alt))
        if heading is not None:
            # MSFS heading turns clockwise seen from above; Blender's Z rotation
            # turns counterclockwise. Scene +Y is north, +X is east.
            rotation = Quaternion((0.0, 0.0, 1.0), -math.radians(heading))
        obj.matrix_world = Matrix.LocRotScale(location, rotation, scale)

    def execute(self, context):
        filepath = Path(bpy.path.abspath(self.filepath)) if self.filepath else None
        if filepath is None or not filepath.is_file():
            self.report({'ERROR'}, f"XML file not found: {self.filepath or '(none)'}")
            return {'CANCELLED'}
        origin, problem = self._origin(context.scene)
        if origin is None:
            self.report({'ERROR'}, problem)
            return {'CANCELLED'}
        try:
            entries, unnamed = _read_scenery_objects(str(filepath))
        except (ET.ParseError, OSError) as exc:
            self.report({'ERROR'}, f"Could not read {filepath.name}: {exc}")
            return {'CANCELLED'}

        collection = context.collection
        objects = {obj.name: obj for obj in collection.all_objects}
        context.view_layer.update()  # matrix_world must reflect pending edits
        placed, not_found, invalid, duplicates, linked = [], [], [], [], []
        seen = set()
        for name, attributes in entries:
            if name in seen:
                duplicates.append(name)
                continue
            seen.add(name)
            obj = objects.get(name)
            if obj is None:
                not_found.append(name)
                continue
            if obj.library is not None:
                linked.append(name)
                continue
            lat = _parse_float(attributes.get("lat"))
            lon = _parse_float(attributes.get("lon"))
            alt = _parse_float(attributes.get("alt")) if self.set_altitude else None
            heading = _parse_float(attributes.get("heading")) if self.apply_heading else None
            if (lat is None or lon is None or not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0)
                    or (self.set_altitude and alt is None)
                    or (self.apply_heading and heading is None)):
                invalid.append(name)
                continue
            east, north = _east_north(lat, lon, *origin)
            self._place(context, obj, east, north, alt, heading)
            placed.append(name)

        if placed and self.store_origin:
            context.scene["lat"], context.scene["lon"] = origin

        details = [f"Origin: lat {origin[0]!r}, lon {origin[1]!r}"]
        for label, names in (("Not in collection", not_found),
                             ("Invalid position", invalid),
                             ("Duplicate in file, first entry used", duplicates),
                             ("Linked object, cannot move", linked)):
            if names:
                shown = ", ".join(names[:10]) + (f" … (+{len(names) - 10})" if len(names) > 10 else "")
                details.append(f"{label} ({len(names)}): {shown}")
        if unnamed:
            details.append(f"{unnamed} SceneryObject(s) without a name comment ignored")

        summary = (f"Placed {len(placed)} of {len(entries)} named SceneryObject(s) "
                   f"from {filepath.name} in '{collection.name}'.")
        print("[BleLIZA Place from Scenery XML] " + summary)
        for line in details:
            print("  " + line)
        if not placed:
            self.report({'WARNING'}, summary)
            return {'CANCELLED'}
        self.report({'INFO'}, summary)

        if not bpy.app.background:
            def draw_summary(menu, _context):
                menu.layout.label(text=summary)
                for line in details:
                    menu.layout.label(text=line)

            context.window_manager.popup_menu(
                draw_summary, title="Scenery XML placement summary", icon='INFO'
            )
        return {'FINISHED'}


# ─────────────────────────────────────────────────────────────────────────────
# Module-level helper: bake a Mapping-node scale into a Detail UV layer
# on EVERY mesh object in the scene that uses the given material.
#
# Parameters
#   mat             – bpy.types.Material to process
#   source_uv_name  – name of the base UV layer to copy from
#   scale_x, scale_y – Mapping node TEXTURE-space scale values
#                     (scale 0.1 → 10× tiling → UV coords ×10)
# Returns
#   detail_uv_name  – the name of the created/updated Detail UV layer
# ─────────────────────────────────────────────────────────────────────────────
def _create_detail_uv_for_material(mat, source_uv_name, scale_x, scale_y):
    """Create (or update) a '<source_uv>_Detail' UV layer on every mesh object
    that uses *mat*, with UVs copied from *source_uv_name* and scaled by the
    inverse of the given Mapping-node scale values."""

    detail_uv_name = source_uv_name + "_Detail"

    # Invert: Mapping scale 0.1 → UV factor 10 (more tiling)
    inv_x = (1.0 / scale_x) if scale_x != 0.0 else 1.0
    inv_y = (1.0 / scale_y) if scale_y != 0.0 else 1.0

    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        # Check whether this object uses the material
        if not any(slot.material == mat for slot in obj.material_slots):
            continue

        mesh = obj.data
        source_layer = mesh.uv_layers.get(source_uv_name)
        if not source_layer:
            continue  # object has no matching UV layer – skip silently

        # Create detail layer if missing; otherwise reuse the existing one
        if detail_uv_name not in mesh.uv_layers:
            detail_layer = mesh.uv_layers.new(name=detail_uv_name)
        else:
            detail_layer = mesh.uv_layers[detail_uv_name]

        for i, loop_uv in enumerate(source_layer.data):
            detail_layer.data[i].uv[0] = loop_uv.uv[0] * inv_x
            detail_layer.data[i].uv[1] = loop_uv.uv[1] * inv_y

    return detail_uv_name


# Operator to add image texture nodes and create a node preset layout,
# filling them with images from existing nodes if available.
class NODE_OT_create_preset_2020(bpy.types.Operator):
    bl_idname = "node.create_preset_2020"
    bl_label = "Create Node Preset 2020"
    bl_description = "Creates image texture nodes with existing image values and arranges nodes in a preset layout for all materials"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        if not obj or not obj.data.materials:
            self.report({'WARNING'}, "Active object must have materials")
            return {'CANCELLED'}
        
        materials_processed = 0
        
        for mat in obj.data.materials:
            if not mat or not mat.use_nodes:
                continue
            
            materials_processed += 1
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
            
            detail_scale_node = node_tree.nodes.get("Detail UV Sca  le")
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

            existing_emissive_tex = node_tree.nodes.get("Emissive Texture (RGB)")
            emissive_image = existing_emissive_tex.image if existing_emissive_tex and existing_emissive_tex.image else None

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

            # --- Emissive Texture ---
            if emissive_image:
                emissive_tex_node = node_tree.nodes.new(type="ShaderNodeTexImage")
                emissive_tex_node.location = (-500, -800)
                emissive_tex_node.name = "Emissive Texture (RGB)"
                emissive_tex_node.image = emissive_image
                emissive_tex_node.image.colorspace_settings.name = 'sRGB'
                # Connect to Emission Color (Blender 4.x) or Emission (older)
                emission_input = bsdf_node.inputs.get("Emission Color") or bsdf_node.inputs.get("Emission")
                if emission_input:
                    node_tree.links.new(emissive_tex_node.outputs["Color"], emission_input)
                # Use the same UV map as the Base Color texture
                node_tree.links.new(uv_map_node.outputs["UV"], emissive_tex_node.inputs["Vector"])

            # --- Bake Detail UV scale into a dedicated UV layer ---
            # Convert stored detail_scale_value (e.g. 20) → Mapping-node scale (0.2).
            # A Mapping scale of 0.2 means 1/0.2 = 5× tiling in UV space.
            if detail_scale_value is not None:
                mapping_scale = detail_scale_value / 100.0
            else:
                mapping_scale = 1.0

            detail_uv_name = _create_detail_uv_for_material(
                mat, first_uv, mapping_scale, mapping_scale
            )

            # Create a UV Map shader node pointing at the new Detail UV layer
            detail_uv_node = node_tree.nodes.new(type="ShaderNodeUVMap")
            detail_uv_node.location = (-1000, -300)
            detail_uv_node.uv_map = detail_uv_name
            detail_uv_node.label = detail_uv_name

            # Wire Detail UV node into the detail image texture nodes
            node_tree.links.new(detail_uv_node.outputs["UV"], detail_color_node.inputs["Vector"])
            node_tree.links.new(detail_uv_node.outputs["UV"], detail_mat_color_node.inputs["Vector"])
        
        self.report({'INFO'}, f"Node preset layout created for {materials_processed} material(s)")
        return {'FINISHED'}
        
# Operator to add image texture nodes and create a node preset layout,
# filling them with images from existing nodes if available.
class NODE_OT_create_preset_2024(bpy.types.Operator):
    bl_idname = "node.create_preset_2024"
    bl_label = "Create Node Preset 2024"
    bl_description = "Creates image texture nodes with existing image values and arranges nodes in a preset layout for all materials"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        if not obj or not obj.data.materials:
            self.report({'WARNING'}, "Active object must have materials")
            return {'CANCELLED'}
        
        materials_processed = 0
        
        for mat in obj.data.materials:
            if not mat or not mat.use_nodes:
                continue
            
            materials_processed += 1
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
        
            # Initialize variables to None before conditional checks
            metallic_value = None
            roughness_value = None
            emissive_value = None
            detail_scale_value = None
        
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

            existing_emissive_tex = node_tree.nodes.get("Emissive Texture (RGB)")
            emissive_image = existing_emissive_tex.image if existing_emissive_tex and existing_emissive_tex.image else None
        
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
                node_tree.links.new(base_color_node.outputs["Alpha"], bsdf_node.inputs["Alpha"])
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

            # --- Emissive Texture ---
            if emissive_image:
                emissive_tex_node = node_tree.nodes.new(type="ShaderNodeTexImage")
                emissive_tex_node.location = (-500, -800)
                emissive_tex_node.name = "Emissive Texture (RGB)"
                emissive_tex_node.image = emissive_image
                emissive_tex_node.image.colorspace_settings.name = 'sRGB'
                # Connect to Emission Color (Blender 4.x) or Emission (older)
                emission_input = bsdf_node.inputs.get("Emission Color") or bsdf_node.inputs.get("Emission")
                if emission_input:
                    node_tree.links.new(emissive_tex_node.outputs["Color"], emission_input)
                # Use the same UV map as the Base Color texture
                node_tree.links.new(uv_map_node.outputs["UV"], emissive_tex_node.inputs["Vector"])

            # --- Bake Detail UV scale into a dedicated UV layer ---
            if detail_scale_value is not None:
                mapping_scale = detail_scale_value / 100.0
            else:
                mapping_scale = 1.0

            detail_uv_name = _create_detail_uv_for_material(
                mat, first_uv, mapping_scale, mapping_scale
            )

            # Create a UV Map shader node pointing at the new Detail UV layer
            detail_uv_node = node_tree.nodes.new(type="ShaderNodeUVMap")
            detail_uv_node.location = (-1000, -300)
            detail_uv_node.uv_map = detail_uv_name
            detail_uv_node.label = detail_uv_name

            # Wire Detail UV node into the detail image texture nodes
            node_tree.links.new(detail_uv_node.outputs["UV"], detail_color_node.inputs["Vector"])
            node_tree.links.new(detail_uv_node.outputs["UV"], detail_mat_color_node.inputs["Vector"])
        
        self.report({'INFO'}, f"Node preset layout created for {materials_processed} material(s)")
        return {'FINISHED'}

class NODE_OT_add_emissive_from_dds(bpy.types.Operator):
    bl_idname = "node.add_emissive_from_dds"
    bl_label = "Add Emissive Texture from DDS"
    bl_description = (
        "For each material on the active object: looks for a DDS emissive texture "
        "whose name matches the Base Color texture with an emissive suffix "
        "(_EMIS, _lm, _EMISSION or custom). Adds it as an Emissive Texture node "
        "connected to the Emission input, using the same UV map as Base Color."
    )
    bl_options = {'REGISTER', 'UNDO'}

    # Suffixes that identify the 'albedo/base color' part of the filename.
    # The first matching suffix is stripped before appending emissive suffixes.
    _BASE_SUFFIXES = [
        "_ALBD", "_albd", "_Albd",
        "_ALBEDO", "_albedo", "_Albedo",
        "_ALB", "_alb", "_Alb",
        "_COL", "_col", "_Col",
        "_COLOR", "_color", "_Color",
        "_Base_Color", "_base_color",
    ]

    # Built-in emissive suffixes tried in order.
    _EMIS_SUFFIXES = [
        "_EMIS", "_emis", "_Emis",
        "_lm", "_LM",
        "_EMISSION", "_emission", "_Emission",
        "_EM", "_em",
        "_Emissive", "_emissive",
    ]

    extra_suffixes: bpy.props.StringProperty(
        name="Extra Emissive Suffixes",
        description=(
            "Comma-separated list of additional emissive suffixes to try "
            "(e.g. '_glow,_LIGHT'). Tried after the built-in list."
        ),
        default="",
    )

    def execute(self, context):
        obj = context.active_object
        if not obj or not hasattr(obj.data, "materials") or not obj.data.materials:
            self.report({'WARNING'}, "Active object has no materials.")
            return {'CANCELLED'}

        # Build full suffix list: built-in + user extras
        extra = [s.strip() for s in self.extra_suffixes.split(",") if s.strip()]
        emis_suffixes = self._EMIS_SUFFIXES + extra

        processed = 0
        skipped = 0
        not_found = 0

        for mat in obj.data.materials:
            if not mat or not mat.use_nodes:
                skipped += 1
                continue

            node_tree = mat.node_tree
            nodes = node_tree.nodes
            links = node_tree.links

            # ── Skip if emissive node already present ─────────────────────────
            if nodes.get("Emissive Texture (RGB)"):
                skipped += 1
                continue

            # ── Find Base Color image texture node ────────────────────────────
            base_tex_node = nodes.get("Base Color Texture")

            # Fallback: texture wired into Principled BSDF Base Color
            if not base_tex_node or not base_tex_node.image:
                for node in nodes:
                    if node.type != 'BSDF_PRINCIPLED':
                        continue
                    bc_input = node.inputs.get("Base Color")
                    if not (bc_input and bc_input.is_linked):
                        continue
                    from_node = bc_input.links[0].from_node
                    if from_node.type == 'TEX_IMAGE' and from_node.image:
                        base_tex_node = from_node
                    elif from_node.type in {'MIX_RGB', 'MIX'}:
                        for idx in (1, 2):
                            inp = from_node.inputs[idx]
                            if inp.is_linked:
                                cand = inp.links[0].from_node
                                if cand.type == 'TEX_IMAGE' and cand.image:
                                    base_tex_node = cand
                                    break
                    if base_tex_node and base_tex_node.image:
                        break

            if not base_tex_node or not base_tex_node.image:
                skipped += 1
                continue

            base_image = base_tex_node.image
            base_filepath = bpy.path.abspath(base_image.filepath).strip()
            if not base_filepath:
                skipped += 1
                continue

            base_path = Path(base_filepath)
            base_dir = base_path.parent
            base_stem = base_path.stem

            # ── UV node to reuse ──────────────────────────────────────────────
            base_uv_node = None
            if base_tex_node.inputs["Vector"].is_linked:
                from_node = base_tex_node.inputs["Vector"].links[0].from_node
                if from_node.type == 'UVMAP':
                    base_uv_node = from_node
            if not base_uv_node:
                for node in nodes:
                    if node.type == 'UVMAP':
                        base_uv_node = node
                        break

            # ── Strip base suffix to get the shared name root ─────────────────
            stripped_stem = base_stem
            for suf in self._BASE_SUFFIXES:
                if base_stem.endswith(suf):
                    stripped_stem = base_stem[: -len(suf)]
                    break

            # ── Search for emissive DDS file ──────────────────────────────────
            found_path = None
            for esuf in emis_suffixes:
                for ext in (".dds", ".DDS"):
                    candidate = base_dir / (stripped_stem + esuf + ext)
                    if candidate.exists():
                        found_path = candidate
                        break
                if found_path:
                    break

            if not found_path:
                not_found += 1
                print(
                    f"[Add Emissive] No emissive DDS found for material '{mat.name}' "
                    f"(base: {base_path.name}, root: '{stripped_stem}')"
                )
                continue

            # ── Load image ────────────────────────────────────────────────────
            emis_image = bpy.data.images.load(str(found_path), check_existing=True)

            # ── Find Principled BSDF ──────────────────────────────────────────
            bsdf_node = None
            for node in nodes:
                if node.type == 'BSDF_PRINCIPLED':
                    bsdf_node = node
                    break
            if not bsdf_node:
                skipped += 1
                continue

            # ── Create emissive texture node ──────────────────────────────────
            emis_node = nodes.new(type="ShaderNodeTexImage")
            emis_node.location = (
                base_tex_node.location.x,
                base_tex_node.location.y - 320,
            )
            emis_node.name = "Emissive Texture (RGB)"
            emis_node.label = "Emissive Texture (RGB)"
            emis_node.image = emis_image
            emis_node.image.colorspace_settings.name = 'sRGB'

            # ── Connect to Emission input (Blender 4.x / 3.x) ────────────────
            emission_input = (
                bsdf_node.inputs.get("Emission Color")
                or bsdf_node.inputs.get("Emission")
            )
            if emission_input:
                links.new(emis_node.outputs["Color"], emission_input)

            # ── Wire the same UV map ──────────────────────────────────────────
            if base_uv_node:
                links.new(base_uv_node.outputs["UV"], emis_node.inputs["Vector"])

            processed += 1
            print(f"[Add Emissive] Added '{found_path.name}' to material '{mat.name}'")

        msg = (
            f"Added emissive textures to {processed} material(s)"
            + (f"; {not_found} emissive file(s) not found" if not_found else "")
            + (f"; {skipped} material(s) skipped" if skipped else "")
            + "."
        )
        self.report({'INFO'} if processed else {'WARNING'}, msg)
        return {'FINISHED'} if processed else {'CANCELLED'}


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
    bl_description = "Removes all unused image texture nodes from all materials of the selected object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object
        if not obj or not obj.data.materials:
            self.report({'WARNING'}, "Active object must have materials")
            return {'CANCELLED'}
        
        removed_nodes_count = 0

        for mat in obj.data.materials:
            if not mat or not mat.use_nodes:
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

        self.report({'INFO'}, f"Removed {removed_nodes_count} empty or unused nodes from selected object.")
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
        # Note: `tex_folder` can be absolute or Blender-relative ("//...").
        # Always resolve it with `bpy.path.abspath()` before joining filenames.
        texture_folder_abs = bpy.path.abspath(self.tex_folder)
        tex_ext = self.tex_ext if self.tex_ext.startswith(".") else f".{self.tex_ext}"

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

        missing_textures = []

        # Create and assign materials
        # Sort faces so counting starts at the top-left tile, then goes right,
        # then the next row, etc. (row-major order in screen/top-view terms).
        # We use world-space polygon centers for robustness.
        polygons_sorted = sorted(
            obj.data.polygons,
            key=lambda p: (
                -(obj.matrix_world @ p.center).y,  # top (largest Y) first
                (obj.matrix_world @ p.center).x,   # then left (smallest X) to right
            ),
        )

        for i, poly in enumerate(polygons_sorted):
            # Coordinate convention:
            # - X = column index, left->right, 0..columns-1 (first number)
            # - Y = row index, top->bottom,  0..rows-1    (second number)
            row = i // columns  # y
            col = i % columns   # x

            # Determine file and material names
            # File name format: "{prefix}{col}<sep>{row}{suffix}{ext}"
            # Some datasets use '_' while others use '-'; try both.
            file_name_candidates = [
                f"{self.tex_name_prefix}{col}-{row}{self.tex_name_suffix}{tex_ext}",
                f"{self.tex_name_prefix}{col}_{row}{self.tex_name_suffix}{tex_ext}",
            ]
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
            poly.material_index = slot_index
            

            # 4. Configure Material Nodes (Albedo Texture)
            nodes = mat.node_tree.nodes
            links = mat.node_tree.links
            
            # Clear existing nodes for a clean slate (optional, but safer)
            for node in list(nodes):
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
            
            # Load Image
            img = None
            abs_path = None
            for file_name in file_name_candidates:
                abs_path = os.path.join(texture_folder_abs, file_name)
                if not os.path.exists(abs_path):
                    continue
                try:
                    img = bpy.data.images.load(abs_path, check_existing=True)
                except RuntimeError as e:
                    print(f"  Warning: Could not load image {abs_path}. Error: {e}")
                    img = None
                break

            if img is None:
                missing_textures.append((row, col, i, tuple(file_name_candidates), texture_folder_abs))
                print(
                    "  Missing texture(s): "
                    + ", ".join(file_name_candidates)
                    + f" (folder={texture_folder_abs}, row={row}, col={col}, face_index={i})"
                )

            tex_image.image = img
            
            # Connect Image Texture to Principled BSDF Base Color
            links.new(tex_image.outputs['Color'], principled_bsdf.inputs['Base Color'])
            
            # Set image texture color space to Non-Color for DDS (often used for non-albedo data)
            # However, for an "albedo image texture", it is usually sRGB.
            # I will keep it as the default which is usually sRGB unless you specify otherwise.
            # If the DDS is raw data, uncomment the line below:
            # tex_image.image.colorspace_settings.name = 'Non-Color'

        if missing_textures:
            print("--- Create & Assign Materials: missing texture summary ---")
            print(f"Resolved texture folder: {texture_folder_abs}")
            print(
                "Expected filename patterns (tried in order):\n"
                f"  1) {self.tex_name_prefix}{{col}}-{{row}}{self.tex_name_suffix}{tex_ext}\n"
                f"  2) {self.tex_name_prefix}{{col}}_{{row}}{self.tex_name_suffix}{tex_ext}"
            )
            preview = missing_textures[:10]
            print(f"Missing {len(missing_textures)} texture(s). Showing up to 10:")
            for (row, col, face_index, candidates, folder) in preview:
                print(f"  - row={row} col={col} face_index={face_index} folder={folder} candidates={list(candidates)}")
            if len(missing_textures) > len(preview):
                print(f"  ... and {len(missing_textures) - len(preview)} more")

            # Show a visible error in Blender UI; details go to the console.
            self.report(
                {'ERROR'},
                f"Missing {len(missing_textures)} texture(s). Check the console. Folder: {texture_folder_abs}",
            )
        else:
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

class NODE_OT_select_flat_islands(bpy.types.Operator):
    bl_idname = "mesh.select_flat_islands"
    bl_label = "Select Flat Z Islands"
    bl_description = "Selects mesh islands where Z max - Z min is within a threshold"
    bl_options = {'REGISTER', 'UNDO'}

    threshold: bpy.props.FloatProperty(
        name="Threshold",
        default=1.0,
        description="Z difference threshold"
    )

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "No mesh object selected.")
            return {'CANCELLED'}

        # Ensure Edit Mode
        if obj.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')

        mesh = bmesh.from_edit_mesh(obj.data)
        mesh.verts.ensure_lookup_table()

        bpy.ops.mesh.select_all(action='DESELECT')

        visited = set()

        for vert in mesh.verts:
            if vert.index in visited:
                continue

            stack = [vert]
            island = set()
            z_values = []

            while stack:
                v = stack.pop()
                if v.index in visited:
                    continue
                visited.add(v.index)
                island.add(v)
                z_values.append(v.co.z)

                for edge in v.link_edges:
                    other = edge.other_vert(v)
                    if other.index not in visited:
                        stack.append(other)
            
            if not z_values:
                continue

            z_min = min(z_values)
            z_max = max(z_values)

            if (z_max - z_min) <= self.threshold:
                for v in island:
                    v.select = True

        bmesh.update_edit_mesh(obj.data)
        self.report({'INFO'}, "Flat islands selected.")
        return {'FINISHED'}

class OBJECT_OT_bleliza_set_custom_property(bpy.types.Operator):
    bl_idname = "object.bleliza_set_custom_property"
    bl_label = "Set Custom Property"
    bl_description = "Add or update a custom property on objects"
    bl_options = {'REGISTER', 'UNDO'}

    prop_name: bpy.props.StringProperty(name="Property Name")
    prop_value: bpy.props.IntProperty(name="Property Value")
    target: bpy.props.EnumProperty(
        name="Target",
        items=[
            ('ALL', "All Objects", "Apply to all objects in the scene"),
            ('SELECTED', "Selected Objects", "Apply to selected objects only"),
        ],
        default='SELECTED'
    )
    overwrite: bpy.props.BoolProperty(name="Overwrite", default=True)

    @classmethod
    def description(cls, context, properties):
        if not properties:
            return cls.bl_description
            
        if properties.prop_name == "aliza_cast_shadow":
            if properties.target == 'ALL' and properties.prop_value == 0:
                return "Adds aliza_cast_shadow=0 to all objects in the scene (only if the property doesn't exist)"
            elif properties.target == 'SELECTED' and properties.prop_value == 1:
                return "Sets aliza_cast_shadow=1 on selected objects (overwrites if exists)"
        elif properties.prop_name == "aliza_marking":
            return "Sets aliza_marking=1 on selected objects"
        elif properties.prop_name == "aliza_tree":
            return "Sets aliza_tree=1 on selected objects"
        elif properties.prop_name == "aliza_layer":
            return "Sets aliza_layer=0 on selected objects"
            
        return cls.bl_description

    def execute(self, context):
        if self.target == 'ALL':
            objects = context.scene.objects
        else:
            objects = context.selected_objects
            if not objects:
                self.report({'WARNING'}, "No objects selected")
                return {'CANCELLED'}

        count = 0
        for obj in objects:
            if not self.overwrite and self.prop_name in obj:
                continue
            
            obj[self.prop_name] = self.prop_value
            count += 1
            
        self.report({'INFO'}, f"Set '{self.prop_name}' to {self.prop_value} on {count} objects.")
        return {'FINISHED'}

class NODE_OT_set_texture_extend(bpy.types.Operator):
    bl_idname = "node.set_texture_extend"
    bl_label = "Set Image Extension to Extend"
    bl_description = "Sets the extension mode of all image texture nodes in the active object's materials to 'EXTEND'"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj:
            self.report({'ERROR'}, "No active object.")
            return {'CANCELLED'}
        
        # Ensure Object Mode (optional but safer as per script)
        if obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        count = 0
        for material in obj.data.materials:
            if material and material.use_nodes:
                for node in material.node_tree.nodes:
                    if node.type == 'TEX_IMAGE':
                        node.extension = 'EXTEND'
                        count += 1
                        
        self.report({'INFO'}, f"Set extension to EXTEND for {count} texture nodes.")
        return {'FINISHED'}

class NODE_OT_assign_random_materials_islands(bpy.types.Operator):
    bl_idname = "mesh.assign_random_materials_islands"
    bl_label = "Assign Random Materials to Islands"
    bl_description = "Assigns a random material index to each connected face group (island)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "No mesh object selected.")
            return {'CANCELLED'}
        
        # Check materials
        num_materials = len(obj.material_slots)
        if num_materials == 0:
            self.report({'WARNING'}, "No materials assigned to object.")
            return {'CANCELLED'}

        # Ensure Object Mode initially
        if obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Switch to Edit Mode to get BMesh
        bpy.ops.object.mode_set(mode='EDIT')
        
        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        
        # Deselect all
        for face in bm.faces:
            face.select = False
        
        visited = set()
        face_groups = []

        # Find islands
        for face in bm.faces:
            if face.index in visited:
                continue
            group = set()
            stack = [face]
            while stack:
                f = stack.pop()
                if f.index in visited:
                    continue
                visited.add(f.index)
                group.add(f)
                for e in f.edges:
                    for linked_face in e.link_faces:
                        if linked_face.index not in visited:
                            stack.append(linked_face)
            face_groups.append(group)
        
        # Assign random materials
        for group in face_groups:
            mat_index = random.randint(0, num_materials - 1)
            for face in group:
                face.material_index = mat_index
        
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        bpy.ops.object.mode_set(mode='OBJECT')
        
        self.report({'INFO'}, f"Assigned materials to {len(face_groups)} islands.")
        return {'FINISHED'}

class NODE_OT_assign_random_materials_selected_islands(bpy.types.Operator):
    bl_idname = "mesh.assign_random_materials_selected_islands"
    bl_label = "Assign Random Materials to Selected Islands"
    bl_description = "Assigns random materials (filtered by name) to connected components of selected faces"
    bl_options = {'REGISTER', 'UNDO'}

    material_name_filter: bpy.props.StringProperty(
        name="Material Name Filter",
        description="Only use materials containing this string (case-insensitive)",
        default="roof"
    )

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object.")
            return {'CANCELLED'}

        # Ensure Edit Mode
        if context.mode != 'EDIT_MESH':
            bpy.ops.object.mode_set(mode='EDIT')

        # Filter materials
        filter_str = self.material_name_filter.lower()
        roof_materials = [mat for mat in bpy.data.materials if filter_str in mat.name.lower()]

        if not roof_materials:
            self.report({'WARNING'}, f"No materials matching '{self.material_name_filter}' found.")
            return {'CANCELLED'}

        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()

        selected_faces = [f for f in bm.faces if f.select]

        if not selected_faces:
            self.report({'INFO'}, "No faces selected.")
            return {'CANCELLED'}

        # Ensure material slots exist
        for mat in roof_materials:
            if obj.data.materials.find(mat.name) == -1:
                obj.data.materials.append(mat)

        visited_faces = set()
        count = 0

        for face in selected_faces:
            if face in visited_faces:
                continue

            # Connected component
            connected_component = set()
            queue = [face]
            visited_faces.add(face)
            connected_component.add(face)

            while queue:
                current_face = queue.pop(0)
                for edge in current_face.edges:
                    for linked_face in edge.link_faces:
                        # Must be selected and not visited
                        if linked_face.select and linked_face not in visited_faces:
                            queue.append(linked_face)
                            visited_faces.add(linked_face)
                            connected_component.add(linked_face)

            # Assign random material
            chosen_material = random.choice(roof_materials)
            material_index = obj.data.materials.find(chosen_material.name)
            
            if material_index != -1:
                for f in connected_component:
                    f.material_index = material_index
            
            count += 1

        bmesh.update_edit_mesh(obj.data)
        self.report({'INFO'}, f"Assigned materials to {count} connected components.")
        return {'FINISHED'}

class NODE_OT_set_materials_to_sat(bpy.types.Operator):
    bl_idname = "node.set_materials_to_sat"
    bl_label = "Set materials to SAT"
    bl_description = "Set material properties of all materials of the selected object to SAT"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a MESH object.")
            return {'CANCELLED'}
            
        if not obj.data.materials:
            self.report({'WARNING'}, f"Selected object '{obj.name}' has no material slots.")
            return {'CANCELLED'}

        modified_count = 0
        
        for material in obj.data.materials:
            if not material or not material.use_nodes:
                continue
                
            nodes = material.node_tree.nodes
            
            principled_bsdf = None
            for node in nodes:
                if node.type == 'BSDF_PRINCIPLED':
                    principled_bsdf = node
                    break
            
            if principled_bsdf:
                try:
                    # Set Roughness to 1.0
                    if 'Roughness' in principled_bsdf.inputs:
                        principled_bsdf.inputs['Roughness'].default_value = 1.0
                    
                    # Set Specular to 0.0
                    if 'Specular' in principled_bsdf.inputs:
                        principled_bsdf.inputs['Specular'].default_value = 0.0
                    elif 'Specular IOR Level' in principled_bsdf.inputs: # For Blender 4.0+
                         principled_bsdf.inputs['Specular IOR Level'].default_value = 0.0
                    
                    modified_count += 1
                except Exception as e:
                    print(f"Warning: Error updating material {material.name}: {e}")

        if modified_count == 0:
            self.report({'WARNING'}, "No materials were modified (ensure Principled BSDF exists).")
        else:
            self.report({'INFO'}, f"Modified {modified_count} materials.")
            
        return {'FINISHED'}

class NODE_OT_bake_mapping_to_detail_uv(bpy.types.Operator):
    bl_idname = "node.bake_mapping_to_detail_uv"
    bl_label = "Bake Mapping Node to Detail UV"
    bl_description = (
        "For every material on the selected object: if a Mapping node exists in the shader, "
        "its scale is baked into a new '<UVMap>_Detail' UV layer (copy of the default UV map "
        "with the scale applied). The Mapping node is then deleted and replaced by a UV Map "
        "shader node that points to the new Detail UV layer."
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a MESH object.")
            return {'CANCELLED'}

        if not obj.data.materials:
            self.report({'WARNING'}, f"Selected object '{obj.name}' has no materials.")
            return {'CANCELLED'}

        mesh = obj.data
        processed_count = 0
        skipped_count = 0

        for mat in obj.data.materials:
            if not mat or not mat.use_nodes:
                skipped_count += 1
                continue

            node_tree = mat.node_tree
            nodes = node_tree.nodes
            links = node_tree.links

            # ── 1. Find the first Mapping node in the shader ──────────────────
            mapping_node = None
            for node in nodes:
                if node.type == 'MAPPING':
                    mapping_node = node
                    break

            if not mapping_node:
                continue  # Nothing to do for this material

            # ── 2. Read scale from the Mapping node ───────────────────────────
            scale = mapping_node.inputs["Scale"].default_value
            scale_x = scale[0]
            scale_y = scale[1]

            # ── 3. Determine the source UV map ────────────────────────────────
            source_uv_name = None
            for lnk in mapping_node.inputs["Vector"].links:
                if lnk.from_node.type == 'UVMAP':
                    source_uv_name = lnk.from_node.uv_map
                    break

            # Fallback: use the first UV layer on the mesh
            if not source_uv_name:
                if mesh.uv_layers:
                    source_uv_name = mesh.uv_layers[0].name
                else:
                    self.report({'WARNING'}, f"Material '{mat.name}': no UV layer found – skipped.")
                    skipped_count += 1
                    continue

            # ── 4. Bake Detail UV on ALL scene objects that use this material ──
            # _create_detail_uv_for_material handles scale inversion internally.
            detail_uv_name = _create_detail_uv_for_material(
                mat, source_uv_name, scale_x, scale_y
            )

            # ── 5. Collect Image Texture nodes wired to Mapping's output ──────
            image_tex_inputs = []
            for lnk in list(mapping_node.outputs["Vector"].links):
                if lnk.to_node.type == 'TEX_IMAGE':
                    image_tex_inputs.append(lnk.to_node.inputs["Vector"])

            # ── 7. Remember position, then delete the Mapping node ────────────
            mapping_loc = mapping_node.location.copy()
            nodes.remove(mapping_node)

            # ── 8. Create a new UV Map node pointing to the Detail UV layer ───
            uv_map_node = nodes.new(type="ShaderNodeUVMap")
            uv_map_node.uv_map = detail_uv_name
            uv_map_node.location = mapping_loc
            uv_map_node.label = detail_uv_name

            # ── 9. Wire the UV Map node into the Image Texture nodes ──────────
            for tex_vector_input in image_tex_inputs:
                links.new(uv_map_node.outputs["UV"], tex_vector_input)

            processed_count += 1

        if processed_count == 0:
            self.report({'INFO'}, "No Mapping nodes found in any material of this object.")
        else:
            self.report(
                {'INFO'},
                f"Baked Mapping node to Detail UV in {processed_count} material(s)"
                + (f" ({skipped_count} skipped)." if skipped_count else "."),
            )
        return {'FINISHED'}


class OBJECT_OT_remove_non_aliza_custom_props(bpy.types.Operator):
    bl_idname = "object.remove_non_aliza_custom_props"
    bl_label = "Remove Non-ALIZA Custom Properties (Objects)"
    bl_description = (
        "Removes all custom properties from every object in the scene "
        "whose property name does NOT contain 'aliza' (case-insensitive)"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        removed_count = 0
        objects_affected = 0

        for obj in bpy.data.objects:
            keys_to_remove = [
                key for key in obj.keys()
                if "aliza" not in key.lower()
            ]
            if keys_to_remove:
                objects_affected += 1
                for key in keys_to_remove:
                    del obj[key]
                    removed_count += 1

        self.report(
            {'INFO'},
            f"Removed {removed_count} non-ALIZA custom propert{'y' if removed_count == 1 else 'ies'} "
            f"from {objects_affected} object{'s' if objects_affected != 1 else ''}.",
        )
        return {'FINISHED'}


class OBJECT_OT_remove_non_aliza_material_custom_props(bpy.types.Operator):
    bl_idname = "object.remove_non_aliza_material_custom_props"
    bl_label = "Remove Non-ALIZA Custom Properties (Materials)"
    bl_description = (
        "Removes all custom properties from every material used by any object in the scene "
        "whose property name does NOT contain 'aliza' (case-insensitive)"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        removed_count = 0
        materials_affected = 0

        visited = set()
        for obj in bpy.data.objects:
            for slot in obj.material_slots:
                mat = slot.material
                if mat is None or mat.name in visited:
                    continue
                visited.add(mat.name)
                keys_to_remove = [
                    key for key in mat.keys()
                    if "aliza" not in key.lower()
                ]
                if keys_to_remove:
                    materials_affected += 1
                    for key in keys_to_remove:
                        del mat[key]
                        removed_count += 1

        self.report(
            {'INFO'},
            f"Removed {removed_count} non-ALIZA custom propert{'y' if removed_count == 1 else 'ies'} "
            f"from {materials_affected} material{'s' if materials_affected != 1 else ''}.",
        )
        return {'FINISHED'}


class OBJECT_OT_make_real_trees(bpy.types.Operator):
    bl_idname = "object.make_real_trees"
    bl_label = "Make real trees"
    bl_description = (
        "Reads the 'aliza_tree_instance' attribute from the evaluated Geometry Nodes mesh "
        "and generates an Empty object for each point, storing the attribute as a custom property"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        import bpy

        # Get active object with the Geometry Nodes modifier
        gn_obj = context.active_object
        ATTRIBUTE_NAME = "aliza_tree_instance"

        if gn_obj and gn_obj.type == 'MESH':
            # 1. Duplicate object and apply GN modifier to evaluate points/attributes
            depsgraph = context.evaluated_depsgraph_get()
            evaluated_obj = gn_obj.evaluated_get(depsgraph)
            eval_mesh = evaluated_obj.data

            # Check if the attribute exists
            if ATTRIBUTE_NAME in eval_mesh.attributes:
                attr = eval_mesh.attributes[ATTRIBUTE_NAME]

                # Create a new collection for exported empties
                export_coll = bpy.data.collections.new("Exported_Empties")
                context.scene.collection.children.link(export_coll)

                # Loop through each point/vertex in the evaluated mesh
                for i, vertex in enumerate(eval_mesh.vertices):
                    # Read position and custom attribute
                    pos = evaluated_obj.matrix_world @ vertex.co
                    attr_value = attr.data[i].value  # Adjust depending on data type (.value, .color, etc.)

                    # Create an Empty object
                    empty = bpy.data.objects.new(f"Empty_{i}", None)
                    empty.location = pos
                    empty.empty_display_type = 'PLAIN_AXES'

                    # Copy custom property to the Object level
                    empty[ATTRIBUTE_NAME] = attr_value

                    # Link to scene
                    export_coll.objects.link(empty)

                count = len(eval_mesh.vertices)
                self.report({'INFO'}, f"Successfully generated {count} empties with custom properties.")
            else:
                self.report({'WARNING'}, f"Attribute '{ATTRIBUTE_NAME}' not found on evaluated mesh.")
                return {'CANCELLED'}
        else:
            self.report({'ERROR'}, "Active object must be a MESH with a Geometry Nodes modifier.")
            return {'CANCELLED'}

        return {'FINISHED'}


# Select all objects of the LOD<n> collections below the active collection
class OBJECT_OT_bleliza_select_lod_objects(bpy.types.Operator):
    bl_idname = "object.bleliza_select_lod_objects"
    bl_label = "Select LOD Objects"
    bl_description = (
        "Select all objects in collections whose name ends with the LOD suffix, "
        "searching only the sub collections of the active collection. "
        "Shift-click to add to the current selection"
    )
    bl_options = {'REGISTER', 'UNDO'}

    lod: bpy.props.IntProperty(name="LOD", default=0, min=0)
    extend: bpy.props.BoolProperty(
        name="Extend",
        description="Add to the current selection instead of replacing it",
        default=False,
    )

    @staticmethod
    def _matches(name, suffix):
        """Name ends with suffix (case-insensitive), ignoring a Blender '.001' duplicate tail."""
        import re
        base = re.sub(r"\.\d{3,}$", "", name)
        return base.lower().endswith(suffix.lower())

    def invoke(self, context, event):
        self.extend = event.shift
        return self.execute(context)

    def execute(self, context):
        active = context.view_layer.active_layer_collection.collection
        suffix = f"LOD{self.lod}"

        def descendants(collection):
            for child in collection.children:
                yield child
                yield from descendants(child)

        lod_collections = [c for c in descendants(active) if self._matches(c.name, suffix)]
        if not lod_collections:
            self.report({'WARNING'}, f"No '*{suffix}' collections found below '{active.name}'")
            return {'CANCELLED'}

        if not self.extend:
            for obj in context.view_layer.objects:
                obj.select_set(False)

        targets = []
        for collection in lod_collections:
            for obj in collection.all_objects:
                if obj not in targets:
                    targets.append(obj)

        selected = 0
        for obj in targets:
            if obj.name in context.view_layer.objects and obj.visible_get():
                obj.select_set(True)
                selected += 1

        if selected:
            first = next(o for o in targets if o.select_get())
            context.view_layer.objects.active = first

        skipped = len(targets) - selected
        msg = f"Selected {selected} objects from {len(lod_collections)} '{suffix}' collections"
        if skipped:
            msg += f" ({skipped} hidden or excluded objects skipped)"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class OBJECT_OT_merge_duplicate_materials(bpy.types.Operator):
    bl_idname = "object.merge_duplicate_materials"
    bl_label = "Merge Duplicate Materials"
    bl_description = (
        "Scans all objects in the scene for materials that use the same image textures, "
        "asks for confirmation, then merges duplicates into one material named after the albedo texture"
    )
    bl_options = {'REGISTER', 'UNDO'}

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _material_image_signature(mat):
        """Return a frozenset of image identifiers (filepath or name) used in
        all TEX_IMAGE nodes of *mat*, or None if the material has no images."""
        if not mat or not mat.use_nodes:
            return None
        paths = set()
        for node in mat.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                identifier = node.image.filepath.strip() or node.image.name
                paths.add(identifier)
        return frozenset(paths) if paths else None

    @staticmethod
    def _find_albedo_image(mat):
        """Return the image most likely to be the albedo / base-color texture.

        Strategy (in order of priority):
        1. TEX_IMAGE directly wired into the Principled BSDF 'Base Color' input.
        2. TEX_IMAGE wired into a Mix node that feeds 'Base Color'.
        3. First TEX_IMAGE with colorspace == 'sRGB'.
        4. Any TEX_IMAGE with an assigned image.
        """
        if not mat or not mat.use_nodes:
            return None

        for node in mat.node_tree.nodes:
            if node.type != 'BSDF_PRINCIPLED':
                continue
            bc_input = node.inputs.get("Base Color")
            if bc_input and bc_input.is_linked:
                from_node = bc_input.links[0].from_node
                if from_node.type == 'TEX_IMAGE' and from_node.image:
                    return from_node.image
                # One level deeper (MixRGB / ShaderNodeMix)
                if from_node.type in {'MIX_RGB', 'MIX'}:
                    for idx in (1, 2):
                        inp = from_node.inputs[idx]
                        if inp.is_linked:
                            candidate = inp.links[0].from_node
                            if candidate.type == 'TEX_IMAGE' and candidate.image:
                                return candidate.image

        # Fallback 1: sRGB image texture
        for node in mat.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                try:
                    if node.image.colorspace_settings.name == 'sRGB':
                        return node.image
                except Exception:
                    pass

        # Fallback 2: any image texture
        for node in mat.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                return node.image

        return None

    def _find_duplicate_groups(self):
        """Collect all materials used in the scene and group duplicates.

        Returns a list of lists – each inner list contains two or more
        bpy.types.Material objects that share the same image texture set.
        """
        all_mats = set()
        for obj in bpy.data.objects:
            for slot in obj.material_slots:
                if slot.material:
                    all_mats.add(slot.material)

        sig_map = {}
        for mat in all_mats:
            sig = self._material_image_signature(mat)
            if sig is None:
                continue
            sig_map.setdefault(sig, []).append(mat)

        return [group for group in sig_map.values() if len(group) > 1]

    @staticmethod
    def _collections_of_object(obj):
        """Return the set of bpy.types.Collection objects that directly contain *obj*."""
        return {col for col in bpy.data.collections if obj.name in col.objects}

    @staticmethod
    def _obj_in_view_layer(obj, context):
        """Return True if *obj* is linked into the active ViewLayer."""
        return context.view_layer.objects.get(obj.name) is not None

    @staticmethod
    def _join_object_group(context, objects):
        """Join a list of MESH objects into the first one.

        Only objects that are present in the active ViewLayer are processed.
        Returns the surviving object or None on failure / if fewer than 2
        objects are visible in the view layer.
        """
        if not objects:
            return None

        vl_objects = context.view_layer.objects

        # Filter to objects actually present in the view layer using .get()
        vl_objs = [o for o in objects
                   if vl_objects.get(o.name) is not None]

        skipped = [o.name for o in objects if vl_objects.get(o.name) is None]
        if skipped:
            print(f"[Merge Duplicates] Skipping – not in ViewLayer: {skipped}")

        if len(vl_objs) < 2:
            return None

        # Ensure Object mode
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # Deselect everything, then select only our group
        for o in vl_objects:
            o.select_set(False)

        active = vl_objs[0]
        for o in vl_objs:
            o.select_set(True)

        try:
            vl_objects.active = active
            bpy.ops.object.join()
        except Exception as exc:
            print(f"[Merge Duplicates] join failed: {exc}")
            return None

        return active

    @staticmethod
    def _build_col_join_map():
        """Return a dict: material → { collection → [mesh objects] }
        for every material that is used by 2+ mesh objects in the same collection.
        Only entries with at least one collection containing 2+ objects are kept.
        """
        mat_col_map = {}  # mat → { col → [obj, ...] }
        for obj in bpy.data.objects:
            if obj.type != 'MESH':
                continue
            seen_mats = set()
            for slot in obj.material_slots:
                mat = slot.material
                if mat is None or mat in seen_mats:
                    continue
                seen_mats.add(mat)
                for col in (c for c in bpy.data.collections if obj.name in c.objects):
                    mat_col_map.setdefault(mat, {}).setdefault(col, []).append(obj)

        # Keep only (mat, col) combos where 2+ objects share the material
        result = {}
        for mat, col_dict in mat_col_map.items():
            filtered = {col: objs for col, objs in col_dict.items() if len(objs) >= 2}
            if filtered:
                result[mat] = filtered
        return result

    # ── Blender operator interface ────────────────────────────────────────────

    def invoke(self, context, event):
        dup_groups = self._find_duplicate_groups()
        join_map = self._build_col_join_map()

        if not dup_groups and not join_map:
            self.report({'INFO'}, "No duplicate materials and no same-collection objects to join found.")
            return {'CANCELLED'}

        print("=" * 60)
        if dup_groups:
            total_redundant = sum(len(g) - 1 for g in dup_groups)
            print(f"[Merge Duplicates] Found {len(dup_groups)} duplicate group(s), "
                  f"{total_redundant} redundant material(s) will be removed:")
            for i, group in enumerate(dup_groups, 1):
                albedo = self._find_albedo_image(group[0])
                albedo_name = (
                    os.path.splitext(os.path.basename(
                        albedo.filepath.strip() or albedo.name))[0]
                    if albedo else "<no albedo>"
                )
                print(f"  Group {i}: new name → '{albedo_name}'")
                for mat in group:
                    print(f"    • {mat.name}")

        if join_map:
            print(f"[Merge Duplicates] Objects to join per material/collection:")
            for mat, col_dict in join_map.items():
                for col, objs in col_dict.items():
                    print(f"  Mat '{mat.name}' in col '{col.name}': "
                          + ", ".join(o.name for o in objs))
        print("=" * 60)

        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        dup_groups = self._find_duplicate_groups()

        merged_slots = 0
        removed_mats = 0

        # ── Step 1: merge duplicate materials ────────────────────────────────
        for group in dup_groups:
            winner = group[0]
            losers = group[1:]

            # Rename winner after its albedo texture filename
            albedo = self._find_albedo_image(winner)
            if albedo:
                raw_path = albedo.filepath.strip() or albedo.name
                new_name = os.path.splitext(os.path.basename(raw_path))[0]
                if new_name:
                    winner.name = new_name

            # Re-point every material slot that uses a loser to the winner
            loser_set = set(losers)
            for obj in bpy.data.objects:
                for slot in obj.material_slots:
                    if slot.material in loser_set:
                        slot.material = winner
                        merged_slots += 1

            # Purge zero-user loser materials
            for loser in losers:
                if loser.users == 0:
                    bpy.data.materials.remove(loser)
                    removed_mats += 1

        # ── Step 2: join same-collection objects that share ANY material ─────
        # Re-build the join map after the merge so newly unified materials are
        # also picked up.
        join_map = self._build_col_join_map()
        joins_done = 0

        for mat, col_dict in join_map.items():
            for col, objs in col_dict.items():
                if len(objs) < 2:
                    continue
                print(
                    f"[Merge Duplicates] Joining {len(objs)} object(s) in "
                    f"collection '{col.name}' sharing material '{mat.name}':"
                )
                for o in objs:
                    print(f"    • {o.name}")

                # Filter to objects still present (some may have been joined already)
                live_objs = [o for o in objs if o.name in bpy.data.objects]
                if len(live_objs) < 2:
                    continue

                survivor = self._join_object_group(context, live_objs)
                if survivor:
                    survivor.name = mat.name
                    joins_done += 1

        if not dup_groups and joins_done == 0:
            self.report({'INFO'}, "No duplicate materials and no objects were joined.")
            return {'CANCELLED'}

        msg = (
            f"Merged {merged_slots} material slot(s) across {len(dup_groups)} group(s); "
            f"removed {removed_mats} duplicate material(s); "
            f"performed {joins_done} join operation(s)."
        )
        self.report({'INFO'}, msg)
        print(f"[Merge Duplicates] {msg}")
        return {'FINISHED'}


class OBJECT_OT_remove_unused_materials(bpy.types.Operator):
    bl_idname = "object.remove_unused_materials"
    bl_label = "Remove Unused Materials"
    bl_description = "Removes material slots that are not assigned to any face on the selected object"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Please select a mesh object.")
            return {'CANCELLED'}
        
        # Ensure Object Mode
        if obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Use built-in operator
        bpy.ops.object.material_slot_remove_unused()
        
        self.report({'INFO'}, "Unused materials removed.")
        return {'FINISHED'}
