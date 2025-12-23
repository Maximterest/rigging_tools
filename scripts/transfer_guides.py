from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import maya.api.OpenMaya as om
import maya.cmds as cmds


def smart_parent_constraint(driver, driven, rotates=True, tolerance=1e-4):
    translates = cmds.getAttr(driven + ".translate")[0]
    rotates = cmds.getAttr(driven + ".rotate")[0]

    skip_trans = []
    skip_rot = []
    for axis, t, r in zip("xyz", translates, rotates):
        if -tolerance <= t <= tolerance:
            skip_trans.append(axis)
        if -tolerance <= r <= tolerance:
            skip_rot.append(axis)

    if len(skip_trans) < 3:
        try:
            cmds.pointConstraint(
                driver,
                driven,
                maintainOffset=True,
                skip=skip_trans,
            )
        except RuntimeError:
            pass
    if len(skip_rot) < 3 and rotates is True:
        try:
            cmds.orientConstraint(
                driver,
                driven,
                maintainOffset=True,
                skip=skip_rot,
            )
        except RuntimeError:
            pass


def get_closest_points(point, target_points, count=1):
    pos = cmds.xform(point, query=True, translation=True, worldSpace=True)
    distances = []
    for tgt_point in target_points:
        position = cmds.pointPosition(tgt_point, world=True)
        distance = sum((a - b) ** 2 for a, b in zip(pos, position)) ** 0.5
        distances.append((distance, tgt_point))
    distances.sort(key=lambda x: x[0])

    return [p for _, p in distances[:count]]


def get_multiple_closest_uvs(mesh, obj, count=3):
    closest_points = get_closest_points(
        obj, cmds.ls(mesh + ".vtx[*]", flatten=True), count=count
    )
    closest_uvs = []
    for point in closest_points:
        uvs = cmds.polyListComponentConversion(point, toUV=True)
        uv_positions = cmds.polyEditUV(uvs, query=True)[0:2]
        closest_uvs.append(uv_positions)

    return closest_uvs


def transfer_guides(
    source_mesh,
    target_mesh,
    connect_guides=False,
    selection=False,
    rotates=False,
    uv_sample_count=5,
):
    guides = []
    if selection:
        for each in cmds.ls(selection=True):
            if each.endswith("_guideObject"):
                guides.append(each)
    else:
        guides = cmds.ls("*_guideObject")

    # make blendshape
    bs = cmds.blendShape(target_mesh, source_mesh)[0]

    # grp
    grp = cmds.createNode("transform", name="out_guides_grp")
    cmds.addAttr(
        grp,
        longName="localScale",
        attributeType="float",
        defaultValue=1.0,
        keyable=True,
    )
    local_scale_plug = "{}.{}".format(grp, "localScale")

    for each in guides:
        transfer_guide = cmds.spaceLocator(
            name=each.replace("_guideObject", "_new_guideObject")
        )[0]
        cmds.parent(transfer_guide, grp)

        mtx = cmds.xform(each, query=True, matrix=True, worldSpace=True)
        cmds.xform(each, matrix=mtx, worldSpace=True)

        closest_uvs = get_multiple_closest_uvs(
            source_mesh, each, uv_sample_count
        )

        uv_pin = cmds.createNode("uvPin", name=transfer_guide + "_uvPin")
        cmds.connectAttr(
            source_mesh + ".worldMesh", uv_pin + ".deformedGeometry"
        )

        for i, uv in enumerate(closest_uvs):
            cmds.setAttr(f"{uv_pin}.coordinate[{i}]", *uv)

        out_mtx_plug = uv_pin + ".outputMatrix[0]"
        offset = (
            om.MMatrix(mtx) * om.MMatrix(cmds.getAttr(out_mtx_plug)).inverse()
        )
        mult_offset = cmds.createNode(
            "multMatrix", name=transfer_guide + "_offset_multMtx"
        )
        cmds.setAttr(mult_offset + ".matrixIn[0]", offset, type="matrix")
        cmds.connectAttr(out_mtx_plug, mult_offset + ".matrixIn[1]")
        cmds.connectAttr(
            mult_offset + ".matrixSum", transfer_guide + ".offsetParentMatrix"
        )

        cmds.connectAttr(local_scale_plug, transfer_guide + ".localScaleX")
        cmds.connectAttr(local_scale_plug, transfer_guide + ".localScaleY")
        cmds.connectAttr(local_scale_plug, transfer_guide + ".localScaleZ")

        if connect_guides:
            try:
                smart_parent_constraint(transfer_guide, each, rotates=rotates)
            except RuntimeError:
                pass

    if connect_guides:
        cmds.setAttr(f"{bs}.{target_mesh}", 1)

