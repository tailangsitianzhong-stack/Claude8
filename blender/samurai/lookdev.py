"""Look development for the samurai character: skin, eyes, hair, brows, lashes,
beard, nails and a simple loincloth for body review.

All geometry is generated here (hair = Blender hair-curves strands), all
materials are procedural Cycles node trees - no third-party textures.
"""
import math
import random

import bmesh
import bpy
from mathutils import Vector, Quaternion
from mathutils.bvhtree import BVHTree

import build_body as BB

RNG = random.Random(1274)  # year of the first Mongol invasion of Tsushima


# =================================================================== helpers
def link(ob, coll):
    for c in ob.users_collection:
        c.objects.unlink(ob)
    coll.objects.link(ob)


def new_coll(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(c)
    return c


def target_mask(names, body_index, n):
    """Per body-vertex weight 0..1 from how much CC0 targets move each vertex."""
    w = [0.0] * n
    for name in names:
        t = BB.load_target(name)
        if not t:
            continue
        m = max(Vector(d).length for d in t.values()) or 1
        for i, d in t.items():
            j = body_index.get(i)
            if j is not None:
                w[j] = max(w[j], Vector(d).length / m)
    return w


def smooth_weights(me, w, iters=2):
    adj = [[] for _ in me.vertices]
    for e in me.edges:
        a, b = e.vertices
        adj[a].append(b); adj[b].append(a)
    for _ in range(iters):
        w = [(w[i] + sum(w[j] for j in adj[i])) / (1 + len(adj[i])) if adj[i] else w[i] for i in range(len(w))]
    return w


def hair_object(name, strands, radius_root, radius_tip, material, coll, scales=None):
    """strands: list of point lists (Vector). Creates a Blender hair-curves object."""
    if scales is None:
        scales = [1.0] * len(strands)
    keep = [k for k, s in enumerate(strands) if len(s) >= 2]
    strands = [strands[k] for k in keep]; scales = [scales[k] for k in keep]
    print(f"[hair] {name}: {len(strands)} strands")
    if not strands:
        return None
    hc = bpy.data.hair_curves.new(name)
    sizes = [len(s) for s in strands]
    hc.add_curves(sizes)
    flat = []
    for s in strands:
        for p in s:
            flat.extend((p.x, p.y, p.z))
    hc.position_data.foreach_set("vector", flat)
    rad = hc.attributes.get("radius") or hc.attributes.new("radius", "FLOAT", "POINT")
    rv = []
    for s, sc in zip(strands, scales):
        n = len(s)
        for k in range(n):
            t = k / max(n - 1, 1)
            rv.append(sc * (radius_root + (radius_tip - radius_root) * t ** 1.5))
    rad.data.foreach_set("value", rv)
    hc.materials.append(material)
    ob = bpy.data.objects.new(name, hc)
    coll.objects.link(ob)
    return ob


# =================================================================== materials
def mat_skin():
    m = bpy.data.materials.new("M_Skin")
    m.use_nodes = True
    nt = m.node_tree; N = nt.nodes; L = nt.links
    N.clear()
    out = N.new("ShaderNodeOutputMaterial"); out.location = (1400, 0)
    bsdf = N.new("ShaderNodeBsdfPrincipled"); bsdf.location = (1100, 0)
    L.new(bsdf.outputs[0], out.inputs[0])
    tex = N.new("ShaderNodeTexCoord"); tex.location = (-1400, 0)
    mask = N.new("ShaderNodeAttribute"); mask.attribute_name = "SkinMask"; mask.location = (-1400, -400)
    sep = N.new("ShaderNodeSeparateColor"); sep.location = (-1200, -400)
    L.new(mask.outputs["Color"], sep.inputs[0])
    nail = N.new("ShaderNodeAttribute"); nail.attribute_name = "NailMask"; nail.location = (-1400, -650)

    def mix(a, b, fac, loc, blend="MIX"):
        n = N.new("ShaderNodeMix"); n.data_type = "RGBA"; n.blend_type = blend; n.location = loc
        if isinstance(a, tuple): n.inputs[6].default_value = a
        else: L.new(a, n.inputs[6])
        if isinstance(b, tuple): n.inputs[7].default_value = b
        else: L.new(b, n.inputs[7])
        if isinstance(fac, float): n.inputs[0].default_value = fac
        else: L.new(fac, n.inputs[0])
        return n.outputs[2]

    def noise(scale, loc, detail=4.0, rough=0.55):
        n = N.new("ShaderNodeTexNoise"); n.location = loc
        n.inputs["Scale"].default_value = scale; n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = rough
        L.new(tex.outputs["Object"], n.inputs["Vector"])
        return n

    def ramp(src, a, b, p0, p1, loc):
        r = N.new("ShaderNodeValToRGB"); r.location = loc
        r.color_ramp.elements[0].position = p0; r.color_ramp.elements[0].color = a
        r.color_ramp.elements[1].position = p1; r.color_ramp.elements[1].color = b
        L.new(src, r.inputs[0]); return r.outputs[0]

    base = (0.43, 0.255, 0.165, 1.0)             # sun-exposed East Asian skin (linear)
    mott = noise(18.0, (-1000, 300))
    c = mix(base, (0.36, 0.20, 0.13, 1), ramp(mott.outputs["Fac"], (0, 0, 0, 1), (0.6, 0.6, 0.6, 1), 0.35, 0.75, (-800, 300)), (-600, 300))
    blot = noise(60.0, (-1000, 120), 6.0, 0.6)
    c = mix(c, (0.44, 0.21, 0.15, 1), ramp(blot.outputs["Fac"], (0, 0, 0, 1), (0.35, 0.35, 0.35, 1), 0.5, 0.8, (-800, 120)), (-400, 300))
    # regional redness (nose, cheeks, ears)
    c = mix(c, (0.47, 0.20, 0.14, 1), sep.outputs["Red"], (-200, 300))
    # lips
    c = mix(c, (0.36, 0.15, 0.12, 1), sep.outputs["Green"], (0, 300))
    # stubble shadow + follicle speckle
    fol = N.new("ShaderNodeTexVoronoi"); fol.location = (-1000, -150)
    fol.inputs["Scale"].default_value = 1800.0
    L.new(tex.outputs["Object"], fol.inputs["Vector"])
    speck = ramp(fol.outputs["Distance"], (1, 1, 1, 1), (0, 0, 0, 1), 0.05, 0.25, (-800, -150))
    stub_col = mix((0.30, 0.21, 0.16, 1), (0.08, 0.065, 0.06, 1), speck, (-400, -150))
    c = mix(c, stub_col, sep.outputs["Blue"], (200, 300))
    # scalp under hair
    c = mix(c, (0.16, 0.11, 0.085, 1), mask.outputs["Alpha"], (400, 300))
    # nails
    c = mix(c, (0.55, 0.36, 0.30, 1), nail.outputs["Fac"], (600, 300))
    L.new(c, bsdf.inputs["Base Color"])

    # roughness: 0.48 with variation, lips/nails shinier
    rough_n = noise(35.0, (-1000, -400))
    r = N.new("ShaderNodeMapRange"); r.location = (-700, -400)
    r.inputs["To Min"].default_value = 0.47; r.inputs["To Max"].default_value = 0.64
    L.new(rough_n.outputs["Fac"], r.inputs["Value"])
    r2 = N.new("ShaderNodeMix"); r2.data_type = "FLOAT"; r2.location = (-400, -450)
    L.new(sep.outputs["Green"], r2.inputs[0]); L.new(r.outputs[0], r2.inputs[2]); r2.inputs[3].default_value = 0.30
    r3 = N.new("ShaderNodeMix"); r3.data_type = "FLOAT"; r3.location = (-200, -450)
    L.new(nail.outputs["Fac"], r3.inputs[0]); L.new(r2.outputs[0], r3.inputs[2]); r3.inputs[3].default_value = 0.18
    L.new(r3.outputs[0], bsdf.inputs["Roughness"])

    # micro surface: pores (voronoi) + fine wrinkles (noise)
    pores = N.new("ShaderNodeTexVoronoi"); pores.location = (-1000, -800)
    pores.inputs["Scale"].default_value = 1400.0
    L.new(tex.outputs["Object"], pores.inputs["Vector"])
    wr = noise(450.0, (-1000, -1000), 8.0, 0.7)
    add = N.new("ShaderNodeMath"); add.operation = "MULTIPLY_ADD"; add.location = (-700, -850)
    L.new(wr.outputs["Fac"], add.inputs[0]); add.inputs[1].default_value = 0.6
    L.new(pores.outputs["Distance"], add.inputs[2])
    bump = N.new("ShaderNodeBump"); bump.location = (800, -600)
    bump.inputs["Strength"].default_value = 0.22; bump.inputs["Distance"].default_value = 0.0004
    L.new(add.outputs[0], bump.inputs["Height"])
    L.new(bump.outputs[0], bsdf.inputs["Normal"])

    bsdf.subsurface_method = "RANDOM_WALK_SKIN"
    bsdf.inputs["Subsurface Weight"].default_value = 1.0
    bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.38, 0.22)
    bsdf.inputs["Subsurface Scale"].default_value = 0.0035
    bsdf.inputs["IOR"].default_value = 1.4
    bsdf.inputs["Specular IOR Level"].default_value = 0.5
    bsdf.inputs["Coat Weight"].default_value = 0.0
    bsdf.inputs["Coat Roughness"].default_value = 0.35
    return m


def mat_hair(name, melanin=0.92, redness=0.12, rough=0.33):
    m = bpy.data.materials.new(name); m.use_nodes = True
    N = m.node_tree.nodes; L = m.node_tree.links
    N.clear()
    out = N.new("ShaderNodeOutputMaterial")
    h = N.new("ShaderNodeBsdfHairPrincipled")
    h.parametrization = "MELANIN"
    for k, v in (("Melanin", melanin), ("Melanin Redness", redness), ("Roughness", rough),
                 ("Radial Roughness", 0.35), ("Coat", 0.1), ("Random Color", 0.08),
                 ("Random Roughness", 0.15), ("IOR", 1.55)):
        if k in h.inputs:
            h.inputs[k].default_value = v
    L.new(h.outputs[0], out.inputs[0])
    return m


def mat_simple(name, color, rough, metallic=0.0, sheen=0.0, coat=0.0, trans=0.0, ior=1.45, sss=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Sheen Weight"].default_value = sheen
    b.inputs["Coat Weight"].default_value = coat
    b.inputs["Transmission Weight"].default_value = trans
    b.inputs["IOR"].default_value = ior
    b.inputs["Subsurface Weight"].default_value = sss
    return m


def mat_eye(r):
    """Sclera + iris + pupil, procedural, in the eye object's local space (+Z = gaze)."""
    m = bpy.data.materials.new("M_Eye"); m.use_nodes = True
    nt = m.node_tree; N = nt.nodes; L = nt.links
    b = N["Principled BSDF"]
    tc = N.new("ShaderNodeTexCoord")
    sep = N.new("ShaderNodeSeparateXYZ"); L.new(tc.outputs["Object"], sep.inputs[0])
    # rho = sqrt(x^2+y^2)/r  (radial distance from gaze axis, normalised)
    vx = N.new("ShaderNodeCombineXYZ"); L.new(sep.outputs["X"], vx.inputs["X"]); L.new(sep.outputs["Y"], vx.inputs["Y"])
    ln = N.new("ShaderNodeVectorMath"); ln.operation = "LENGTH"; L.new(vx.outputs[0], ln.inputs[0])
    rho = N.new("ShaderNodeMath"); rho.operation = "DIVIDE"; L.new(ln.outputs["Value"], rho.inputs[0]); rho.inputs[1].default_value = r
    front = N.new("ShaderNodeMath"); front.operation = "GREATER_THAN"; L.new(sep.outputs["Z"], front.inputs[0]); front.inputs[1].default_value = 0.0
    # iris fibres: noise stretched radially (use angle via x/y normalised)
    nrm = N.new("ShaderNodeVectorMath"); nrm.operation = "NORMALIZE"; L.new(vx.outputs[0], nrm.inputs[0])
    sc = N.new("ShaderNodeVectorMath"); sc.operation = "SCALE"; L.new(nrm.outputs[0], sc.inputs[0]); sc.inputs["Scale"].default_value = 9.0
    comb = N.new("ShaderNodeVectorMath"); comb.operation = "ADD"; L.new(sc.outputs[0], comb.inputs[0])
    rz = N.new("ShaderNodeCombineXYZ"); L.new(rho.outputs[0], rz.inputs["Z"]); L.new(rz.outputs[0], comb.inputs[1])
    fib = N.new("ShaderNodeTexNoise"); fib.inputs["Scale"].default_value = 3.0; fib.inputs["Detail"].default_value = 8.0
    L.new(comb.outputs[0], fib.inputs["Vector"])
    iris_ramp = N.new("ShaderNodeValToRGB")
    e = iris_ramp.color_ramp.elements
    e[0].position, e[0].color = 0.30, (0.020, 0.010, 0.006, 1)
    e[1].position, e[1].color = 0.70, (0.16, 0.075, 0.03, 1)
    L.new(fib.outputs["Fac"], iris_ramp.inputs[0])
    # radial zones
    zone = N.new("ShaderNodeValToRGB")
    z = zone.color_ramp.elements
    zone.color_ramp.interpolation = "LINEAR"
    z[0].position, z[0].color = 0.0, (0, 0, 0, 1)         # pupil
    z[1].position, z[1].color = 0.155, (0, 0, 0, 1)
    p1 = zone.color_ramp.elements.new(0.175); p1.color = (1, 1, 1, 1)      # iris start
    p2 = zone.color_ramp.elements.new(0.42); p2.color = (1, 1, 1, 1)
    p3 = zone.color_ramp.elements.new(0.47); p3.color = (0.25, 0.25, 0.25, 1)  # limbal ring
    p4 = zone.color_ramp.elements.new(0.50); p4.color = (2, 2, 2, 1)          # sclera code
    L.new(rho.outputs[0], zone.inputs[0])
    # sclera colour with slight warm edge
    scl = N.new("ShaderNodeMix"); scl.data_type = "RGBA"
    scl.inputs[6].default_value = (0.78, 0.74, 0.70, 1); scl.inputs[7].default_value = (0.62, 0.48, 0.44, 1)
    edge = N.new("ShaderNodeMapRange"); L.new(rho.outputs[0], edge.inputs["Value"])
    edge.inputs["From Min"].default_value = 0.6; edge.inputs["From Max"].default_value = 1.0
    L.new(edge.outputs[0], scl.inputs[0])
    # combine: zone<1 -> iris*zone ; zone>1 (sclera code) -> sclera
    sepz = N.new("ShaderNodeSeparateColor"); L.new(zone.outputs[0], sepz.inputs[0])
    is_scl = N.new("ShaderNodeMath"); is_scl.operation = "GREATER_THAN"; L.new(sepz.outputs["Red"], is_scl.inputs[0]); is_scl.inputs[1].default_value = 1.5
    back = N.new("ShaderNodeMath"); back.operation = "SUBTRACT"; back.inputs[0].default_value = 1.0; L.new(front.outputs[0], back.inputs[1])
    use_scl = N.new("ShaderNodeMath"); use_scl.operation = "MAXIMUM"; L.new(is_scl.outputs[0], use_scl.inputs[0]); L.new(back.outputs[0], use_scl.inputs[1])
    irisc = N.new("ShaderNodeMix"); irisc.data_type = "RGBA"; irisc.blend_type = "MULTIPLY"
    irisc.inputs[0].default_value = 1.0; L.new(iris_ramp.outputs[0], irisc.inputs[6]); L.new(zone.outputs[0], irisc.inputs[7])
    fin = N.new("ShaderNodeMix"); fin.data_type = "RGBA"
    L.new(use_scl.outputs[0], fin.inputs[0]); L.new(irisc.outputs[2], fin.inputs[6]); L.new(scl.outputs[2], fin.inputs[7])
    L.new(fin.outputs[2], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.35
    b.inputs["Subsurface Weight"].default_value = 0.3
    b.inputs["Subsurface Radius"].default_value = (1.0, 0.4, 0.3)
    b.inputs["Subsurface Scale"].default_value = 0.002
    return m


# =================================================================== masks on the body
def landmarks(body, eyes):
    me = body.data
    co = [v.co for v in me.vertices]
    eye_c = {s: c for s, c, r in eyes}
    eye_r = {s: r for s, c, r in eyes}
    cl, cr = eye_c["L"], eye_c["R"]
    mid_eye = (cl + cr) / 2
    top = max(p.z for p in co)
    face = [p for p in co if p.z > mid_eye.z - 0.14]
    return dict(co=co, eye_c=eye_c, eye_r=eye_r, mid_eye=mid_eye, top=top)


def compute_masks(body, eyes, body_index):
    me = body.data
    n = len(me.vertices)
    lm = landmarks(body, eyes)
    co = lm["co"]; me_ = lm["mid_eye"]

    red = target_mask(["nose/nose-point-width-incr", "nose/nose-flaring-incr"], body_index, n)
    cheek = target_mask(["cheek/l-cheek-volume-incr", "cheek/r-cheek-volume-incr"], body_index, n)
    ears = target_mask(["ears/l-ear-scale-incr", "ears/r-ear-scale-incr"], body_index, n)
    lips = target_mask(["mouth/mouth-upperlip-volume-incr", "mouth/mouth-lowerlip-volume-incr"], body_index, n)
    lips = [min(1.0, max(0.0, (w - 0.18) / 0.45)) for w in lips]
    lips = smooth_weights(me, lips, 1)
    redness = [min(1.0, 0.55 * red[i] + 0.35 * cheek[i] + 0.45 * ears[i]) for i in range(n)]

    # mouth / nose landmarks from masks
    lw = sum(lips) or 1
    mouth = sum((co[i] * lips[i] for i in range(n)), Vector()) / lw
    nostril = target_mask(["nose/nose-nostrils-width-incr"], body_index, n)
    nw = sum(nostril) or 1
    nose_base = sum((co[i] * nostril[i] for i in range(n)), Vector()) / nw
    # pogonion: most forward midline point below the lower lip
    pog_c = [p for p in co if abs(p.x) < 0.01 and mouth.z - 0.07 < p.z < mouth.z - 0.018]
    pog = min(pog_c, key=lambda p: p.y).copy()
    # chin underside (menton): lowest midline point near the pogonion
    men_c = [p for p in co if abs(p.x) < 0.01 and pog.z - 0.04 < p.z <= pog.z and p.y < pog.y + 0.03]
    chin = min(men_c, key=lambda p: p.z).copy()
    print("[landmarks] mouth", tuple(round(x, 3) for x in mouth), "pogonion", tuple(round(x, 3) for x in pog),
          "menton", tuple(round(x, 3) for x in chin))

    # stubble / beard shadow region
    stub = [0.0] * n
    ear_front_y = me_.y + 0.075
    for i, p in enumerate(co):
        if p.z > nose_base.z + 0.004 or p.z < chin.z - 0.035:
            continue
        if p.y > ear_front_y - 0.012:
            continue
        ax = abs(p.x)
        # upper boundary: from nose wing down to jaw angle (cheek line)
        cheek_line = nose_base.z - 0.004 - 0.55 * max(0.0, ax - 0.02)
        if p.z > cheek_line and ax > 0.018:
            continue
        # under the jaw: only near the jawline, fade into the neck
        f = 1.0
        if p.z < chin.z:
            f = max(0.0, 1 - (chin.z - p.z) / 0.035)
        stub[i] = f * (1 - lips[i])
    stub = smooth_weights(me, stub, 3)

    # scalp / hairline (angle-dependent hairline height above eye level)
    hair = [0.0] * n
    front_band = [0.0] * n
    cy = me_.y + 0.085
    ear_top = max((co[i].z for i in range(n) if ears[i] > 0.85), default=me_.z + 0.03) + 0.004
    for i, p in enumerate(co):
        if p.z < me_.z - 0.10:
            continue
        ang = math.degrees(math.atan2(abs(p.x), -(p.y - cy)))       # 0 = front, 180 = back
        # hairline height above eye level as a function of angle around the head
        if ang < 42:
            hl = 0.044 + 0.003 * (ang / 42)          # forehead, slight M-shape
        elif ang < 82:                               # temple curves smoothly down to the sideburn
            u = (ang - 42) / 40
            hl = 0.047 - 0.059 * (0.5 - 0.5 * math.cos(math.pi * u))
        elif ang < 100:
            hl = -0.012                              # sideburn (bin) down to mid-ear
        elif ang < 140:
            hl = -0.012 - 0.053 * ((ang - 100) / 40)  # behind the ear down to the nape
        else:
            hl = -0.065
        hl += 0.0025 * math.sin(ang * 0.31) + 0.0015 * math.sin(ang * 0.83 + 1.3) + RNG.gauss(0, 0.0012)
        d = (p.z - me_.z) - hl
        # keep the ears bare
        if ears[i] > 0.5 and p.z < ear_top:        # only the ear itself stays bare
            d = min(d, -0.01)
        hair[i] = max(0.0, min(1.0, d / 0.0045 + 0.5))
        front_band[i] = hair[i] * max(0.0, 1 - max(0.0, d) / 0.025)
    hair = smooth_weights(me, hair, 1)
    # scalp tint: under dense hair the skin reads dark; fade softly at the hairline
    scalp_tint = [max(0.0, min(1.0, (h - 0.45) / 0.4)) for h in hair]

    attr = me.color_attributes.new("SkinMask", "FLOAT_COLOR", "POINT")
    for i in range(n):
        attr.data[i].color = (redness[i], lips[i], stub[i] * 0.85, scalp_tint[i])
    return dict(lips=lips, stub=stub, hair=hair, front_band=front_band, mouth=mouth, nose_base=nose_base, chin=chin, cy=cy, lm=lm)


def nails(body, joints):
    """Nail mask + slight raised nail plate, located from CC0 joint helpers."""
    me = body.data
    n = len(me.vertices)
    w = [0.0] * n
    for side in "lr":
        j = lambda f, k: joints.get(f"joint-{side}-finger-{f}-{k}")
        if not j(2, 1) or not j(5, 1):
            continue
        lateral = (j(2, 1) - j(5, 1)).normalized()          # towards the thumb side
        fdir = (j(3, 4) - j(3, 1)).normalized()
        dorsal = fdir.cross(lateral).normalized()
        sgn = 1 if j(3, 1).x > 0 else -1
        if dorsal.dot(Vector((sgn, 0, 0.6))) < 0:
            dorsal = -dorsal
        for f in range(1, 6):
            a, b = j(f, 3), j(f, 4)
            if not a or not b:
                continue
            seg = b - a
            ddir = dorsal if f > 1 else (0.35 * dorsal + lateral).normalized()
            centre = a + seg * 0.62
            L = seg.length
            for i, v in enumerate(me.vertices):
                d = v.co - centre
                if d.length > 0.75 * L:
                    continue
                along = d.dot(seg.normalized())
                side_off = (d - seg.normalized() * along)
                if side_off.normalized().dot(ddir) < 0.55:
                    continue
                if along < -0.45 * L:
                    continue
                w[i] = max(w[i], max(0.0, 1 - abs(along) / (0.75 * L)))
    w = smooth_weights(me, w, 1)
    attr = me.attributes.new("NailMask", "FLOAT", "POINT")
    for i, v in enumerate(me.vertices):
        attr.data[i].value = min(1.0, w[i] * 2.2)
    return w


# =================================================================== eyes
def make_eyes(eyes, coll):
    objs = []
    for side, c, r in eyes:
        r_eye = r * 0.985
        bpy.ops.mesh.primitive_uv_sphere_add(radius=r_eye, location=c, segments=64, ring_count=32,
                                             rotation=(math.radians(90), 0, 0))
        eye = bpy.context.object; eye.name = f"SAM_Eye_{side}"
        # gaze: slightly convergent, aim at a point ~2 m in front
        tgt = Vector((0, c.y - 2.0, c.z - 0.02))
        q = (tgt - c).to_track_quat("Z", "Y")
        eye.rotation_euler = q.to_euler()
        bpy.ops.object.shade_smooth()
        eye.data.materials.append(mat_eye(r_eye) if not bpy.data.materials.get("M_Eye") else bpy.data.materials["M_Eye"])
        link(eye, coll)
        # cornea: clear, slightly bulging shell (no shadow casting so the iris stays lit)
        bpy.ops.mesh.primitive_uv_sphere_add(radius=r_eye * 1.012, location=c, segments=64, ring_count=32)
        cor = bpy.context.object; cor.name = f"SAM_Cornea_{side}"
        for v in cor.data.vertices:
            if v.co.z > 0:
                k = (v.co.z / (r_eye * 1.012)) ** 6
                v.co.z *= 1 + 0.10 * k
        cor.rotation_euler = eye.rotation_euler
        bpy.ops.object.shade_smooth()
        cm = bpy.data.materials.get("M_Cornea") or mat_simple("M_Cornea", (1, 1, 1), 0.0, trans=1.0, ior=1.376)
        cor.data.materials.append(cm)
        cor.visible_shadow = False
        link(cor, coll)
        objs += [eye, cor]
    return objs


# =================================================================== strands
def surface_bvh(body):
    """BVH of the body at RENDER subdivision level (hair must sit on the rendered skin)."""
    sub = body.modifiers.get("Subdivision")
    keep = sub.levels if sub else None
    if sub:
        sub.levels = sub.render_levels
    bpy.context.view_layer.update()                 # re-evaluate at the new level
    dg = bpy.context.evaluated_depsgraph_get()
    bvh = BVHTree.FromObject(body, dg)
    if sub:
        sub.levels = keep
        bpy.context.view_layer.update()
    return bvh, body.evaluated_get(dg)


def sample_surface(body, weights, count, rng=RNG, thresh=0.5):
    """Random points on the body surface with density following `weights`.

    Triangles are picked by area * max weight, then each point is accepted with
    probability smoothstep(interpolated weight around `thresh`), so thin bands
    (eyebrows) and soft edges (hairline) both work.
    """
    import bisect
    me = body.data
    tris = []
    for poly in me.polygons:
        vs = poly.vertices
        if max(weights[i] for i in vs) < 0.02:
            continue
        for k in range(1, len(vs) - 1):
            ids = (vs[0], vs[k], vs[k + 1])
            a, b, c = (me.vertices[x].co for x in ids)
            area = (b - a).cross(c - a).length / 2
            tris.append((area * max(weights[x] for x in ids), a, b, c, poly.normal.copy(),
                         [weights[x] for x in ids]))
    if not tris:
        return []
    acc, s_ = [], 0
    for t in tris:
        s_ += t[0]; acc.append(s_)
    lo, hi = thresh * 0.5, min(1.0, thresh * 1.5)
    pts = []
    tries = 0
    while len(pts) < count and tries < count * 20:
        tries += 1
        t = tris[min(bisect.bisect_left(acc, rng.random() * s_), len(tris) - 1)]
        u, v = rng.random(), rng.random()
        if u + v > 1:
            u, v = 1 - u, 1 - v
        w = t[5][0] * (1 - u - v) + t[5][1] * u + t[5][2] * v
        x = min(1.0, max(0.0, (w - lo) / max(hi - lo, 1e-6)))
        if rng.random() > x * x * (3 - 2 * x):
            continue
        a, b, c = t[1], t[2], t[3]
        pts.append((a + (b - a) * u + (c - a) * v, t[4]))
    return pts


def project(bvh, p, max_d=0.02):
    hit = bvh.find_nearest(p, max_d)
    return (hit[0], hit[1]) if hit and hit[0] else (p, None)


def make_scalp_hair(body, masks, coll, mat, count=18000, tuft=3500):
    lm = masks["lm"]; me_ = lm["mid_eye"]; top = lm["top"]
    bvh, _ = surface_bvh(body)
    C = Vector((0, masks["cy"], me_.z + 0.025))                   # head centre
    G = Vector((0, masks["cy"] + 0.040, top - 0.012))             # gather point (crown)
    # place the gather point just above the scalp
    gp, gn = project(bvh, G, 0.05)
    G = gp + (gn or Vector((0, 0, 1))) * 0.006
    roots = [(project(bvh, r, 0.01)[0], n) for r, n in sample_surface(body, masks["hair"], count)]
    # density boost in the first 2.5 cm behind the hairline (coverage builds up from the edge)
    roots += [(project(bvh, r, 0.01)[0], n) for r, n in sample_surface(body, masks["front_band"], count // 2, thresh=0.3)]
    # extra density along the hairline so the edge reads as hair, not as a ledge
    me = body.data
    bvh_base = BVHTree.FromPolygons([v.co.copy() for v in me.vertices], [list(p.vertices) for p in me.polygons])
    def root_weight(p):
        loc, nrm, idx, dist = bvh_base.find_nearest(p)
        return sum(masks["hair"][v] for v in me.polygons[idx].vertices) / len(me.polygons[idx].vertices)
    scales = [0.75 + 0.25 * min(1.0, max(0.0, (root_weight(r) - 0.3) / 0.6)) for r, _ in roots]
    # clump guides
    guides = RNG.sample(range(len(roots)), max(1, len(roots) // 60))
    gpts = [roots[g][0] for g in guides]

    def path(root, layer):
        pts = []
        d0 = (root - C).normalized(); d1 = (G - C).normalized()
        ang = d0.angle(d1) if d0.dot(d1) < 0.9999 else 0.0
        steps = 12
        r_prev = None
        for k in range(steps):
            t = k / (steps - 1)
            if ang > 1e-4:
                axis = d0.cross(d1).normalized()
                d = Quaternion(axis, ang * t) @ d0
            else:
                d = d0
            # ray from outside towards the head centre to find the scalp
            o = C + d * 0.25
            hit = bvh.ray_cast(o, -d, 0.3)
            surf = hit[0] if hit[0] else C + d * 0.1
            r = (surf - C).length
            if r_prev is not None and r > r_prev + 0.005:   # ray hit the ear: stay on the skull
                r = r_prev; surf = C + d * r
            r_prev = r
            ramp_in = min(1.0, t / 0.6) ** 2
            lift = 0.0009 + layer * ramp_in * (0.0010 + 0.0006 * math.sin(math.pi * t))  # oiled, sleek
            p = surf + d * lift
            # converge into the gather point
            if t > 0.75:
                p = p.lerp(G, ((t - 0.75) / 0.25) ** 1.5)
            pts.append(p)
        pts[0] = root - (root - C).normalized() * 0.0005
        return pts

    guide_paths = {}
    strands = []
    for idx, (root, nrm) in enumerate(roots):
        gi = min(range(len(gpts)), key=lambda k: (gpts[k] - root).length_squared) if len(gpts) < 400 else None
        layer = RNG.random() ** 1.6
        s = path(root, layer)
        if gi is not None:
            if gi not in guide_paths:
                guide_paths[gi] = path(gpts[gi], 0.5)
            gpth = guide_paths[gi]
            off = root - gpts[gi]
            for k in range(1, len(s) - 2):
                t = k / (len(s) - 1)
                s[k] = s[k].lerp(gpth[k] + off * (1 - t), 0.35 * t)
        # tiny natural waviness
        for k in range(2, len(s) - 2):
            s[k] += Vector((RNG.gauss(0, 0.0004), RNG.gauss(0, 0.0004), RNG.gauss(0, 0.0003)))
        strands.append(s)
    scalp = hair_object("SAM_Hair_Scalp", strands, 0.000060, 0.000040, mat, coll, scales=scales)

    # topknot: hair gathered at the crown, tied with a paper cord (motoyui), the
    # tail rises 2-3 cm then folds forward and lies along the top of the head
    axis = Vector((0, 0.15, 1.0)).normalized()
    fwd = Vector((0, -1, 0))
    tufts = []
    for _ in range(tuft):
        a = RNG.random() * 2 * math.pi
        rr = 0.0068 * math.sqrt(RNG.random())
        off = Vector((math.cos(a) * rr, math.sin(a) * rr * 0.7, 0))
        base = G + off
        rise = 0.014 + RNG.random() * 0.004
        L = 0.060 + RNG.random() * 0.018
        R = 0.010 + RNG.random() * 0.002
        T = base + axis * rise
        centre = T + fwd * R
        th_end = math.pi * 0.92
        arc_len = R * th_end
        pts = []
        for k in range(16):
            t = k / 15
            dist = t * L
            if dist < rise:
                p = base + axis * dist
            elif dist < rise + arc_len:
                th = (dist - rise) / R
                p = centre - fwd * R * math.cos(th) + axis * R * math.sin(th)
            else:
                tang = (fwd * math.sin(th_end) + axis * math.cos(th_end)).normalized()
                end = centre - fwd * R * math.cos(th_end) + axis * R * math.sin(th_end)
                p = end + tang * (dist - rise - arc_len)
            u = max(0.0, (dist - rise) / max(L - rise, 1e-4))
            p = p + off * (1.6 * u)          # fans out a little along the tail
            pts.append(p)
        tufts.append(pts)
    tuft_ob = hair_object("SAM_Hair_Topknot", tufts, 0.00006, 0.00004, mat, coll)

    # motoyui (paper cord) wraps
    bpy.ops.mesh.primitive_cylinder_add(radius=0.0078, depth=0.018, vertices=32,
                                        location=G + axis * 0.012)
    cord = bpy.context.object; cord.name = "SAM_Hair_Motoyui"
    cord.rotation_euler = axis.to_track_quat("Z", "Y").to_euler()
    for k in range(4):
        bpy.ops.mesh.primitive_torus_add(major_radius=0.0080, minor_radius=0.0010,
                                         location=G + axis * (0.005 + k * 0.0045),
                                         major_segments=32, minor_segments=8)
        t = bpy.context.object
        t.rotation_euler = cord.rotation_euler
        t.select_set(True)
    cord.select_set(True)
    bpy.context.view_layer.objects.active = cord
    bpy.ops.object.join()
    cord.data.materials.append(mat_simple("M_Motoyui_Paper", (0.45, 0.43, 0.38), 0.75, sheen=0.2))
    bpy.ops.object.shade_smooth()
    link(cord, coll)
    # fine short hairs in the hairline transition (soft, natural edge)
    band = [max(0.0, 1 - abs(h - 0.35) / 0.3) for h in masks["hair"]]
    def up_back(p, n):
        return (G - p).normalized()
    vellus = strands_on_region(body, band, count // 14, 0.007, up_back, coll, "SAM_Hair_Hairline", mat,
                               r_root=0.000028, r_tip=0.000010, npts=5, lift=0.08, thresh=0.3)
    return [scalp, tuft_ob, cord, vellus]


def strands_on_region(body, weights, count, length, direction_fn, coll, name, mat,
                      r_root=0.00004, r_tip=0.000012, npts=6, lift=0.25, thresh=0.5, curl=0.0):
    pts = sample_surface(body, weights, count, thresh=thresh)
    strands = []
    for p, nrm in pts:
        d = direction_fn(p, nrm)
        d = (d - nrm * d.dot(nrm)).normalized()           # lie on the skin
        d = (d + nrm * lift).normalized()
        Ls = length * (0.7 + 0.6 * RNG.random())
        s = []
        for k in range(npts):
            t = k / (npts - 1)
            q = p + d * Ls * t + nrm * (curl * Ls * t * t)
            s.append(q)
        s[0] = p - nrm * 0.0003
        strands.append(s)
    return hair_object(name, strands, r_root, r_tip, mat, coll)


def make_brows(body, eyes, coll, mat):
    me = body.data
    w = [0.0] * len(me.vertices)
    for side, c, r in eyes:
        sg = 1 if c.x > 0 else -1
        for i, v in enumerate(me.vertices):
            p = v.co
            if p.y > c.y + 0.004:
                continue
            u = (sg * p.x - (sg * c.x - 0.019)) / 0.044         # 0 inner .. 1 outer
            if not 0 <= u <= 1:
                continue
            zc = c.z + 0.0185 + 0.0030 * math.sin(math.pi * min(u * 1.25, 1)) - 0.004 * u * u
            th = 0.0050 * (1 - 0.6 * u) + 0.0012
            d = abs(p.z - zc) / th
            w[i] = max(w[i], max(0.0, 1 - d))
    w = smooth_weights(me, w, 1)

    def dirf(p, n):
        sg = 1 if p.x > 0 else -1
        c = eyes[0][1] if p.x > 0 else eyes[1][1]
        u = (sg * p.x - (sg * c.x - 0.019)) / 0.044
        up = 0.9 - 1.3 * u
        return Vector((sg, 0, up)).normalized()
    return strands_on_region(body, w, 1100, 0.0062, dirf, coll, "SAM_Hair_Eyebrows", mat,
                             r_root=0.000040, r_tip=0.000012, lift=0.10, thresh=0.3)


def make_lashes(body, eyes, coll, mat):
    """Lash roots on the lid margin = body vertices touching the eyeball sphere."""
    me = body.data
    strands = []
    for side, c, r in eyes:
        cand = [v.co.copy() for v in me.vertices
                if (v.co - c).length < r * 1.13 and v.co.y < c.y - 0.35 * r]
        for upper in (True, False):
            row = sorted([p for p in cand if (p.z > c.z) == upper], key=lambda p: p.x)
            print(f"[lashes] eye {side} {'upper' if upper else 'lower'}: {len(row)} margin verts")
            for a, b in zip(row, row[1:]):
                if (b - a).length > 0.006:
                    continue
                per = 6 if upper else 2
                for k in range(per):
                    t = (k + RNG.random()) / per
                    p = a.lerp(b, t)
                    out = (p - c).normalized()
                    along = min(1.0, abs(p.x - c.x) / (r * 1.1))
                    Lh = (0.0085 if upper else 0.0045) * (1.0 - 0.5 * along ** 2) * (0.8 + 0.4 * RNG.random())
                    up = Vector((0, 0, 1 if upper else -1))
                    lat = Vector((1 if p.x > c.x else -1, 0, 0)) * 0.35 * along
                    d0 = (out * 0.6 + Vector((0, -0.8, 0)) + lat).normalized()
                    pts = [p + d0 * Lh * (j / 5) + up * Lh * 0.6 * (j / 5) ** 2 for j in range(6)]
                    strands.append(pts)
    return hair_object("SAM_Hair_Eyelashes", strands, 0.000038, 0.000008, mat, coll)


def make_beard(body, masks, coll, mat):
    """Trimmed moustache following the upper lip + rounded chin beard."""
    me = body.data
    mouth, nose, chin = masks["mouth"], masks["nose_base"], masks["chin"]
    lips = masks["lips"]
    must = [0.0] * len(me.vertices)
    goat = [0.0] * len(me.vertices)
    for i, v in enumerate(me.vertices):
        p = v.co
        if p.y > mouth.y + 0.022:
            continue
        ax = abs(p.x)
        # moustache: band above the upper lip, follows the lip line down at the corners
        lip_top = mouth.z + 0.006 - 0.20 * ax
        band = (p.z - lip_top) / 0.009
        if 0.0 < band < 1.0 and ax < 0.030 and p.z < nose.z - 0.003:
            must[i] = (1 - lips[i]) * (1 - max(0, (ax - 0.022) / 0.008))
        # chin beard: rounded patch below the lower lip down to the chin underside
        cy_ = (mouth.z - 0.010 + chin.z - 0.008) / 2
        ry = (mouth.z - 0.010 - (chin.z - 0.008)) / 2
        e = (p.x / 0.020) ** 2 + ((p.z - cy_) / ry) ** 2
        if e < 1.0:
            goat[i] = min(1.0, (1 - e) * 3)
    must = smooth_weights(me, must, 1); goat = smooth_weights(me, goat, 2)
    print("[beard] mouth", tuple(round(x, 3) for x in mouth), "chin", tuple(round(x, 3) for x in chin),
          "goat verts", sum(1 for g in goat if g > 0.02))
    m_ob = strands_on_region(body, must, 3200, 0.008,
                             lambda p, n: Vector((0.55 * (1 if p.x > 0 else -1), -0.1, -1)),
                             coll, "SAM_Hair_Moustache", mat, r_root=0.000045, r_tip=0.000015,
                             lift=0.2, thresh=0.35)
    g_ob = strands_on_region(body, goat, 4200, 0.012,
                             lambda p, n: Vector((0.05 * (1 if p.x > 0 else -1), -0.2, -1)),
                             coll, "SAM_Hair_Beard", mat, r_root=0.000045, r_tip=0.000015,
                             lift=0.25, thresh=0.35, curl=0.04)
    return [m_ob, g_ob]


def make_fundoshi(body, joints, coll):
    """Simple cotton loincloth fitted to the pelvis (placeholder until STEP 4 clothing)."""
    me = body.data
    pel = joints.get("joint-pelvis", Vector((0, 0, 0.95)))
    crotch_z = min(v.co.z for v in me.vertices if abs(v.co.x) < 0.008 and abs(v.co.y - pel.y) < 0.08 and v.co.z < pel.z)
    top_z = pel.z + 0.045
    bm = bmesh.new(); bm.from_mesh(me)
    keep = set()
    for f in bm.faces:
        zs = [v.co.z for v in f.verts]
        if min(zs) > crotch_z - 0.012 and max(zs) < top_z and max(abs(v.co.x) for v in f.verts) < 0.22:
            c = f.calc_center_median()
            # fundoshi: waistband (~3.5 cm) all round + a front/back panel through the crotch
            band = c.z > top_z - 0.035
            panel_w = 0.045 + 0.035 * max(0.0, (c.z - crotch_z) / (top_z - crotch_z))
            if band or abs(c.x) < panel_w:
                keep.add(f)
    for f in [f for f in bm.faces if f not in keep]:
        bm.faces.remove(f)
    for v in [v for v in bm.verts if not v.link_faces]:
        bm.verts.remove(v)
    for v in bm.verts:
        v.co += v.normal * 0.003
    nm = bpy.data.meshes.new("SAM_Fundoshi"); bm.to_mesh(nm); bm.free()
    for a in list(nm.color_attributes):
        nm.color_attributes.remove(a)
    ob = bpy.data.objects.new("SAM_Fundoshi", nm); coll.objects.link(ob)
    nm.polygons.foreach_set("use_smooth", [True] * len(nm.polygons))
    sol = ob.modifiers.new("Thickness", "SOLIDIFY"); sol.thickness = 0.0018; sol.offset = 1
    sub = ob.modifiers.new("Subdivision", "SUBSURF"); sub.levels = 1; sub.render_levels = 2
    m = mat_simple("M_Cotton_Sarashi", (0.78, 0.76, 0.70), 0.85, sheen=0.4)
    weave = m.node_tree.nodes.new("ShaderNodeTexWave")
    weave.inputs["Scale"].default_value = 900; weave.inputs["Distortion"].default_value = 2
    bump = m.node_tree.nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.15
    m.node_tree.links.new(weave.outputs["Fac"], bump.inputs["Height"])
    m.node_tree.links.new(bump.outputs[0], m.node_tree.nodes["Principled BSDF"].inputs["Normal"])
    nm.materials.append(m)
    return ob
