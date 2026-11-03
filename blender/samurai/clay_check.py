"""Quick clay check renders of a built character .blend (forms only, no hair).

  blender -b <file.blend> --python clay_check.py -- --out <dir> [--views torso_front,...] [--samples 16]
"""
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_views as RV  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
arg = lambda n, d=None: ARGS[ARGS.index(n) + 1] if n in ARGS else d
out = arg("--out", "/tmp"); os.makedirs(out, exist_ok=True)
views = arg("--views", "torso_front,torso_back,hand_dorsal,hand_palm,foot,foot_medial,face,face_side,face_45,front,side,back").split(",")
sc = bpy.context.scene
sc.cycles.samples = int(arg("--samples", "16"))
clay = bpy.data.materials.new("CLAY"); clay.use_nodes = True
p = clay.node_tree.nodes["Principled BSDF"]
p.inputs["Base Color"].default_value = (0.45, 0.42, 0.40, 1); p.inputs["Roughness"].default_value = 0.6
body = bpy.data.objects["SAM_Body"]; body.data.materials[0] = clay
for o in bpy.data.objects:
    if o.name.startswith("SAM_Hair") or o.name.startswith("SAM_Fundoshi") and "--keepcloth" not in ARGS:
        o.hide_render = True
J = {o.name.replace("J_", "joint-"): o.location.copy() for o in bpy.data.objects if o.name.startswith("J_")}
eL = bpy.data.objects["SAM_Eye_L"].location
RV.render_all(out, height=1.69, face_z=eL.z - 0.01, views=views)
RV.render_closeups(out, J, views=views)
