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
