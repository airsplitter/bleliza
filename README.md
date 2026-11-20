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
