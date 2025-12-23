from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import maya.cmds as cmds
import maya.OpenMayaUI as omui
import shiboken2
from PySide2 import QtCore
from PySide2 import QtWidgets

from .. import utils
from . import tools


def get_maya_main_window():
    """Get the main Maya window instance."""
    ptr = omui.MQtUtil.mainWindow()
    return shiboken2.wrapInstance(int(ptr), QtWidgets.QWidget)


class MoveJointsWindow(QtWidgets.QWidget):
    def __init__(self, parent=None):
        maya_parent = parent or get_maya_main_window()
        super(MoveJointsWindow, self).__init__(maya_parent)
        QtWidgets.QWidget(self)

        # Build Window
        self.setWindowTitle("Move Joints Tool")
        self.setGeometry(300, 300, 310, 470)

        self.setWindowFlags(
            QtCore.Qt.Window
            | QtCore.Qt.WindowMinimizeButtonHint
            | QtCore.Qt.WindowCloseButtonHint
        )
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)

        # Install an event filter on the Maya main window
        maya_parent.installEventFilter(self)

        # ---------- LAYOUT MAIN ----------- #
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)

        scroll_area = QtWidgets.QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(container)

        outer_layout = QtWidgets.QVBoxLayout(self)
        outer_layout.addWidget(scroll_area)

        # ---- Layout Move ---- #
        layout_tool = QtWidgets.QVBoxLayout()
        # Group Move
        group_tool = QtWidgets.QGroupBox(" Move Tool ")
        group_tool.setLayout(layout_tool)
        layout.addWidget(group_tool)

        group_tool.setStyleSheet("""
    QGroupBox {
        border: 2px solid #505050;
        border-radius: 4px;
        padding: 5px;
        font-weight: bold;
    }
""")
        # Layout Mesh
        layout_mesh = QtWidgets.QHBoxLayout(container)
        layout_tool.addLayout(layout_mesh)
        # layout list
        layout_list = QtWidgets.QHBoxLayout(container)
        layout_tool.addLayout(layout_list)
        # Layout Move
        layout_move = QtWidgets.QHBoxLayout(container)
        layout_tool.addLayout(layout_move)

        # ---- Layout Export ---- #
        layout_exp = QtWidgets.QVBoxLayout()
        # Group Move
        group_exp = QtWidgets.QGroupBox(" Export/Import ")
        group_exp.setLayout(layout_exp)
        layout.addWidget(group_exp)

        group_exp.setStyleSheet("""
    QGroupBox {
        border: 2px solid #505050;
        border-radius: 4px;
        padding: 5px;
        font-weight: bold;
    }
""")

        layout.setSizeConstraint(
            QtWidgets.QLayout.SetMinimumSize
        )  # Allow dynamic resizing
        layout.setStretchFactor(group_tool, 1)  # Let "Move Tool" expand
        layout.setStretchFactor(group_exp, 1)  # Let "Export" expand

        # Layout Path
        layout_path = QtWidgets.QHBoxLayout(container)
        layout_exp.addLayout(layout_path)
        # Export
        layout_imp_exp = QtWidgets.QHBoxLayout(container)
        layout_exp.addLayout(layout_imp_exp)

        locators_button = QtWidgets.QPushButton("Export Locators")
        layout_exp.addWidget(locators_button)

        layout_locators = QtWidgets.QHBoxLayout(container)
        layout_exp.addLayout(layout_locators)
        build_button = QtWidgets.QPushButton("Build From Locator")
        layout_exp.addWidget(build_button)

        rebuild_button = QtWidgets.QPushButton("Rebuild SkinClusters")
        layout_exp.addWidget(rebuild_button)

        # ----- INPUTS ----- #

        # ----- Move Tool ---- #
        # Mesh
        joint_label = QtWidgets.QLabel("Base Joint:")
        joint_button = QtWidgets.QPushButton("Select")

        layout_mesh.addWidget(joint_label)
        layout_mesh.addWidget(joint_button)

        # list
        self.plus_button = QtWidgets.QPushButton("+")
        self.plus_button.setFixedWidth(30)
        self.plus_button.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed
        )
        self.minus_button = QtWidgets.QPushButton("-")
        self.minus_button.setFixedWidth(30)
        self.minus_button.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed
        )

        layout_mesh.addWidget(self.plus_button)
        layout_mesh.addWidget(self.minus_button)

        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection
        )
        layout_list.addWidget(self.list_widget)

        # Unbind/Rebind
        unbind_button = QtWidgets.QPushButton("Unbind")
        rebind_button = QtWidgets.QPushButton("Rebind")
        layout_move.addWidget(unbind_button)
        layout_move.addWidget(rebind_button)

        # ----- Export ----- #
        # Path Label
        path_label = QtWidgets.QLabel("Path: ")
        self.path_line = QtWidgets.QLineEdit("")
        browse_button = QtWidgets.QPushButton("Browse")

        layout_path.addWidget(path_label)
        layout_path.addWidget(self.path_line)
        layout_path.addWidget(browse_button)

        export_button = QtWidgets.QPushButton("Export Weights")
        import_button = QtWidgets.QPushButton("Import Weights")
        layout_imp_exp.addWidget(export_button)
        layout_imp_exp.addWidget(import_button)

        locator_label = QtWidgets.QLabel("Source Loc: ")
        self.locator_line = QtWidgets.QLineEdit("")
        select_loc_button = QtWidgets.QPushButton("Select")

        layout_locators.addWidget(locator_label)
        layout_locators.addWidget(self.locator_line)
        layout_locators.addWidget(select_loc_button)

        joint_button.clicked.connect(self.mesh_button_clicked)
        self.plus_button.clicked.connect(self.plus_button_clicked)
        self.minus_button.clicked.connect(self.minus_button_clicked)
        unbind_button.clicked.connect(self.unbind_button_clicked)
        rebind_button.clicked.connect(self.rebind_button_clicked)

        browse_button.clicked.connect(self.browse_path)
        export_button.clicked.connect(self.export_button_clicked)
        import_button.clicked.connect(self.import_button_clicked)
        locators_button.clicked.connect(self.locators_button_clicked)

        select_loc_button.clicked.connect(self.select_loc_button_clicked)
        build_button.clicked.connect(self.build_button_clicked)

        rebuild_button.clicked.connect(self.rebuild_button_clicked)

        self.joints = []

    def eventFilter(self, source, event):
        if (
            source == get_maya_main_window()
            and event.type() == QtCore.QEvent.WindowActivate
        ):
            self.raise_()
        return QtCore.QObject.eventFilter(self, source, event)

    def mesh_button_clicked(self):
        joints = utils.get_selection()
        self.joints = []
        self.list_widget.clear()
        if not joints:
            return

        for joint in joints:
            self.joints.append(joint)
            self.list_widget.addItem(joint)

    def plus_button_clicked(self):
        joints = utils.get_selection()
        for joint in joints:
            if joint in self.joints:
                continue

            self.joints.append(joint)
            self.list_widget.addItem(joint)

    def minus_button_clicked(self):
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            return

        for item in selected_items:
            joint_name = item.text()
            if joint_name in self.joints:
                self.joints.remove(joint_name)
            self.list_widget.takeItem(self.list_widget.row(item))

    def unbind_button_clicked(self):
        try:
            for joint in self.joints:
                tools.unbind_skinclusters(joint=joint)
        except Exception as e:
            print(e)

    def rebind_button_clicked(self):
        try:
            for joint in self.joints:
                tools.rebind_skinclusters(joint=joint)
        except Exception as e:
            print(e)

    def browse_path(self):
        selected_path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Directory", "", QtWidgets.QFileDialog.ShowDirsOnly
        )
        if selected_path:
            self.path_line.setText(selected_path)

    def export_button_clicked(self):
        directory = self.path_line.text()
        try:
            for joint in self.joints:
                meshes = tools.get_meshes_influenced_by_joint(joint)
                for mesh in meshes:
                    utils.export_skinning_weights(
                        mesh=mesh, directory=directory
                    )
                    print("Skinning weights exported for: {}".format(mesh))

                tools.export_skincluster_data_from_joint(
                    directory=directory, joint=joint
                )

        except Exception as e:
            print(e)

    def import_button_clicked(self):
        try:
            directory = self.path_line.text()
            joints = self.joints
            for joint in joints:
                if not joint:
                    print("Please select a joint in 'Baase Joint' field.")
                    continue
                if not directory:
                    print(
                        "Please specify a path from where to fetch skinWeights"
                    )
                    continue

                meshes = []
                joint_hierarchy = cmds.listRelatives(
                    joint, allDescendents=True, type="joint"
                )
                for jnt in joint_hierarchy:
                    skinclusters = (
                        cmds.listConnections(jnt, type="skinCluster") or []
                    )
                    for skincluster in skinclusters:
                        mesh_shapes = (
                            cmds.skinCluster(
                                skincluster, query=True, geometry=True
                            )
                            or []
                        )

                        meshes.extend(mesh_shapes)

                meshes = list(set(meshes))
                for mesh in meshes:
                    utils.import_skinning_weights(
                        mesh=utils.get_parent(mesh), directory=directory
                    )

        except Exception as e:
            print(e)

    def locators_button_clicked(self):
        try:
            joints = self.joints
            path = self.path_line.text()
            for joint in joints:
                tools.export_locators(joint, path)

        except Exception as e:
            print(e)

    def select_loc_button_clicked(self):
        self.loc = utils.get_selection()
        if not self.loc:
            cmds.warning("Please select at least one locator.")

        display = ", ".join(self.loc)
        self.locator_line.setText(display)

    def build_button_clicked(self):
        try:
            for loc in self.loc:
                tools.build_joint_hierarchy_from_locators(
                    loc, parent_joint=None
                )

        except Exception as e:
            print(e)

    def rebuild_button_clicked(self):
        directory = self.path_line.text()
        joints = list(self.joints)

        try:
            for joint in joints:
                tools.import_skincluster_data_from_joint(
                    joint=joint, directory=directory
                )
                meshes = tools.get_meshes_influenced_by_joint(joint=joint)
                for mesh in meshes:
                    utils.import_skinning_weights(
                        mesh=mesh, directory=directory
                    )
        except Exception as e:
            print(e)


def show_move_joints_tool():
    global move_joints_window
    try:
        move_joints_window.close()  # Close previous instances
    except Exception:
        pass
    move_joints_window = MoveJointsWindow(
        None
    )  # Pass None as parent to make it fully movable
    move_joints_window.setStyle(
        QtWidgets.QStyleFactory.create("Fusion")
    )  # Apply UI style
    move_joints_window.show()
