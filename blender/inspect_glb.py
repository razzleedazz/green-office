import bpy, sys
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=sys.argv[sys.argv.index('--')+1])
for o in bpy.data.objects:
    print(f"{o.name:40s} {o.type:9s} parent={o.parent.name if o.parent else '-':18s} dims={tuple(round(d,2) for d in o.dimensions)} loc={tuple(round(v,2) for v in o.matrix_world.translation)}")
