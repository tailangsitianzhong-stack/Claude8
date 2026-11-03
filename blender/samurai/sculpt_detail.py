"""Anatomical detail sculpting for the samurai body (Multires workflow).

The rig-friendly base mesh is kept untouched. Detail is computed on a
subdivided copy (same topology as Multires level N) with numpy and transferred
back with `multires_reshape`, so the result is a standard Multires sculpt that
can be edited by hand in Sculpt Mode and baked to normal maps for a game engine.

Landmarks come from the CC0 MakeHuman joint helpers (`joints`) and from the
face landmarks computed in lookdev.compute_masks (`masks`).
Units: metres, Z up, -Y front, +X = character's left.
"""
import math
import random

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

MM = 0.001


class Sculptor:
    def __init__(self, dense):
        me = dense.data
        n = len(me.vertices)
        self.obj = dense
        self.P = np.empty(n * 3, dtype=np.float64); me.vertices.foreach_get("co", self.P)
        self.P = self.P.reshape(n, 3)
        self.N = np.empty(n * 3, dtype=np.float64); me.vertices.foreach_get("normal", self.N)
        self.N = self.N.reshape(n, 3)
        self.D = np.zeros(n, dtype=np.float64)        # displacement along the normal (m)
        self.Z = np.zeros((n, 3), dtype=np.float64)   # free-direction displacement (m)
        self.bvh = BVHTree.FromPolygons([tuple(p) for p in self.P], [list(p.vertices) for p in me.polygons])
        self.rng = random.Random(1274)
        self.log = []
        self.probes = []          # (name, vertex index) for debugging feature placement
        self.probe_log = []

    def add_probe(self, name, point):
        i = int(((self.P - np.array(point)) ** 2).sum(1).argmin())
        self.probes.append((name, i))

    def _probe(self, feature, before):
        for pname, i in self.probes:
            d = (self.D[i] - before[i]) * 1000
            if abs(d) > 0.05:
                self.probe_log.append((pname, feature, round(d, 2)))

    # ------------------------------------------------------------- surface queries
    def hit(self, origin, direction, maxd=0.5):
        h = self.bvh.ray_cast(Vector(origin), Vector(direction).normalized(), maxd)
        return h[0]

    def onto(self, origin, direction):
        """Surface point reached from `origin` (inside the body) going along `direction`."""
        p = self.hit(origin, direction)
        return p if p is not None else Vector(origin)

    def from_out(self, target, direction, back=0.3):
        """Surface point hit when coming from outside along -direction towards target."""
        d = Vector(direction).normalized()
        p = self.hit(Vector(target) + d * back, -d, back * 2)
        return p if p is not None else Vector(target)

    # ------------------------------------------------------------- primitives
    def _mask(self, facing):
        if facing is None:
            return 1.0
        d, lo = facing
        d = np.array(Vector(d).normalized())
        f = self.N @ d
        return np.clip((f - lo) / max(1e-6, 1 - lo), 0, 1)

    def blob(self, c, sigma, amp_mm, facing=None, name=""):
        c = np.array(c)
        d2 = ((self.P - c) ** 2).sum(1)
        w = np.exp(-d2 / (sigma * sigma)) * self._mask(facing)
        before = self.D.copy() if self.probes else None
        self.D += amp_mm * MM * w
        if self.probes: self._probe(name, before)
        self.log.append(("blob", name, amp_mm))

    def line(self, pts, sigma, amps_mm, facing=None, name=""):
        """Ridge (+) or groove (-) along a polyline; amps per point (interpolated)."""
        pts = [np.array(p) for p in pts]
        if not isinstance(amps_mm, (list, tuple)):
            amps_mm = [amps_mm] * len(pts)
        best = np.zeros(len(self.P))
        sign = 1 if sum(amps_mm) >= 0 else -1
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            ab = b - a; L2 = float(ab @ ab) or 1e-12
            t = np.clip(((self.P - a) @ ab) / L2, 0, 1)
            C = a + t[:, None] * ab
            d2 = ((self.P - C) ** 2).sum(1)
            amp = np.abs(amps_mm[i] + (amps_mm[i + 1] - amps_mm[i]) * t)
            best = np.maximum(best, amp * np.exp(-d2 / (sigma * sigma)))
        before = self.D.copy() if self.probes else None
        self.D += sign * best * MM * self._mask(facing)
        if self.probes: self._probe(name, before)
        self.log.append(("line", name, amps_mm[0]))

    def move(self, c, sigma, vec_mm, facing=None):
        c = np.array(c)
        w = np.exp(-((self.P - c) ** 2).sum(1) / (sigma * sigma)) * self._mask(facing)
        self.Z += w[:, None] * np.array(vec_mm) * MM

    # ------------------------------------------------------------- apply
    def apply(self, smooth_iters=1):
        me = self.obj.data
        D = self.D
        if smooth_iters:
            # light Laplacian smoothing of the displacement field (removes faceting)
            ev = np.empty(len(me.edges) * 2, dtype=np.int64); me.edges.foreach_get("vertices", ev)
            ev = ev.reshape(-1, 2)
            deg = np.bincount(ev.ravel(), minlength=len(D)).astype(np.float64)
            for _ in range(smooth_iters):
                acc = np.zeros_like(D)
                np.add.at(acc, ev[:, 0], D[ev[:, 1]]); np.add.at(acc, ev[:, 1], D[ev[:, 0]])
                D = 0.5 * D + 0.5 * np.where(deg > 0, acc / np.maximum(deg, 1), D)
        newP = self.P + self.N * D[:, None] + self.Z
        me.vertices.foreach_set("co", newP.ravel())
        me.update()
        return float(np.abs(D).max())


# =================================================================== anatomy
def _side(v, s):
    """Mirror a left-side vector (x>0) to side s (+1 left, -1 right)."""
    return Vector((v[0] * s, v[1], v[2]))


def sculpt_anatomy(sc, J, masks):
    rng = sc.rng
    j = lambda n: J[n].copy()
    up, front, back = Vector((0, 0, 1)), Vector((0, -1, 0)), Vector((0, 1, 0))

    for s, tag in ((1, "l"), (-1, "r")):
        k = lambda: 1.0 + rng.uniform(-0.12, 0.12)        # natural left/right differences
        out = Vector((s, 0, 0))
        sh, el, wr = j(f"joint-{tag}-shoulder"), j(f"joint-{tag}-elbow"), j(f"joint-{tag}-hand")
        sc_j, scap = j(f"joint-{tag}-clavicle"), j(f"joint-{tag}-scapula")
        hip, kn, an = j(f"joint-{tag}-upper-leg"), j(f"joint-{tag}-knee"), j(f"joint-{tag}-ankle")
        neck, pel = j("joint-neck"), j("joint-pelvis")
        sp1 = j("joint-spine-1")

        # ---------------- neck / clavicle
        notch = sc.from_out(Vector((0.012 * s, 0, sc_j.z + 0.005)), front)
        acro = sc.from_out(sh + Vector((0.015 * s, 0, 0.045)), up)
        clav = [sc.from_out(sc_j.lerp(sh + Vector((0, 0, 0.04)), t) + Vector((0, 0, 0.012)), (front + up * 0.8))
                for t in np.linspace(0.05, 0.95, 8)]
        sc.line(clav, 0.0055, 2.2 * k(), facing=(front + up * 0.5, -0.1), name="clavicle")
        fossa = [p + Vector((0, 0.012, 0.016)) for p in clav[2:7]]
        sc.line(fossa, 0.009, -1.8 * k(), facing=(up + front, 0.0), name="supraclavicular fossa")
        mast = sc.from_out(j("joint-head") + Vector((0.045 * s, 0.035, -0.035)), out)
        scm = [sc.from_out(mast.lerp(notch, t) + Vector((0, -0.01 * math.sin(math.pi * t), 0)),
                           (out * 0.6 + front)) for t in np.linspace(0, 1, 9)]
        sc.line(scm, 0.0075, [1.0, 1.8, 2.0, 2.0, 1.8, 1.6, 1.4, 1.0, 0.6], facing=(out + front, -0.2),
                name="sternocleidomastoid")
        # trapezius edge from neck to acromion (back-up)
        trap = [sc.from_out(neck.lerp(acro, t) + Vector((0, 0.02, 0.02)), up + back * 0.6) for t in np.linspace(0.1, 0.9, 7)]
        sc.line(trap, 0.012, 1.2 * k(), facing=(up + back * 0.3, 0.0), name="trapezius")

        # ---------------- chest
        pec_c = sc.from_out(Vector((0.075 * s, 0, sh.z - 0.11)), front)
        sc.blob(pec_c, 0.035, 1.6 * k(), facing=(front, 0.2), name="pectoral mass")
        pec_edge = [sc.from_out(Vector((x * s, 0, sh.z - 0.165 + 0.06 * (x / 0.15) ** 2)), front)
                    for x in np.linspace(0.012, 0.15, 9)]
        sc.line(pec_edge, 0.0065, [-1.2, -2.0, -2.4, -2.4, -2.2, -2.0, -1.8, -1.6, -1.2], facing=(front, 0.1),
                name="pectoral lower border")
        delto_pec = [sc.from_out(Vector((x * s, 0, sh.z - 0.02 - 0.5 * (x - 0.13))), front + out * 0.4)
                     for x in np.linspace(0.13, 0.17, 4)]
        sc.line(delto_pec, 0.006, -1.4, facing=(front, 0.0), name="deltopectoral groove")

        # ---------------- abdomen / pelvis connection
        xiph_z = sh.z - 0.25
        navel_z = pel.z + 0.10
        semil = [sc.from_out(Vector((s * (0.075 - 0.03 * t), 0, xiph_z - t * (xiph_z - (pel.z - 0.02)))), front)
                 for t in np.linspace(0, 1, 9)]
        sc.line(semil, 0.007, -1.0 * k(), facing=(front, 0.2), name="linea semilunaris")
        for zz in np.linspace(xiph_z - 0.035, navel_z + 0.02, 3):
            seg = [sc.from_out(Vector((x * s, 0, zz)), front) for x in np.linspace(0.006, 0.055, 4)]
            sc.line(seg, 0.004, -0.55, facing=(front, 0.4), name="tendinous intersection")
        cost = [sc.from_out(Vector((s * (0.02 + 0.10 * t), 0, xiph_z + 0.02 - 0.09 * t)), front + out * t)
                for t in np.linspace(0, 1, 7)]
        sc.line(cost[:5], 0.012, [-0.15, -0.3, -0.35, -0.3, -0.15], facing=(front, 0.2), name="costal margin")
        asis = sc.from_out(Vector((0.105 * s, 0, pel.z + 0.06)), front + out * 0.5)
        pubic = sc.from_out(Vector((0.025 * s, 0, pel.z - 0.065)), front)
        ing = [asis.lerp(pubic, t) + (Vector((0, -0.004, 0)) * math.sin(math.pi * t)) for t in np.linspace(0, 1, 8)]
        ing = [sc.from_out(p, front + out * 0.3) for p in ing]
        sc.line(ing, 0.0075, -2.0 * k(), facing=(front, -0.1), name="inguinal line")
        sc.blob(sc.from_out(Vector((0.115 * s, 0, pel.z + 0.10)), out + front * 0.3), 0.025, 1.0,
                facing=(out, -0.2), name="external oblique")

        # ---------------- back
        med_top = sc.from_out(Vector((0.065 * s, 0, sh.z - 0.02)), back)
        med_bot = sc.from_out(Vector((0.085 * s, 0, sh.z - 0.165)), back)
        sc.line([med_top.lerp(med_bot, t) for t in np.linspace(0, 1, 6)], 0.007, 1.4 * k(),
                facing=(back, 0.2), name="scapula medial border")
        sc.blob(med_bot, 0.010, 1.3, facing=(back, 0.2), name="scapula inferior angle")
        sspine = [sc.from_out(med_top.lerp(acro, t) + Vector((0, 0, -0.012 * (1 - t))), back + up * 0.3)
                  for t in np.linspace(0, 1, 7)]
        sc.line(sspine, 0.006, 1.0, facing=(back, -0.1), name="spine of scapula")
        sc.blob(sc.from_out(Vector((0.10 * s, 0, sh.z - 0.09)), back), 0.03, 1.1, facing=(back, 0.2),
                name="infraspinatus")
        lat = [sc.from_out(med_bot.lerp(sh + Vector((0.02 * s, 0.03, -0.09)), t), back + out * 0.6)
               for t in np.linspace(0, 1, 6)]
        sc.line(lat, 0.007, -0.9, facing=(back + out, 0.0), name="teres/lat edge")
        erec = [sc.from_out(Vector((0.032 * s, 0, z)), back) for z in np.linspace(pel.z + 0.0, sp1.z, 8)]
        sc.line(erec, 0.012, [2.4, 2.4, 2.2, 1.8, 1.4, 1.0, 0.8, 0.6], facing=(back, 0.3), name="erector spinae")
        sc.blob(sc.from_out(Vector((0.04 * s, 0, pel.z - 0.02)), back), 0.007, -1.6, facing=(back, 0.4),
                name="sacral dimple")

        # ---------------- upper arm (A-pose): directions perpendicular to the bone
        ua = (el - sh).normalized()
        fr = (front - ua * front.dot(ua)).normalized()
        lt = (out - ua * out.dot(ua)).normalized()
        def arm_line(a, b, d, t0, t1, n=7):
            return [sc.onto(a.lerp(b, t), d) for t in np.linspace(t0, t1, n)]
        sc.blob(sc.onto(sh + ua * 0.03, (lt + up * 0.4).normalized()), 0.032, 2.2 * k(), facing=(lt, -0.3),
                name="deltoid")
        sc.line(arm_line(sh, el, fr, 0.35, 0.85), 0.018, [0.6, 1.8, 2.6, 2.8, 2.4, 1.6, 0.6], facing=(fr, 0.0),
                name="biceps")
        sc.line(arm_line(sh, el, -fr, 0.2, 0.8), 0.018, [0.6, 1.6, 2.2, 2.2, 1.8, 1.0, 0.4], facing=(-fr, 0.0),
                name="triceps")
        sc.line(arm_line(sh, el, lt, 0.45, 0.85), 0.006, -1.1, facing=(lt, 0.0), name="lateral intermuscular groove")
        sc.line(arm_line(sh, el, -lt, 0.35, 0.85), 0.006, -0.9, facing=(-lt, 0.0), name="medial groove")
        sc.line(arm_line(sh, el, lt, 0.40, 0.55, 3), 0.007, -1.2, facing=(lt, 0.0), name="deltoid insertion")
        sc.blob(sc.onto(el, -fr), 0.009, 1.8, facing=(-fr, 0.2), name="olecranon")
        sc.blob(sc.onto(el, -lt), 0.008, 1.2, facing=(-lt, 0.0), name="medial epicondyle")
        # ---------------- forearm
        fa = (wr - el).normalized()
        ffr = (front - fa * front.dot(fa)).normalized()
        flt = (out - fa * out.dot(fa)).normalized()
        sc.line(arm_line(el, wr, (flt + ffr * 0.5).normalized(), 0.0, 0.5), 0.016,
                [1.8, 2.8, 2.6, 2.0, 1.2, 0.6, 0.2], facing=(flt + ffr * 0.5, -0.1), name="brachioradialis/extensors")
        sc.line(arm_line(el, wr, (-flt + ffr * 0.6).normalized(), 0.05, 0.55), 0.016,
                [0.8, 2.0, 2.2, 1.8, 1.2, 0.6, 0.2], facing=(-flt + ffr * 0.6, -0.1), name="forearm flexors")
        sc.line(arm_line(el, wr, ffr, 0.75, 0.98, 4), 0.007, -0.7, facing=(ffr, 0.2), name="wrist flat (palmar)")
        sc.line(arm_line(el, wr, -ffr, 0.75, 0.98, 4), 0.007, -0.6, facing=(-ffr, 0.2), name="wrist flat (dorsal)")
        sc.blob(sc.onto(wr - fa * 0.012, (-flt - ffr * 0.6).normalized()), 0.006, 1.4, name="ulnar styloid")

        # ---------------- thigh
        th = (kn - hip).normalized()
        tfr = (front - th * front.dot(th)).normalized()
        tlt = (out - th * out.dot(th)).normalized()
        sc.line(arm_line(hip, kn, (-tlt + tfr * 0.9).normalized(), 0.68, 0.95, 5), 0.016,
                [0.8, 2.4, 3.2, 2.8, 1.2], facing=(-tlt + tfr, -0.1), name="vastus medialis")
        sc.line(arm_line(hip, kn, (tlt + tfr * 0.3).normalized(), 0.25, 0.80), 0.022,
                [0.6, 1.6, 2.0, 2.0, 1.6, 1.0, 0.4], facing=(tlt, -0.2), name="vastus lateralis")
        sc.line(arm_line(hip, kn, tfr, 0.2, 0.75), 0.02, [0.4, 1.2, 1.6, 1.6, 1.2, 0.8, 0.3], facing=(tfr, 0.0),
                name="rectus femoris")
        sc.line(arm_line(hip, kn, (tlt - tfr * 0.4).normalized(), 0.35, 0.92), 0.007, -1.1,
                facing=(tlt, -0.1), name="iliotibial band")
        sc.line(arm_line(hip, kn, (-tlt - tfr * 0.3).normalized(), 0.05, 0.4, 5), 0.02, 0.8, name="adductors")
        # ---------------- knee
        pat = sc.onto(kn + th * -0.015, tfr)
        sc.blob(pat, 0.016, 2.2, facing=(tfr, 0.2), name="patella")
        sh_ = (an - kn).normalized()
        sfr = (front - sh_ * front.dot(sh_)).normalized()
        slt = (out - sh_ * out.dot(sh_)).normalized()
        tub = sc.onto(kn + sh_ * 0.07, sfr)
        sc.line([pat, tub], 0.005, 0.9, facing=(sfr, 0.3), name="patellar tendon")
        for side_d in (slt, -slt):
            sc.blob(sc.onto(kn + sh_ * 0.03, (sfr + side_d * 0.8).normalized()), 0.010, -1.4,
                    facing=(sfr + side_d * 0.5, 0.0), name="knee hollow")
        sc.line(arm_line(hip, kn, -tfr, 0.82, 1.0, 4), 0.012, -1.4, facing=(-tfr, 0.2), name="popliteal hollow")
        for side_d in (tlt, -tlt):
            sc.line(arm_line(hip, kn, (-tfr + side_d * 0.7).normalized(), 0.65, 0.98, 4), 0.006, 1.0,
                    facing=(-tfr + side_d * 0.5, 0.0), name="hamstring tendon")
        # ---------------- calf / shin
        sc.line(arm_line(kn, an, (-sfr - slt * 0.6).normalized(), 0.12, 0.48, 6), 0.018,
                [1.0, 2.8, 3.2, 2.8, 1.8, 0.6], facing=(-sfr - slt * 0.5, -0.1), name="gastrocnemius medial")
        sc.line(arm_line(kn, an, (-sfr + slt * 0.6).normalized(), 0.10, 0.40, 6), 0.016,
                [0.8, 2.2, 2.4, 2.0, 1.2, 0.4], facing=(-sfr + slt * 0.5, -0.1), name="gastrocnemius lateral")
        for side_d in (slt, -slt):
            sc.line(arm_line(kn, an, (-sfr + side_d * 0.9).normalized(), 0.72, 0.96, 4), 0.006, -1.6,
                    facing=(-sfr + side_d, -0.1), name="achilles side groove")
        sc.line(arm_line(kn, an, (sfr + slt * 0.2).normalized(), 0.1, 0.85), 0.004, 0.7, facing=(sfr, 0.3),
                name="tibial crest")
        sc.line(arm_line(kn, an, (sfr + slt * 0.8).normalized(), 0.1, 0.6, 5), 0.012, 1.1,
                facing=(sfr + slt, 0.0), name="tibialis anterior")
        # ---------------- ankle / foot
        med_m = sc.onto(an + Vector((0, 0, 0.003)), -slt)
        lat_m = sc.onto(an + Vector((0, 0.006, -0.010)), slt)
        sc.blob(med_m, 0.009, 2.4, facing=(-slt, 0.0), name="medial malleolus")
        sc.blob(lat_m, 0.009, 2.6, facing=(slt, 0.0), name="lateral malleolus")
        f1, f2 = j(f"joint-{tag}-foot-1"), j(f"joint-{tag}-foot-2")
        heel = Vector((an.x, an.y + 0.045, 0.02))
        # arch: lift the medial sole between heel and ball (free displacement, upward)
        for t, lift in ((0.35, 4.0), (0.5, 6.0), (0.65, 5.0), (0.8, 2.5)):
            c = heel.lerp(f1, t) + Vector((-0.022 * s, 0, -0.012))
            sc.move(c, 0.018, (0, 0, lift), facing=((0, 0, -1), 0.2))
        sc.blob(sc.from_out(heel + Vector((0, 0.01, 0.02)), back), 0.018, 1.2, name="heel roundness")
        for f in range(1, 6):
            t1 = J.get(f"joint-{tag}-toe-{f}-1")
            if t1 is None:
                continue
            dors = [sc.from_out(an.lerp(t1, t) + Vector((0, 0, 0.01)), up + front * 0.3) for t in np.linspace(0.25, 0.9, 5)]
            sc.line(dors, 0.0028, 0.55, facing=(up, 0.3), name="extensor tendon")
            sc.blob(sc.from_out(t1, up), 0.005, 0.9, facing=(up, 0.3), name="toe knuckle")

        # ---------------- hand
        sculpt_hand(sc, J, tag, s)
        sculpt_toenails(sc, J, tag, s)

    neck, pel = J["joint-neck"], J["joint-pelvis"]
    sh_z = J["joint-l-shoulder"].z
    spine_pts = [sc.from_out(Vector((0, 0, z)), back) for z in np.linspace(pel.z - 0.03, neck.z - 0.01, 12)]
    sc.line(spine_pts, 0.0065, [-1.6, -2.6, -3.0, -3.0, -2.6, -2.2, -2.0, -1.8, -1.6, -1.2, -0.6, 0.0],
            facing=(back, 0.3), name="spinal groove")
    sc.blob(sc.from_out(Vector((0, 0, neck.z - 0.025)), back + up * 0.4), 0.009, 1.8, facing=(back, 0.2),
            name="C7 vertebra prominens")
    alba = [sc.from_out(Vector((0, 0, z)), front) for z in np.linspace(sh_z - 0.25, pel.z + 0.10, 8)]
    sc.line(alba, 0.0045, -1.0, facing=(front, 0.4), name="linea alba")
    return sc


def sculpt_toenails(sc, J, tag, s):
    up = Vector((0, 0, 1))
    for f in range(1, 6):
        ks = [k for k in range(1, 5) if J.get(f"joint-{tag}-toe-{f}-{k}") is not None]
        if len(ks) < 2:
            continue
        a, b = J[f"joint-{tag}-toe-{f}-{ks[-2]}"], J[f"joint-{tag}-toe-{f}-{ks[-1]}"]
        u = (b - a).normalized()
        dd = (up - u * up.dot(u)).normalized()
        side = u.cross(dd).normalized()
        L = (b - a).length
        axis_c = a + (b - a) * 0.6
        top = sc.onto(axis_c, dd)
        r = (top - axis_c).length
        rel = sc.P - np.array(top)
        al = rel @ np.array(u); lt_ = rel @ np.array(side); dz = rel @ np.array(dd)
        hl, hw = 0.5 * L * (1.2 if f == 1 else 1.0), 0.80 * r
        ell = (lt_ / hw) ** 2 + (np.clip(-al, 0, None) / hl) ** 2 + (np.clip(al, 0, None) / (hl * 1.15)) ** 4
        on_top = dz > -0.5 * r
        sc.D += 0.40 * MM * np.clip((1.0 - ell) / 0.12, 0, 1) * on_top
        sc.D -= 0.30 * MM * np.exp(-((ell - 1.0) / 0.10) ** 2) * on_top * (al < 0.2 * hl)
        sc.log.append(("toenail", f"{tag}{f}", 0.4))


def sculpt_hand(sc, J, tag, s):
    j = lambda f, k: J.get(f"joint-{tag}-finger-{f}-{k}")
    wr = J[f"joint-{tag}-hand"]
    if not j(2, 1) or not j(5, 1):
        return
    lateral = (j(2, 1) - j(5, 1)).normalized()
    fdir = (j(3, 4) - j(3, 1)).normalized()
    dorsal = fdir.cross(lateral).normalized()
    if dorsal.dot(Vector((s, 0, 0.6))) < 0:
        dorsal = -dorsal
    # knuckles (MCP) and finger joints, dorsal side
    for f in range(2, 6):
        sc.blob(sc.onto(j(f, 1), dorsal), 0.0065, 1.6, facing=(dorsal, 0.2), name="MCP knuckle")
        for k_, a in ((2, 0.8), (3, 0.5)):
            sc.blob(sc.onto(j(f, k_), dorsal), 0.004, a, facing=(dorsal, 0.3), name="finger joint")
        # extensor tendons on the back of the hand
        sc.line([sc.onto(wr.lerp(j(f, 1), t), dorsal) for t in np.linspace(0.25, 0.9, 5)], 0.0025, 0.6,
                facing=(dorsal, 0.4), name="hand extensor tendon")
        # palm-side flexion creases at finger joints
        for k_ in (1, 2, 3):
            sc.blob(sc.onto(j(f, k_) + (j(f, min(k_ + 1, 4)) - j(f, k_)) * 0.12, -dorsal), 0.0022, -0.45,
                    facing=(-dorsal, 0.3), name="flexion crease")
    # thenar / hypothenar
    sc.blob(sc.onto(j(1, 1).lerp(wr, 0.5), (-dorsal + lateral * 0.5).normalized()), 0.014, 1.4,
            facing=(-dorsal, -0.2), name="thenar")
    sc.blob(sc.onto(j(5, 1).lerp(wr, 0.55), (-dorsal - lateral * 0.5).normalized()), 0.012, 0.9,
            facing=(-dorsal, -0.2), name="hypothenar")
    # nails: raised plate with a soft cuticle groove, located from the joint chain
    for f in range(1, 6):
        a, b = j(f, 3), j(f, 4)
        if not a or not b:
            continue
        u = (b - a).normalized()
        dd = dorsal if f > 1 else (0.35 * dorsal + lateral * (1 if s > 0 else 1)).normalized()
        dd = (dd - u * dd.dot(u)).normalized()
        side = u.cross(dd).normalized()
        L = (b - a).length
        axis_c = a + (b - a) * 0.62
        top = sc.onto(axis_c, dd)
        r = (top - axis_c).length
        C = np.array(top)
        rel = sc.P - C
        al = rel @ np.array(u); lt_ = rel @ np.array(side); dz = rel @ np.array(dd)
        half_l, half_w = 0.55 * L, 0.86 * r
        # rounded proximal (cuticle) end, straight-ish distal edge
        ell = (lt_ / half_w) ** 2 + (np.clip(-al, 0, None) / half_l) ** 2 + (np.clip(al, 0, None) / (half_l * 1.2)) ** 4
        on_top = dz > -0.55 * r
        plate = np.clip((1.0 - ell) / 0.12, 0, 1) * on_top
        sc.D += 0.45 * MM * plate
        groove = np.exp(-((ell - 1.0) / 0.10) ** 2) * on_top * (al < 0.2 * half_l)
        sc.D -= 0.35 * MM * groove
        sc.log.append(("nail", f"{tag}{f}", 0.32))


def sculpt_face(sc, J, masks, eyes):
    rng = sc.rng
    front, up = Vector((0, -1, 0)), Vector((0, 0, 1))
    mouth, nose, chin = masks["mouth"], masks["nose_base"], masks["chin"]
    eye = {s_: c for s_, c, r in eyes}
    for s, tag in ((1, "L"), (-1, "R")):
        k = lambda: 1.0 + rng.uniform(-0.18, 0.18)            # facial asymmetry
        dz = rng.uniform(-0.0008, 0.0008)
        ec = eye[tag]
        out = Vector((s, 0, 0))
        # nasolabial fold: nose wing -> past the mouth corner
        wing = sc.from_out(Vector((0.019 * s, 0, nose.z + 0.004)), front + out * 0.4)
        corner = sc.from_out(Vector((0.031 * s, 0, mouth.z - 0.012)), front + out * 0.3)
        nl = [sc.from_out(wing.lerp(corner, t) + Vector((0.004 * s * math.sin(math.pi * t), 0, 0)), front + out * 0.3)
              for t in np.linspace(0, 1, 7)]
        sc.line(nl, 0.0032, [-0.3, -0.55, -0.6, -0.55, -0.4, -0.3, -0.1], facing=(front, -0.2), name="nasolabial fold")
        sc.line([p + Vector((0.006 * s, 0.002, 0)) for p in nl[1:6]], 0.006, 0.55 * k(), facing=(front, -0.1),
                name="cheek mass over fold")
        # upper lid crease (low, Japanese "okubutae"-like, fading inward)
        crease = [sc.from_out(ec + Vector((s * x, 0, 0.0095 + 0.003 * (1 - (x / 0.013) ** 2))), front + up * 0.3)
                  for x in np.linspace(-0.008, 0.015, 7)]
        sc.line(crease, 0.0013, [-0.05, -0.15, -0.3, -0.4, -0.4, -0.35, -0.2], facing=(front, 0.0), name="lid crease")
        # brow ridge and temple
        sc.blob(sc.from_out(ec + Vector((0.006 * s, 0, 0.024 + dz)), front), 0.011, 1.1 * k(), facing=(front, 0.0),
                name="brow ridge")
        sc.blob(sc.from_out(ec + Vector((0.040 * s, 0.045, 0.028)), out), 0.012, -1.5 * k(), facing=(out, 0.0),
                name="temple hollow")
        # tear trough / infraorbital
        tt = [sc.from_out(ec + Vector((s * x, 0, -0.0135 - 0.004 * (x / 0.02))), front)
              for x in np.linspace(-0.012, 0.012, 5)]
        sc.line(tt, 0.003, -0.45, facing=(front, 0.0), name="tear trough")
        # zygomatic: ridge from below outer canthus back toward the ear, hollow underneath
        zy = [sc.from_out(ec + Vector((s * (0.02 + 0.035 * t), 0.012 + 0.05 * t, -0.022 + 0.008 * t)), front + out * (0.6 + t))
              for t in np.linspace(0, 1, 7)]
        sc.line(zy, 0.0055, 1.2 * k(), facing=(front + out, -0.2), name="zygomatic ridge")
        sc.line([p + Vector((0, 0.004, -0.017)) for p in zy[1:6]], 0.010, -0.75 * k(), facing=(front + out, -0.2),
                name="buccal hollow")
        # mandible border + submandibular shadow
        angle = sc.from_out(Vector((0.058 * s, ec.y + 0.085, mouth.z - 0.028)), out + Vector((0, 0, -0.4)))
        jaw = [sc.from_out(Vector((0.012 * s, 0, chin.z + 0.004)).lerp(angle, t), (front * (1 - t) + out * t - up * 0.5))
               for t in np.linspace(0, 1, 9)]
        sc.line(jaw, 0.004, 0.9 * k(), facing=(-up + out * 0.3, -0.3), name="jawline")
        sc.line([p + Vector((0, 0.006, -0.010)) for p in jaw[1:8]], 0.007, -1.3, facing=(-up, -0.2),
                name="submandibular shadow")
        sc.blob(sc.from_out(Vector((0.055 * s, ec.y + 0.07, mouth.z - 0.005)), out), 0.013, 0.9, facing=(out, 0.0),
                name="masseter")
        # forehead lines and crow's feet (faint, age ~30)
        for zz in (0.040, 0.050, 0.060):
            fl = [sc.from_out(Vector((s * x, 0, ec.z + zz + 0.002 * math.sin(x * 120))), front) for x in np.linspace(0.0, 0.035, 5)]
            sc.line(fl, 0.0009, -0.06, facing=(front, 0.3), name="forehead line")
        for a in (-0.25, 0.0, 0.3):
            cf = [sc.from_out(ec + Vector((s * (0.021 + 0.008 * t), 0.006, a * 0.012 * t + 0.002)), front + out)
                  for t in np.linspace(0, 1, 3)]
            sc.line(cf, 0.0008, -0.10, facing=(out + front, 0.0), name="crow's feet")
    # midline
    phil = [sc.from_out(Vector((0, 0, nose.z - 0.003)).lerp(Vector((0, 0, mouth.z + 0.007)), t), front)
            for t in np.linspace(0, 1, 4)]
    sc.line(phil, 0.0016, -0.35, facing=(front, 0.3), name="philtrum groove")
    for s in (1, -1):
        sc.line([p + Vector((0.0045 * s, 0, 0)) for p in phil], 0.0013, 0.30, facing=(front, 0.3), name="philtrum column")
    ml = [sc.from_out(Vector((x, 0, mouth.z - 0.016)), front) for x in np.linspace(-0.018, 0.018, 7)]
    sc.line(ml, 0.0032, -1.1, facing=(front, 0.2), name="mentolabial sulcus")
    sc.blob(sc.from_out(Vector((0, 0, chin.z + 0.012)), front), 0.008, 0.8, facing=(front, 0.0), name="chin pad")
    dor = [sc.from_out(Vector((0, 0, z)), front) for z in np.linspace(eye["L"].z - 0.008, nose.z + 0.012, 6)]
    sc.line(dor, 0.003, 0.45, facing=(front, 0.3), name="nasal dorsum")
    for s in (1, -1):
        al = [sc.from_out(Vector((s * 0.016, 0, nose.z + 0.004 + 0.008 * t)) + Vector((0, 0.002 * t, 0)), front + Vector((s, 0, 0)) * 0.5)
              for t in np.linspace(0, 1, 4)]
        sc.line(al, 0.0014, -0.7, facing=(front, -0.3), name="alar crease")
    return sc


# =================================================================== driver
def add_detail(body, joints, masks, eyes, levels=2, probes=None):
    """Replace the Subdivision modifier with Multires(levels) carrying the sculpted detail."""
    for m in list(body.modifiers):
        if m.type in ("SUBSURF", "MULTIRES"):
            body.modifiers.remove(m)
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = body
    body.select_set(True)
    mr = body.modifiers.new("Multires", "MULTIRES")
    for _ in range(levels):
        bpy.ops.object.multires_subdivide(modifier="Multires", mode="CATMULL_CLARK")
    # dense copy with identical topology
    dense = body.copy(); dense.data = body.data.copy(); dense.name = "TMP_Dense"
    bpy.context.collection.objects.link(dense)
    dense.modifiers.clear()
    s = dense.modifiers.new("S", "SUBSURF"); s.levels = levels
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = dense; dense.select_set(True)
    bpy.ops.object.modifier_apply(modifier="S")

    sc = Sculptor(dense)
    for pname, pt in (probes or []):
        sc.add_probe(pname, pt)
    sculpt_anatomy(sc, joints, masks)
    sc.D *= 1.6          # body forms read too soft at 1.0 under game-style lighting
    sculpt_face(sc, joints, masks, eyes)
    maxd = sc.apply(smooth_iters=1)
    for row in sc.probe_log:
        print("[probe]", *row)
    print(f"[detail] {len(sc.log)} features, max displacement {maxd * 1000:.2f} mm on {len(sc.P)} verts")

    bpy.ops.object.select_all(action="DESELECT")
    dense.select_set(True); body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.multires_reshape(modifier="Multires")
    bpy.data.objects.remove(dense)
    mr.levels = 1; mr.sculpt_levels = levels; mr.render_levels = levels
    bpy.context.view_layer.update()
    return sc.log
