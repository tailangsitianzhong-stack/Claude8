"""Re-render review views from a saved character .blend (no rebuild).

  blender -b <file.blend> --python rerender_views.py -- --out <dir> [--views front,side,back,three_quarter] [--samples 96] [--dist 6.0]
"""
import os
import sys

import bpy
from mathutils import Vector

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return ARGS[ARGS.index(n) + 1] if n in ARGS else d


out = arg("--out", "/tmp")
views = arg("--views", "front,side,back,three_quarter").split(",")
sc = bpy.context.scene
sc.cycles.samples = int(arg("--samples", "96"))
dist = float(arg("--dist", "6.0"))

# keep the back wall far enough behind every camera position
wall = bpy.data.objects.get("REV_Wall")
floor = bpy.data.objects.get("REV_Floor")
if floor:
    floor.scale = (2.2, 2.2, 1)

body = bpy.data.objects["SAM_Body"]
H = max((body.matrix_world @ v.co).z for v in body.data.vertices)
mid = H * 0.53
cams = {
    "front": (0, -1), "side": (1, 0), "back": (0, 1), "three_quarter": (-0.7071, -0.7071),
}
for name in views:
    dx, dy = cams[name]
    loc = Vector((dx * dist, dy * dist, mid))
    # the wall always sits behind the subject as seen from this camera
    if wall:
        wall.location = Vector((-dx * 6.0, -dy * 6.0, 7.0))
        wall.rotation_euler = (Vector((dx, dy, 0))).to_track_quat("Z", "Y").to_euler()
    cd = bpy.data.cameras.new("REV_Cam2_" + name); cd.lens = 85
    cam = bpy.data.objects.new("REV_Cam2_" + name, cd)
    sc.collection.objects.link(cam)
    cam.location = loc
    cam.rotation_euler = (Vector((0, 0, mid)) - loc).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y = 1200, 1600
    sc.render.filepath = os.path.join(out, f"{name}.png")
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam)

# restore the wall for the saved review scene (behind the front camera)
if wall:
    wall.location = Vector((0, 6.0, 7.0))
    wall.rotation_euler = Vector((0, -1, 0)).to_track_quat("Z", "Y").to_euler()
