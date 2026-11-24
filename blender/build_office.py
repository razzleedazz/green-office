"""Build the Green Office in Blender, bake its lighting, export office.glb.

Run:  Blender -b -P build_office.py -- <out_dir> [samples] [atlas_px] [empty]

"empty" builds one low-poly cluster with nobody at it (cluster.glb), repeated across the open office.

Coordinates are written the way the Three.js scene uses them (Y up, centimetres)
and converted on the fly: three (x, y, z) -> blender (x, -z, y) * 0.01.
"""
import bpy, bmesh, math, os, sys, time
import numpy as np
from mathutils import Vector, Matrix, Euler

argv = sys.argv[sys.argv.index('--') + 1:]
OUT = argv[0]
SAMPLES = int(argv[1]) if len(argv) > 1 else 256
ATLAS = int(argv[2]) if len(argv) > 2 else 4096
FLOOR_PX = 2048
EMPTY = len(argv) > 3 and argv[3] == 'empty'
SEG = 1 if EMPTY else 5
os.makedirs(OUT, exist_ok=True)
S = 0.01
t0 = time.time()
def log(*a): print(f'[{time.time() - t0:6.1f}s]', *a, flush=True)

def T(x, y, z): return Vector((x * S, -z * S, y * S))
def R(rx=0.0, ry=0.0): return (Matrix.Rotation(ry, 4, 'Z') @ Matrix.Rotation(rx, 4, 'X'))
def M(x, y, z, rx=0.0, ry=0.0): return Matrix.Translation(T(x, y, z)) @ R(rx, ry)
def Rz(a): return Matrix.Rotation(a, 4, 'Z')
I = Matrix.Identity(4)

# ---------------------------------------------------------------- scene
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.view_settings.view_transform = 'Standard'
scene.view_settings.look = 'None'
try:
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'METAL'
    prefs.get_devices()
    for d in prefs.devices: d.use = True
    scene.cycles.device = 'GPU'
    log('devices:', [d.name for d in prefs.devices if d.use])
except Exception as e:
    log('GPU unavailable, using CPU:', e)
scene.cycles.samples = SAMPLES

coll_bake = bpy.data.collections.new('bake'); scene.collection.children.link(coll_bake)
coll_active = bpy.data.collections.new('active_chair'); scene.collection.children.link(coll_active)
coll_extra = bpy.data.collections.new('casters'); scene.collection.children.link(coll_extra)

# ---------------------------------------------------------------- materials
def lin(h):
    c = [(h >> 16) & 255, (h >> 8) & 255, h & 255]
    out = []
    for v in c:
        v /= 255
        out.append(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4)
    return (*out, 1.0)

def material(name, hexcol, rough=0.6, noise=0.0, emit=None, emit_strength=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; bsdf = nt.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = lin(hexcol)
    bsdf.inputs['Roughness'].default_value = rough
    if noise:
        tex = nt.nodes.new('ShaderNodeTexNoise'); tex.inputs['Scale'].default_value = 900; tex.inputs['Detail'].default_value = 2
        mix = nt.nodes.new('ShaderNodeMix'); mix.data_type = 'RGBA'; mix.blend_type = 'MULTIPLY'
        mix.inputs['Factor'].default_value = noise
        mix.inputs['A'].default_value = lin(hexcol)
        nt.links.new(tex.outputs['Color'], mix.inputs['B'])
        nt.links.new(mix.outputs['Result'], bsdf.inputs['Base Color'])
    if emit is not None:
        bsdf.inputs['Emission Color'].default_value = lin(emit)
        bsdf.inputs['Emission Strength'].default_value = emit_strength
    return m

MAT = {
    'desk': material('desk', 0xebe8e1, .5, noise=.05),
    'deskEdge': material('deskEdge', 0xd3cfc6, .55),
    'part': material('part', 0x1b1f1d, .95, noise=.35),
    'trim': material('trim', 0xe3e0d8, .45),
    'crt': material('crt', 0xe6dfce, .42, noise=.05),
    'crtDark': material('crtDark', 0xcbc2ad, .5),
    'kbBase': material('kbBase', 0xdfe3e8, .35),
    'chair': material('chair', 0x24262c, .55),
    'chairMesh': material('chairMesh', 0x2c2f36, .85, noise=.3),
    'metal': material('metal', 0x4a4e57, .3),
    'leg': material('leg', 0xb4b8bd, .35),
    'ledOn': material('ledOn', 0x6cf08a, .4, emit=0x6cf08a, emit_strength=8),
    'ledOff': material('ledOff', 0x5a4a2a, .4),
    # casters / emitters that are not exported
    'suit': material('suit', 0x3b4049, .85),
    'skin': material('skin', 0xd8a88a, .6),
    'glass': material('glass', 0x131a17, .1),
    'screenOn': material('screenOn', 0x9be3a0, .5, emit=0xc8f5cc, emit_strength=6),
    'floor': material('floor', 0x4a9a5e, .45),
}

# ---------------------------------------------------------------- primitives (built with bmesh, no operators)
def finish(bm, name, mat, mw, coll, smooth=False, bevel=0.0):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for p in me.polygons: p.use_smooth = smooth
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me); coll.objects.link(ob)
    ob.matrix_world = mw
    if bevel > 0:
        b = ob.modifiers.new('bevel', 'BEVEL'); b.width = bevel; b.segments = SEG; b.limit_method = 'NONE'
        b.harden_normals = True
        for p in me.polygons: p.use_smooth = True
    return ob

def rbox(w, h, d, r, mat, x, y, z, P=I, rx=0.0, ry=0.0, coll=None, name='box'):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(w * S, d * S, h * S), verts=bm.verts)
    r = min(r * 1.8, r + 1.5, min(w, h, d) / 2 * .94)    # generous rounding, never collapsing the thinnest side
    return finish(bm, name, MAT[mat], P @ M(x, y, z, rx, ry), coll or coll_bake, bevel=max(0.0, r) * S)

def cyl(rt, rb, h, mat, x, y, z, P=I, rx=0.0, seg=16, coll=None, name='cyl'):
    bm = bmesh.new()
    if EMPTY: seg = min(seg, 8)
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg, radius1=rb * S, radius2=rt * S, depth=h * S)
    return finish(bm, name, MAT[mat], P @ M(x, y, z, rx), coll or coll_bake, smooth=True)

def sphere(r, mat, x, y, z, P=I, scale=(1, 1, 1), coll=None, name='sph'):
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=8 if EMPTY else 20, v_segments=6 if EMPTY else 14, radius=r * S)
    sx, sy, sz = scale
    bmesh.ops.scale(bm, vec=(sx, sz, sy), verts=bm.verts)
    return finish(bm, name, MAT[mat], P @ M(x, y, z), coll or coll_bake, smooth=True)

def plane(w, h, mat, x, y, z, P=I, rx=0.0, coll=None, name='plane'):
    bm = bmesh.new()
    vs = [bm.verts.new((sx * w * S / 2, 0, sy * h * S / 2)) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    bm.faces.new(vs)
    return finish(bm, name, MAT[mat], P @ M(x, y, z, rx), coll or coll_bake)

def limb(a, b, r, mat, P, coll):
    A, B = Vector(a), Vector(b)
    mid = (A + B) / 2; L = (B - A).length
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=r * S, radius2=r * S, depth=L * S)
    for end in (-L / 2, L / 2):
        tmp = bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=r * S)
        bmesh.ops.translate(bm, vec=(0, 0, end * S), verts=tmp['verts'])
    # orient local +Z (blender) along the limb, expressed in three coordinates
    d3 = (B - A).normalized()
    dB = Vector((d3.x, -d3.z, d3.y))
    rot = dB.to_track_quat('Z', 'Y').to_matrix().to_4x4()
    return finish(bm, 'limb', MAT[mat], P @ Matrix.Translation(T(*mid)) @ rot, coll, smooth=True)

# ---------------------------------------------------------------- props
def chair(P, coll):
    rbox(48, 7, 46, 3, 'chairMesh', 0, 47, 0, P, coll=coll)
    rbox(46, 48, 6, 3, 'chairMesh', 0, 82, 24, P, rx=.12, coll=coll)
    rbox(5, 28, 3, 1.5, 'chair', 0, 60, 24, P, coll=coll)
    for s in (-1, 1):
        rbox(3, 15, 3, 1, 'chair', s * 24, 57, 4, P, coll=coll)
        rbox(5.5, 3, 26, 1.3, 'chair', s * 24, 65.5, 2, P, coll=coll)
    cyl(2.2, 2.2, 36, 'metal', 0, 26, 0, P, seg=12, coll=coll)
    for i in range(5):
        a = i / 5 * math.tau + .3
        rbox(27, 3, 4, 1.2, 'chair', math.cos(a) * 13, 6, -math.sin(a) * 13, P, ry=a, coll=coll)
        sphere(3, 'chair', math.cos(a) * 26, 3, -math.sin(a) * 26, P, coll=coll)

def worker(P):
    c = coll_extra
    for s in (-1, 1):
        limb((s * 9, 56, 3), (s * 9, 57, -36), 6.6, 'suit', P, c)
        limb((s * 9, 56, -37), (s * 9.5, 10, -41), 5.6, 'suit', P, c)
        rbox(10, 6, 22, 2.5, 'suit', s * 9.5, 3, -46, P, coll=c)
        limb((s * 18, 98, 5), (s * 21, 79, -12), 5, 'suit', P, c)
        limb((s * 21, 79, -12), (s * 8, 80, -43), 4.3, 'suit', P, c)
        sphere(3.8, 'skin', s * 8, 80, -45, P, coll=c)
    rbox(34, 46, 20, 7, 'suit', 0, 81, 5, P, rx=-.1, coll=c)
    cyl(4.2, 4.6, 7, 'skin', 0, 106, 3, P, coll=c)
    sphere(9.5, 'skin', 0, 117, 2, P, scale=(.92, 1.05, 1), coll=c)

def station(i, active):
    Q = Rz(i * math.pi / 2)
    rbox(170, 112, 4, 1.5, 'part', 85, 60, 0, Q)
    rbox(172, 3.2, 5.5, 1.4, 'trim', 85.5, 117.6, 0, Q)
    rbox(3.2, 117, 5.5, 1.4, 'trim', 171, 58.5, 0, Q)
    rbox(4, 4, 34, 1.5, 'trim', 150, 2, 0, Q); rbox(4, 4, 34, 1.5, 'trim', 40, 2, 0, Q)
    rbox(140, 3.6, 72, 1.6, 'desk', 90, 73.2, 40, Q)
    # drawer pedestal on a recessed plinth
    rbox(42, 66, 66, 2.5, 'desk', 138, 38, 40, Q)
    rbox(38, 5, 60, 1, 'metal', 138, 2.5, 40, Q)
    for y in (52, 30): rbox(38, .7, .7, .3, 'deskEdge', 138, y, 73.2, Q)
    # metal sled leg: foot bar, two posts, top rail, glides
    rbox(6, 3, 70, 1.2, 'leg', 24, 2.5, 40, Q)
    for z in (9, 71):
        rbox(5, 66, 5, 1.2, 'leg', 24, 37, z, Q)
        cyl(1.8, 2.2, 1, 'chair', 24, .5, z, Q, seg=12)
    rbox(5, 3.4, 66, 1.2, 'leg', 24, 69.7, 40, Q)
    # back beam tying the leg to the pedestal
    rbox(92, 4, 2.5, 1, 'leg', 70.5, 64, 8, Q)
    C = Q @ Matrix.Translation(T(100, 75, 34))
    rbox(22, 3, 22, 1.2, 'crtDark', 0, 1.5, -4, C)
    rbox(38, 32, 34, 4.5, 'crt', 0, 19, 0, C)
    rbox(30, 24, 14, 4.5, 'crtDark', 0, 18, -21, C)
    for k in range(5): rbox(.6, 1.2, 16, .3, 'crtDark', 19.1, 24 - k * 3, -4, C)
    rbox(33.6, 26.2, 1.4, 1.4, 'crtDark', 0, 19.5, 17.1, C)
    cyl(1.2, 1.2, 1.4, 'crtDark', 14, 5.5, 17.4, C, rx=math.pi / 2)
    sphere(.55, 'ledOn' if active else 'ledOff', 10.5, 5.5, 17.6, C)
    plane(30, 22.5, 'screenOn' if active else 'glass', 0, 19.5, 17.85, C, coll=coll_bake if EMPTY else coll_extra, name='screen')
    K = Q @ Matrix.Translation(T(96, 75, 62))
    rbox(43, 1.8, 15, .8, 'kbBase', 0, .9, 0, K)
    rbox(40, 1.2, 12, .4, 'kbBase', 0, 2.2, 0, K, coll=coll_bake if EMPTY else coll_extra)   # stand-in for the animated keys
    sphere(1, 'kbBase', 126, 76.2, 62, Q, scale=(3, 1.3, 4.6))
    if active:
        chair(Q @ Matrix.Translation(T(112, 0, 126)) @ Rz(.45), coll_active)
    else:
        P = Q @ Matrix.Translation(T(96, 0, 108))
        chair(P, coll_bake)
        CHAIRS.append(P)

CHAIRS = []
for i in range(4): station(i, i == 0 and not EMPTY)

# real (MakeHuman) coworkers as shadow casters, posed exactly as in workers.glb
WORKERS_GLB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'workers_out', 'workers.glb')
if EMPTY:
    log('empty cluster: no workers')
elif os.path.exists(WORKERS_GLB):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=WORKERS_GLB)
    new = [o for o in bpy.data.objects if o not in before]
    # the glTF importer adds icospheres as bone display shapes; they must not cast shadows
    for o in list(new):
        if o.type == 'ARMATURE':
            for pb in o.pose.bones: pb.custom_shape = None
    for o in list(new):
        if o.type == 'MESH' and o.parent is None:
            new.remove(o); bpy.data.objects.remove(o, do_unlink=True)
    for o in new:
        for c in o.users_collection: c.objects.unlink(o)
        coll_extra.objects.link(o)
    scene.frame_set(1)
    for j, P in enumerate(CHAIRS):
        root = bpy.data.objects.get(f'Worker{j}')
        act = bpy.data.actions.get(f'Worker{j}_typing')
        if root and act:
            root.animation_data_create().action = act      # seated pose lives in the action
        if root: root.matrix_world = P @ root.matrix_world
    scene.frame_set(1)
    log('imported', len(new), 'worker objects as casters')
else:
    log('workers.glb not found, falling back to capsule casters')
    for P in CHAIRS: worker(P)
log('geometry built:', len(coll_bake.objects), 'bake objs,', len(coll_active.objects), 'active chair objs,', len(coll_extra.objects), 'casters')

# floor (8 m square) — its lighting is baked separately as a multiply overlay
bm = bmesh.new()
half = 4.0
vs = [bm.verts.new((x, y, 0)) for x, y in ((-half, -half), (half, -half), (half, half), (-half, half))]
f = bm.faces.new(vs)
uv = bm.loops.layers.uv.new('UVMap')
for loop in f.loops:
    co = loop.vert.co; loop[uv].uv = ((co.x + half) / (2 * half), (co.y + half) / (2 * half))
me = bpy.data.meshes.new('FloorShade'); bm.to_mesh(me); bm.free(); me.materials.append(MAT['floor'])
floor = bpy.data.objects.new('FloorShade', me); scene.collection.objects.link(floor)

# ---------------------------------------------------------------- lights
sun_data = bpy.data.lights.new('sun', 'SUN'); sun_data.energy = 2.4; sun_data.angle = math.radians(9)
sun_data.color = (1.0, .97, .92)
sun = bpy.data.objects.new('sun', sun_data); scene.collection.objects.link(sun)
d = -T(-320, 720, 260).normalized()
sun.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
world = bpy.data.worlds.new('world'); world.use_nodes = True; scene.world = world
bg = world.node_tree.nodes['Background']; bg.inputs['Color'].default_value = (.82, .9, .86, 1); bg.inputs['Strength'].default_value = .5

# ---------------------------------------------------------------- helpers for operators
def select_only(objs, active=None):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = active or objs[0]

def apply_and_join(objs, name):
    select_only(objs)
    bpy.ops.object.convert(target='MESH')
    select_only(objs)
    bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active; ob.name = name; ob.data.name = name
    return ob

office = apply_and_join(list(coll_bake.objects), 'Office')
achair = apply_and_join(list(coll_active.objects), 'ActiveChair') if coll_active.objects else None
baked = [o for o in (office, achair) if o]
log('joined: office tris ~', sum(len(p.vertices) - 2 for p in office.data.polygons),
    'chair tris ~', sum(len(p.vertices) - 2 for p in achair.data.polygons) if achair else 0)

# shared UV atlas for both
select_only(baked)
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.003, area_weight=0.0, scale_to_bounds=False)
bpy.ops.uv.pack_islands(margin=0.003, rotate=True)
bpy.ops.object.mode_set(mode='OBJECT')
log('uv unwrapped')

def bake_into(objs, img, pass_color):
    for ob in objs:
        for slot in ob.material_slots:
            nt = slot.material.node_tree
            node = nt.nodes.get('BAKE_TARGET') or nt.nodes.new('ShaderNodeTexImage')
            node.name = 'BAKE_TARGET'; node.image = img
            nt.nodes.active = node
    select_only(objs)
    bk = scene.render.bake
    bk.use_pass_direct = True; bk.use_pass_indirect = True; bk.use_pass_color = pass_color
    bk.margin = 16; bk.margin_type = 'EXTEND'
    bpy.ops.object.bake(type='DIFFUSE')

def export_mat(name, path, noncolor=False):
    img = bpy.data.images.load(path)
    if noncolor: img.colorspace_settings.name = 'Non-Color'
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; bsdf = nt.nodes['Principled BSDF']
    tex = nt.nodes.new('ShaderNodeTexImage'); tex.image = img
    nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 1.0
    return m

# ---- objects atlas
atlas = bpy.data.images.new('office_bake', ATLAS, ATLAS, alpha=False)
bake_into(baked, atlas, True)
log('office baked')

if EMPTY:
    scene.render.image_settings.file_format = 'JPEG'; scene.render.image_settings.quality = 82
    scene.render.image_settings.color_mode = 'RGB'
    path = os.path.join(OUT, 'cluster_bake.jpg'); atlas.save_render(path, scene=scene)
    office.name = office.data.name = 'Cluster'
    office.data.materials.clear(); office.data.materials.append(export_mat('BakedCluster', path))
    select_only([office])
    glb = os.path.join(OUT, 'cluster.glb')
    bpy.ops.export_scene.gltf(filepath=glb, export_format='GLB', use_selection=True, export_apply=True,
                              export_yup=True, export_image_format='JPEG', export_jpeg_quality=82,
                              export_normals=False, export_tangents=False, export_materials='EXPORT')
    log('exported', glb, round(os.path.getsize(glb) / 1e6, 2), 'MB')
    sys.exit(0)

# ---- floor lighting (irradiance only), normalised so open floor = 1, faded to 1 at the edges
fimg = bpy.data.images.new('floor_bake', FLOOR_PX, FLOOR_PX, alpha=False, float_buffer=True)
fimg.colorspace_settings.name = 'Non-Color'
bake_into([floor], fimg, False)
px = np.empty(FLOOR_PX * FLOOR_PX * 4, dtype=np.float32); fimg.pixels.foreach_get(px)
px = px.reshape(FLOOR_PX, FLOOR_PX, 4)
lum = px[..., :3].mean(axis=2)
ring = np.concatenate([lum[:80].ravel(), lum[-80:].ravel(), lum[:, :80].ravel(), lum[:, -80:].ravel()])
ref = float(np.median(ring))
v = np.clip(px[..., :3] / max(ref, 1e-4), 0, 1)
yy, xx = np.mgrid[0:FLOOR_PX, 0:FLOOR_PX] / (FLOOR_PX - 1)
edge = np.minimum.reduce([xx, 1 - xx, yy, 1 - yy])
mask = np.clip((edge - 0.02) / 0.18, 0, 1); mask = mask * mask * (3 - 2 * mask)
v = 1 - (1 - v) * mask[..., None]
out = np.ones_like(px); out[..., :3] = v
fimg.pixels.foreach_set(out.ravel())
log('floor baked, open-floor reference', round(ref, 3), 'darkest', round(float(v.min()), 3))

# ---------------------------------------------------------------- save textures + swap to export materials
scene.render.image_settings.file_format = 'JPEG'; scene.render.image_settings.quality = 88
scene.render.image_settings.color_mode = 'RGB'
atlas_path = os.path.join(OUT, 'office_bake.jpg'); atlas.save_render(atlas_path, scene=scene)
floor_png = bpy.data.images.new('floor_out', FLOOR_PX, FLOOR_PX, alpha=False)
floor_png.colorspace_settings.name = 'Non-Color'
floor_png.pixels.foreach_set(out.ravel())
floor_path = os.path.join(OUT, 'floor_bake.jpg'); floor_png.save_render(floor_path, scene=scene)
log('textures saved')

m_office = export_mat('BakedOffice', atlas_path)
m_floor = export_mat('BakedFloor', floor_path)
for ob, m in ((office, m_office), (achair, m_office), (floor, m_floor)):
    ob.data.materials.clear(); ob.data.materials.append(m)

select_only([office, achair, floor])
glb = os.path.join(OUT, 'office.glb')
bpy.ops.export_scene.gltf(filepath=glb, export_format='GLB', use_selection=True, export_apply=True,
                          export_yup=True, export_image_format='JPEG', export_jpeg_quality=88,
                          export_normals=False, export_tangents=False, export_materials='EXPORT')
log('exported', glb, round(os.path.getsize(glb) / 1e6, 2), 'MB')
