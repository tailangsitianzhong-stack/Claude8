"""Face look-dev pass on a saved character .blend: tighter skin SSS (so the
sculpted bone/muscle forms read) + a sculpting key light, then re-render the
three face views and re-save the file.

  blender -b <file.blend> --python face_lookdev_pass.py -- --out <dir> [--samples 64] [--save]
"""
import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_views as RV  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda n, d=None: ARGS[ARGS.index(n) + 1] if n in ARGS else d
out = arg("--out", "/tmp"); os.makedirs(out, exist_ok=True)
sc = bpy.context.scene
sc.cycles.samples = int(arg("--samples", "64"))

# --- skin: shorter scattering distance keeps cheekbone/jaw planes crisp
skin = bpy.data.materials["M_Skin"]
b = next(n for n in skin.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
b.inputs["Subsurface Scale"].default_value = 0.0018
b.inputs["Subsurface Weight"].default_value = 0.85

# --- a face key light: 3/4 high (classic portrait 'Rembrandt'-style) + keep rims
fk = bpy.data.lights.new("REV_FaceKey", "AREA"); fk.energy = 55; fk.size = 0.6; fk.color = (1.0, 0.95, 0.88)
fko = bpy.data.objects.new("REV_FaceKey", fk); sc.collection.objects.link(fko)
eL = bpy.data.objects["SAM_Eye_L"].location
face_c = Vector((0, eL.y + 0.04, eL.z - 0.02))
fko.location = face_c + Vector((-0.9, -0.9, 0.75))
fko.rotation_euler = (face_c - fko.location).to_track_quat("-Z", "Y").to_euler()
for name, k in (("REV_Key", 0.45), ("REV_Fill", 0.8)):
    o = bpy.data.objects.get(name)
    if o:
        o.data.energy *= k

# --- nails: tighter shading region and less gloss (geometry carries the plate edge)
body = bpy.data.objects["SAM_Body"]
na = body.data.attributes.get("NailMask")
if na and "--nonails" not in ARGS:
    for d in na.data:
        d.value = max(0.0, min(1.0, (d.value - 0.55) * 2.5))
for n in skin.node_tree.nodes:
    if n.type == "MIX" and n.data_type == "FLOAT" and abs(n.inputs[3].default_value - 0.18) < 1e-4:
        n.inputs[3].default_value = 0.32

RV.render_all(out, height=1.69, face_z=eL.z - 0.01, views=["face", "face_side", "face_45"])
if "--hands" in ARGS:
    for name, k in (("REV_Key", 0.45), ("REV_Fill", 0.8)):
        o = bpy.data.objects.get(name)
        if o:
            o.data.energy /= k
    fko.hide_render = True
    J = {o.name.replace("J_", "joint-"): o.location.copy() for o in bpy.data.objects if o.name.startswith("J_")}
    RV.render_closeups(out, J, views=["hand_dorsal", "hand_palm", "foot_medial"])
    fko.hide_render = False
    for name, k in (("REV_Key", 0.45), ("REV_Fill", 0.8)):
        o = bpy.data.objects.get(name)
        if o:
            o.data.energy *= k

# keep the face key in the saved review scene but restore body-light levels
for name, k in (("REV_Key", 0.45), ("REV_Fill", 0.8)):
    o = bpy.data.objects.get(name)
    if o:
        o.data.energy /= k
if "--save" in ARGS:
    rev = bpy.data.collections.get("REV_Review_Scene")
    if rev:
        for c in fko.users_collection:
            c.objects.unlink(fko)
        rev.objects.link(fko)
    bpy.ops.wm.save_mainfile(compress=True)
