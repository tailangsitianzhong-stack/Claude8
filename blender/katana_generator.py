"""Procedural katana (uchigatana) generator for Blender 4.x.

Run inside Blender (Scripting workspace > Open > Run Script), or:
    blender --background --python katana_generator.py -- --out katana.blend

Builds a shinogi-zukuri blade with taper, sori (curvature), yokote/kissaki,
machi and nakago, plus habaki, seppa, tsuba, fuchi, tsuka, kashira and saya.
Units: metres (1 BU = 1 m). Blade lies along +X, edge (ha) faces -Z, tip at +X.
Real-world reference values come from knowledge/01_katana.md.
"""
import math
import sys

import bmesh
import bpy

# ---------------------------------------------------------------- parameters
P = dict(
    nagasa=0.70,        # blade length machi -> tip
    sori=0.018,         # curvature depth (chord to mune)
    moto_haba=0.032,    # width at base
    saki_haba=0.022,    # width at yokote
    moto_kasane=0.0075, # thickness at base
    saki_kasane=0.005,  # thickness near tip
    kissaki=0.035,      # kissaki length (yokote -> tip)
    nakago=0.22,        # tang length
    tsuka=0.26,         # handle length
    segments=60,        # sections along the blade
    hamon_height=0.30,  # hamon line as fraction of width from edge
)


def curve_z(x):
    """Centre-line rise so the chord-to-mune gap at mid-blade equals sori."""
    L = P["nagasa"]
    return 4.0 * P["sori"] * (x / L) ** 2 if x > 0 else 0.0


def section(w, t):
    """Shinogi-zukuri cross-section. Returns (u, y) with u from edge(0) to mune(w)."""
    return [
        (0.00 * w, 0.0),            # ha (edge)
        (0.40 * w, 0.42 * t),       # hira-ji with slight niku
        (0.72 * w, 0.50 * t),       # shinogi ridge
        (0.93 * w, 0.36 * t),       # shinogi-ji
        (1.00 * w, 0.0),            # iori-mune peak
        (0.93 * w, -0.36 * t),
        (0.72 * w, -0.50 * t),
        (0.40 * w, -0.42 * t),
    ]


def build_blade():
    L, K, n = P["nagasa"], P["kissaki"], P["segments"]
    yokote = L - K
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    rings = []
    for i in range(n + 1):
        x = L * i / n
        if x <= yokote:
            f = x / yokote
            w = P["moto_haba"] + (P["saki_haba"] - P["moto_haba"]) * f
            t = P["moto_kasane"] + (P["saki_kasane"] - P["moto_kasane"]) * f
        else:  # kissaki: edge sweeps up to meet the straight mune (fukura)
            s = (x - yokote) / K
            w = P["saki_haba"] * max(math.sqrt(max(1 - s * s, 0.0)), 0.002)
            t = P["saki_kasane"] * (1 - 0.85 * s)
        base_z = curve_z(x)
        mune_z = base_z + P["moto_haba"] / 2  # keep mune line continuous
        ring = []
        for u, y in section(w, t):
            ring.append(bm.verts.new((x, y, mune_z - w + u)))
        rings.append((ring, w))
    ring_len = len(rings[0][0])
    for i in range(n):
        a, b = rings[i][0], rings[i + 1][0]
        for j in range(ring_len):
            k = (j + 1) % ring_len
            face = bm.faces.new((a[j], a[k], b[k], b[j]))
            for loop in face.loops:
                v = loop.vert
                idx_ring = i if v in a else i + 1
                ring, w = rings[idx_ring]
                mune_z = curve_z(v.co.x) + P["moto_haba"] / 2
                rel = (v.co.z - (mune_z - w)) / max(w, 1e-6)  # 0 edge .. 1 mune
                loop[uv].uv = (v.co.x / L, rel)
    bm.faces.new(list(reversed(rings[0][0])))  # cap at machi (hidden by habaki)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new("Katana_Blade")
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new("Katana_Blade", me)
    for p in me.polygons:
        p.use_smooth = True
    return obj


def ellipse_cyl(name, length, ry, rz, x0, verts=32, taper=1.0):
    """Cylinder along +X from x0 to x0+length with elliptical section."""
    bm = bmesh.new()
    rings = []
    for x, s in ((x0, 1.0), (x0 + length, taper)):
        rings.append([bm.verts.new((x, ry * s * math.cos(a), rz * s * math.sin(a)))
                      for a in (2 * math.pi * i / verts for i in range(verts))])
    for j in range(verts):
        k = (j + 1) % verts
        bm.faces.new((rings[0][j], rings[0][k], rings[1][k], rings[1][j]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    for p in me.polygons:
        p.use_smooth = True
    return o


# ---------------------------------------------------------------- materials
def mat_principled(name, color, metallic, rough, coat=0.0, sheen=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Roughness"].default_value = rough
    if "Coat Weight" in b.inputs:
        b.inputs["Coat Weight"].default_value = coat
    if "Sheen Weight" in b.inputs:
        b.inputs["Sheen Weight"].default_value = sheen
    return m


def mat_blade():
    """Polished steel with a misty hamon band on the edge side (UV v < hamon)."""
    m = bpy.data.materials.new("Blade_Steel_Hamon")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Metallic"].default_value = 1.0
    uvn = nt.nodes.new("ShaderNodeUVMap")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 40.0
    wave = nt.nodes.new("ShaderNodeMath"); wave.operation = "MULTIPLY_ADD"
    wave.inputs[1].default_value = 0.12           # gunome-like undulation amount
    wave.inputs[2].default_value = P["hamon_height"] - 0.06
    ramp = nt.nodes.new("ShaderNodeValToRGB")      # soft nioiguchi transition
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[1].position = 0.04
    sub = nt.nodes.new("ShaderNodeMath"); sub.operation = "SUBTRACT"
    mix_col = nt.nodes.new("ShaderNodeMix"); mix_col.data_type = "RGBA"
    # ShaderNodeMix sockets: 6/7 = colour A/B, output 2 = colour result
    mix_col.inputs[6].default_value = (0.85, 0.86, 0.87, 1)   # hardened edge (whitish)
    mix_col.inputs[7].default_value = (0.55, 0.57, 0.60, 1)   # ji-gane (darker)
    mix_r = nt.nodes.new("ShaderNodeMapRange")
    mix_r.inputs["To Min"].default_value = 0.30   # misty edge
    mix_r.inputs["To Max"].default_value = 0.08   # mirror-polished ji
    L = nt.links
    L.new(uvn.outputs["UV"], sep.inputs["Vector"])
    L.new(uvn.outputs["UV"], noise.inputs["Vector"])
    L.new(noise.outputs["Fac"], wave.inputs[0])
    L.new(sep.outputs["Y"], sub.inputs[0])
    L.new(wave.outputs[0], sub.inputs[1])
    L.new(sub.outputs[0], ramp.inputs["Fac"])
    L.new(ramp.outputs["Color"], mix_col.inputs[0])
    L.new(ramp.outputs["Color"], mix_r.inputs["Value"])
    L.new(mix_col.outputs[2], bsdf.inputs["Base Color"])
    L.new(mix_r.outputs["Result"], bsdf.inputs["Roughness"])
    return m


def assign(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)


# ---------------------------------------------------------------- assembly
def build(with_saya=True):
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    col = bpy.context.collection
    blade = build_blade()
    col.objects.link(blade)
    bevel = blade.modifiers.new("EdgeHighlight", "BEVEL")
    bevel.width, bevel.segments, bevel.limit_method = 0.0002, 2, "ANGLE"
    wn = blade.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")
    wn.keep_sharp = True

    W, T = P["moto_haba"], P["moto_kasane"]
    zc = P["moto_haba"] / 2 - W / 2  # blade centre height at machi
    nak = ellipse_cyl("Katana_Nakago", P["nakago"], T * 0.45, W * 0.42, -P["nakago"], 4, 0.7)
    nak.location.z = zc
    habaki = ellipse_cyl("Katana_Habaki", 0.032, T * 0.9, W * 0.58, -0.002, 24, 0.92)
    habaki.location.z = zc
    seppa_a = ellipse_cyl("Katana_Seppa_A", 0.0015, 0.016, 0.024, -0.0035, 32)
    tsuba = ellipse_cyl("Katana_Tsuba", 0.005, 0.038, 0.041, -0.0085, 48)
    seppa_b = ellipse_cyl("Katana_Seppa_B", 0.0015, 0.016, 0.024, -0.010, 32)
    fuchi = ellipse_cyl("Katana_Fuchi", 0.014, 0.0135, 0.0175, -0.024, 32)
    tsuka = ellipse_cyl("Katana_Tsuka", P["tsuka"] - 0.03, 0.0125, 0.0165, -0.024 - (P["tsuka"] - 0.03), 32)
    # slight waist of the tsuka (narrower in the middle)
    for v in tsuka.data.vertices:
        mid = -0.024 - (P["tsuka"] - 0.03) / 2
        k = 1 - 0.06 * math.exp(-((v.co.x - mid) / 0.06) ** 2)
        v.co.y *= k; v.co.z *= k
    kashira = ellipse_cyl("Katana_Kashira", 0.016, 0.0128, 0.0168, -P["tsuka"] - 0.01, 32, 0.8)
    for o in (seppa_a, tsuba, seppa_b, fuchi, tsuka, kashira):
        o.location.z = zc

    steel = mat_blade()
    iron = mat_principled("Tsuba_Iron", (0.06, 0.05, 0.045), 0.8, 0.6)
    copper_gold = mat_principled("Habaki_Gold", (0.83, 0.62, 0.25), 1.0, 0.3)
    shakudo = mat_principled("Shakudo", (0.05, 0.04, 0.05), 1.0, 0.35)
    ito = mat_principled("Tsuka_Ito_Silk", (0.03, 0.03, 0.05), 0.0, 0.7, sheen=0.6)
    nakago_rust = mat_principled("Nakago_Rust", (0.12, 0.07, 0.04), 0.6, 0.8)
    lacquer = mat_principled("Saya_Black_Urushi", (0.01, 0.01, 0.01), 0.0, 0.25, coat=1.0)
    assign(blade, steel); assign(nak, nakago_rust); assign(habaki, copper_gold)
    for o in (seppa_a, seppa_b):
        assign(o, copper_gold)
    assign(tsuba, iron); assign(fuchi, shakudo); assign(kashira, shakudo); assign(tsuka, ito)

    parts = [blade, nak, habaki, seppa_a, tsuba, seppa_b, fuchi, tsuka, kashira]
    root = bpy.data.objects.new("Katana", None)
    col.objects.link(root)
    for o in parts:
        o.parent = root

    if with_saya:
        # simple saya: offset blade hull following the sori, separate object (hidden)
        saya = blade.copy(); saya.data = blade.data.copy(); saya.name = "Katana_Saya"
        col.objects.link(saya)
        saya.modifiers.clear()
        for v in saya.data.vertices:
            v.co.y *= 2.4
        sol = saya.modifiers.new("Thickness", "SOLIDIFY")
        sol.thickness, sol.offset = 0.004, 1.0
        saya.data.materials.clear(); saya.data.materials.append(lacquer)
        saya.location.x = 0.03
        saya.parent = root
        saya.hide_viewport = saya.hide_render = True
    return root


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    build()
    if "--out" in argv:
        bpy.ops.wm.save_as_mainfile(filepath=argv[argv.index("--out") + 1])


if __name__ == "__main__":
    main()
