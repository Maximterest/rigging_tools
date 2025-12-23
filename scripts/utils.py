from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
import re

from maya import cmds
from maya import mel
from ngSkinTools2 import api
from rig.utils import facial_rig

GROUPS_DATA = {
    "tool": "tool_mesh_grp",
    "clusters": "clusters_grp",
    "rivet": "rivet_grp",
    "temp": "TMP_grp",
}
CTRLS_SEARCH = "*_ctrl"
CTRLS_EXCEPTION = ["M_global_ctrl"]
ATTRIBUTES_TYPE = {"long", "short", "byte", "bool", "enum", "double", "float"}
COLOR_IDX = {
    "yellow": 17,
    "red": 13,
    "blue": 6,
    "green": 14,
    "pink": 20,
}
CTRL_SHAPE_RATIO_ATTR = "ctrlShapeRatio{}"
CTRL_SHAPE_RATIO_NODE_DATA_ATTR = CTRL_SHAPE_RATIO_ATTR.format("XYZ") + "Nodes"
DEFORMER_SUFFIX_ASSOCIATIONS = [
    {"suffix": "ffd1", "type": "ffd"},
    {"suffix": "cluster", "type": "cluster"},
    {"suffix": "blendShape", "type": "blendShape"},
    {"suffix": "wrap", "type": "wrap"},
    {"suffix": "proximityWrap", "type": "proximityWrap"},
    {"suffix": "shrinkWrap", "type": "shrinkWrap"},
    {"suffix": "wire", "type": "wire"},
    {"suffix": "skinCluster", "type": "skinCluster"},
]
SKINCLUSTER_SETTINGS = {
    "toSelectedBones": True,
    "bindMethod": 0,
    "skinMethod": 2,
    "normalizeWeights": 1,
    "weightDistribution": 1,
    "maximumInfluences": 3,
    "obeyMaxInfluences": True,
    "dropoffRate": 4,
    "removeUnusedInfluence": False,
}

cmds.selectPref(trackSelectionOrder=True)


def add_offset(obj, suffix="offset", remove_obj_suffix=True):
    matrix = cmds.xform(obj, query=True, matrix=True, worldSpace=True)

    obj_split = obj
    if remove_obj_suffix:
        obj_split = "_".join(obj.split("_")[:-1])
    if not obj_split:
        obj_split = obj
    name = obj_split + "_" + suffix

    node = create_nodes(["transform"], name, type_suffix=False)

    obj_parent = get_parent(obj)
    if obj_parent:
        cmds.parent(node["transform"], obj_parent)
    cmds.parent(obj, node["transform"])

    reset_transforms(obj)
    apply_matrix(node["transform"], matrix)

    return node["transform"]


def apply_matrix(target, matrix):
    cmds.xform(target, matrix=matrix, worldSpace=True)


def add_sym_joints_to_skincluster(replaces=("L_", "R_")):
    added = []
    selection = get_selection()
    for mesh in selection:
        skincluster, type = list_deformers(mesh, ["skinCluster"])
        joints = cmds.skinCluster(
            skincluster, query=True, influence=True, weightedInfluence=False
        )
        for jnt in joints:
            if replaces[0] not in jnt:
                continue
            sym_jnt = jnt.replace(replaces[0], replaces[-1], 1)
            if sym_jnt in joints:
                continue
            cmds.skinCluster(
                skincluster, edit=True, addInfluence=sym_jnt, lockWeights=True
            )
            added.append(sym_jnt)
    print(f"ADDED :\n{added}")


def add_custom_attr(obj, attr_name, attr_type, **kwargs):
    """Add attribute to an obj

    Args:
        obj (str): The object node
        attr_name (str): attribute long name
        attr_type (str): attribute type
            Can be: bool, enum, float, double, long, string
        **kwargs: Can be: default, keyable, min, max, nice_name, enum_names,
            hidden, lock, channel_box, string

    """
    # Common optional parameters
    default = kwargs.get("default")
    keyable = kwargs.get("keyable")
    min_val = kwargs.get("min")
    max_val = kwargs.get("max")
    nice_name = kwargs.get("nice_name")
    enum_names = kwargs.get("enum_names")
    hidden = kwargs.get("hidden")
    lock = kwargs.get("lock")
    channel_box = kwargs.get("channel_box")
    string = kwargs.get("string")

    default_value = default if default is not None else 0
    if keyable is None:
        keyable = True
    if hidden is None:
        hidden = False
    if channel_box is None:
        channel_box = True

    attr_flags = {}
    attr_flags["keyable"] = keyable
    attr_flags["hidden"] = hidden
    if nice_name:
        attr_flags["niceName"] = nice_name
    if default_value:
        attr_flags["defaultValue"] = default_value

    float_flags = {}
    if min_val is not None:
        float_flags["min"] = min_val
    if max_val is not None:
        float_flags["max"] = max_val

    set_flags = {}
    set_flags["channelBox"] = channel_box
    if lock:
        set_flags["lock"] = lock

    if attr_type == "bool":
        cmds.addAttr(
            obj, longName=attr_name, attributeType=attr_type, **attr_flags
        )

    elif attr_type == "enum":
        if not enum_names:
            return None
        enum_str = ":".join(enum_names)
        cmds.addAttr(
            obj,
            longName=attr_name,
            attributeType=attr_type,
            enumName=enum_str,
            **attr_flags,
        )

    elif attr_type in {"float", "double", "long", "short"}:
        cmds.addAttr(
            obj,
            longName=attr_name,
            attributeType=attr_type,
            **attr_flags,
            **float_flags,
        )

    elif attr_type == "string":
        cmds.addAttr(obj, longName=attr_name, dataType=attr_type, **attr_flags)
        if string:
            cmds.setAttr(f"{obj}.{attr_name}", string, type=attr_type)

    cmds.setAttr(f"{obj}.{attr_name}", **set_flags)
    cmds.setAttr(f"{obj}.{attr_name}", keyable=keyable)

    return attr_name


def build_cluster_plugs(cluster):
    handle = cmds.listConnections(f"{cluster}.matrix", source=True)[0]
    parent = get_parent(handle)

    input_plug = f"{parent}.worldInverseMatrix[0]"
    dest_plug = f"{cluster}.bindPreMatrix"

    return input_plug, dest_plug


def colorize(obj, color="yellow"):
    color_idx = COLOR_IDX[color]
    cmds.setAttr("{}.overrideEnabled".format(obj), True)
    cmds.setAttr("{}.overrideColor".format(obj), color_idx)


def clean_facial_scene(delete_move_cluster=False):
    disconnect_clusters_bpm()
    facial_rig.check_modeling_match()

    # Delete unwanted
    unwanted = (
        get_children("trash_grp")
        + [
            "M_move_cluster",
            "M_move_cluster_loc",
        ]
        if delete_move_cluster is True
        else get_children("trash_grp")
    )
    [cmds.delete(obj) for obj in unwanted if cmds.objExists(obj)]

    # Extra clean
    delete_unused_nodes()
    delete_unknown_plugins()
    clean_controllers_ratio()

    # Remove data structure (maya crap...)
    cmds.dataStructure(removeAll=True)


def clean_controllers_ratio():
    attrs_to_check = ["ctrlShapeRatio" + xyz for xyz in "XYZ"]
    to_clean = []
    for node in get_controllers():
        for attr in attrs_to_check:
            if not cmds.attributeQuery(attr, node=node, exists=True):
                continue
        to_clean.add(node)

    cleanup_ctrl_shape_ratio_attr(to_clean)


def create_ng_node(mesh):
    if not api.get_layers_enabled(mesh):
        layers = api.init_layers(mesh)
        layers.add("base")


def create_joints_on_center_faces():
    selection = cmds.ls(orderedSelection=True)
    for face in selection:
        vertices = cmds.polyInfo(face, faceToVertex=True)[0]
        vertices = vertices.strip().split()[2:]
        vertices = list(set(vertices))
        vertices = [
            "{}.vtx[{}]".format(face.split(".")[0], v) for v in vertices
        ]
        cmds.select(clear=True)
        joint = cmds.joint()
        xform_average_match_transforms(joint, vertices)


def create_locator(
    name,
    parent=None,
    child=None,
    reset=True,
    match_to="parent",
    color="yellow",
    scale=1,
):
    """Create a locator

    Args:
        name (str): locator name
        parent (str): parent object
        child (str): child object
        reset (bool): reset locator or child transforms
            Depending of the match_to
        match_to (str): match locator to parent or child
            Can be "parent" or "child" or node
        color
        scale (float): radius locator size

    Returns:
        str: locator

    """
    loc = cmds.spaceLocator(name=name)[0]
    scales = ["localScale" + y for y in "XYZ"]
    [cmds.setAttr("{}.{}".format(loc, s), scale) for s in scales]

    if parent:
        if match_to == "parent":
            matrix_match_transforms(loc, parent)
        cmds.parent(loc, parent)

    if child:
        if match_to == "child":
            matrix_match_transforms(loc, child)
        cmds.parent(child, loc)

    if match_to not in {"parent", "child"}:
        matrix_match_transforms(loc, match_to)

    if reset:
        reset_obj = loc
        reset_attrs = ["translate", "rotate", "scale"]
        if match_to == "child":
            reset_obj = child
            if cmds.objectType(child) == "joint":
                reset_attrs = reset_attrs + ["jointOrient"]
        reset_transforms(reset_obj, reset_attrs)

    if color:
        colorize(loc, color)

    return loc


def create_locator_on_all_ctrls():
    if not cmds.objExists(GROUPS_DATA["temp"]):
        create_nodes(["transform"], GROUPS_DATA["temp"], type_suffix=False)

    for ctrl in get_controllers():
        name = ctrl + "_locator"
        loc = create_locator(
            name, GROUPS_DATA["temp"], color="yellow", scale=2
        )
        cmds.parentConstraint(ctrl, loc)


def create_sphere():
    selection = get_selection()
    sphere_suffix = "TMP_surface"
    if not cmds.objExists(GROUPS_DATA["temp"]):
        create_nodes(["transform"], GROUPS_DATA["temp"], type_suffix=False)

    for obj in selection:
        sphere = cmds.sphere(name="{}_{}".format(obj, sphere_suffix))[0]
        cmds.parentConstraint(obj, sphere)
        cmds.parent(sphere, GROUPS_DATA["temp"])
        colorize(sphere, "pink")

    if not selection:
        sphere = cmds.sphere(name=sphere_suffix)[0]
        cmds.parent(sphere, GROUPS_DATA["temp"])
        colorize(sphere, "pink")


def create_shapeorig(obj):
    return cmds.deformableShape(obj, createOriginalGeometry=True)[0]


def create_bs():
    selection = get_selection()
    if not len(selection) > 1:
        cmds.error("Please select at least 2 objects", noContext=True)
    bases = selection[:-1]
    target = selection[-1]
    name = target + "_blendshape"
    return cmds.blendShape(bases, target, name=name)[0]


def create_blendshape(value=1):
    selection = get_selection()
    bs = create_bs()
    bases = selection[:-1]
    for base in bases:
        cmds.setAttr("{}.{}".format(bs, base), value)


def create_delta_blendshape(second_only=False):
    selection = get_selection()
    bs = create_bs()
    bases = selection[:-1]
    for base in bases:
        value = 1 if base == bases[0] and len(bases) > 1 else -1
        if second_only and base != bases[1]:
            value = 1
        cmds.setAttr("{}.{}".format(bs, base), value)


def create_blendshape_by_prefix():
    meshes = get_selection()
    for mesh in meshes:
        prefix = mesh.split("_")[0]
        match = mesh.replace("{}_".format(prefix), "")
        if not cmds.objExists(match):
            cmds.warning("No match for {}".format(mesh), noContext=True)
            continue
        create_blendshape(mesh, match)


def create_hook_on_curve(
    curve,
    position=0.0,
    child=None,
    reset=True,
    attrs=("translate", "rotate", "scale"),
    curve_attrs=("position", "normalizedNormal", "normalizedTangent"),
    inherits_transform=False,
    remove_child_suffix=True,
    child_axis_order="X-YZ",
    relative=True,
):
    name = curve + "_crv"
    if child:
        name = "{}_crv".format(child)
        if remove_child_suffix:
            name = "{}_crv".format("_".join(child.split("_")[:-1]))

    hook = create_nodes(["transform"], "{}_hook_grp".format(name), False, True)
    nodes = create_nodes(
        [
            "pointOnCurveInfo",
            "fourByFourMatrix",
            "multMatrix",
            "decomposeMatrix",
        ],
        name,
    )
    connections_data = {
        curve + ".worldSpace[0]": nodes["point"] + ".inputCurve",
        nodes["four"] + ".output": nodes["mult"] + ".matrixIn[0]",
        hook + ".parentInverseMatrix[0]": nodes["mult"] + ".matrixIn[1]",
        nodes["mult"] + ".matrixSum": nodes["decompose"] + ".inputMatrix",
    }

    if not inherits_transform:
        cmds.setAttr("{}.inheritsTransform".format(hook), 0, lock=True)

    cmds.setAttr("{}.parameter".format(nodes["point"]), position, lock=True)

    match_indices = {
        "position": 3,
        "normalizedNormal": 0,
        "normalizedTangent": 1,
    }
    for surf_attr in curve_attrs:
        indice = match_indices[surf_attr]
        for i, axis in enumerate("XYZ"):
            connections_data[
                "{}.{}{}".format(nodes["point"], surf_attr, axis)
            ] = "{}.in{}{}".format(nodes["four"], indice, i)

    if child:
        matrix_match_transforms(hook, child)

    for attr in attrs:
        connections_data[
            "{}.output{}".format(
                nodes["decompose"], attr[0].upper() + attr[1:]
            )
        ] = "{}.{}".format(hook, attr)

    connect_plugs(connections_data)

    if child:
        child_parent = get_parent(child)
        cmds.parent(child, hook, relative=relative)
        if child_parent:
            cmds.parent(hook, child_parent)

        if reset:
            reset_attrs = attrs
            if cmds.objectType(child) == "joint":
                reset_attrs = list(attrs) + ["jointOrient"]
            reset_transforms(child, reset_attrs)

            axis_to_rotation = {
                "X-YZ": (0, 0, 0),
                "XZY": (90, 0, 0),
                "X-Z-Y": (-90, 0, 0),
                "Z-Y-X": (0, 90, 0),
                "-Z-YX": (0, -90, 0),
                "-Y-XZ": (0, 0, 90),
                "YXZ": (0, 0, -90),
                "Y-X-Z": (180, 0, 90),
                "XY-Z": (180, 0, 0),
            }
            rot = axis_to_rotation[child_axis_order]
            cmds.xform(child, rotation=rot, objectSpace=True)

    return hook


def create_nodes(nodes, label, type_suffix=True, return_str=False):
    created = {}
    for node in nodes:
        name = "{}_{}".format(label, node) if type_suffix else label
        created_node = cmds.createNode(node, name=name, skipSelect=True)
        short_name = re.split(r"(?=[A-Z])", node, maxsplit=1)[0]
        if short_name in created:
            count = 1
            new_key = short_name + str(count)
            while new_key in created:
                count += 1
                new_key = short_name + str(count)
            short_name = new_key

        created[short_name] = created_node

    if return_str:
        return created_node
    return created


def create_deformer(
    name,
    meshes,
    deformer_type=None,
    association_map=DEFORMER_SUFFIX_ASSOCIATIONS,
):
    """Create a deformer

    Args:
        name (str): deformer name
        meshes (list): meshes where to create the deformer
        type (str, optional): deformer type
                              if not provided, create a deformer depending of the suffix in name
        association_map: (List[Dict[str, str]]): each dictionary contains 'suffix' and 'type' keys.
                                                 associate a suffix with a deformer type

    Return:
        list: result command of the deformer creation
    """
    if not deformer_type:
        suffix = name.split("_")[-1]
        for association in association_map:
            if association["suffix"] == suffix:
                deformer_type = association["type"]
                break

    if deformer_type:
        if deformer_type == "cluster":
            deformer = cmds.cluster(meshes, name=name)
        elif deformer_type == "ffd":
            deformer = cmds.lattice(meshes, name=name, objectCentered=True)
        elif deformer_type == "blendShape":
            deformer = cmds.blendShape(meshes, name=name)
        elif deformer_type == "wire":
            deformer = cmds.wire(meshes[0], wire=meshes[1:], name=name)
        elif deformer_type == "wrap":
            deformer = create_wrap(meshes[0], meshes[1], name)
            cmds.setAttr(name + ".maxDistance", 1)
            cmds.setAttr(name + ".autoWeightThreshold", 1)
            base = cmds.ls(meshes[0] + "Base*", type="transform")[-1]
            cmds.parent(base, GROUPS_DATA["tool"])
        elif deformer_type == "proximityWrap":
            deformer = create_proximity_wrap([meshes[0]], [meshes[1]], name)
        elif deformer_type == "shrinkWrap":
            deformer = create_shrinkwrap(meshes[1], meshes[0], name)
        elif deformer_type == "bend":
            deformer = cmds.nonLinear(meshes[0], name=name, type="bend")
        else:
            deformer = cmds.deformer(type=deformer_type, name=name)
    else:
        deformer = []

    return deformer


def create_wrap(driver, driven, name):
    driver_shape = get_shape(driver)
    wrap = cmds.deformer(driven, type="wrap")[0]

    # add influence
    base = duplicate_node(driver, strict_name=driver + "Base")[0]
    base_shape = get_shape(base)
    cmds.hide(base)

    plugs_data = {
        driven + ".worldMatrix[0]": wrap + ".geomMatrix",
        driver + ".dropoff": wrap + ".dropoff[0]",
    }

    if not cmds.attributeQuery("dropoff", node=driver, exists=True):
        add_custom_attr(
            driver,
            "dropoff",
            "double",
            nice_name="dr",
            default=4,
            min=0,
            max=20,
        )

    if cmds.nodeType(driver_shape) == "mesh":
        if not cmds.attributeQuery("smoothness", node=driver, exists=True):
            add_custom_attr(
                driver,
                "smoothness",
                "double",
                nice_name="smt",
                default=0,
                min=0,
            )
        if not cmds.attributeQuery("inflType", node=driver, exists=True):
            add_custom_attr(
                driver,
                "inflType",
                "short",
                nice_name="ift",
                default=2,
                min=1,
                max=2,
                keyable=False,
            )

        plugs_data[driver_shape + ".w"] = wrap + ".driverPoints[0]"
        plugs_data[base_shape + ".worldMesh"] = wrap + ".basePoints[0]"
        plugs_data[driver + ".inflType"] = wrap + ".inflType[0]"
        plugs_data[driver + ".smoothness"] = wrap + ".smoothness[0]"

    if (
        cmds.nodeType(driver_shape) == "nurbsCurve"
        or cmds.nodeType(driver_shape) == "nurbsSurface"
    ):
        if not cmds.attributeQuery("wrapSamples", node=driver, exists=True):
            add_custom_attr(
                driver,
                "wrapSamples",
                "short",
                nice_name="wsm",
                default=10,
                min=1,
            )

        plugs_data[driver_shape + ".ws"] = wrap + ".driverPoints[0]"
        plugs_data[base_shape + ".ws"] = wrap + ".basePoints[0]"
        plugs_data[driver + ".wsm"] = wrap + ".nurbsSamples[0]"

    connect_plugs(plugs_data)

    return [cmds.rename(wrap, name)]


def create_proximity_wrap(drivers, targets, name, falloff=10):
    available_drivers = drivers
    for each in available_drivers:
        if not cmds.objExists(each):
            available_drivers.remove(each)
            cmds.warning("Driver not found or doesn't exist!")

    targets = targets or []
    targets = [x for x in targets if cmds.objExists(x)]
    if not targets:
        cmds.warning("Targets not found or don't exist!")
        return None

    deformer = cmds.deformer(targets, name=name, type="proximityWrap")
    for i, driver in enumerate(available_drivers):
        orig_plug = create_shapeorig(driver)
        plugs_data = {
            orig_plug: "{}.drivers[{}].driverBindGeometry".format(
                deformer[0], i
            )
        }
        driver_shape = get_shape(driver)
        if cmds.nodeType(driver_shape) == "mesh":
            plugs_data[driver + ".worldMesh"] = (
                "{}.drivers[{}].driverGeometry".format(deformer[0], i)
            )
        if (
            cmds.nodeType(driver_shape) == "nurbsCurve"
            or cmds.nodeType(driver_shape) == "nurbsSurface"
        ):
            plugs_data[driver + ".worldSpace"] = (
                "{}.drivers[{}].driverGeometry".format(deformer[0], i)
            )
        connect_plugs(plugs_data)

    cmds.setAttr(deformer[0] + ".falloffScale", falloff)

    return deformer


def create_shrinkwrap(mesh, target, name, **kwargs):
    """Create a shrinkWrap

    Args:
        mesh (str): mesh base
        target (str): mesh where to create the deformer
        name (str): name of the shrinkWrap

    Return:
        list: result command of the deformer creation
    """
    parameters = [
        ("projection", 2),
        ("closestIfNoIntersection", 1),
        ("reverse", 0),
        ("bidirectional", 1),
        ("boundingBoxCenter", 1),
        ("axisReference", 1),
        ("alongX", 0),
        ("alongY", 0),
        ("alongZ", 1),
        ("offset", 0),
        ("targetInflation", 0),
        ("targetSmoothLevel", 0),
        ("falloff", 0),
        ("falloffIterations", 1),
        ("shapePreservationEnable", 0),
        ("shapePreservationSteps", 1),
    ]

    target_shape = get_shape(target)
    shrink_wrap = cmds.deformer(mesh, type="shrinkWrap", name=name)[0]

    for parameter, default in parameters:
        cmds.setAttr(
            shrink_wrap + "." + parameter, kwargs.get(parameter, default)
        )

    connections = [
        ("worldMesh", "targetGeom"),
        ("continuity", "continuity"),
        ("smoothUVs", "smoothUVs"),
        ("keepBorder", "keepBorder"),
        ("boundaryRule", "boundaryRule"),
        ("keepHardEdge", "keepHardEdge"),
        ("propagateEdgeHardness", "propagateEdgeHardness"),
        ("keepMapBorders", "keepMapBorders"),
    ]

    for out_plug, in_plug in connections:
        connect_plugs({
            target_shape + "." + out_plug: shrink_wrap + "." + in_plug
        })

    return [shrink_wrap]


def create_ctrl_shape_ratio_attr():
    selection = get_selection()
    for each in selection:
        shape_orig_plug = create_shapeorig(each)
        shape_orig = shape_orig_plug.split(".")[0]
        neg_offset = get_parent(each)
        top_offset = get_parent(neg_offset)
        shape = get_shape(each)

        plugs_data = {}
        nodes = create_nodes(
            ["composeMatrix", "transformGeometry"], each + "_ctrlShapeRatio"
        )

        created = list(nodes.values())

        for xyz in "XYZ":
            plug = "{}.{}".format(each, CTRL_SHAPE_RATIO_ATTR.format(xyz))
            if cmds.objExists(plug):
                continue

            default_value = cmds.getAttr("{}.scale{}".format(top_offset, xyz))
            negative_sign = default_value <= 0
            absolute_default_value = abs(default_value)

            add_custom_attr(
                each,
                CTRL_SHAPE_RATIO_ATTR.format(xyz),
                "double",
                min=0.01,
                max=100,
                default=absolute_default_value,
            )

            mults = create_nodes(
                ["multiplyDivide", "multiplyDivide"],
                "{}_ctrlShapeRatio_{}".format(each, xyz),
            )

            cmds.setAttr(
                mults["multiply"] + ".input2X", -1 if negative_sign else 1
            )

            cmds.setAttr(
                mults["multiply1"] + ".input1X", absolute_default_value
            )
            cmds.setAttr(mults["multiply1"] + ".operation", 2)

            plugs_data[plug] = [
                mults["multiply1"] + ".input2X",
                "{}.input1{}".format(mults["multiply"], xyz),
            ]
            plugs_data[mults["multiply1"] + ".outputX"] = (
                "{}.inputScale{}".format(nodes["compose"], xyz)
            )
            plugs_data["{}.output{}".format(mults["multiply"], xyz)] = (
                "{}.scale{}".format(top_offset, xyz),
            )
            created += list(mults.values()) + [shape_orig]

        plugs_data[nodes["compose"] + ".outputMatrix"] = (
            nodes["transform"] + ".transform"
        )
        plugs_data[shape_orig_plug] = nodes["transform"] + ".inputGeometry"
        plugs_data[nodes["transform"] + ".outputGeometry"] = shape + ".create"

        connect_plugs(plugs_data)

        # stamp temp nodes
        data = ",".join(created)
        attr = add_custom_attr(
            each, CTRL_SHAPE_RATIO_NODE_DATA_ATTR, "string", keyable=False
        )
        cmds.setAttr("{}.{}".format(each, attr), data, type="string")

    cmds.select(selection)


def cleanup_ctrl_shape_ratio_attr(controllers=None):
    if not controllers:
        controllers = get_selection()
    for each in controllers:
        plug = "{}.{}".format(each, CTRL_SHAPE_RATIO_NODE_DATA_ATTR)
        if not cmds.objExists(plug):
            continue

        dest_ctrl_shape_plug = each + ".create"
        src_ctrl_shape_plug = (
            cmds.listConnections(
                dest_ctrl_shape_plug,
                source=True,
                destination=False,
                plugs=True,
            )
            or []
        )
        if src_ctrl_shape_plug:
            print(src_ctrl_shape_plug[0], "->", dest_ctrl_shape_plug)
            cmds.disconnectAttr(src_ctrl_shape_plug[0], dest_ctrl_shape_plug)

        # all other nodes
        nodes = cmds.getAttr(
            "{}.{}".format(each, CTRL_SHAPE_RATIO_NODE_DATA_ATTR)
        ).split(",")
        cmds.delete(nodes)

        cmds.deleteAttr("{}.{}".format(each, CTRL_SHAPE_RATIO_NODE_DATA_ATTR))
        for xyz in "XYZ":
            plug = "{}.{}".format(each, CTRL_SHAPE_RATIO_ATTR.format(xyz))
            cmds.deleteAttr(plug)


def connect_plugs(data):
    """Dict {source: target}"""
    for source, target in data.items():
        if isinstance(target, (list, tuple)):
            for tgt in target:
                cmds.connectAttr(source, tgt, force=True)
        elif isinstance(target, str):
            cmds.connectAttr(source, target, force=True)


def copy_skincluster_callback(method="closestPoint"):
    selection = get_selection()
    if not selection:
        cmds.error("Please select at least 2 meshes", noContext=True)

    source, targets = selection[0], selection[1:]
    for target in targets:
        copy_skincluster(source, target, method)

    cmds.select(selection)


def copy_skincluster(source, target, method="closestPoint"):
    copy_settings = {
        "influenceAssociation": ["closestJoint", "closestBone", "oneToOne"],
        "sampleSpace": 0,
        "noMirror": True,
        "smooth": True,
    }

    # get skinclusters and influences
    source_skc, types = get_deformers(source, ["skinCluster"])
    if not source_skc:
        cmds.error("{} as not a skincluster".format(source), noContext=True)
    source_skc = source_skc[0]

    source_infs = cmds.skinCluster(
        source_skc, query=True, influence=True, weightedInfluence=False
    )
    infs_objects = [_ for _ in source_infs if cmds.nodeType(_) != "joint"]
    source_infs = [_ for _ in source_infs if _ not in infs_objects]

    # add influences if skincluster already exists
    target_infs = None
    target_skc, types = get_deformers(target, ["skinCluster"])
    if target_skc:
        target_infs = cmds.skinCluster(
            target_skc, query=True, influence=True, weightedInfluence=False
        )
        diff_influences = set(source_infs + infs_objects) - set(target_infs)
        if diff_influences:
            cmds.skinCluster(
                target_skc, edit=True, addInfluence=list(diff_influences)
            )

    # create skincluster otherwise
    else:
        name = "{}_skinCluster".format(target).rsplit("|")[-1]
        name = name + "#" if cmds.objExists(name) else name
        skc_settings = dict(SKINCLUSTER_SETTINGS)
        skc_settings["skinMethod"] = cmds.skinCluster(
            source_skc, query=True, skinMethod=True
        )
        skc_settings["normalizeWeights"] = cmds.skinCluster(
            source_skc, query=True, normalizeWeights=True
        )
        target_skc = cmds.skinCluster(
            source_infs, target, name=name, **skc_settings
        )[0]

        if infs_objects:
            cmds.skinCluster(target_skc, edit=True, addInfluence=infs_objects)

    # copy skincluster weights
    if method == "uv":
        copy_settings["uvSpace"] = ["map1", "map1"]
    else:
        copy_settings["surfaceAssociation"] = method

    cmds.copySkinWeights(
        sourceSkin=source_skc, destinationSkin=target_skc, **copy_settings
    )


def delete_ng_nodes():
    for each in ("ngst2MeshDisplay", "ngst2SkinLayerData", "ngSkinLayerData"):
        nodes = cmds.ls(type=each)
        if nodes:
            cmds.delete(nodes)


def delete_tmp():
    if cmds.objExists(GROUPS_DATA["temp"]):
        cmds.delete(GROUPS_DATA["temp"])


def delete_unknown_plugins():
    for each in cmds.unknownPlugin(query=True, list=True) or []:
        cmds.unknownPlugin(each, remove=True)


def delete_unused_nodes():
    mel.eval("MLdeleteUnused;")


def delete_unknown_nodes():
    for each in (cmds.ls(type="unknown") + cmds.ls(type="unknownDag")) or []:
        if not cmds.objExists(each):
            continue
        cmds.lockNode(each, lock=False)
        cmds.delete(each)


def disconnect_clusters_bpm(clusters=None):
    if not clusters:
        clusters = get_clusters()
    for cluster in clusters:
        input_plug, dest_plug = build_cluster_plugs(cluster)
        try:
            cmds.disconnectAttr(input_plug, dest_plug)
        except Exception as e:
            cmds.warning(e)


def duplicate_node(
    node, parent=None, complement_name=None, replace=None, strict_name=None
):
    """Duplicate node

    Args:
        node (str): node to duplicate
        parent (str): parent duplicated mesh to this transform
        complement_name (str, optional): add the given string before the suffix of the node
        replace (list, optional): search and replace an element of the name, needs to be list of 2 items
        strict_name (str, optional): override name

    Return:
        list of duplicated node and all childrens
    """
    nodes = []
    new_nodes = cmds.duplicate(node, renameChildren=True)
    if parent:
        cmds.parent(new_nodes[0], parent)

    for new in new_nodes:
        tokens = new.split("_")
        if complement_name:
            tokens.insert(-1, complement_name)
        new_name = "_".join(tokens)
        if new_name[-1].isdigit():
            new_name = new_name[:-1]
        if replace:
            new_name = new_name.replace(replace[0], replace[1])
        if strict_name:
            new_name = strict_name

        cmds.rename(new, new_name)
        nodes.append(new_name)

    return nodes


def export_skinning_weights(mesh, directory):
    deformers, types = list_deformers(mesh, types=["skinCluster"])
    if not deformers:
        return
    filepath = os.path.join(
        directory, "{}_ngSkinWeights.json".format(deformers[0])
    )

    export_ng_layer(filepath, mesh)


def export_ng_layer(file_path, mesh):
    load_ng_plugin()

    create_ng_node(mesh)
    api.export_json(mesh, file=file_path)

    return file_path


def export_alembic_from_rig_scene():
    label = "_model_grp"
    asset = cmds.ls("*" + label)[0].split(label)[0]
    dir_root = r"Y:\YL2FAB\assets\characters\{}\maya".format(asset)
    selection = get_selection()
    for obj in selection:
        dir_add = r"\autorig\proxy\{}.abc".format(obj)
        command = (
            "-frameRange 1001 1001 -uvWrite -worldSpace -root "
            + obj
            + " -file "
            + dir_root
            + dir_add
        )

        cmds.AbcExport(j=command)
        msg_path = "{root}" + dir_add
        cmds.warning("ABC exported to : {}".format(msg_path), noContext=True)


def flip_obj(obj):
    mirror_obj(obj, replaces=("", ""))


def get_attributes(obj, attributes="trs", axis="xyz"):
    attribute_list = []
    attribute_value_list = []
    for attr in [x + y for x in attributes for y in axis]:
        value = cmds.getAttr("{}.{}".format(obj, attr))
        attribute_list.append(attr)
        attribute_value_list.append(value)

    return attribute_list, attribute_value_list


def get_closest_point(point, target_points):
    closest = None
    coords = cmds.xform(point, query=True, translation=True, worldSpace=True)
    min_distance = float("inf")

    for tgt_point in target_points:
        position = cmds.pointPosition(tgt_point)
        distance = sum((a - b) ** 2 for a, b in zip(coords, position)) ** 0.5
        if distance < min_distance:
            min_distance = distance
            closest = tgt_point

    return closest


def get_component_label(obj):
    shape = cmds.listRelatives(obj, shapes=True)
    if not shape:
        cmds.error("No shape found for object: {}".format(obj), noContext=True)
    shape_type = cmds.objectType(shape[0])

    label_map = {
        "mesh": ".vtx[*]",
        "nurbsCurve": ".cv[*]",
        "nurbsSurface": ".cv[*][*]",
    }

    if shape_type not in label_map:
        cmds.error(
            "Unsupported shape type: {}".format(shape_type), noContext=True
        )

    return label_map[shape_type]


def get_selection():
    return cmds.ls(selection=True)


def get_selection_flatten():
    return cmds.ls(selection=True, flatten=True)


def get_shape(obj):
    shapes = cmds.listRelatives(obj, shapes=True)
    if not shapes:
        return None
    return shapes[0]


def get_children(node, typ=None):
    """Get all child transforms of a node

    Args:
        node (str): node where to list childs

    Return:
        list: all founded childs
    """
    childs = []

    if typ:
        children = cmds.listRelatives(node, children=True, type=typ) or []
    else:
        children = cmds.listRelatives(node, children=True) or []

    for child in children:
        if "Shape" not in child:
            childs.append(child)
            continue

    return childs


def get_parent(node):
    parents = cmds.listRelatives(node, parent=True) or []
    if parents:
        parent = parents[0]
    else:
        parent = None
    return parent


def get_clusters(cluster_group=GROUPS_DATA["clusters"]):
    clusters = []
    children = cmds.listRelatives(cluster_group, allDescendents=True)
    for child in children:
        typ = cmds.nodeType(child)
        if typ != "clusterHandle":
            continue
        name = child
        if "HandleShape" in child:
            name = child.replace("HandleShape", "")
        clusters.append(name)

    return clusters


def get_controllers():
    return cmds.ls(CTRLS_SEARCH) + cmds.ls("*:" + CTRLS_SEARCH)


def get_deformers(mesh, types):
    """List deformers from a mesh

    Args:
        mesh (str): mesh with all deformers
        types (list): deformer filter for research

    Return:
        tuple:
            list of direct deformers,
            list of their respective types.
    """
    deformers = []
    deformers_types = []

    relatives = cmds.listRelatives(mesh, shapes=True, fullPath=True)
    shape_node = relatives[0] if relatives else None
    if shape_node:
        history = cmds.listHistory(shape_node, pruneDagObjects=True) or []
        for deformer in history:
            for typ in types:
                deformer_filtered = cmds.ls(deformer, type=typ) or None

                if deformer_filtered:
                    deformers.append(deformer_filtered[0])
                    deformers_types.append(typ)
                    continue

    return deformers, deformers_types


def import_skinning_weights(mesh, directory):
    deformers, types = list_deformers(mesh, types=["skinCluster"])
    if not deformers:
        return
    skincluster = deformers[0]

    try:
        load_ng_node(mesh, directory, skincluster)
        delete_ng_nodes()
    except:
        cmds.warning(
            "Import skinning weights failed for {}.".format(skincluster),
            noContext=True,
        )


def is_controller(obj):
    shapes = cmds.listRelatives(obj, shapes=True, fullPath=True) or []
    for shape in shapes:
        if not cmds.objExists(shape):
            continue
        if cmds.objectType(shape) != "nurbsCurve":
            continue
        if cmds.getAttr("{}.intermediateObject".format(shape)):
            continue

        return True
    return False


def load_ng_plugin(plugin="ngSkinTools2"):
    if not cmds.pluginInfo(plugin, query=True, loaded=True):
        cmds.loadPlugin(plugin)


def load_ng_node(msh, directory_path, skin_cluster):
    file_path = os.path.join(
        directory_path,
        skin_cluster + "_ngSkinWeights.json",
    )

    config = api.InfluenceMappingConfig()
    config.globs = []
    config.distance_threshold = 0.1

    api.import_json(
        msh,
        file=file_path,
        vertex_transfer_mode=api.VertexTransferMode.vertexId,
        influences_mapping_config=config,
    )


def list_deformers(mesh, types):
    deformers = []
    deformers_types = []

    relatives = cmds.listRelatives(mesh, shapes=True, fullPath=True)
    shape_node = relatives[0] if relatives else None
    if shape_node:
        history = cmds.listHistory(shape_node, pruneDagObjects=True) or []
        for deformer in history:
            for typ in types:
                deformer_filtered = cmds.ls(deformer, type=typ) or None
                if deformer_filtered:
                    deformers.append(deformer_filtered[0])
                    deformers_types.append(typ)
                    continue

    return deformers, deformers_types


def list_set_members(sets):
    sets_and_objects = {}
    for obj_set in sets:
        # Get members of the set
        members = cmds.sets(obj_set, query=True) or []
        if members:
            sets_and_objects[obj_set] = members

    return sets_and_objects


def matrix_match_transforms(target, source):
    """Match transforms by matrix"""
    matrix = cmds.xform(source, query=True, matrix=True, worldSpace=True)
    apply_matrix(target, matrix)


def mirror_obj(
    obj, replaces=("L_", "R_"), invert=True, attrs=("tx", "ry", "rz", "sx")
):
    obj_other_side = obj.replace(replaces[0], replaces[1], 1)
    if not cmds.objExists(obj_other_side):
        return
    typ = cmds.objectType(obj)
    if typ in ["pointConstraint", "parentConstraint", "aimConstraint"]:
        attributes, values = get_attributes(obj, attributes="o")
        for i, attr in enumerate(attributes):
            new_value = -values[i] if "x" in attr else values[i]
            cmds.setAttr("{}.{}".format(obj_other_side, attr), new_value)

    target_typ = ["transform", "joint"]
    if typ not in target_typ:
        return
    attributes, values = get_attributes(obj)
    for i, attr in enumerate(attributes):
        if invert:
            new_value = (
                -values[i] if any(x in attr for x in attrs) else values[i]
            )
        else:
            new_value = values[i]

        try:
            cmds.setAttr("{}.{}".format(obj_other_side, attr), new_value)
        except:
            cmds.warning(
                "Can not setAttr: {}.{}".format(obj_other_side, attr),
                noContext=True,
            )


def mirror_cvs(cvs, mode="x", replaces=("L_", "R_")):
    for cv in cvs:
        pos = cmds.xform(cv, q=1, ws=1, t=1)
        cv_side = cv.replace(replaces[0], replaces[1], 1)
        if not cmds.objExists(cv_side):
            continue

        if mode == "x":
            cmds.xform(cv_side, ws=1, t=[pos[0] * (-1), pos[1], pos[2]])
        if mode == "z":
            cmds.xform(cv_side, ws=1, t=[pos[0], pos[1], pos[2] * (-1)])


def mirror_controllers(search="L_" + CTRLS_SEARCH, replaces=("L_", "R_")):
    double_offsets = []
    point_constraints = []
    controllers = cmds.ls(search)
    for obj in controllers:
        other_side = obj.replace(replaces[0], replaces[1], 1)
        if (
            not cmds.objExists(other_side)
            or ("eye_" in obj and "cluster_" not in obj)
            or "Twk" in obj
            or "twk" in obj
            or "Lid" in obj
        ):
            controllers.remove(obj)
            continue
        offset = get_parent(obj)
        double_offset = get_parent(offset)
        if not double_offset:
            continue
        if "offset_offset" not in double_offset:
            if "offset" not in offset:
                continue
            double_offset = offset

        children = get_children(double_offset)
        point_constraint = children[-1] if len(children) > 1 else None
        double_offsets.append(double_offset)
        if (
            point_constraint
            and cmds.objectType(point_constraint) == "pointConstraint"
        ):
            point_constraints.append(point_constraint)

    for obj in double_offsets + point_constraints:
        mirror_obj(obj, replaces=replaces, invert=True)

    for ctrl in controllers:
        ctrl_cvs = cmds.ls(f"{ctrl}.cv[*]", flatten=True)
        mirror_cvs(ctrl_cvs, replaces=replaces)

    cmds.inViewMessage(
        amg='<font color="deepskyblue">Controllers are mirrored</font>',
        fontSize=25,
        pos="midCenter",
        fade=True,
    )


def mirror_joints(search="M_base_*_jnt_offset", replaces=("L_", "R_")):
    raw = []
    bases = cmds.ls(search)
    for base in bases:
        if not cmds.objExists(base):
            continue
        children = cmds.listRelatives(base, allDescendents=True)[::-1]
        raw.extend(children)

    nodes = []
    for node in raw:
        if "_offset" not in node:
            continue
        if replaces[0] not in node:
            continue
        nodes.append(node)

    for obj in nodes:
        obj_other_side = obj.replace(replaces[0], replaces[1], 1)
        fullpath = cmds.listRelatives(
            obj_other_side, allParents=True, fullPath=True
        )[0]
        parents = fullpath.split("|")
        invert = True
        for parent in parents:
            if not parent or not cmds.objExists(parent):
                continue
            sx = cmds.getAttr(f"{parent}.sx")
            if sx < 0:
                invert = False
                break

        mirror_obj(obj, replaces=replaces, invert=invert)

    cmds.inViewMessage(
        amg='<font color="orchid">Joints are mirrored</font>',
        fontSize=25,
        pos="midCenter",
        fade=True,
    )


def mirror_ng_layers():
    # ng config
    config = api.InfluenceMappingConfig.transfer_defaults()
    config.globs = [
        ("L_*", "R_*"),
        ("l_*", "r_*"),
        ("lf_*", "rt_*"),
        ("*_lf", "*_rt"),
        ("M_*L_*", "M_*R_*"),
        ("M_*M_*", "M_*M_*"),
    ]
    config.use_label_matching = False
    config.use_distance_matching = False
    config.use_name_matching = True

    meshes = get_selection()
    for mesh in meshes:
        skincluster, types = list_deformers(mesh, types=["skinCluster"])
        mirror = api.Mirror(skincluster)
        mirror.recalculate_influences_mapping()

        layer_data = api.init_layers(mesh)
        for layer in layer_data.list():
            layer.set_current()
            mirror.mirror(api.MirrorOptions())


def rebuild_blendshape_target(blendshape, index):
    target = cmds.sculptTarget(
        blendshape, edit=True, regenerate=True, target=index
    )
    if not target:
        cmds.error(
            f"Please delete all targets curves from {blendshape}",
            noContext=True,
        )

    return target[0]


def reset_transforms(
    obj,
    reset_attrs=("translate", "rotate", "scale"),
    axis="XYZ",
    force_locked=False,
):
    """Reset transforms attributes of an object node

    Args:
        obj (str): object node
        reset_attrs (list): transforms attributes to reset
            Any attributes with "XYZ" after
        axis (list): reset axis

    """
    attrs = [x + y for x in reset_attrs for y in axis]
    for attr in attrs:
        value = 1 if attr.startswith("scale") else 0
        try:
            plug = "{}.{}".format(obj, attr)
            locked = False
            if force_locked:
                locked = cmds.getAttr(plug, lock=True)
                if locked:
                    cmds.setAttr(plug, lock=False)
            cmds.setAttr(plug, value, lock=locked)
        except RuntimeError:
            continue


def reset_user_attributes(obj):
    for attr in cmds.listAttr(obj, userDefined=True) or []:
        full = "{}.{}".format(obj, attr)
        if not cmds.getAttr(full, settable=True):
            continue
        if cmds.getAttr(full, type=True) not in ATTRIBUTES_TYPE:
            continue

        default_value = cmds.addAttr(full, query=True, defaultValue=True)
        try:
            cmds.setAttr(full, default_value)
        except:
            continue


def reset_selection(
    reset_attrs=("translate", "rotate", "scale"),
    user_attr=True,
    force_locked=False,
):
    reset_attrs = list(reset_attrs)
    for obj in get_selection() or []:
        if cmds.objectType(obj) == "joint":
            reset_attrs.append("jointOrient")
        reset_transforms(obj, reset_attrs, force_locked=force_locked)
        if not user_attr:
            continue
        if obj in CTRLS_EXCEPTION:
            continue
        reset_user_attributes(obj)


def reset_controller_selection(user_attr=True):
    for ctrl in get_selection() or []:
        if not is_controller(ctrl):
            continue
        reset_transforms(ctrl)
        if not user_attr:
            continue
        if ctrl in CTRLS_EXCEPTION:
            continue
        reset_user_attributes(ctrl)


def reset_all_controllers(user_attr=True):
    for ctrl in get_controllers():
        if not is_controller(ctrl):
            continue
        reset_transforms(ctrl)
        if not user_attr:
            continue
        if ctrl in CTRLS_EXCEPTION:
            continue
        reset_user_attributes(ctrl)


def reset_cvs_to_local_axis():
    """
    Resets the CV positions by applying the pivot offset.
    """
    # Get selected object
    selection = get_selection()
    for obj in selection:
        current_pivot = cmds.xform(
            obj, query=True, worldSpace=True, rotatePivot=True
        )
        temp = cmds.duplicate(obj, renameChildren=True)[0]
        children = cmds.listRelatives(temp, children=True)
        [cmds.delete(c) for c in children if "Shape" not in c]
        cmds.xform(temp, centerPivots=True, worldSpaceDistance=True)
        reset_pivot = cmds.xform(
            temp, query=True, worldSpace=True, rotatePivot=True
        )
        cmds.delete(temp)
        offset = [
            current - reset
            for reset, current in zip(reset_pivot, current_pivot)
        ]
        cvs = cmds.ls(
            "{}.cv[*]".format(obj), flatten=True
        )  # Flatten to get all CVs
        for cv in cvs:
            pos = cmds.xform(cv, query=True, translation=True, worldSpace=True)
            new_pos = [p + o for p, o in zip(pos, offset)]
            cmds.xform(cv, translation=new_pos, worldSpace=True)

        cmds.select(selection)


def set_current_value_as_default():
    channel_box = "mainChannelBox"
    selected_attrs = cmds.channelBox(
        channel_box, query=True, selectedMainAttributes=True
    )
    selection_nodes = cmds.ls(selection=True, objectsOnly=False)
    for node in selection_nodes:
        for attr in selected_attrs:
            plug = "{}.{}".format(node, attr)
            value = cmds.getAttr(plug)
            if not cmds.objExists(plug):
                cmds.warning(
                    "{} doesn't exist on {}. Cannot edit.".format(attr, node),
                    noContext=True,
                )
                continue
            try:
                cmds.addAttr(plug, edit=True, defaultValue=value)
                cmds.warning(
                    "{} default value attribute set to {}".format(plug, value),
                    noContext=True,
                )
            except RuntimeError:
                cmds.warning(
                    "Cannot set the default value for {}".format(plug),
                    noContext=True,
                )


def selection_to_cvs():
    selection = get_selection()
    all_cvs = []
    for obj in selection:
        shape = get_shape(obj)
        cvs = cmds.ls(shape + ".cv[*]", flatten=True)
        all_cvs.extend(cvs)
    cmds.select(all_cvs)


def setup_ng_custom_hotkeys():
    if cmds.hotkeySet("ngSkinTools2", query=True, exists=True):
        # Add custom hotkeys
        cmds.hotkey(
            keyShortcut="q",
            ctrlModifier=True,
            shiftModifier=True,
            altModifier=True,
            name="ngskintools_2_PaintNameCommand",
        )
        cmds.hotkey(
            keyShortcut="x",
            ctrlModifier=True,
            name="ngskintools_2_dR_viewXrayTGL",
        )

        # Set current hotkey set to ng
        cmds.hotkeySet("ngSkinTools2", edit=True, current=True)


def transfer_points_weights(points, target_points):
    for point in points:
        cmds.select(point)
        mel.eval("CopyVertexWeights;")

        closest = get_closest_point(point, target_points)
        cmds.select(closest)
        mel.eval("PasteVertexWeights;")


def transfer_points_weights_from_sel():
    selection = get_selection()
    if len(selection) != 2:
        cmds.error("Please select exactly 2 objects", noContext=True)

    labels = [get_component_label(obj) for obj in selection]

    source_points = cmds.ls(selection[0] + labels[0], flatten=True)
    target_points = cmds.ls(selection[1] + labels[1], flatten=True)

    transfer_points_weights(source_points, target_points)


def transfer_skincluster_to_mirrored_mesh(
    mesh, target, method="closestPoint", keep_layers=False
):
    # ng config
    infl_config = api.InfluenceMappingConfig.transfer_defaults()
    infl_config.globs = [
        ("L_*", "R_*"),
        ("l_*", "r_*"),
        ("lf_*", "rt_*"),
        ("*_lf", "*_rt"),
        ("M_*", "M_*"),
    ]
    infl_config.use_label_matching = False
    infl_config.use_distance_matching = False
    infl_config.use_name_matching = True

    # mirror mesh
    cmds.setAttr("{}.scaleX".format(mesh), lock=False)
    cmds.setAttr("{}.scaleX".format(mesh), -1, lock=True)

    # transfer skinCluster
    skincluster, types = list_deformers(target, types=["skinCluster"])
    if skincluster and not keep_layers:
        cmds.select(target)
        cmds.DetachSkin()

    cmds.select(mesh, target)
    copy_skincluster_callback(method="closestPoint")

    t = api.transfer.LayersTransfer()
    t.source = mesh
    t.target = target
    t.vertex_transfer_mode = method
    t.influences_mapping.config = infl_config
    t.keep_existing_layers = keep_layers

    t.execute()

    # restore mesh
    cmds.setAttr("{}.scaleX".format(mesh), lock=False)
    cmds.setAttr("{}.scaleX".format(mesh), 1, lock=True)


def transfer_ng_layers(method="closestPoint", keep_layers=False):
    # ng config
    infl_config = api.InfluenceMappingConfig.transfer_defaults()
    infl_config.globs = [
        ("L_*", "L_*"),
        ("R_*", "R_*"),
        ("M_*", "M_*"),
    ]
    infl_config.use_label_matching = False
    infl_config.use_distance_matching = False
    infl_config.use_name_matching = True

    selection = get_selection()
    base = selection[0]
    selection.pop(0)
    for obj in selection:
        skincluster, types = list_deformers(obj, types=["skinCluster"])
        if skincluster and not keep_layers:
            cmds.select(obj)
            cmds.DetachSkin()

        cmds.select(base, obj)
        copy_skincluster_callback(method="closestPoint")
        t = api.transfer.LayersTransfer()
        t.source = base
        t.target = obj
        t.vertex_transfer_mode = method
        t.influences_mapping.config = infl_config
        t.keep_existing_layers = keep_layers

        t.execute()


def xform_match_transforms(
    target, source, attrs=("translation", "rotation", "scale")
):
    """Match transforms by xform"""
    for attr in attrs:
        if attr in {"translation", "rotation", "scale"}:
            values = cmds.xform(
                source, query=True, **{attr: True}, worldSpace=True
            )
            cmds.xform(target, **{attr: values}, worldSpace=True)


def xform_average_match_transforms(
    target, sources, attrs=("translation", "rotation", "scale")
):
    for attr in attrs:
        if attr not in {"translation", "rotation", "scale"}:
            continue

        summed_pos = [0.0, 0.0, 0.0]
        for source in sources:
            pos = cmds.xform(
                source,
                query=True,
                **{attr: True},
                worldSpace=True,
            )
            summed_pos = [sum_val + p for sum_val, p in zip(summed_pos, pos)]

        count = len(sources)
        avg_pos = [val / count for val in summed_pos]
        cmds.xform(target, **{attr: avg_pos}, worldSpace=True)
