"""Samurai character - STEP 1-3: anatomical human body.

Builds an original Japanese male body from the CC0 MakeHuman base mesh and CC0
shape targets (no MPFB/MakeHuman program code is used), then applies this
project's own anatomical adjustments, eyes, teeth, materials and review renders.

Run:
  blender -b --factory-startup --python build_body.py -- \
      --data <path to makehuman 'data' dir> --out <dir> [--render] [--samples N]

License of inputs: base.obj and *.target.gz are CC0 1.0 (see
knowledge/08_character_build_notes.md). This script is project code.
"""
import gzip
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None):
    return ARGS[ARGS.index(name) + 1] if name in ARGS else default


DATA = arg("--data")
OUT = arg("--out", "/tmp/samurai_out")
SAMPLES = int(arg("--samples", "64"))
os.makedirs(OUT, exist_ok=True)

# ------------------------------------------------------------------ character design
# Macro values use MakeHuman's 0..1 slider conventions.
MACRO = dict(
    gender=1.0,        # male
    age=0.545,         # ~ 31 years (0.5 = 25 y, 1.0 = 90 y)
    muscle=0.74,       # trained swordsman: clearly muscular, not a bodybuilder
    weight=0.30,       # lean
    height=0.38,       # below MH average -> final stature set explicitly below
    proportions=0.75,  # natural adult proportions
    race=dict(asian=0.88, caucasian=0.12, african=0.0),
)
TARGET_HEIGHT_M = 1.69

# Detail targets: +value -> "<name>-incr/up/..." file, value given per file name.
# Values were chosen for a lean, sharp Japanese male face and a swordsman's build.
DETAILS = {
    # --- head shape
    "head/head-oval": 0.40, "head/head-square": 0.10, "head/head-invertedtriangular": 0.40,
    "head/head-scale-horiz-decr": 0.08, "head/head-fat-decr": 0.95,
    "head/head-back-scale-depth-decr": 0.15, "head/head-scale-depth-decr": 0.05,
    # --- forehead / brow
    "forehead/forehead-temple-decr": 0.20, "forehead/forehead-scale-vert-decr": 0.15,
    "forehead/forehead-trans-forward": 0.15,
    "eyebrows/eyebrows-trans-down": 0.25, "eyebrows/eyebrows-angle-up": 0.25,
    # --- eyes (narrower aperture, mild epicanthic fold, lowered fold)
    "eyes/l-eye-epicanthus-in": 0.35, "eyes/r-eye-epicanthus-in": 0.35,
    "eyes/l-eye-height2-incr": 0.10, "eyes/r-eye-height2-incr": 0.10,
    "eyes/l-eye-eyefold-down": 0.30, "eyes/r-eye-eyefold-down": 0.30,
    "eyes/l-eye-corner2-up": 0.20, "eyes/r-eye-corner2-up": 0.18,
    "eyes/l-eye-bag-decr": 0.55, "eyes/r-eye-bag-decr": 0.55,
    "eyes/l-eye-scale-decr": 0.08, "eyes/r-eye-scale-decr": 0.08,
    # --- cheeks: defined zygomatic, hollow below
    "cheek/l-cheek-bones-incr": 0.60, "cheek/r-cheek-bones-incr": 0.56,
    "cheek/l-cheek-volume-decr": 0.85, "cheek/r-cheek-volume-decr": 0.80,
    "cheek/l-cheek-inner-decr": 0.55, "cheek/r-cheek-inner-decr": 0.50,
    "mouth/mouth-laugh-lines-in": 0.30,
    # --- nose: straight, moderately low bridge, firm tip
    "nose/nose-scale-horiz-decr": 0.10, "nose/nose-point-width-decr": 0.25,
    "nose/nose-hump-decr": 0.20, "nose/nose-flaring-decr": 0.15,
    "nose/nose-scale-depth-incr": 0.30, "nose/nose-greek-decr": 0.20,
    "nose/nose-scale-vert-incr": 0.08, "nose/nose-trans-forward": 0.15, "nose/nose-volume-decr": 0.10,
    # --- mouth: firm, slightly thin lips
    "mouth/mouth-upperlip-volume-decr": 0.25, "mouth/mouth-lowerlip-volume-decr": 0.10,
    "mouth/mouth-scale-horiz-incr": 0.10, "mouth/mouth-angles-down": 0.10,
    "mouth/mouth-philtrum-volume-incr": 0.15,
    # --- chin / jaw: strong but not heroic
    "chin/chin-width-incr": 0.08, "chin/chin-prominent-incr": 0.45, "chin/chin-prognathism-incr": 0.12,
    "chin/chin-bones-decr": 0.15, "chin/chin-height-decr": 0.10,
    # --- ears
    "ears/l-ear-scale-decr": 0.10, "ears/r-ear-scale-decr": 0.10,
    "ears/l-ear-flap-decr": 0.20, "ears/r-ear-flap-decr": 0.15,
    # --- neck: strong trapezius line
    "neck/measure-neck-circ-incr": 0.40, "neck/neck-scale-horiz-incr": 0.15,
    "neck/measure-neck-height-decr": 0.30,
    # --- torso: swordsman (back, shoulders), not gym-bodybuilder
    "torso/torso-vshape-incr": 0.30, "torso/torso-muscle-dorsi-incr": 0.35,
    "torso/torso-muscle-pectoral-incr": 0.20, "torso/measure-shoulder-dist-incr": 0.15,
    "torso/measure-waist-circ-decr": 0.10,
    "stomach/stomach-tone-incr": 0.35, "torso/measure-napetowaist-dist-incr": 0.10,
    # --- arms: forearm strength (grip), defined deltoid
    "arms/l-lowerarm-muscle-incr": 0.45, "arms/r-lowerarm-muscle-incr": 0.50,
    "arms/l-upperarm-shoulder-muscle-incr": 0.30, "arms/r-upperarm-shoulder-muscle-incr": 0.30,
    "arms/l-upperarm-muscle-incr": 0.25, "arms/r-upperarm-muscle-incr": 0.25,
    # --- hands: working hands
    "hands/l-hand-fingers-diameter-incr": 0.15, "hands/r-hand-fingers-diameter-incr": 0.15,
    "hands/measure-wrist-circ-incr": 0.20,
    "hands/l-hand-scale-decr": 0.45, "hands/r-hand-scale-decr": 0.45,
    # --- legs: low stance strength (thigh, calf)
    "legs/l-upperleg-muscle-incr": 0.40, "legs/r-upperleg-muscle-incr": 0.40,
    "legs/l-lowerleg-muscle-incr": 0.35, "legs/r-lowerleg-muscle-incr": 0.35,
    "legs/measure-thigh-circ-incr": 0.15,
    "hip/hip-scale-horiz-decr": 0.05,
    "buttocks/buttocks-volume-incr": 0.15,
}

# Small asymmetries (real faces are not mirror-perfect)
ASYM = {
    "asym/asym-brown-1-l": 0.15, "asym/asym-eye-2-r": 0.30, "asym/asym-nose-1-l": 0.30,
    "asym/asym-mouth-1-r": 0.30, "asym/asym-jaw-1-l": 0.25, "asym/asym-cheek-1-r": 0.25,
    "asym/asym-ear-2-l": 0.30,
}


# ------------------------------------------------------------------ loading
def parse_obj(path):
    verts, uvs, faces, face_uvs, face_groups = [], [], [], [], []
    group = None
    with open(path) as f:
        for line in f:
            if line.startswith("v "):
                verts.append(tuple(map(float, line.split()[1:4])))
            elif line.startswith("vt "):
                uvs.append(tuple(map(float, line.split()[1:3])))
            elif line.startswith("g "):
                group = line.split()[1]
            elif line.startswith("f "):
                vi, ti = [], []
                for tok in line.split()[1:]:
                    p = tok.split("/")
                    vi.append(int(p[0]) - 1)
                    ti.append(int(p[1]) - 1 if len(p) > 1 and p[1] else -1)
                faces.append(vi); face_uvs.append(ti); face_groups.append(group)
    return verts, uvs, faces, face_uvs, face_groups


def load_target(rel):
    path = os.path.join(DATA, "targets", rel + ".target.gz")
    if not os.path.exists(path):
        print("MISSING TARGET", rel)
        return {}
    out = {}
    with gzip.open(path, "rt") as f:
        for line in f:
            if not line.strip() or line.startswith("#"):
                continue
            p = line.split()
            out[int(p[0])] = (float(p[1]), float(p[2]), float(p[3]))
    return out


def two_way(v, low, high):
    """MakeHuman-style split of a 0..1 slider into (low_w, avg_w, high_w)."""
    if v < 0.5:
        return {low: (0.5 - v) / 0.5, "average": v / 0.5}
    return {"average": 1 - (v - 0.5) / 0.5, high: (v - 0.5) / 0.5}


def macro_targets(m):
    gender = {"female": 1 - m["gender"], "male": m["gender"]}
    a = m["age"]
    if a < 0.1875:
        age = {"baby": 1 - a / 0.1875, "child": a / 0.1875}
    elif a < 0.5:
        t = (a - 0.1875) / (0.5 - 0.1875); age = {"child": 1 - t, "young": t}
    else:
        t = (a - 0.5) / 0.5; age = {"young": 1 - t, "old": t}
    mus = {("averagemuscle" if k == "average" else k): w
           for k, w in two_way(m["muscle"], "minmuscle", "maxmuscle").items()}
    wei = {("averageweight" if k == "average" else k): w
           for k, w in two_way(m["weight"], "minweight", "maxweight").items()}
    hgt = {"minheight": (0.5 - m["height"]) / 0.5} if m["height"] < 0.5 else {"maxheight": (m["height"] - 0.5) / 0.5}
    pro = ({"uncommonproportions": (0.5 - m["proportions"]) / 0.5} if m["proportions"] < 0.5
           else {"idealproportions": (m["proportions"] - 0.5) / 0.5})
    race_total = sum(m["race"].values())
    race = {k: v / race_total for k, v in m["race"].items() if v > 0}
    out = []
    for g, gw in gender.items():
        for ag, aw in age.items():
            for r, rw in race.items():
                out.append((f"macrodetails/{r}-{g}-{ag}", gw * aw * rw))
            for mu, mw in mus.items():
                for we, ww in wei.items():
                    base = gw * aw * mw * ww
                    out.append((f"macrodetails/universal-{g}-{ag}-{mu}-{we}", base))
                    for h, hw in hgt.items():
                        out.append((f"macrodetails/height/{g}-{ag}-{mu}-{we}-{h}", base * hw))
                    for p, pw in pro.items():
                        out.append((f"macrodetails/proportions/{g}-{ag}-{mu}-{we}-{p}", base * pw))
    return [(n, w) for n, w in out if w > 1e-4]


# ------------------------------------------------------------------ custom anatomy pass
def gauss(p, c, r):
    d = (p - c).length / r
    return math.exp(-d * d)


def custom_sculpt(co, groups_by_vert):
    """Project-specific anatomical shaping on top of the targets (metres, Z-up).

    Landmarks are measured from the shaped mesh itself so the edits follow the
    anatomy rather than fixed coordinates.
    """
    body = [i for i, g in groups_by_vert.items() if g == "body"]
    zs = [co[i].z for i in body]
    top, bottom = max(zs), min(zs)
    H = top - bottom
    head_z = top - 0.065 * H

    def push(center, radius, offset, side_mirror=True, mask=None):
        centers = [center]
        if side_mirror and abs(center.x) > 1e-4:
            centers.append(Vector((-center.x, center.y, center.z)))
        for c in centers:
            off = Vector((offset.x if c.x >= 0 else -offset.x, offset.y, offset.z))
            for i in body:
                if mask and not mask(co[i]):
                    continue
                w = gauss(co[i], c, radius)
                if w > 0.01:
                    co[i] += off * w

    # --- cranium: Japanese crania tend to be shorter front-to-back with a flatter
    # occiput than the MakeHuman default; also lower the vault above the brow.
    eye_pts = [co[i] for i, g in groups_by_vert.items() if g == "helper-l-eye"]
    eye_line = sum(p.z for p in eye_pts) / len(eye_pts) + 0.022   # start above the brow
    ear_y = sorted(co[i].y for i in body if co[i].z > eye_line)[len([1 for i in body if co[i].z > eye_line]) // 2]
    for i in body:
        p = co[i]
        if p.z > eye_line - 0.02:
            t = min(1.0, (p.z - (eye_line - 0.02)) / 0.04)        # smooth start
            p.z = p.z - t * (p.z - eye_line) * 0.0                 # vault height unchanged
            if p.y > ear_y:                                        # occiput behind the ear line
                p.y = ear_y + (p.y - ear_y) * (1 - 0.08 * t)       # flatten back of skull
    zs2 = [co[i].z for i in body]
    top = max(zs2); H = top - bottom

    # landmarks (in Blender space: -Y is front)
    def front_y_at(z, x=0.0, band=0.01):
        ys = [co[i].y for i in body if abs(co[i].z - z) < band and abs(co[i].x - x) < 0.015]
        return min(ys) if ys else 0.0

    brow_z = head_z + 0.02 * H * 0.6
    eye_z = top - 0.115 * H * 0.98
    # brow ridge: slight forward mass above the eyes (supraorbital)
    push(Vector((0.03, front_y_at(eye_z + 0.03, 0.03), eye_z + 0.026)), 0.020, Vector((0, -0.0040, 0.0005)))
    # zygomatic arch / cheekbone lateral emphasis
    push(Vector((0.055, front_y_at(eye_z - 0.025, 0.05) + 0.02, eye_z - 0.03)), 0.02, Vector((0.002, -0.001, 0.0)))
    # buccal hollow under the cheekbone
    push(Vector((0.048, front_y_at(eye_z - 0.065, 0.045) + 0.012, eye_z - 0.068)), 0.024, Vector((-0.0045, 0.0025, 0.0)))
    # lower-face taper: pull the jowl area in (lean, sharp face)
    push(Vector((0.045, front_y_at(eye_z - 0.10, 0.04) + 0.02, eye_z - 0.10)), 0.022, Vector((-0.0035, 0.001, 0.0)))
    # laryngeal prominence (Adam's apple)
    push(Vector((0.0, front_y_at(eye_z - 0.175, 0.0), eye_z - 0.175)), 0.012, Vector((0, -0.0028, 0)), side_mirror=False)
    # mandible angle: squarer jaw corner
    push(Vector((0.058, front_y_at(eye_z - 0.1, 0.0) + 0.075, eye_z - 0.105)), 0.02, Vector((0.0025, 0.0, -0.001)))
    # trapezius slope (neck-shoulder) - fuller for a swordsman
    sh_z = top - 0.19 * H
    push(Vector((0.075, 0.02, sh_z + 0.015)), 0.045, Vector((0.0, 0.002, 0.006)))
    return top, bottom


# ------------------------------------------------------------------ build
def build():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    verts, uvs, faces, face_uvs, face_groups = parse_obj(os.path.join(DATA, "3dobjs", "base.obj"))
    co = [Vector(v) for v in verts]

    applied = []
    for name, w in macro_targets(MACRO):
        t = load_target(name)
        for i, d in t.items():
            co[i] += Vector(d) * w
        applied.append((name, round(w, 4)))
    for name, w in list(DETAILS.items()) + list(ASYM.items()):
        if w == 0:
            continue
        t = load_target(name)
        for i, d in t.items():
            co[i] += Vector(d) * w
        applied.append((name, w))

    # MakeHuman: Y-up decimetres -> Blender: Z-up metres, -Y front
    co = [Vector((v.x, -v.z, v.y)) * 0.1 for v in co]

    groups_by_vert = {}
    for f, g in zip(faces, face_groups):
        for i in f:
            groups_by_vert.setdefault(i, g)
    top, bottom = custom_sculpt(co, groups_by_vert)

    # scale to stature, feet on the ground
    s = TARGET_HEIGHT_M / (top - bottom)
    co = [Vector((v.x * s, v.y * s, (v.z - bottom) * s)) for v in co]

    def make(name, keep_groups):
        idx = [k for k, g in enumerate(face_groups) if g in keep_groups]
        used = sorted({i for k in idx for i in faces[k]})
        remap = {o: n for n, o in enumerate(used)}
        me = bpy.data.meshes.new(name)
        me.from_pydata([co[i] for i in used], [], [[remap[i] for i in faces[k]] for k in idx])
        uv = me.uv_layers.new(name="UVMap")
        li = 0
        for k in idx:
            for t in face_uvs[k]:
                uv.data[li].uv = uvs[t] if t >= 0 else (0, 0)
                li += 1
        me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
        me.validate()
        ob = bpy.data.objects.new(name, me)
        bpy.context.collection.objects.link(ob)
        return ob, used

    body, _ = make("SAM_Body", {"body"})
    teeth_up, _ = make("SAM_Teeth_Upper", {"helper-upper-teeth"})
    teeth_lo, _ = make("SAM_Teeth_Lower", {"helper-lower-teeth"})
    tongue, _ = make("SAM_Tongue", {"helper-tongue"})
    eyes = []
    for side, g in (("L", "helper-l-eye"), ("R", "helper-r-eye")):
        ids = sorted({i for k, gg in enumerate(face_groups) if gg == g for i in faces[k]})
        pts = [co[i] for i in ids]
        c = sum(pts, Vector()) / len(pts)
        front = min(p.y for p in pts)
        eyes.append((side, c, c.y - front))
    # joint centres (MakeHuman joint cubes) - used for nails, rig planning, sword grip
    joints = {}
    for k, g in enumerate(face_groups):
        if g and g.startswith("joint-"):
            joints.setdefault(g, set()).update(faces[k])
    joints = {g: sum((co[i] for i in ids), Vector()) / len(ids) for g, ids in joints.items()}
    # per-target vertex weights in body-mesh index space (for masks: lips etc.)
    body_index = {old: new for new, old in enumerate(sorted({i for k, g in enumerate(face_groups) if g == "body" for i in faces[k]}))}
    build.body_index = body_index
    build.joints = joints
    return body, (teeth_up, teeth_lo, tongue), eyes, applied


if __name__ == "__main__" and "--clay" not in ARGS and False:
    body, mouth, eyes, applied = build()
    print("APPLIED", len(applied))
    print("EYES", eyes)
    dims = body.dimensions
    print("BODY DIMS", tuple(round(x, 3) for x in dims))


def clay_preview():
    """Quick shape check: grey clay material + subdivision, front/side/back/face."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import render_views
    body, mouth, eyes, applied = build()
    sub = body.modifiers.new("Subdivision", "SUBSURF"); sub.levels = 1; sub.render_levels = 2
    m = bpy.data.materials.new("Clay"); m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (0.42, 0.38, 0.35, 1); p.inputs["Roughness"].default_value = 0.55
    body.data.materials.append(m)
    for side, c, r in eyes:
        bpy.ops.mesh.primitive_uv_sphere_add(radius=r * 0.78, location=c, segments=32, ring_count=16)
    render_views.setup_scene(samples=SAMPLES, res=(900, 1200))
    render_views.render_all(OUT, prefix="clay_", views=(arg("--views", "front,side,back,face,face_side").split(",")))


if __name__ == "__main__" and "--clay" in ARGS:
    clay_preview()
