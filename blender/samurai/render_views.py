"""Review renders (front / side / back / 3-4 / face) for the samurai character.

Usage inside a build script:  render_views.setup_scene(); render_views.render_all(OUT, ...)
"""
import math
import os

import bpy
from mathutils import Vector


def setup_scene(samples=64, res=(1200, 1600)):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    world = bpy.data.worlds.new("World") if not sc.world else sc.world
    sc.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.32, 0.33, 0.35, 1)
    bg.inputs["Strength"].default_value = 0.25
    # backdrop: floor + back wall (neutral grey)
    m = bpy.data.materials.new("REV_Backdrop"); m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.11, 0.11, 0.12, 1)
    m.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
    bpy.ops.mesh.primitive_plane_add(size=14, location=(0, 0, 0))
    bpy.context.object.name = "REV_Floor"; bpy.context.object.data.materials.append(m)
    bpy.ops.mesh.primitive_plane_add(size=14, location=(0, 4.0, 7), rotation=(math.radians(90), 0, 0))
    bpy.context.object.name = "REV_Wall"; bpy.context.object.data.materials.append(m)
    # lights: key (front-left high), fill (front-right), rim (back), all area lights
    def area(name, loc, energy, size, color=(1, 1, 1)):
        ld = bpy.data.lights.new(name, "AREA"); ld.energy = energy; ld.size = size; ld.color = color
        ob = bpy.data.objects.new(name, ld); bpy.context.collection.objects.link(ob)
        ob.location = loc
        d = Vector((0, 0, 1.2)) - Vector(loc)
        ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        return ob
    area("REV_Key", (-3.0, -1.6, 2.5), 300, 1.4, (1.0, 0.95, 0.88))
    area("REV_Fill", (2.4, -2.6, 1.5), 45, 3.0, (0.85, 0.92, 1.0))
    area("REV_Rim_L", (-2.0, 2.4, 2.2), 220, 1.2)
    area("REV_Rim_R", (2.0, 2.4, 2.2), 160, 1.2)


def _camera(name, loc, target, lens=85, ortho=None):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    if ortho:
        cd.type = "ORTHO"; cd.ortho_scale = ortho
    ob = bpy.data.objects.new(name, cd); bpy.context.collection.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return ob


def render_all(out, height=1.69, face_z=1.58, prefix="", views=None):
    sc = bpy.context.scene
    mid = height * 0.53
    dist = 5.6
    cams = {
        "front": ((0, -dist, mid), (0, 0, mid), 85),
        "side": ((dist, 0, mid), (0, 0, mid), 85),
        "back": ((0, dist, mid), (0, 0, mid), 85),
        "three_quarter": ((-dist * 0.707, -dist * 0.707, mid), (0, 0, mid), 85),
        "face": ((-0.25, -0.95, face_z + 0.02), (0, 0, face_z - 0.01), 100),
        "face_side": ((0.98, -0.12, face_z + 0.02), (0, 0, face_z - 0.01), 100),
        "face_45": ((-0.70, -0.70, face_z + 0.02), (0, -0.02, face_z - 0.01), 100),
    }
    res_full = (sc.render.resolution_x, sc.render.resolution_y)
    for name, (loc, tgt, lens) in cams.items():
        if views and name not in views:
            continue
        cam = _camera("REV_Cam_" + name, loc, tgt, lens)
        sc.camera = cam
        _rig_facing("back" in name)
        if name.startswith("face"):
            sc.render.resolution_x, sc.render.resolution_y = 1400, 1400
        else:
            sc.render.resolution_x, sc.render.resolution_y = res_full
        sc.render.filepath = os.path.join(out, f"{prefix}{name}.png")
        bpy.ops.render.render(write_still=True)
    sc.render.resolution_x, sc.render.resolution_y = res_full


def render_closeups(out, joints, views=None):
    """Hand, foot and torso close-ups framed from the anatomical joint centres."""
    sc = bpy.context.scene
    full = (sc.render.resolution_x, sc.render.resolution_y)
    J = joints
    hand = (J["joint-l-hand"] + J["joint-l-finger-3-2"]) / 2
    foot = (J["joint-l-ankle"] + J["joint-l-foot-1"]) / 2 + Vector((0, 0, -0.02))
    chest_z = (J["joint-l-shoulder"].z + J["joint-pelvis"].z) / 2
    shots = {
        "hand_dorsal": (hand + Vector((0.25, -0.35, 0.30)), hand, 100, (1400, 1400)),
        "hand_palm": (hand + Vector((-0.10, -0.45, -0.10)), hand, 100, (1400, 1400)),
        "foot": (foot + Vector((0.30, -0.45, 0.22)), foot, 100, (1400, 1000)),
        "foot_medial": (foot + Vector((-0.36, -0.78, 0.07)), foot + Vector((0, 0.02, 0.01)), 85, (1400, 1000)),
        "torso_front": (Vector((0, -2.4, chest_z + 0.05)), Vector((0, 0, chest_z)), 85, (1200, 1400)),
        "torso_back": (Vector((0, 2.4, chest_z + 0.05)), Vector((0, 0, chest_z)), 85, (1200, 1400)),
    }
    for name, (loc, tgt, lens, res) in shots.items():
        if views and name not in views and "closeups" not in views:
            continue
        cam = _camera("REV_Cam_" + name, loc, tgt, lens)
        sc.camera = cam
        _rig_facing("back" in name)
        sc.render.resolution_x, sc.render.resolution_y = res
        sc.render.filepath = os.path.join(out, f"{name}.png")
        bpy.ops.render.render(write_still=True)
    sc.render.resolution_x, sc.render.resolution_y = full
    _rig_facing(False)


def _rig_facing(back):
    """Rotate the review light rig 180 deg about Z so back views are lit like front views."""
    import math as _m
    for ob in bpy.data.objects:
        if (ob.type == "LIGHT" and ob.name.startswith("REV_")) or ob.name == "REV_Wall":
            want = 1 if back else 0
            have = ob.get("rev_flipped", 0)
            if want != have:
                ob.location.x, ob.location.y = -ob.location.x, -ob.location.y
                ob.rotation_euler.z += _m.pi
                ob["rev_flipped"] = want
