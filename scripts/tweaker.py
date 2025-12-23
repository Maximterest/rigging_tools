from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

try:
    from qtpy import QtCore
    from qtpy import QtWidgets
except ImportError:
    try:
        from PySide2.QtCore import *
        from PySide2.QtGui import *
        from PySide2.QtWidgets import *

        # Create compatibility aliases
        class QtWidgets:
            QWidget = QWidget
            QVBoxLayout = QVBoxLayout
            QHBoxLayout = QHBoxLayout
            QFormLayout = QFormLayout
            QLabel = QLabel
            QPushButton = QPushButton
            QLineEdit = QLineEdit
            QSpinBox = QSpinBox
            QCheckBox = QCheckBox
            QFrame = QFrame
            QMessageBox = QMessageBox
            QApplication = QApplication
            QStyleFactory = QStyleFactory

        class QtCore:
            Qt = Qt
            QTimer = QTimer

        class QtGui:
            QFont = QFont

    except ImportError:
        from PySide.QtCore import *
        from PySide.QtGui import *

        # Create compatibility aliases for PySide
        class QtWidgets:
            QWidget = QWidget
            QVBoxLayout = QVBoxLayout
            QHBoxLayout = QHBoxLayout
            QFormLayout = QFormLayout
            QLabel = QLabel
            QPushButton = QPushButton
            QLineEdit = QLineEdit
            QSpinBox = QSpinBox
            QCheckBox = QCheckBox
            QFrame = QFrame
            QMessageBox = QMessageBox
            QApplication = QApplication
            QStyleFactory = QStyleFactory


import rig.control
from maya import cmds
from rig.utils import constraint_util

SIDES = "LR"
MOVE_LOC = "M_move_locator"
RIG_GRP = "rig_grp"
SECONDARY_GRP = "secondary_grp"
PARENT_JOINT = "M_base_02_jnt"
TARGET_MESH = "M_head_rig02_mesh"


def build_tweakers(label="eyelid_upper", jnt_number=3, do_sym=True):
    sel = get_selection_flatten()
    if not sel:
        cmds.error(
            "Please select edges where to build the setup", noContext=True
        )

    sym_sel = []
    if do_sym:
        cmds.symmetricModelling(symmetry=True, axis="x", about="object")
        cmds.select(sel, symmetry=True)
        sym = get_selection_flatten()
        cmds.symmetricModelling(symmetry=False)
        sym_sel = [edge for edge in sym if edge not in sel]

    for i, edges in enumerate([sel, sym_sel]):
        if not edges:
            continue

        # groups
        side_label = SIDES[i] + "_" + label
        base_grp = cmds.createNode(
            "transform",
            name=side_label + "_rig_grp",
            parent=RIG_GRP,
            skipSelect=True,
        )
        jnt_grp = cmds.createNode(
            "transform",
            name=side_label + "_jnt_grp",
            parent=PARENT_JOINT,
            skipSelect=True,
        )
        ctrl_grp = cmds.createNode(
            "transform",
            name=side_label + "_ctrl_grp",
            parent=SECONDARY_GRP,
            skipSelect=True,
        )
        misc_grp = cmds.createNode(
            "transform",
            name=side_label + "_misc_grp",
            parent=base_grp,
            skipSelect=True,
        )

        # build setup
        cmds.select(edges)
        curve, history = cmds.polyToCurve(name=side_label + "_curve")
        cmds.setAttr(history + ".conformToSmoothMeshPreview", 0, lock=True)
        cmds.parent(curve, misc_grp)
        lenght = cmds.getAttr(curve + "Shape.maxValue")
        distance = lenght / (jnt_number - 1)
        for i in range(jnt_number):
            name = "{}_{}".format(side_label, i)
            jnt_zero = cmds.createNode(
                "transform", name=name + "_jnt_offset", parent=jnt_grp
            )
            jnt = cmds.createNode(
                "joint", name=name + "_bind", parent=jnt_zero
            )
            ctrl_raw = rig.control.Control(
                name=name, shape_type="sphere", priority=0, offset_ctrl=False
            )
            ctrl = str(ctrl_raw)
            ctrl_zero = cmds.listRelatives(ctrl, parent=True)[0]
            cmds.parent(ctrl_zero, ctrl_grp)

            attrs = ["." + x + y for x in "trs" for y in "xyz"]
            for attr in attrs:
                cmds.connectAttr(ctrl + attr, jnt + attr)

            pos = distance * i
            hook = create_hook_on_curve(
                curve,
                pos,
                ctrl_zero,
                attrs=["translate"],
                curve_attrs=["position"],
                inherits_transform=True,
            )
            matrix_match_transforms(jnt_zero, ctrl_zero)

            # add jnt to skin
            if cmds.objExists(TARGET_MESH):
                history = cmds.listHistory(TARGET_MESH, pruneDagObjects=True)
                skin_cluster = cmds.ls(history, type="skinCluster")[0]
                cmds.skinCluster(
                    skin_cluster, edit=True, addInfluence=jnt, weight=0
                )

            # cancel double translates
            md = cmds.createNode(
                "multiplyDivide", name=name + "_md", skipSelect=True
            )
            cmds.connectAttr(ctrl + ".translate", md + ".input1")
            cmds.connectAttr(md + ".output", ctrl_zero + ".translate")
            for axis in "XYZ":
                cmds.setAttr(md + ".input2" + axis, -1, lock=True)

            # connect to global transforms
            for attr in "rs":
                plug = "." + attr
                cmds.connectAttr(MOVE_LOC + plug, hook + plug)
        constraint_util.mtx_parent_constraint(
            MOVE_LOC, curve, maintain_offset=True
        )


def get_selection_flatten():
    return cmds.ls(selection=True, flatten=True)


def matrix_match_transforms(target, source):
    matrix = cmds.xform(source, query=True, matrix=True, worldSpace=True)
    apply_matrix(target, matrix)


def apply_matrix(target, matrix):
    cmds.xform(target, matrix=matrix, worldSpace=True)


def reset_transforms(
    obj, reset_attrs=("translate", "rotate", "scale"), axis="XYZ"
):
    attrs = [x + y for x in reset_attrs for y in axis]
    for attr in attrs:
        value = 1 if attr.startswith("scale") else 0
        try:
            cmds.setAttr("{}.{}".format(obj, attr), value)
        except RuntimeError:
            continue


def create_hook_on_curve(
    curve,
    position=0.0,
    child=None,
    reset=True,
    attrs=("translate", "rotate"),
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

    hook = cmds.createNode(
        "transform", name="{}_hook_grp".format(name), skipSelect=True
    )
    posi = cmds.createNode(
        "pointOnCurveInfo", name="{}_posi".format(name), skipSelect=True
    )
    fbfmx = cmds.createNode(
        "fourByFourMatrix", name="{}_fbmx".format(name), skipSelect=True
    )
    mmx = cmds.createNode(
        "multMatrix", name="{}_mx".format(name), skipSelect=True
    )
    dmx = cmds.createNode(
        "decomposeMatrix", name="{}_dmx".format(name), skipSelect=True
    )

    if not inherits_transform:
        cmds.setAttr("{}.inheritsTransform".format(hook), 0, lock=True)
    cmds.setAttr("{}.parameter".format(posi), position, lock=True)

    # connect hook
    cmds.connectAttr(curve + ".worldSpace[0]", posi + ".inputCurve")

    match_indices = {
        "position": 3,
        "normalizedNormal": 0,
        "normalizedTangent": 1,
    }
    for surf_attr in curve_attrs:
        indice = match_indices[surf_attr]
        for i, axis in enumerate("XYZ"):
            cmds.connectAttr(
                "{}.{}{}".format(posi, surf_attr, axis),
                "{}.in{}{}".format(fbfmx, indice, i),
            )

    cmds.connectAttr(fbfmx + ".output", mmx + ".matrixIn[0]")
    cmds.connectAttr(hook + ".parentInverseMatrix[0]", mmx + ".matrixIn[1]")
    cmds.connectAttr(mmx + ".matrixSum", dmx + ".inputMatrix")

    if child:
        matrix_match_transforms(hook, child)

    for attr in attrs:
        cmds.connectAttr(
            "{}.output{}".format(dmx, attr[0].upper() + attr[1:]),
            "{}.{}".format(hook, attr),
        )

    if child:
        try:
            childParent = cmds.listRelatives(child, parent=True, path=True)
        except RuntimeError:
            childParent = None

        cmds.parent(child, hook, relative=relative)
        if childParent:
            cmds.parent(hook, childParent)

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


def maya_main_window():
    """Return the Maya main window widget as a Python object."""
    try:
        import maya.OpenMayaUI as omui
        import shiboken2

        main_window_ptr = omui.MQtUtil.mainWindow()
        return shiboken2.wrapInstance(int(main_window_ptr), QtWidgets.QWidget)
    except ImportError:
        try:
            import shiboken

            main_window_ptr = omui.MQtUtil.mainWindow()
            return shiboken.wrapInstance(
                int(main_window_ptr), QtWidgets.QWidget
            )
        except ImportError:
            # Fallback - find Maya window by object name
            for widget in QtWidgets.QApplication.topLevelWidgets():
                if widget.objectName() == "MayaWindow":
                    return widget
    return None


class ModernSpinBox(QtWidgets.QSpinBox):
    """Custom styled spinbox with modern appearance"""

    def __init__(self, parent=None):
        super(ModernSpinBox, self).__init__(parent)
        self.setStyleSheet("""
            QSpinBox {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                          stop: 0 #3a3a3a, stop: 1 #2a2a2a);
                border: 2px solid #555;
                border-radius: 8px;
                padding: 8px 12px;
                color: #ffffff;
                font-size: 12px;
                font-weight: bold;
            }
            QSpinBox:hover {
                border: 2px solid #0078d4;
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                          stop: 0 #4a4a4a, stop: 1 #3a3a3a);
            }
            QSpinBox:focus {
                border: 2px solid #00bcf2;
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                          stop: 0 #4a4a4a, stop: 1 #3a3a3a);
            }
            QSpinBox::up-button, QSpinBox::down-button {
                width: 20px;
                background: transparent;
                border: none;
            }
            QSpinBox::up-arrow {
                image: url(none);
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-bottom: 8px solid #0078d4;
                width: 0px;
                height: 0px;
            }
            QSpinBox::down-arrow {
                image: url(none);
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 8px solid #0078d4;
                width: 0px;
                height: 0px;
            }
            QSpinBox::up-arrow:hover, QSpinBox::down-arrow:hover {
                border-color: #00bcf2;
            }
        """)


class ModernLineEdit(QtWidgets.QLineEdit):
    """Custom styled line edit with modern appearance"""

    def __init__(self, parent=None):
        super(ModernLineEdit, self).__init__(parent)
        self.setStyleSheet("""
            QLineEdit {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                          stop: 0 #3a3a3a, stop: 1 #2a2a2a);
                border: 2px solid #555;
                border-radius: 8px;
                padding: 8px 12px;
                color: #ffffff;
                font-size: 12px;
                font-weight: bold;
            }
            QLineEdit:hover {
                border: 2px solid #0078d4;
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                          stop: 0 #4a4a4a, stop: 1 #3a3a3a);
            }
            QLineEdit:focus {
                border: 2px solid #00bcf2;
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                          stop: 0 #4a4a4a, stop: 1 #3a3a3a);
            }
        """)


class ModernCheckBox(QtWidgets.QCheckBox):
    """Custom styled checkbox with modern appearance"""

    def __init__(self, text, parent=None):
        super(ModernCheckBox, self).__init__(text, parent)
        self.setStyleSheet("""
            QCheckBox {
                color: #ffffff;
                font-size: 12px;
                font-weight: bold;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 9px;
                border: 2px solid #555;
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                          stop: 0 #3a3a3a, stop: 1 #2a2a2a);
            }
            QCheckBox::indicator:hover {
                border: 2px solid #0078d4;
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                          stop: 0 #4a4a4a, stop: 1 #3a3a3a);
            }
            QCheckBox::indicator:checked {
                border: 2px solid #00bcf2;
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1,
                                          stop: 0 #00bcf2, stop: 1 #0078d4);
            }
            QCheckBox::indicator:checked:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1,
                                          stop: 0 #20dcf2, stop: 1 #2098d4);
            }
        """)


class ModernButton(QtWidgets.QPushButton):
    """Custom styled button with modern appearance and hover effects"""

    def __init__(self, text, parent=None, primary=False):
        super(ModernButton, self).__init__(text, parent)
        self.primary = primary
        self._setup_style()

    def _setup_style(self):
        if self.primary:
            style = """
                QPushButton {
                    background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1,
                                              stop: 0 #00bcf2, stop: 1 #0078d4);
                    border: none;
                    border-radius: 12px;
                    padding: 12px 24px;
                    color: white;
                    font-size: 14px;
                    font-weight: bold;
                    min-height: 20px;
                }
                QPushButton:hover {
                    background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1,
                                              stop: 0 #20dcf2, stop: 1 #2098d4);
                }
                QPushButton:pressed {
                    background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1,
                                              stop: 0 #0098d2, stop: 1 #0058b4);
                }
                QPushButton:disabled {
                    background: #555555;
                    color: #888888;
                }
            """
        else:
            style = """
                QPushButton {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                              stop: 0 #4a4a4a, stop: 1 #3a3a3a);
                    border: 2px solid #555;
                    border-radius: 8px;
                    padding: 8px 16px;
                    color: #ffffff;
                    font-size: 12px;
                    font-weight: bold;
                    min-height: 16px;
                }
                QPushButton:hover {
                    border: 2px solid #0078d4;
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                              stop: 0 #5a5a5a, stop: 1 #4a4a4a);
                }
                QPushButton:pressed {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                                              stop: 0 #2a2a2a, stop: 1 #1a1a1a);
                }
            """
        self.setStyleSheet(style)


class TweakerUI(QtWidgets.QWidget):
    """Modern UI for Maya Tweaker Script"""

    def __init__(self, parent=None):
        super(TweakerUI, self).__init__(parent or maya_main_window())

        # Set window properties
        self.setWindowTitle("Tweaker Builder")
        self.setFixedSize(400, 900)
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)

        # Set the main background and styling
        self.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1,
                                          stop: 0 #1e1e1e, stop: 1 #2d2d2d);
                color: #ffffff;
                font-family: Arial, sans-serif;
            }
            QLabel {
                color: #ffffff;
                font-size: 12px;
                font-weight: bold;
            }
            QToolTip {
                background-color: #3a3a3a;
                color: #ffffff;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px;
                font-size: 11px;
            }
        """)

        self._build_ui()
        self._connect_signals()

        # Auto-validate selection on startup
        QtCore.QTimer.singleShot(100, self.validate_selection)

    def _build_ui(self):
        """Build the user interface"""
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Header
        self._create_header(main_layout)

        # Selection validation
        self._create_selection_section(main_layout)

        # Parameters section
        self._create_parameters_section(main_layout)

        # Global variables section
        self._create_globals_section(main_layout)

        # Action buttons
        self._create_buttons(main_layout)

        # Add stretch to push everything to top
        main_layout.addStretch()

    def _create_header(self, layout):
        """Create the header section"""
        header_layout = QtWidgets.QVBoxLayout()

        title = QtWidgets.QLabel("Tweaker Builder")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setStyleSheet("""
            QLabel {
                font-size: 24px;
                font-weight: bold;
                color: #00bcf2;
                padding: 10px 0;
            }
        """)

        subtitle = QtWidgets.QLabel(
            "Create geometry-following tweaker controls"
        )
        subtitle.setAlignment(QtCore.Qt.AlignCenter)
        subtitle.setStyleSheet("""
            QLabel {
                font-size: 12px;
                color: #aaaaaa;
                padding-bottom: 10px;
            }
        """)

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        layout.addLayout(header_layout)

    def _create_selection_section(self, layout):
        """Create selection validation section"""
        selection_frame = QtWidgets.QFrame()
        selection_frame.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid #555;
                border-radius: 8px;
                padding: 8px;
            }
        """)

        selection_layout = QtWidgets.QVBoxLayout(selection_frame)

        # Selection status
        self.selection_label = QtWidgets.QLabel("Selection: No edges selected")
        self.selection_label.setStyleSheet("""
            QLabel {
                color: #ff6b6b;
                font-size: 11px;
                padding: 4px;
            }
        """)

        # Validate button
        self.validate_btn = ModernButton("Validate Selection")
        self.validate_btn.setToolTip(
            "Check if current selection contains valid edges for tweaker setup"
        )

        selection_layout.addWidget(self.selection_label)
        selection_layout.addWidget(self.validate_btn)

        layout.addWidget(selection_frame)

    def _create_parameters_section(self, layout):
        """Create parameters input section"""
        params_frame = QtWidgets.QFrame()
        params_frame.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid #555;
                border-radius: 8px;
                padding: 12px;
            }
        """)

        params_layout = QtWidgets.QFormLayout(params_frame)
        params_layout.setSpacing(12)

        # Label input
        self.label_input = ModernLineEdit()
        self.label_input.setPlaceholderText("e.g., eyelid_upper")
        self.label_input.setText("eyelid_upper")
        self.label_input.setToolTip(
            "Name label for the tweaker setup (e.g., 'eyelid_upper', 'lip_lower')"
        )

        # Joint number spinbox
        self.joint_spinbox = ModernSpinBox()
        self.joint_spinbox.setRange(2, 20)
        self.joint_spinbox.setValue(3)
        self.joint_spinbox.setToolTip(
            "Number of joints/controls to create along the edge loop"
        )

        # Symmetry checkbox
        self.symmetry_checkbox = ModernCheckBox("Create Symmetrical Setup")
        self.symmetry_checkbox.setChecked(True)
        self.symmetry_checkbox.setToolTip(
            "Automatically create left and right side tweakers based on selection"
        )

        params_layout.addRow("Label:", self.label_input)
        params_layout.addRow("Joint Count:", self.joint_spinbox)
        params_layout.addRow("", self.symmetry_checkbox)

        layout.addWidget(params_frame)

    def _create_globals_section(self, layout):
        """Create global variables section"""
        globals_frame = QtWidgets.QFrame()
        globals_frame.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid #555;
                border-radius: 8px;
                padding: 12px;
            }
        """)

        globals_layout = QtWidgets.QVBoxLayout(globals_frame)

        # Header
        globals_header = QtWidgets.QLabel("Global Variables")
        globals_header.setStyleSheet("""
            QLabel {
                color: #00bcf2;
                font-size: 14px;
                font-weight: bold;
                padding-bottom: 8px;
            }
        """)
        globals_layout.addWidget(globals_header)

        # Create form layout for global variables
        globals_form = QtWidgets.QFormLayout()
        globals_form.setSpacing(8)

        # SIDES
        self.sides_input = ModernLineEdit()
        self.sides_input.setText("LR")
        self.sides_input.setToolTip(
            "Characters representing left and right sides"
        )

        # MOVE_LOC
        self.move_loc_input = ModernLineEdit()
        self.move_loc_input.setText("M_move_locator")
        self.move_loc_input.setToolTip("Name of the move locator")

        # RIG_GRP
        self.rig_grp_input = ModernLineEdit()
        self.rig_grp_input.setText("rig_grp")
        self.rig_grp_input.setToolTip("Name of the main rig group")

        # SECONDARY_GRP
        self.secondary_grp_input = ModernLineEdit()
        self.secondary_grp_input.setText("secondary_grp")
        self.secondary_grp_input.setToolTip("Name of the secondary group")

        # PARENT_JOINT
        self.parent_joint_input = ModernLineEdit()
        self.parent_joint_input.setText("M_base_02_jnt")
        self.parent_joint_input.setToolTip("Name of the parent joint")

        # TARGET_MESH
        self.target_mesh_input = ModernLineEdit()
        self.target_mesh_input.setText("M_head_rig02_mesh")
        self.target_mesh_input.setToolTip(
            "Name of the target mesh for skinning"
        )

        # Add to form layout
        globals_form.addRow("Sides:", self.sides_input)
        globals_form.addRow("Move Locator:", self.move_loc_input)
        globals_form.addRow("Rig Group:", self.rig_grp_input)
        globals_form.addRow("Secondary Group:", self.secondary_grp_input)
        globals_form.addRow("Parent Joint:", self.parent_joint_input)
        globals_form.addRow("Target Mesh:", self.target_mesh_input)

        globals_layout.addLayout(globals_form)
        layout.addWidget(globals_frame)

    def _create_buttons(self, layout):
        """Create action buttons"""
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.setSpacing(10)

        # Build button (primary action)
        self.build_btn = ModernButton("Build Tweakers", primary=True)
        self.build_btn.setEnabled(False)
        self.build_btn.setToolTip(
            "Create the tweaker setup with current parameters"
        )

        # Close button
        self.close_btn = ModernButton("Close")
        self.close_btn.setToolTip("Close the tweaker builder")

        button_layout.addWidget(self.close_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.build_btn)

        layout.addLayout(button_layout)

    def _connect_signals(self):
        """Connect widget signals to slots"""
        self.validate_btn.clicked.connect(self.validate_selection)
        self.build_btn.clicked.connect(self.run_tweakers)
        self.close_btn.clicked.connect(self.close)

        # Auto-validate when parameters change
        self.label_input.textChanged.connect(self._update_build_button)
        self.joint_spinbox.valueChanged.connect(self._update_build_button)

    def keyPressEvent(self, event):
        """Override keyPressEvent to prevent Maya from taking focus."""
        # This prevents Maya from intercepting key events
        if event.key() == QtCore.Qt.Key_Escape:
            self.close()
        else:
            super(TweakerUI, self).keyPressEvent(event)

    def validate_selection(self):
        """Validate current Maya selection"""
        try:
            # Get current selection
            selection = cmds.ls(selection=True, flatten=True)

            if not selection:
                self._update_selection_status("No selection found", False)
                self.validated_selection = []
                return False

            # Check if selection contains edges
            edges = cmds.filterExpand(
                selection, selectionMask=32
            )  # 32 = edges

            if not edges:
                self._update_selection_status(
                    "Selection contains no edges", False
                )
                self.validated_selection = []
                return False

            # Store validated selection for later use
            self.validated_selection = edges

            # Valid selection found
            edge_count = len(edges)
            self._update_selection_status(
                "Valid: {} edges selected".format(edge_count), True
            )
            return True

        except Exception as e:
            self._update_selection_status("Error: {}".format(str(e)), False)
            self.validated_selection = []
            return False

    def _update_selection_status(self, message, is_valid):
        """Update selection status display"""
        self.selection_label.setText("Selection: {}".format(message))

        if is_valid:
            self.selection_label.setStyleSheet("""
                QLabel {
                    color: #4ecdc4;
                    font-size: 11px;
                    padding: 4px;
                }
            """)
        else:
            self.selection_label.setStyleSheet("""
                QLabel {
                    color: #ff6b6b;
                    font-size: 11px;
                    padding: 4px;
                }
            """)

        self._update_build_button()

    def _update_build_button(self):
        """Update build button enabled state"""
        has_valid_selection = "Valid:" in self.selection_label.text()
        has_valid_label = bool(self.label_input.text().strip())

        self.build_btn.setEnabled(has_valid_selection and has_valid_label)

    def run_tweakers(self):
        """Execute the tweaker building process"""
        try:
            # Restore the validated selection before building
            if self.validated_selection:
                cmds.select(self.validated_selection)

            # Get parameters
            label = self.label_input.text().strip()
            joint_count = self.joint_spinbox.value()
            do_symmetry = self.symmetry_checkbox.isChecked()

            global \
                SIDES, \
                MOVE_LOC, \
                RIG_GRP, \
                SECONDARY_GRP, \
                PARENT_JOINT, \
                TARGET_MESH

            SIDES = self.sides_input.text().strip()
            MOVE_LOC = self.move_loc_input.text().strip()
            RIG_GRP = self.rig_grp_input.text().strip()
            SECONDARY_GRP = self.secondary_grp_input.text().strip()
            PARENT_JOINT = self.parent_joint_input.text().strip()
            TARGET_MESH = self.target_mesh_input.text().strip()

            # Call the build function
            build_tweakers(
                label=label, jnt_number=joint_count, do_sym=do_symmetry
            )

            # For testing - show success message
            msg = "Tweakers built successfully!\nLabel: {}\nJoints: {}\nSymmetry: {}".format(
                label, joint_count, do_symmetry
            )
            self._show_success_message(msg)

        except Exception as e:
            self._show_error_message(
                "Error building tweakers: {}".format(str(e))
            )

    def _show_success_message(self, message):
        """Show success message"""
        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setWindowTitle("Success")
        msg_box.setText(message)
        msg_box.setIcon(QtWidgets.QMessageBox.Information)
        msg_box.setStyleSheet("""
            QMessageBox {
                background: #2d2d2d;
                color: #ffffff;
            }
            QMessageBox QPushButton {
                background: #0078d4;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                min-width: 60px;
            }
        """)
        msg_box.exec_()

    def _show_error_message(self, message):
        """Show error message"""
        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setWindowTitle("Error")
        msg_box.setText(message)
        msg_box.setIcon(QtWidgets.QMessageBox.Critical)
        msg_box.setStyleSheet("""
            QMessageBox {
                background: #2d2d2d;
                color: #ffffff;
            }
            QMessageBox QPushButton {
                background: #ff6b6b;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                min-width: 60px;
            }
        """)
        msg_box.exec_()


def show_tweaker_ui():
    """Show the tweaker UI window"""
    global tweaker_ui_instance

    # Close any existing instances
    try:
        if tweaker_ui_instance and tweaker_ui_instance.isVisible():
            tweaker_ui_instance.close()
    except:
        pass

    # Create and show new instance
    tweaker_ui_instance = TweakerUI()
    tweaker_ui_instance.show()
    tweaker_ui_instance.raise_()
    tweaker_ui_instance.activateWindow()

    return tweaker_ui_instance


# Global variable to keep reference
tweaker_ui_instance = None
