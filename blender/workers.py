"""Make seated, suited MakeHuman (MPFB) office workers.

Run:  Blender -b -P workers.py -- <out_dir> preview     -> renders preview.png of one worker
      Blender -b -P workers.py -- <out_dir> export      -> exports workers.glb (3 workers, typing loop)
"""
import bpy, math, os, sys, time
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index('--') + 1:]
OUT, MODE = argv[0], (argv[1] if len(argv) > 1 else 'preview')
os.makedirs(OUT, exist_ok=True)
t0 = time.time()
def log(*a): print(f'[{time.time() - t0:6.1f}s]', *a, flush=True)

import addon_utils
addon_utils.enable('bl_ext.user_default.mpfb', default_set=True)
from bl_ext.user_default.mpfb.services.humanservice import HumanService
from bl_ext.user_default.mpfb.services.assetservice import AssetService
from bl_ext.user_default.mpfb.services.targetservice import TargetService

bpy.ops.wm.read_factory_settings(use_empty=True)
import addon_utils as _au; _au.enable('bl_ext.user_default.mpfb', default_set=True)
scene = bpy.context.scene

def asset(path, sub):
    p = AssetService.find_asset_absolute_path(path, sub)
    if not p: raise FileNotFoundError(f'{sub}/{path}')
    return p

# one look per coworker: skin, hair, suit, shoes, eyebrows, body
LOOKS = [
    dict(skin='young_caucasian_male/young_caucasian_male.mhmat', hair='short02/short02.mhclo', suit='male_elegantsuit01/male_elegantsuit01.mhclo',
         shoes='shoes01/shoes01.mhclo', brows='eyebrow001/eyebrow001.mhclo', age=.45, weight=.5, muscle=.5, height=.55, race=(.1, .85, .05)),
    dict(skin='middleage_caucasian_male/middleage_caucasian_male.mhmat', hair='short04/short04.mhclo', suit='male_elegantsuit01/male_elegantsuit01.mhclo',
         shoes='shoes01/shoes01.mhclo', brows='eyebrow007/eyebrow007.mhclo', age=.62, weight=.62, muscle=.45, height=.5, race=(.05, .9, .05)),
    dict(skin='young_asian_male/young_asian_male.mhmat', hair='short01/short01.mhclo', suit='male_elegantsuit01/male_elegantsuit01.mhclo',
         shoes='shoes01/shoes01.mhclo', brows='eyebrow003/eyebrow003.mhclo', age=.4, weight=.45, muscle=.5, height=.48, race=(.8, .15, .05)),
]

def make_worker(look, name):
    macro = TargetService.get_default_macro_info_dict()
    macro.update(gender=1.0, age=look['age'], weight=look['weight'], muscle=look['muscle'], height=look['height'], proportions=.6)
    a, c, f = look['race']; macro['race'] = {'asian': a, 'caucasian': c, 'african': f}
    body = HumanService.create_human(macro_detail_dict=macro, feet_on_ground=True, scale=0.1)
    rig = HumanService.add_builtin_rig(body, 'game_engine')
    HumanService.set_character_skin(asset(look['skin'], 'skins'), body, skin_type='MAKESKIN')
    for path, sub, kind in ((('low-poly/low-poly.mhclo'), 'eyes', 'Eyes'), (look['brows'], 'eyebrows', 'Eyebrows'),
                            (look['hair'], 'hair', 'Hair'), (look['suit'], 'clothes', 'Clothes'), (look['shoes'], 'clothes', 'Clothes')):
        HumanService.add_mhclo_asset(asset(path, sub), body, asset_type=kind, subdiv_levels=0, material_type='MAKESKIN')
    rig.name = name
    return rig, body

# ---- pose by aiming bones (directions in armature space: the human faces -Y, +X is their left)
AIM = {
    'spine_01': (0, -.04, 1), 'spine_02': (0, -.06, 1), 'spine_03': (0, -.09, 1),
    'neck_01': (0, -.25, 1), 'head': (0, -.35, 1),
    'thigh_l': (.06, -1, -.04), 'thigh_r': (-.06, -1, -.04),
    'calf_l': (0, .12, -1), 'calf_r': (0, .12, -1),
    'foot_l': (0, -.85, -.45), 'foot_r': (0, -.85, -.45),
}
ORDER = ['spine_01', 'spine_02', 'spine_03', 'neck_01', 'head', 'thigh_l', 'thigh_r', 'calf_l', 'calf_r', 'foot_l', 'foot_r']

def aim(rig, overrides=None):
    aims = dict(AIM, **(overrides or {}))
    bpy.context.view_layer.objects.active = rig
    for pb in rig.pose.bones: pb.rotation_mode = 'QUATERNION'   # keep one rotation mode so later keyframes don't drop the pose
    for bname in ORDER:
        pb = rig.pose.bones.get(bname)
        if not pb: log('missing bone', bname); continue
        bpy.context.view_layer.update()
        m = pb.matrix.copy()
        cur = m.col[1].xyz.normalized(); tgt = Vector(aims[bname]).normalized()
        q = cur.rotation_difference(tgt)
        head = m.translation.copy()
        pb.matrix = Matrix.Translation(head) @ q.to_matrix().to_4x4() @ Matrix.Translation(-head) @ m
    bpy.context.view_layer.update()

# ---- hands on the keyboard. Keyboard keys in chair space: y 77.7 cm (top), z -46 cm, rows +-4 cm
FINGERS = {'index': -.07, 'middle': 0.0, 'ring': .07, 'pinky': .15}     # sideways fan
CURL = (16, 40, 60)                                                     # cumulative bend per phalanx, degrees
TIP_TARGET = Vector((.095, -.47, .79))                                  # middle fingertip, +X is the left hand

def set_dir(pb, tgt):
    bpy.context.view_layer.update()
    m = pb.matrix.copy()
    q = m.col[1].xyz.normalized().rotation_difference(tgt.normalized())
    head = m.translation.copy()
    pb.matrix = Matrix.Translation(head) @ q.to_matrix().to_4x4() @ Matrix.Translation(-head) @ m

def roll(pb, angle):
    bpy.context.view_layer.update()
    m = pb.matrix.copy()
    head = m.translation.copy()
    pb.matrix = Matrix.Translation(head) @ Matrix.Rotation(angle, 4, m.col[1].xyz.normalized()) @ Matrix.Translation(-head) @ m

def hand_roll_error(rig, side, sx):
    """Signed angle that turns the knuckle line (index -> pinky) to level, palm down."""
    bpy.context.view_layer.update()
    b = rig.pose.bones
    axis = b[f'hand_{side}'].matrix.col[1].xyz.normalized()
    have = b[f'pinky_01_{side}'].head - b[f'index_01_{side}'].head
    want = Vector((sx, 0, -.18))
    have = (have - axis * have.dot(axis)).normalized()
    want = (want - axis * want.dot(axis)).normalized()
    return math.atan2(have.cross(want).dot(axis), have.dot(want))

def reach(rig):
    """Two-bone IK from the shoulder, then palm-down hands with curled fingers resting on the home row."""
    b = rig.pose.bones
    to_rig = rig.matrix_world.inverted()
    for side, sx in (('l', 1.0), ('r', -1.0)):
        tip = to_rig @ Vector((sx * TIP_TARGET.x, TIP_TARGET.y, TIP_TARGET.z))
        hand_dir = Vector((-sx * .10, -1, -.08)).normalized()
        wrist = tip - hand_dir * .17
        upper, lower = b[f'upperarm_{side}'], b[f'lowerarm_{side}']
        L1, L2 = upper.length, lower.length
        for _ in range(6):
            bpy.context.view_layer.update()
            S = upper.head.copy()
            d = min((wrist - S).length, (L1 + L2) * .995)
            D = (wrist - S).normalized()
            pole = Vector((sx * .38, .55, -1))
            P = (pole - D * pole.dot(D)).normalized()
            along = (L1 * L1 - L2 * L2 + d * d) / (2 * d)
            elbow = S + D * along + P * math.sqrt(max(L1 * L1 - along * along, 0))
            set_dir(upper, elbow - S)
            bpy.context.view_layer.update()
            set_dir(lower, wrist - lower.head)
            set_dir(b[f'hand_{side}'], hand_dir)
            # share the pronation between forearm and wrist so neither one wrings the mesh
            roll(lower, hand_roll_error(rig, side, sx) * .55)
            set_dir(b[f'hand_{side}'], hand_dir)
            roll(b[f'hand_{side}'], hand_roll_error(rig, side, sx))
            bpy.context.view_layer.update()
            lateral = Vector((sx, 0, 0)) - hand_dir * sx * hand_dir.x
            lateral.normalize()
            down = lateral.cross(hand_dir).normalized()
            if down.z > 0: down = -down
            for f, fan in FINGERS.items():
                base = (hand_dir + lateral * fan).normalized()
                for i, deg in enumerate(CURL):
                    a = math.radians(deg)
                    set_dir(b[f'{f}_0{i + 1}_{side}'], base * math.cos(a) + down * math.sin(a))
            for i, v in enumerate(((-sx * .55, -.8, -.25), (-sx * .35, -.9, -.3), (-sx * .2, -.9, -.4))):
                set_dir(b[f'thumb_0{i + 1}_{side}'], Vector(v))
            bpy.context.view_layer.update()
            wrist += tip - b[f'middle_03_{side}'].tail
    bpy.context.view_layer.update()
    for side in 'lr':
        t = rig.matrix_world @ b[f'middle_03_{side}'].tail
        log(rig.name, side, 'middle tip cm', [round(v * 100, 1) for v in t])

def seat(rig, seat_height=.505):
    """Move the rig so the pelvis sits on the chair seat."""
    bpy.context.view_layer.update()
    pel = rig.matrix_world @ rig.pose.bones['pelvis'].head
    thigh = rig.matrix_world @ rig.pose.bones['thigh_l'].head
    rig.location.z += seat_height + .06 - min(pel.z, thigh.z)
    bpy.context.view_layer.update()

def finger_press(rig, name, deg):
    """Local quaternion of a finger bone bent further down by deg."""
    pb = rig.pose.bones[name]
    d = pb.matrix.col[1].xyz.normalized()
    axis = d.cross(Vector((0, 0, -1)))
    if axis.cross(d).z > 0: axis = -axis
    local = (pb.matrix.to_3x3().inverted() @ axis).normalized()
    return pb.rotation_quaternion @ Matrix.Rotation(math.radians(deg), 4, local).to_quaternion()

def typing_action(rig, phase=0.0):
    """One second loop: single fingers tap the keys, wrists drift, head moves a little; 24 frames."""
    bpy.context.view_layer.update()
    ad = rig.animation_data_create()
    act = bpy.data.actions.new(rig.name + '_typing'); ad.action = act
    rates = {'index': 4, 'middle': 3, 'ring': 2, 'pinky': 1}
    fingers = []
    for s, sp in (('l', 0.0), ('r', 2.1)):
        for k, (f, n) in enumerate(rates.items()):
            for joint, deg in (('01', 9), ('02', 5)):
                bone = f'{f}_{joint}_{s}'
                fingers.append((bone, n, sp + k * 1.9, rig.pose.bones[bone].rotation_quaternion.copy(), finger_press(rig, bone, deg)))
    base = {b: rig.pose.bones[b].rotation_quaternion.copy() for b in ('hand_l', 'hand_r', 'head')}
    for f in range(0, 25, 2):
        t = f / 24 * math.tau
        for bone, n, ph, q0, q1 in fingers:
            pb = rig.pose.bones[bone]
            pb.rotation_quaternion = q0.slerp(q1, max(0.0, math.sin(t * n + ph + phase)) ** 3)
            pb.keyframe_insert('rotation_quaternion', frame=f + 1)
        for side, ph in (('l', 0), ('r', 1.7)):
            pb = rig.pose.bones[f'hand_{side}']
            pb.rotation_quaternion = base[f'hand_{side}'] @ Matrix.Rotation(math.sin(t + ph + phase) * .018, 4, 'X').to_quaternion()
            pb.keyframe_insert('rotation_quaternion', frame=f + 1)
        pb = rig.pose.bones['head']
        pb.rotation_quaternion = base['head'] @ Matrix.Rotation(math.sin(t + phase) * .03, 4, 'Z').to_quaternion()
        pb.keyframe_insert('rotation_quaternion', frame=f + 1)
    for fc in act.fcurves:
        for kp in fc.keyframe_points: kp.interpolation = 'BEZIER'

if MODE == 'preview':
    rig, body = make_worker(LOOKS[0], 'Worker0')
    log('worker built; bones:', len(rig.pose.bones))
    aim(rig); seat(rig); reach(rig)
    # simple chair seat + desk for scale
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, .05, .48)); bpy.context.object.scale = (.48, .46, .07)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -.62, .73)); bpy.context.object.scale = (1.4, .72, .036)
    cam_data = bpy.data.cameras.new('cam'); cam = bpy.data.objects.new('cam', cam_data); scene.collection.objects.link(cam)
    cam.location = (1.6, -1.7, 1.45); cam.rotation_euler = (Vector((0, -.25, .8)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam_data.lens = 45; scene.camera = cam
    sun = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN')); scene.collection.objects.link(sun)
    sun.data.energy = 3; sun.data.angle = math.radians(8); sun.rotation_euler = (math.radians(40), 0, math.radians(-40))
    w = bpy.data.worlds.new('w'); w.use_nodes = True; scene.world = w
    w.node_tree.nodes['Background'].inputs['Color'].default_value = (.45, .62, .5, 1); w.node_tree.nodes['Background'].inputs['Strength'].default_value = .8
    scene.render.engine = 'CYCLES'; scene.cycles.samples = 48; scene.cycles.use_denoising = True
    try:
        p = bpy.context.preferences.addons['cycles'].preferences; p.compute_device_type = 'METAL'; p.get_devices()
        for d in p.devices: d.use = True
        scene.cycles.device = 'GPU'
    except Exception as e: log('cpu', e)
    scene.render.resolution_x, scene.render.resolution_y = 900, 900
    scene.render.filepath = os.path.join(OUT, 'preview.png')
    bpy.ops.render.render(write_still=True)
    log('preview rendered')

# ------------------------------------------------------------------ export
def simplify_materials(objs, max_px=1024):
    """MakeSkin node groups don't survive glTF; rebuild each as Principled + its diffuse texture (alpha kept)."""
    done = {}
    for ob in objs:
        if ob.type != 'MESH': continue
        for slot in ob.material_slots:
            m = slot.material
            if not m or m.name in done: 
                if m: slot.material = done[m.name]
                continue
            img = None
            for n in m.node_tree.nodes if m.use_nodes else []:
                if n.type == 'TEX_IMAGE' and n.image and ('diffuse' in n.image.name.lower() or img is None):
                    img = n.image
                if n.type == 'GROUP' and n.node_tree:
                    for gn in n.node_tree.nodes:
                        if gn.type == 'TEX_IMAGE' and gn.image and img is None: img = gn.image
            nm = bpy.data.materials.new('x_' + m.name); nm.use_nodes = True
            bsdf = nm.node_tree.nodes['Principled BSDF']
            low = m.name.lower()
            bsdf.inputs['Roughness'].default_value = .45 if 'shoe' in low else .55 if 'skin' in low or 'body' in low else .8
            if img:
                if max(img.size) > max_px: img.scale(max_px, max_px)
                tex = nm.node_tree.nodes.new('ShaderNodeTexImage'); tex.image = img
                nm.node_tree.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
                if any(k in low for k in ('hair', 'eyebrow', 'eyelash')):
                    nm.node_tree.links.new(tex.outputs['Alpha'], bsdf.inputs['Alpha'])
                    nm.blend_method = 'CLIP' if hasattr(nm, 'blend_method') else None
            done[m.name] = nm; slot.material = nm

if MODE == 'export':
    rigs = []
    for i, look in enumerate(LOOKS):
        rig, body = make_worker(look, f'Worker{i}')
        aim(rig); seat(rig); reach(rig)
        rig.rotation_euler.z = math.pi          # face blender +Y == three -Z (towards the desk)
        bpy.context.view_layer.update()
        typing_action(rig, phase=i * 1.3)
        rigs.append(rig)
        log('worker', i, 'ready')
    meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    simplify_materials(meshes)
    tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in meshes)
    log('meshes', len(meshes), 'tris ~', tris)
    # save a .blend copy too, so the office bake can reuse the posed workers as shadow casters
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, 'workers.blend'))
    # export only the workers: MPFB rigs use helper icospheres as bone display shapes,
    # which the glTF exporter would otherwise write out as real meshes
    widgets = set()
    for r in rigs:
        for pb in r.pose.bones:
            if pb.custom_shape: widgets.add(pb.custom_shape); pb.custom_shape = None
    for o in list(bpy.data.objects):
        if o in widgets or (o.type == 'MESH' and o.parent is None and o.name.startswith('Icosphere')):
            bpy.data.objects.remove(o, do_unlink=True)
    log('removed', len(widgets), 'bone widgets')
    bpy.ops.object.select_all(action='DESELECT')
    for r in rigs:
        r.select_set(True)
        for c in r.children_recursive: c.select_set(True)
    for o in bpy.data.objects:
        if o.type == 'MESH' and o.parent is None: log('skipping stray object', o.name)
    glb = os.path.join(OUT, 'workers.glb')
    bpy.ops.export_scene.gltf(filepath=glb, export_format='GLB', use_selection=True, export_apply=True, export_yup=True,
                              export_image_format='JPEG', export_jpeg_quality=85, export_skins=True,
                              export_animations=True, export_animation_mode='ACTIONS', export_force_sampling=True,
                              export_frame_range=False, export_materials='EXPORT')
    log('exported', glb, round(os.path.getsize(glb) / 1e6, 2), 'MB')
    # preview of all three, for a look
    for i, r in enumerate(rigs): r.location.x = (i - 1) * 1.0
    cam_data = bpy.data.cameras.new('cam'); cam = bpy.data.objects.new('cam', cam_data); scene.collection.objects.link(cam)
    cam.location = (0.4, 3.4, 1.7); cam.rotation_euler = (Vector((0, 0, .75)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam_data.lens = 35; scene.camera = cam
    sun = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN')); scene.collection.objects.link(sun)
    sun.data.energy = 3; sun.rotation_euler = (math.radians(40), 0, math.radians(150))
    w = bpy.data.worlds.new('w'); w.use_nodes = True; scene.world = w
    w.node_tree.nodes['Background'].inputs['Color'].default_value = (.45, .62, .5, 1)
    scene.render.engine = 'BLENDER_EEVEE_NEXT'; scene.render.resolution_x, scene.render.resolution_y = 1200, 600
    scene.frame_set(1); scene.render.filepath = os.path.join(OUT, 'workers_preview.png')
    bpy.ops.render.render(write_still=True); log('preview rendered')
