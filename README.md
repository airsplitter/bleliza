# bleliza
Blender 3.6 add-on for material conversion tasks, texture and mesh operations, and scene optimizations to prepare airport scenes for ALIZA by ATRiCS

Select mesh objects, then open **Object Properties > BleLIZA Object Tools >
Merge by Distance & Reset Vectors**. The routine enters Edit Mode, selects all
visible geometry, merges vertices at 0.0001 m, resets normal vectors, and returns
to Object Mode. A popup reports merged vertices per mesh and skipped objects.
The same summary is written to Blender's Info log and the system console.

Object selection and the active object are preserved. Non-mesh objects and
linked read-only meshes are skipped. Hidden geometry stays hidden and is not
processed, matching Blender's Select All behavior. Shared mesh data is processed
once and affects all its instances, including unselected instances. The merge
distance respects scene units and uses mesh-local coordinates, just like the
native Edit Mode operation; object transforms are not applied. Use Undo to revert.

## Import files to collections

**File > Import > Directory to Collections (BleLIZA)**, or **Object Properties >
BleLIZA Object Tools > Import Files to Collections**, opens a directory browser.
Every supported file in the chosen directory gets its own new collection, named
after the file, containing all objects from that file:

- `.blend`: every object stored in the file is appended, including objects that
  are not linked to any scene there. Parenting, modifiers and materials are kept.
- FBX, OBJ, glTF/GLB, STL and PLY: imported with Blender's importer, then moved
  from the active collection into the new collection.

Options in the browser sidebar: include subdirectories, keep the file extension
in the collection name, reuse existing materials, and choose the file types.

**Reuse Existing Materials** (on by default): when an imported material arrives
as `Name.001` because `Name` already existed before that file was imported, its
users are switched to the existing `Name` and the copy is deleted, together
with new images that only the copy used. This also applies between files of the
same run. Materials are matched by name only; the existing one wins. The currently open `.blend`,
hidden files and other extensions are skipped. A file that fails to import is
listed in the summary and gets no collection; if it failed after creating
objects, those objects stay in its collection and the file is reported as
partially imported. Duplicate collection names get Blender's `.001` suffix.

## LOD collections to empties

**File > Import > LOD Collections to Empties (BleLIZA)**, or **Object Properties >
BleLIZA Object Tools > LOD Collections to Empties**, opens a `.blend` file
browser. All collections of the chosen file are loaded and grouped by their name
without the `_LOD<n>` suffix. Blender cannot parent a collection to an object,
so each collection becomes a collection-instance empty under a plain parent
empty:

```
ENGM_TaxiSigns_268                (plain empty)
├── ENGM_TaxiSigns_268_LOD0       (instance of collection ENGM_TaxiSigns_268_LOD0)
├── ENGM_TaxiSigns_268_LOD1
└── ENGM_TaxiSigns_268_LOD2
```

Options in the browser sidebar:

- **Link** (on): linked collections are read-only and follow changes to the
  source file. Turn it off to append editable copies.
- **Skip Container Collections** (on): collections that hold only other
  collections are skipped, so their LODs are not instanced twice.
- **LOD Pattern**: case-insensitive regular expression; group `base` names the
  parent empty, optional group `lod` sorts the LODs numerically.
- **Target Collection**: collection for the new empties, created if missing;
  empty means the active collection.
- **Empty Size**: display size of the new empties.

Collections without an LOD suffix still get a parent empty with one instance.
All empties are placed at the world origin. Running it again creates a second
set of empties with `.001` names. If an exporter ignores collection instances,
use **Object > Apply > Make Instances Real** on the instance empties.

## Place objects from scenery XML

**File > Import > Scenery XML Positions (BleLIZA)**, or **Object Properties >
BleLIZA Object Tools > Place Objects from Scenery XML**, opens an `.xml` file
browser for an MSFS scenery file. Each `SceneryObject` is named by the comment
directly before it:

```xml
<!--SceneryObject name: LOTUS_wasserfilter_001-->
<SceneryObject lat="60.21456851714919" lon="11.09151156430177" alt="0.0" heading="-157.677622" ...>
```

An object of the active collection (including its child collections) with the
same name, for example an empty holding linked collections, is moved to that
position. Other objects stay where they are.

Positions are converted to metres in the local tangent plane of the scene
origin on the WGS84 ellipsoid: +X is east, +Y is north, the origin is (0, 0).
The origin comes from the scene custom properties `lat` and `lon` (decimal
degrees). If the scene has none, enter the origin in the browser sidebar;
**Save Origin in Scene** (on) then writes it to the scene properties, so the
next run uses the same origin.

Options in the browser sidebar:

- **Apply Heading** (on): sets the rotation to the file's heading, clockwise
  from north around Z. Pitch and bank are ignored. Off keeps the rotation.
- **Set Altitude** (off): sets Z to the file's `alt` value in metres. Off keeps
  the current Z. With `altitudeIsAgl="TRUE"`, `alt` is the height above ground.

Parented objects are placed in world space. The summary lists names from the
file that were not found in the active collection, invalid positions and
duplicate names (the first entry is used).

## Bake emission lightmap

**Object Properties > BleLIZA Object Tools > Emission Lightmap**: choose the
**Target** mesh that holds the lightmap, then click **Bake Emission Lightmap**.
Cycles bakes the light that emissive materials in the scene cast onto the
target into the target's UV map (Diffuse bake with Direct and Indirect light,
Color off), so the result is pure light without the target's own textures. The
target's own emission is not part of its lightmap.

Options in the dialog:

- **Image Name**: empty means `<target>_Lightmap`. An existing image with this
  name is replaced, and materials that already show it switch to the new bake.
- **Resolution**, **UV Map** (empty means the active render UV map),
  **Samples** and **Margin**.
- **Emission Only** (on): the world and all lamps are switched off during the
  bake, so only emissive materials light the target. Lamps inside collection
  instances or linked from another file cannot be switched off and still count.
- **Emission Scale**: multiplies every material's emission strength during the
  bake. Strengths that are driven by node links stay unchanged.
- **32-bit Float (HDR)**: keeps light brighter than 1.0; saved as OpenEXR
  instead of PNG.
- **Save To**: file for the lightmap. Empty packs the image into the `.blend`.

Render engine, samples, world, lamps, emission strengths, selection and the
active object are restored afterwards; the add-on adds and removes a temporary
Image Texture node in the target's materials. Cycles does not denoise bakes, so
raise **Samples** or **Emission Scale** if the lightmap is noisy.
