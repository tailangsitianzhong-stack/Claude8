"""Assemble the samurai character (STEP 1-3 + review renders + .blend).

  blender -b --factory-startup --python build_character.py -- \
      --data <makehuman data dir> --out <render dir> --blend <file.blend> \
      [--samples 96] [--hair 18000] [--views front,side,back,three_quarter,face,face_side] [--norender]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import build_body as BB  # noqa: E402
import lookdev as LD  # noqa: E402
import render_views as RV  # noqa: E402

A = BB.ARGS
arg = BB.arg


def main():
    body, (tu, tl, tg), eyes, applied = BB.build()
    joints = BB.build.joints
    body_index = BB.build.body_index

    root = LD.new_coll("SAM_Character")
    c_body = LD.new_coll("SAM_Body", root)
    c_head = LD.new_coll("SAM_Head_Parts", root)
    c_hair = LD.new_coll("SAM_Hair", root)
    c_cloth = LD.new_coll("SAM_Clothing", root)
    c_ref = LD.new_coll("SAM_Reference_Joints", root)
    c_ref.hide_render = True

    LD.link(body, c_body)
    for o in (tu, tl, tg):
        LD.link(o, c_head)
        o.modifiers.new("Subdivision", "SUBSURF").render_levels = 2
    teeth_m = LD.mat_simple("M_Teeth", (0.80, 0.76, 0.66), 0.25, sss=0.3)
    gum_m = LD.mat_simple("M_Mouth", (0.35, 0.10, 0.09), 0.35, sss=0.5)
    tu.data.materials.append(teeth_m); tl.data.materials.append(teeth_m); tg.data.materials.append(gum_m)

    # body: subdivision for render, skin
    sub = body.modifiers.new("Subdivision", "SUBSURF"); sub.levels = 1; sub.render_levels = 2
    masks = LD.compute_masks(body, eyes, body_index)
    LD.nails(body, joints)
    body.data.materials.append(LD.mat_skin())

    LD.make_eyes(eyes, c_head)
    hair_m = LD.mat_hair("M_Hair_Black", 1.0, 0.03, 0.30)
    fine_m = LD.mat_hair("M_Hair_Fine", 0.98, 0.04, 0.36)
    nh = int(arg("--hair", "18000"))
    LD.make_scalp_hair(body, masks, c_hair, hair_m, count=nh, tuft=max(800, nh // 5))
    LD.make_brows(body, eyes, c_hair, fine_m)
    LD.make_lashes(body, eyes, c_hair, fine_m)
    LD.make_beard(body, masks, c_hair, hair_m)
    LD.make_fundoshi(body, joints, c_cloth)

    # reference empties at the anatomical joint centres (for rigging in a later phase)
    for name, p in sorted(joints.items()):
        e = bpy.data.objects.new("J_" + name[6:], None)
        e.empty_display_size = 0.01; e.location = p
        c_ref.objects.link(e)
    c_ref.hide_viewport = True

    bpy.context.scene.cycles_curves.shape = "THICK" if hasattr(bpy.context.scene, "cycles_curves") else None
    rev = LD.new_coll("REV_Review_Scene")
    before = set(bpy.data.objects)
    RV.setup_scene(samples=int(arg("--samples", "96")), res=(1200, 1600))
    for o in set(bpy.data.objects) - before:
        LD.link(o, rev)

    blend = arg("--blend")
    if blend:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(blend), compress=True)
    if "--norender" not in A:
        views = arg("--views", "front,side,back,three_quarter,face,face_side").split(",")
        before = set(bpy.data.objects)
        RV.render_all(arg("--out"), height=BB.TARGET_HEIGHT_M,
                      face_z=(eyes[0][1].z + eyes[1][1].z) / 2 - 0.01, views=views)
        for o in set(bpy.data.objects) - before:
            LD.link(o, rev)
        if blend:
            bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(blend), compress=True)


main()
