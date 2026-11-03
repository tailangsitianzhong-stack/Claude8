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
    mid = height * 0.52
    dist = 7.5
    cams = {
        "front": ((0, -dist, mid), (0, 0, mid), 85),
        "side": ((dist, 0, mid), (0, 0, mid), 85),
        "back": ((0, dist, mid), (0, 0, mid), 85),
        "three_quarter": ((-dist * 0.707, -dist * 0.707, mid), (0, 0, mid), 85),
        "face": ((-0.25, -0.95, face_z + 0.02), (0, 0, face_z - 0.01), 100),
        "face_side": ((0.98, -0.12, face_z + 0.02), (0, 0, face_z - 0.01), 100),
    }
    res_full = (sc.render.resolution_x, sc.render.resolution_y)
    for name, (loc, tgt, lens) in cams.items():
        if views and name not in views:
            continue
        cam = _camera("REV_Cam_" + name, loc, tgt, lens)
        sc.camera = cam
        if name.startswith("face"):
            sc.render.resolution_x, sc.render.resolution_y = 1400, 1400
        else:
            sc.render.resolution_x, sc.render.resolution_y = res_full
        sc.render.filepath = os.path.join(out, f"{prefix}{name}.png")
        bpy.ops.render.render(write_still=True)
    sc.render.resolution_x, sc.render.resolution_y = res_full
