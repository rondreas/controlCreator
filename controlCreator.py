import pymel.core as pm
import json
import os

from maya import OpenMayaUI as omui

try:
    from PySide2.QtCore import *
    from PySide2.QtGui import *
    from PySide2.QtWidgets import *
    from PySide2 import __version__
    from shiboken2 import wrapInstance
except ImportError:
    from PySide.QtCore import *
    from PySide.QtGui import *
    from PySide import __version__
    from shiboken import wrapInstance

# TODO add options for loading curve, position to create them at, buffer groups.
# TODO Change Icon Highlight color to a more contrasting one on click
# TODO on curve loads, if nothing selected position at origo, else position at selected.
# TODO Orthographic camera three-quarter view to better render icons.

# Get the Maya window so we can parent our widget to it.
mayaMainWindowPtr = omui.MQtUtil.mainWindow()
mayaMainWindow = wrapInstance(long(mayaMainWindowPtr), QWidget)

# Path to folder where we will keep Curves, replacing slashes to work in windows
save_folder = os.path.join(pm.internalVar(userAppDir=True), 'ccLibrary').replace("/", "\\")

# Maya recognized image file formats for setting the render settings image type.
IMAGE_FILE_FORMAT = {
  "AVI": 23,
  "Alias PIX": 6,
  "Cineon": 11,
  "DDS": 35,
  "EPS": 9,
  "EXR(exr)": 40,
  "GIF": 0,
  "JPEG": 8,
  "MacPaint": 30,
  "Maya IFF": 7,
  "Maya16 IFF": 10,
  "PNG": 32,
  "PSD": 31,
  "PSD Layered": 36,
  "Quantel": 12,
  "QuickDraw": 33,
  "QuickTime Image": 34,
  "Quicktime": 22,
  "RLA": 2,
  "SGI": 5,
  "SGI Movie": 21,
  "SGI16": 13,
  "SoftImage": 1,
  "Targa": 19,
  "Tiff": 3,
  "Tiff16": 4,
  "Windows Bitmap": 20
}

# If the Folder doesn't exist, make dir
if not os.path.exists(save_folder):
    os.mkdir(save_folder)

def save_curve(name, curve=None, centerPivot=True):
    """ Store information to rebuild the shape of a curve. """

    # If no curve specified try get curve from selection
    if not curve:
        try:
            curve = pm.selected()[0]
        except Exception as e:
            print e.message

    # Most likely the selection or supplied object will be the transform node and not the actual shape node that
    # we are looking for. So redefine curve variable to actually point toward the shape and not the transform.
    if type(curve) is pm.nodetypes.Transform:
        curve = curve.getShape()

    # If the shape was not a Nurbs Curve raise an error.
    if type(curve) is not pm.nodetypes.NurbsCurve:
        raise TypeError("{} is not of type {}".format(curve.name(), pm.nodetypes.NurbsCurve))

    # Get all pertinent data to recreate our curve.
    degrees = curve.degree()
    # Can also be either Open or Closed, not sure how this effects what I am trying to do.
    periodic = True if curve.form().key is "periodic" else False
    cvs = [(p.x, p.y, p.z) for p in curve.getCVs()]
    knots = curve.getKnots()

    if centerPivot:
        # Get average position of all points, this would be same as "center pivot"
        center = [sum(p) / float(len(cvs)) for p in zip(*cvs)]

        # Add inverse of new vector to all point positions
        inverseCenter = pm.datatypes.Vector([i for i in map(lambda x: x * -1, center)])
        cvs = [(point.x, point.y, point.z) for point in map(lambda x: inverseCenter + x, cvs)]

    data = ([name, {"degree": degrees, "periodic": periodic, "point": cvs, "knot": knots}])

    file_name = os.path.join(save_folder, '{}.json'.format(name))
    with open(file_name, 'w') as fp:
        json.dump(data, fp, indent=2, sort_keys=True, ensure_ascii=False)

    # Save the icon
    save_icon(
        curve.listRelatives(parent=True)[0],
        name,
        IMAGE_FILE_FORMAT['PNG']
    )

def save_icon(object, filename, imageFormat):
    """ Take picture of object, render using playblast for later use as a QT Button icon. """
    path = os.path.join(save_folder, "{}.png".format(filename))

    # Store all hidden items
    items = pm.hide(allObjects=True, returnHidden=True)

    # Show only object we want to focus on and fit view
    pm.showHidden(object)
    pm.viewFit()

    # PNG is 32 in the imageFormat enum.
    pm.setAttr("defaultRenderGlobals.imageFormat", imageFormat)
    pm.playblast(completeFilename=path, forceOverwrite=True, format='image', width=200, height=200,
                 showOrnaments=False, startTime=1, endTime=1, viewer=False)

    # Show all the items we hid a while back.
    pm.showHidden(items)

    # Return camera to previous view.
    pm.viewSet(previousView=True)

def load_curve(file_name):
    """ Load a saved curve from disk. """
    file_path = os.path.join(save_folder, file_name)
    if not os.path.exists(file_path):
        raise IOError("File {} does not exist in {}".format(file_name, save_folder))

    with open(file_path, 'r') as fp:
        data = json.load(fp)

    return data

def parse(data):
    """ Parse the json data and write the command that we're going to run, used to have this for actual functionality
     but calling eval(command) isn't the most clever thing to do. """
    try:
        degrees = "d={}".format(data["degree"])
        periodic = "periodic={}".format(data["periodic"])
        points = 'p={}'.format([tuple(p) for p in data["point"]])
        knots = 'k={}'.format([int(k) for k in data["knot"]])

        # String of the pymel command to recreate saved curve.
        return "pm.curve({})".format(', '.join([degrees, periodic, points, knots]))

    except Exception as e:
        print e.message

class Window(QWidget):
    def __init__(self, parent=mayaMainWindow):
        super(Window, self).__init__(parent=parent)

        if os.name is 'posix':
            self.setWindowFlags(Qt.Tool)
        else:
            self.setWindowFlags(Qt.Window)

        self.setWindowTitle("Control Creator")

        self.mainLayout()
        self.saveGroupbox()
        self.loadGroupbox()

        self.listWidget = CurveList()

        self.layout().addWidget(self.listWidget)

        # Load items in save folder
        self.listWidget.load_library()

    def mainLayout(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

    def saveGroupbox(self):
        save_groupbox = QGroupBox("Save Options")
        layout = QGridLayout()
        save_groupbox.setLayout(layout)

        self.curve_lineEdit = QLineEdit()
        self.curve_lineEdit.setToolTip("Specify Curve to save, if empty will use first item in selection.")

        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save)

        self.name_lineEdit = RequiredLineEdit("controller1", self.save_button)
        self.name_lineEdit.setToolTip("Name must be specified to save a curve.")

        self.name_lineEdit.sizePolicy().setHorizontalStretch(1)
        self.curve_lineEdit.sizePolicy().setHorizontalStretch(1)

        self.save_center_pivot = QCheckBox("From Center Pivot")
        self.save_center_pivot.setToolTip("If unchecked, will save curve points in world position.")
        layout.addWidget(self.save_center_pivot, 1, 1)

        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Name:"))
        name_layout.addWidget(self.name_lineEdit)

        curve_layout = QHBoxLayout()
        curve_layout.addWidget(QLabel("Curve:"))
        curve_layout.addWidget(self.curve_lineEdit)

        layout.addLayout(name_layout, 2, 1, 1, 2)
        layout.addLayout(curve_layout, 3, 1, 1, 2)

        layout.addWidget(self.save_button, 4, 1, 1, 2, Qt.AlignCenter)

        self.layout().addWidget(save_groupbox)

    def loadGroupbox(self):
        """ Create the group box containing the options for loading the curves. """
        load_groupbox = QGroupBox("Load Options")
        layout = QGridLayout()
        load_groupbox.setLayout(layout)
        self.offset_transform = QCheckBox("Add &Offset Transform")
        layout.addWidget(self.offset_transform, 1, 1)
        self.layout().addWidget(load_groupbox)

    def save(self):
        save_curve(
            name=self.name_lineEdit.text(),
            curve=self.curve_lineEdit.text(),
            centerPivot=self.save_center_pivot.isChecked()
        )

        # Reload the library on saves.
        self.listWidget.load_library()

class RequiredLineEdit(QLineEdit):
    def __init__(self, text, button):
        super(RequiredLineEdit, self).__init__(text=text)

        self.button = button

        self.textChanged.connect(self.checkNotEmpty)

    def checkNotEmpty(self):
        if not self.text():
            self.button.setEnabled(False)
        else:
            self.button.setEnabled(True)

class CurveList(QListWidget):
    def __init__(self):
        super(CurveList, self).__init__()
        self.itemClicked.connect(self.createCurve)

        # Set and create connections for custom context menu
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.showContextMenu)

        self.setViewMode(QListView.IconMode)
        self.setMovement(QListView.Static)

        # Get some graphical issue if IconSize is same as GridSize
        self.setIconSize(QSize(96, 96))
        self.setGridSize(QSize(100, 100))

        # Set resize mode for our list view to adjust layout
        self.setResizeMode(QListView.ResizeMode.Adjust)

        """ Think in order to solve the QIcon highlighting issue I will have to look into QItemDelegates and 
        make a custom one. """

    def showContextMenu(self, pos):
        """ Set a custom context menu """

        # Get the position where user right-clicked to request the context menu
        position = self.mapToGlobal(pos)

        menu = QMenu()

        # Define our action and add it to the context menu
        action = QAction("Delete", self, triggered=self.deleteItem)
        menu.addAction(action)

        # Execute the context menu to show it and hopefully have it die when not in focus.
        menu.exec_(position)

    def load_library(self):
        """ Clear widget of items, and fill with all items in save folder. """

        # Clear the widget
        self.clear()

        # Get all files in our folder, then sort out all our jsons to library list, and png icons to theirs.
        files = os.listdir(save_folder)
        library = [f for f in files if f.endswith("json")]

        for f in library:
            data = load_curve(f)
            iconPath = os.path.join(save_folder, "{}.png".format(data[0]))
            self.addItem(CurveItem(data[0], data[1], QIcon(iconPath), None))

    def deleteItem(self):
        """ Remove files for selected items. """

        for item in self.selectedItems():
            data_file = os.path.join(save_folder, '{}.json'.format(item.name))
            icon_file = os.path.join(save_folder, '{}.png'.format(item.name))

            print("Removing {0}.json and {0}.png in folder {1}".format(item.name, save_folder))

            os.remove(data_file)
            os.remove(icon_file)

        # Refresh items.
        self.load_library()

    def createCurve(self, item):
        """ Make a pymel call to curve with the stored params. """
        selection = pm.selected()
        if selection:
            for selected in selection:
                curve = pm.curve(**item.params)

                # Match Transforms, can also be done using parenting with relative flag set.
                pm.xform(
                    curve,
                    ws=True,
                    translation=pm.xform(selected, q=True, ws=True, t=True),
                    rotation=pm.xform(selected, q=True, ws=True, ro=True),
                )

                # Match Names,
                pm.rename(curve, selected.nodeName() + '_CTRL')

                # If Offset group in parent is checked, add an offset group to zero out transforms for controller.
                if self.parentWidget().offset_transform.isChecked():
                    offset_grp = pm.group(empty=True, name='{}_Offset'.format(curve.nodeName()))
                    pm.parent(offset_grp, selected, relative=True)
                    pm.parent(offset_grp, world=True)
                    pm.parent(curve, offset_grp)
        else:
            pm.curve(**item.params)

class CurveItem(QListWidgetItem):
    def __init__(self, name, params, *args):
        super(CurveItem, self).__init__(*args)
        # JSON parses the data as unicode which apparently pymel had issues parsing to MEL
        self.params = {str(k): v for k, v in params.iteritems()}
        self.name = name

        self.setToolTip(self.name)

def getUI():
    window = Window()
    window.show()
    return window