from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import json
import os

import maya.cmds as cmds
import stim

from .. import utils

LOG = stim.get_logger(__name__)


def get_meshes_influenced_by_joint(joint):
    if not cmds.objExists(joint):
        cmds.warning(f"No match found in the scene for '{joint}'.")
        return None

    # Get joint hierarchy
    joint_hierarchy = (
        cmds.listRelatives(joint, allDescendents=True, type="joint") or []
    )
    joint_hierarchy.append(joint)

    meshes_shapes = []
    for jnt in joint_hierarchy:
        skin_clusters = cmds.listConnections(jnt, type="skinCluster") or []
        for skin_cluster in skin_clusters:
            mesh_shapes = (
                cmds.skinCluster(skin_cluster, query=True, geometry=True) or []
            )
            meshes_shapes.extend(mesh_shapes)

    # Remove instances of the same mesh
    meshes_shapes = list(set(meshes_shapes))

    return [utils.get_parent(shape) for shape in meshes_shapes]


def get_data_from_joint(joint):
    """
    return: dict = {'mesh': {skinCluster: ['jnt1', 'jnt2', 'jnt3', ...]}}
    """
    joint_data_dict = {}

    meshes = get_meshes_influenced_by_joint(joint=joint)
    for mesh in meshes:
        if not mesh:
            cmds.warning(f"No meshes found to be connected to '{joint}'.")
            continue
        try:
            history = cmds.listHistory(mesh, pruneDagObjects=True) or []
            skin_clusters = [
                node
                for node in history
                if cmds.nodeType(node) == "skinCluster"
            ]

            skin_cluster_dict = {}
            if not skin_clusters:
                print(f"No skinClusters found for {mesh}")
                return {{}}

            for skin_cluster in skin_clusters:
                joints = cmds.skinCluster(
                    skin_cluster,
                    query=True,
                    influence=True,
                    weightedInfluence=False,
                )
                skin_cluster_dict[skin_cluster] = joints

            joint_data_dict[mesh] = skin_cluster_dict

        except Exception as e:
            print(e)

    return joint_data_dict


def create_locator_hierarchy(source, parent_locator=None, first_loc=None):
    """
    Recursively creates a locator hierarchy based on the source transform hierarchy,

    Args:
        source (str): The name of the source transform node.
        first_loc (str): The first locator in the hierarchy (tracked for return).

    Returns:
        str: first created locator
    """
    loc = utils.create_locator(
        "{}_loc".format(source), parent=parent_locator, match_to=source
    )
    if first_loc is None:
        first_loc = loc  # Store root locator

    children = utils.get_children(source)
    for child in children:
        if cmds.nodeType(child) != "joint":
            first_loc = create_locator_hierarchy(
                child, parent_locator=loc, first_loc=first_loc
            )
            continue

        sub_children = utils.get_children(child)
        for sub_child in sub_children:
            first_loc = create_locator_hierarchy(
                sub_child, parent_locator=loc, first_loc=first_loc
            )

    return first_loc


def unbind_skinclusters(joint):
    joint_data_dict = get_data_from_joint(joint=joint)

    processed_clusters = []
    meshes = list(joint_data_dict.keys())
    for mesh in meshes:
        for skin_cluster in joint_data_dict[mesh]:
            if skin_cluster in processed_clusters:
                continue
            cmds.skinCluster(skin_cluster, edit=True, unbindKeepHistory=True)
            processed_clusters.append(skin_cluster)

    string_value = "{}_customData_tmp".format(joint)
    stored_data = {}
    if cmds.optionVar(exists=string_value):
        cmds.warning(
            "Custom data has already been exported for {}.".format(joint)
        )
        return None

    json_string = json.dumps(joint_data_dict)
    cmds.optionVar(stringValue=(string_value, json_string))
    raw_json = cmds.optionVar(query=string_value)
    stored_data = json.loads(raw_json)
    print("Stored data :" + json.dumps(stored_data, indent=2))

    return joint_data_dict


def rebind_skinclusters(joint):
    if not joint:
        cmds.warning("Please select a joint as 'Base Joint'.")
        return
    try:
        if not cmds.optionVar(exists="{}_customData_tmp".format(joint)):
            print(f"OptionVar {joint}_customData_tmp was not found.")
            return

        raw_data = cmds.optionVar(query=f"{joint}_customData_tmp")
        stored_data = json.loads(raw_data)

        processed_clusters = []
        meshes = list(stored_data.keys())
        for mesh in meshes:
            for skin_cluster in stored_data[mesh]:
                if skin_cluster in processed_clusters:
                    continue

                joints = stored_data[mesh][skin_cluster]
                cmds.skinCluster(
                    joints,
                    mesh,
                    toSelectedBones=True,
                    maximumInfluences=5,
                    name=skin_cluster,
                )
                print(
                    "Skin Cluster has been recreated for mesh: {}".format(mesh)
                )
                processed_clusters.append(skin_cluster)

        cmds.optionVar(remove="{}_customData_tmp".format(joint))

    except Exception as e:
        print(e)


def export_locators(joint, path):
    if not cmds.objExists(joint):
        cmds.warning(
            "Please select a joint to extract a locator hierarchy from."
        )
        return

    joint_offset = joint
    if cmds.objectType(joint) == "joint":
        joint_offset = utils.get_parent(joint) or joint

    try:
        first_loc = create_locator_hierarchy(source=joint_offset)
        cmds.select(first_loc, add=False)
        file_path = os.path.join(
            path, "{}_hierarchy_locators.ma".format(joint_offset)
        )

        cmds.file(
            file_path,
            force=True,
            options="v=0",
            type="mayaAscii",
            exportSelected=True,
        )
        cmds.confirmDialog(
            title="Export Complete",
            message="Locators exported:\n\n{}".format(file_path),
        )
        cmds.delete(first_loc)

    except Exception as e:
        print(e)


def build_joint_hierarchy_from_locators(locator, parent_joint=None):
    offset_name = "_".join(locator.split("_")[:-1])
    offset_grp = cmds.group(empty=True, world=True, name=offset_name)

    joint_name = "_".join(offset_grp.split("_")[:-1])
    joint_node = cmds.joint(name=joint_name)

    utils.matrix_match_transforms(locator, offset_grp)

    if parent_joint:
        cmds.parent(offset_grp, parent_joint)

    children = utils.get_children(locator)
    for child in children:
        shape = utils.get_shape(child)
        if shape and cmds.nodeType(shape) == "locator":
            build_joint_hierarchy_from_locators(child, parent_joint=joint_node)

    return joint_node


def export_skincluster_data_from_joint(joint, directory):
    joint_data_dict = get_data_from_joint(joint=joint)
    filepath = os.path.join(
        directory, "{}_related_skinClusters_data.json".format(joint)
    )
    with open(filepath, "w") as json_file:
        json.dump(joint_data_dict, json_file, indent=4)

    return joint_data_dict


def import_skincluster_data_from_joint(joint, directory):
    if not directory:
        print("No directory given.")
        return
    try:
        file = os.path.join(
            directory, "{}_related_skinClusters_data.json".format(joint)
        )
        file = os.path.normpath(file)

        with open(file) as f:
            stored_data = json.load(f)
            processed_clusters = []
            meshes = list(stored_data.keys())
            for mesh in meshes:
                for skin_cluster in stored_data[mesh]:
                    if skin_cluster in processed_clusters:
                        continue

                    joints = stored_data[mesh][skin_cluster]
                    cmds.skinCluster(
                        joints,
                        mesh,
                        toSelectedBones=True,
                        maximumInfluences=5,
                        name=skin_cluster,
                    )
                    print(
                        "Skin Cluster has been recreated for: {}".format(mesh)
                    )
                    processed_clusters.append(skin_cluster)

    except Exception as e:
        print(e)
