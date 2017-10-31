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

# TODO add options for loading curve, position to create them at, buffer groups. Custom attributes to throw them on creation?
# TODO Change Icon Highlight color to a more contrasting one on click
# TODO add checkbox to save curves objectspace or worldspace
# TODO on curve loads, if nothing selected position at origo, else position at selected.

# Get the Maya window so we can parent our widget to it.
mayaMainWindowPtr = omui.MQtUtil.mainWindow()
mayaMainWindow = wrapInstance(long(mayaMainWindowPtr), QWidget)

# Path to folder where we will keep Curves.
save_folder = os.path.join(pm.internalVar(userAppDir=True), 'ccLibrary')

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

def save_curve(name, curve=None, objectSpace=True):
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

    if objectSpace:
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
    if  not os.path.exists(file_path):
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

        self.listWidget = CurveList()
        self.listWidget.setViewMode(QListView.IconMode)

        # Get some graphical issue if IconSize is same as GridSize
        self.listWidget.setIconSize(QSize(96, 96))
        self.listWidget.setGridSize(QSize(100, 100))

        self.layout().addWidget(self.listWidget)

        # Set resize mode for our list view to adjust layout
        self.listWidget.setResizeMode(QListView.ResizeMode.Adjust)

        self.load_library()

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

        layout.addWidget(QLabel("Name:"), 1, 1)
        layout.addWidget(self.name_lineEdit, 1, 2)

        layout.addWidget(QLabel("Curve:"), 2, 1)
        layout.addWidget(self.curve_lineEdit, 2, 2)

        layout.addWidget(self.save_button, 3, 1, 1, 2, Qt.AlignCenter)

        self.layout().addWidget(save_groupbox)

    def save(self):
        save_curve(
            self.name_lineEdit.text(),
            self.curve_lineEdit.text()
        )

        # Reload the library on saves.
        self.load_library()

    def load_library(self):

        # Clear the widget
        self.listWidget.clear()

        # Get all files in our folder, then sort out all our jsons to library list, and png icons to theirs.
        files = os.listdir(save_folder)
        library = [f for f in files if f.endswith("json")]

        for f in library:
            data = load_curve(f)
            iconPath = os.path.join(save_folder, "{}.png".format(data[0]))
            self.listWidget.addItem(CurveItem(data[0], data[1], QIcon(iconPath), None))

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

    def createCurve(self, item):
        """ Make a pymel call to curve with the stored params. """
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