from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import re

from maya import cmds

from . import utils

DEFORMERS_STACK = {
    # Body deformers
    "M_body_compil_mesh": {
        "M_body_skull_skinCluster": {
            "joints": ["M_base_04_jnt"],
            "use_hierarchy": True,
            "envelope": 1,
        },
        "lattice_lower_ffd1": None,
        "lattice_middle_ffd1": None,
        "lattice_upper_ffd1": None,
        "lattice_clusters_ffd1": None,
        "lattice_global_ffd1": None,
        "M_mouth_cluster": None,
        "{}_cheekboneOuter_cluster": None,
        "{}_cheekboneCenter_cluster": None,
        "{}_cheekboneInner_cluster": None,
        "{}_eye_region_cluster": None,
        "{}_eye_exept_eyeball_cluster": None,
        "{}_eye_global_cluster": None,
        "{}_cheekbone_follow_cluster": None,
        "M_noseFollow_cluster": None,
    }
}


def update_inside_mouth_setup(edges=None, jaw_joint="M_jaw_main_jnt"):
    if not edges:
        edges = cmds.ls(selection=True, flatten=True) or None
    if not edges or len(edges) != 2:
        cmds.error(
            "Please select exactly 2 edges to create a rivet.", noContext=True
        )

    update_teeth_tongue_follow_jaw(edges, jaw_joint)
    scale_tongue_ikfk()
    add_teeth_bend()


def update_rivet_edges(edges=None):
    # Checks
    if not edges:
        edges = cmds.ls(selection=True, flatten=True) or None
    if not edges or len(edges) != 2:
        cmds.error(
            "Please select exactly 2 edges to create a rivet.", noContext=True
        )
    blendshape = "jaw_blendShape"
    for i in range(3):
        target = utils.rebuild_blendshape_target(blendshape, i)
        cmds.delete(target)

    # Data
    rivet = cmds.ls("*.mouth_rivet")[0].split(".")[0]

    # Reset controllers
    utils.reset_all_controllers(user_attr=False)

    # Edit edges
    driver = utils.get_children(rivet)[0]
    cmds.parent(driver, world=True)

    set_edges_rivet(edges, rivet)

    cmds.parent(driver, rivet)

    # Edit pluMinusAverage values
    pma = cmds.listConnections(
        f"{rivet}.message", plugs=True, type="plusMinusAverage"
    )
    for node_plug in pma:
        node, node_attr = node_plug.split(".")
        node_attr_value = cmds.getAttr(f"{node}.{node_attr}")
        match = re.search(r"\[(\d+)\]", node_attr_value)
        number = int(match.group(1))
        node_attr_edit = node_attr_value.replace(
            f"[{number}]", f"[{number + 1}]"
        )

        for axis in "xyz":
            value = cmds.getAttr(f"{node}.{node_attr_value}{axis}")
            cmds.setAttr(f"{node}.{node_attr_edit}{axis}", -value)

    apply_tongue_crv_delta()


def add_teeth_bend():
    for mode in ["lower", "upper"]:
        # Data
        misc = f"{mode}Teeth_misc_grp"
        mesh_grp = f"{mode}Teeth_geo_grp"
        mesh = utils.get_children(mesh_grp)[-1]
        name = f"{mode}_Teeth_bendX"
        bend_ref = f"{mode}Teeth_bendYHandle"
        ctrl = f"M_{mode}Teeth_main_ctrl"
        attr_name = "curvatureX"

        # Create the bend
        deformer = utils.create_deformer(
            name=name, meshes=[mesh], deformer_type="bend"
        )

        bend = deformer[0]
        handle = deformer[-1]

        # Position the bend
        cmds.parent(handle, misc)
        t = cmds.xform(bend_ref, query=True, translation=True, worldSpace=True)
        r = cmds.xform(bend_ref, query=True, rotation=True, worldSpace=True)
        s = cmds.xform(bend_ref, query=True, scale=True, worldSpace=True)
        r[0] = 90.0
        cmds.xform(handle, translation=t, rotation=r, scale=s)

        # Connect curvature
        cmds.select(ctrl)
        cmds.addAttr(ctrl, longName=attr_name, keyable=True)
        cmds.connectAttr(f"{ctrl}.{attr_name}", f"{bend}.curvature")


def apply_tongue_crv_delta():
    blendshape = "jaw_blendShape"
    crv_ref = "M_tongue_high_crv"
    jaw_ctrl = "M_jaw_main_ctrl"
    jaw_pos = [
        [f"{jaw_ctrl}.translateY", -1],
        [f"{jaw_ctrl}.translateX", 1],
        [f"{jaw_ctrl}.translateX", -1],
    ]
    crv_neutral = "M_tongue_shape_tmp_driver"

    utils.reset_all_controllers(user_attr=False)

    for i in range(3):
        target = cmds.sculptTarget(
            blendshape, edit=True, regenerate=True, target=i
        )
        if not target:
            cmds.error(
                f"Please delete all tongue targets curves from {blendshape}",
                noContext=True,
            )

        target = target[0]

        tokens = target.split("_")
        tokens.insert(-1, "tmp")
        tmp = "_".join(tokens)

        cmds.setAttr(jaw_pos[i][0], jaw_pos[i][1])

        # Delta
        tmp_delta = utils.duplicate_node(crv_neutral, "trash_grp", "delta")[0]
        bs = cmds.blendShape(tmp, crv_ref, tmp_delta)[0]
        cmds.setAttr(f"{bs}.{tmp}", 1)
        cmds.setAttr(f"{bs}.{crv_ref}", -1)
        cmds.delete(tmp_delta, constructionHistory=True)

        bs = cmds.blendShape(tmp_delta, target)[0]
        cmds.setAttr(f"{bs}.{tmp_delta}", 1)
        cmds.delete(target, constructionHistory=True)

        cmds.delete(tmp_delta)
        cmds.delete(target)

        utils.reset_all_controllers(user_attr=False)


def make_edges_rivet(edges, input_mesh_plug, name="mouth"):
    # Node names
    node_names = {
        "crvfe": [f"rivet_{name}_crvfe_0{i + 1}" for i in range(2)],
        "loft": f"rivet_{name}_loft",
        "posi": f"rivet_{name}_posi",
        "vector": f"rivet_{name}_vprdt",
        "fbfmx": f"rivet_{name}_fbfmx",
        "rivet": f"rivet_{name}_loc",
    }

    # Create nodes
    crvfe_nodes = [
        cmds.createNode("curveFromMeshEdge", name=name)
        for name in node_names["crvfe"]
    ]
    loft = cmds.createNode("loft", name=node_names["loft"])
    posi = cmds.createNode("pointOnSurfaceInfo", name=node_names["posi"])
    vector = cmds.createNode("vectorProduct", name=node_names["vector"])
    fbfmx = cmds.createNode("fourByFourMatrix", name=node_names["fbfmx"])
    rivet = cmds.spaceLocator(name=node_names["rivet"])[0]

    cmds.parent(rivet, utils.GROUPS_DATA["rivet"])

    # Set node attributes
    cmds.setAttr(f"{loft}.uniform", 1)
    cmds.setAttr(f"{posi}.parameterU", 0.5)
    cmds.setAttr(f"{posi}.parameterV", 0.5)
    cmds.setAttr(f"{posi}.turnOnPercentage", 1)
    cmds.setAttr(f"{vector}.operation", 2)

    # Connect nodes
    for i, crvfe in enumerate(crvfe_nodes):
        cmds.connectAttr(input_mesh_plug, f"{crvfe}.inputMesh")
        cmds.connectAttr(f"{crvfe}.outputCurve", f"{loft}.inputCurve[{i}]")

    cmds.connectAttr(f"{loft}.outputSurface", f"{posi}.inputSurface")

    attributes = ["p", "n", "tv"]
    indices = "301"
    for y, (attr, row) in enumerate(zip(attributes, indices)):
        for i, axis in enumerate("xyz"):
            cmds.connectAttr(f"{posi}.{attr}{axis}", f"{fbfmx}.i{row}{i}")
            if y == 0:
                cmds.connectAttr(f"{vector}.o{axis}", f"{fbfmx}.i2{i}")
                continue
            cmds.connectAttr(f"{posi}.{attr}{axis}", f"{vector}.i{y}{axis}")

    cmds.connectAttr(f"{fbfmx}.output", f"{rivet}.offsetParentMatrix")

    # Add message connections
    for crvfe in crvfe_nodes:
        attr_name = "rivetLink"
        if not cmds.attributeQuery(attr_name, node=crvfe, exists=True):
            cmds.addAttr(crvfe, longName=attr_name, dataType="string")
        cmds.setAttr(
            f"{crvfe}.{attr_name}", node_names["rivet"], type="string"
        )
        cmds.connectAttr(
            f"{rivet}.message", f"{crvfe}.{attr_name}", force=True
        )

    # Add indentifier attribute
    id_name = f"{name}_rivet"
    cmds.addAttr(rivet, longName=id_name, dataType="string")
    cmds.setAttr(f"{rivet}.{id_name}", "rivetID", type="string", lock=True)

    set_edges_rivet(edges, rivet)

    return rivet


def update_teeth_tongue_follow_jaw(edges=None, jaw_joint="M_jaw_main_jnt"):
    # Checks
    if not edges:
        edges = cmds.ls(selection=True, flatten=True) or None
    if not edges or len(edges) != 2:
        cmds.error(
            "Please select exactly 2 edges to create a rivet.", noContext=True
        )
    blendshape = "jaw_blendShape"
    for i in range(3):
        target = utils.rebuild_blendshape_target(blendshape, i)
        cmds.delete(target)

    # Reset controllers
    utils.reset_all_controllers(user_attr=False)

    # Reset tongue blendShape targets
    base_grp = "trash_grp"
    parent = cmds.createNode(
        "transform", name="tongue_crv_ref", parent=base_grp
    )
    crv_drive = "M_tongue_shape_driver"
    utils.duplicate_node(crv_drive, parent, "tmp")[0]

    for i in range(3):
        target = utils.rebuild_blendshape_target(blendshape, i)
        utils.duplicate_node(target, parent, "tmp")[0]

        bs = cmds.blendShape(crv_drive, target)[0]
        cmds.setAttr(f"{bs}.{crv_drive}", 1)
        cmds.delete(target, constructionHistory=True)
        cmds.delete(target)

    # Create rivet
    for association in utils.DEFORMER_SUFFIX_ASSOCIATIONS:
        if association["type"] == "ffd":
            pattern = association["suffix"]
            break

    keys = list(DEFORMERS_STACK["M_body_compil_mesh"].keys())
    last_pattern_index = -1
    for i, key in enumerate(keys):
        if pattern in key:
            last_pattern_index = i

    input_mesh_plug = keys[last_pattern_index + 1] + ".outputGeometry[0]"
    rivet = make_edges_rivet(edges, input_mesh_plug)

    # Create driver
    driver = cmds.createNode("transform", name=f"{rivet}_driver", parent=rivet)
    dmx = cmds.createNode("decomposeMatrix", name="rivet_driver_mouth_dmx")
    cmds.matchTransform(driver, jaw_joint)
    cmds.connectAttr(f"{driver}.worldMatrix[0]", f"{dmx}.inputMatrix")

    # Update setup
    for attr in ["translate", "rotate"]:
        pma_teeth, pma_attr = cmds.listConnections(
            f"{jaw_joint}.{attr}X",
            plugs=True,
            skipConversionNodes=True,
            type="plusMinusAverage",
        )[0].split(".", 1)

        match = re.search(r"\[(\d+)\]", pma_attr)
        number = int(match.group(1))
        pma_attr_increment = pma_attr.replace(f"[{number}]", f"[{number + 1}]")
        pma_tongue = cmds.createNode(
            "plusMinusAverage", name=f"tongue_jawHook{attr}_sum"
        )

        for axis in "xyz":
            # Connect plusMinusAverage
            for pma in [pma_teeth, pma_tongue]:
                cmds.connectAttr(
                    f"{dmx}.output{attr.capitalize()}{axis.upper()}",
                    f"{pma}.{pma_attr[:-1]}{axis}",
                    force=True,
                )

                dmx_value = cmds.getAttr(
                    f"{dmx}.output{attr.capitalize()}{axis.upper()}"
                )
                cmds.setAttr(
                    f"{pma}.{pma_attr_increment[:-1]}{axis}",
                    -dmx_value,
                )

            cmds.connectAttr(
                f"{pma_tongue}.output3D{axis}",
                f"M_tongue_joint_hook.{attr}{axis.upper()}",
            )

        # Reset remap
        remaps = cmds.listConnections(pma_teeth, plugs=True, type="remapValue")
        for remap_plug in remaps:
            remap = remap_plug.split(".")[0]
            for att in ["inputMin", "inputMax", "outputMin", "outputMax"]:
                cmds.setAttr(f"{remap}.{att}", 0)

            for i, plug in enumerate(cmds.ls(f"{remap}.value[*]")):
                value = 0
                if i == len(cmds.ls(f"{remap}.value[*]")) - 1:
                    value = 1
                cmds.setAttr(f"{plug}.value_FloatValue", value)

        # Add message connections
        attr_name = "get"
        attr_string = pma_attr[:-1]
        for node in [pma_teeth, pma_tongue]:
            cmds.addAttr(node, longName=attr_name, dataType="string")
            cmds.setAttr(f"{node}.{attr_name}", attr_string, type="string")
            cmds.connectAttr(
                f"{rivet}.message", f"{node}.{attr_name}", force=True
            )

    apply_tongue_crv_delta()


def scale_tongue_ikfk():
    joints = cmds.ls("tongue_*_jnt") + cmds.ls("tongue_*_bind")
    ik_ctrls = cmds.ls("M_tongue_ik_*_ctrl")
    loc_plug = "M_move_locator.inverseMatrix"
    joints_number = []
    numbers = []

    for jnt in joints:
        match = re.search(r"\_(\d+)\_", jnt)
        number = match.group(1)
        joints_number.append(number)
        if number in numbers:
            continue
        numbers.append(number)

    div = len(numbers) / len(ik_ctrls)
    round_div = round(div)

    for i, ctrl in enumerate(ik_ctrls):
        start_idx = i * round_div
        end_idx = start_idx + round_div
        end_idx = min(end_idx, len(numbers))

        dmx = cmds.createNode("decomposeMatrix", name=f"{ctrl}_dmx")
        mmx = cmds.createNode("multMatrix", name=f"{ctrl}_mmx")

        cmds.connectAttr(f"{ctrl}.worldMatrix[0]", f"{mmx}.matrixIn[0]")
        cmds.connectAttr(loc_plug, f"{mmx}.matrixIn[1]")
        cmds.connectAttr(f"{mmx}.matrixSum", f"{dmx}.inputMatrix")

        for num in numbers[start_idx:end_idx]:
            jnt_idxs = [
                index
                for index, value in enumerate(joints_number)
                if value == num
            ]
            for y in jnt_idxs:
                for axis in "XYZ":
                    cmds.connectAttr(
                        f"{dmx}.outputScale{axis}",
                        f"{joints[y]}.scale{axis}",
                        force=True,
                    )


def set_edges_rivet(edges, rivet):
    crvfe_nodes = cmds.listConnections(
        f"{rivet}.message", type="curveFromMeshEdge"
    )
    for node, edge in zip(crvfe_nodes, edges):
        match = re.search(r"\[(\d+)\]", edge)
        number = int(match.group(1))
        cmds.setAttr(f"{node}.edgeIndex[0]", number)
