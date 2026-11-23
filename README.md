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

## Make real and join LODs

**Object Properties > BleLIZA Object Tools > Make Real & Join LODs** works on
the active collection (including its child collections). It makes every linked
or instanced object real and local, then joins all meshes with the same LOD
suffix into one object per suffix, for example `Airport_LOD0`, `Airport_LOD1`
and `Airport_LOD2` for the collection `Airport`. The joined objects are placed
at the world origin; every part keeps its world position.

- Collection instances (for example the empties of **LOD Collections to
  Empties**), nested instances, directly linked objects and plain mesh objects
  are all included.
- The LOD suffix is read from the object name, then from the name of the
  collection the object is in, then from the instanced collection and the
  instance empty. `Pole` in collection `Sign_LOD0` therefore joins `LOD0`.
- Meshes without an LOD suffix are made real but not joined.

Options in the dialog:

- **LOD Pattern**: case-insensitive regular expression for the suffix; the
  optional group `lod` holds the number, so `_LOD00` and `_lod0` both join `LOD0`.
- **Reuse Materials by Name** (on): a linked material uses the local material
  with the same name if there is one, otherwise it is made local once and that
  copy is reused. `Name.001` duplicates are replaced by `Name` everywhere and
  deleted. Linked images and node groups of the materials are made local the
  same way. Slots with the same material are merged.
- **Remove Instance Empties** (on): deletes the instance empties that were made
  real and parent empties left without children. Instance empties that also
  instance non-mesh objects (lights, empties) are kept.

Modifiers of instanced objects are not applied; the joined mesh uses the
original mesh data. Instances of hidden collections are not evaluated and are
listed in the summary. Use Undo to revert.

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
