from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import maya.cmds as cmds

"""
# Copy / Paste this in the script editor:

# Step 00
# import all scripts and modules
import maya.cmds as cmds
import bgdev.utils.skincluster

def import_script(path):
    with open(path, 'r') as file:
        content = file.read()
    exec(content, globals())
path = r"N:\sandbox\mverclytte\scripts\transfer_deformer_weights\core.py" # Add the script path
import_script(path)

# Step 01
# Select the reference mesh with all deformers
mesh_reference = cmds.ls(sl=True)[0]
target_types = ['cluster', 'ffd']
duplicates = []
skinclusters = []
deformers, deformers_types = list_deformers(mesh_reference, target_types)
for deformer in deformers:
    duplicate, skincluster = deformer_weight_to_skin(mesh_reference, deformer)
    duplicates.append(duplicate)
    skinclusters.append(skincluster)

# Step 02
# Select the final mesh
mesh_target = cmds.ls(sl=True)[0]
for i, mesh in enumerate(duplicates):
    base = duplicate_mesh(mesh=mesh_target, custom_name=None, parent='TMP') # mesh=mesh if you want to copy for a vertex order changement
    cmds.select(mesh, base)
    bgdev.utils.skincluster.copy_skincluster_callback(method="closestPoint")
    history = cmds.listHistory(base)
    skincluster = cmds.ls(history, type='skinCluster')[0]
    cmds.delete(mesh)
    cmds.rename(base, mesh)
    cmds.rename(skincluster, skinclusters[i])

copy_deformers(mesh_reference, mesh_target)
for i, duplicate in enumerate(duplicates):
    skincluster_to_deformer_weight(
        mesh_base=duplicate,
        mesh_target=mesh_target,
        skincluster_base=skinclusters[i],
        deformer_target=deformers[i]
    )

"""


def skincluster_to_deformer_weight(
    mesh_base="", mesh_target="", skincluster_base="", deformer_target=""
):
    """Transfer skinCluster from a mesh to deformer weight map on an other mesh

    Args:
        mesh_base (str): mesh with the skinning
        mesh_target (str): mesh with the deformer
        skincluster_base (str): skinCluster name in the mesh history
        deformer_target (str): deformer name in the mesh history
    """

    for i in range(cmds.polyEvaluate(mesh_base, vertex=True)):
        vertex_weight = cmds.skinPercent(
            skincluster_base,
            "{}.vtx[{}]".format(mesh_base, i),
            q=True,
            value=True,
        )
        cmds.select("{}.vtx[{}]".format(mesh_target, i))
        cmds.percent(deformer_target, value=vertex_weight[1])
        cmds.select(clear=True)


def duplicate_mesh(mesh="", custom_name="", parent=""):
    """Duplicate a mesh

    Args:
        mesh (str): mesh to duplicate
        custom_name (str): name for the duplicated mesh
        parent (str): parent duplicated mesh to this transform

    Return:
        str of duplicated mesh
    """

    duplicated = cmds.duplicate(mesh, n=custom_name)[0]

    for attr in [x + y for x in "trs" for y in "xyz"]:
        cmds.setAttr(f"{duplicated}.{attr}", lock=False)
    if not parent:
        try:
            cmds.parent(duplicated, world=True)
        except:
            pass
    else:
        try:
            cmds.parent(duplicated, parent)
        except:
            pass

    return duplicated


def deformer_weight_to_skin(mesh_base="", deformer_base=""):
    """Convert deformer weights to skinCluster

    Args:
        mesh_base (str): mesh with the deformer
        deformer_base (str): deformer name in the mesh history

    Return:
        tuple:
            str of result skinned mesh
            str of skinCluster name
    """

    if not cmds.objExists("TMP"):
        cmds.createNode("transform", name="TMP")

    duplicated = duplicate_mesh(
        mesh=mesh_base,
        custom_name="transfert_{}_from_{}".format(deformer_base, mesh_base),
        parent="TMP",
    )
    joint_base = cmds.joint("TMP", name="jnt_base")
    joint_transfer = cmds.joint("TMP", name="jnt_transfert", p=(0, 0.5, 0))

    skincluster = cmds.skinCluster(joint_base, duplicated)[0]
    cmds.skinCluster(
        skincluster, edit=True, addInfluence=joint_transfer, lockWeights=True
    )

    for i in range(cmds.polyEvaluate(mesh_base, vertex=True)):
        weight = cmds.percent(
            deformer_base, "{}.vtx[{}]".format(mesh_base, i), q=True, v=True
        )
        cmds.skinPercent(
            skincluster,
            "{}.vtx[{}]".format(duplicated, i),
            transformValue=(joint_transfer, weight[0]),
        )

    return duplicated, skincluster


def list_deformers(mesh="", types=("cluster", "ffd")):
    """List deformers from a mesh

    Args:
        mesh (str): mesh with all deformers
        types (list): deformer filter for research

    Return:
        tuple:
            list of deformers,
            list of their respective types.
    """

    shape_node = cmds.listRelatives(mesh, shapes=True, fullPath=True)[0] or []
    if shape_node:
        history = cmds.listHistory(shape_node, pruneDagObjects=True) or []

        deformers = []
        deformers_types = []
        for deformer in history:
            deformer_filtered = None
            for typ in types:
                deformer_filtered = cmds.ls(deformer, type=typ) or None
                if deformer_filtered:
                    deformers.append(deformer_filtered[0])
                    deformers_types.append(typ)
                    break

    return deformers, deformers_types


def copy_deformers(source, target, types=("cluster", "ffd")):
    """Copy deformers from a source to a target

    Args:
        source (str): mesh with all deformers
        target (str): mesh where to copy deformers
        types (list): deformer filter for research
    """

    deformer_stack = cmds.listHistory(source, pruneDagObjects=True)
    if not deformer_stack:
        return

    deformer_stack = [x for x in deformer_stack if cmds.nodeType(x) in types]
    for deformer in reversed(deformer_stack):
        cmds.deformer(deformer, edit=True, geometry=target)
