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

# TODO Allow items to flow as a grid and fill up row, continue on column

# Get the Maya window so we can parent our widget to it.
mayaMainWindowPtr = omui.MQtUtil.mainWindow()
mayaMainWindow = wrapInstance(long(mayaMainWindowPtr), QWidget)

# Path to folder where we will keep Curves.
save_folder = os.path.join(pm.internalVar(userAppDir=True), 'ccLibrary')

# If the Folder doesn't exist, make dir
if not os.path.exists(save_folder):
    os.mkdir(save_folder)

def save_curve(name, curve=None):
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
    periodic = True if curve.form().key is "periodic" else False    # Can also be either Open or Closed, not sure how this effects what I am trying to do.
    cvs = [(p.x, p.y, p.z) for p in curve.getCVs()]
    knots = curve.getKnots()

    data = ([name, {"degree": degrees, "periodic": periodic, "point": cvs, "knot": knots}])

    file_name = os.path.join(save_folder, '{}.json'.format(name))
    with open(file_name, 'w') as fp:
        json.dump(data, fp, indent=2, sort_keys=True, ensure_ascii=False)

    # Save the icon
    save_icon(curve.listRelatives(parent=True)[0], name)

def save_icon(object, filename):
    """ Take picture of object, render using playblast for later use as a QT Button icon. """
    path = os.path.join(save_folder, "{}.png".format(filename))

    # Store all hidden items
    items = pm.hide(allObjects=True, returnHidden=True)

    # Show only object we want to focus on and fit view
    pm.showHidden(object)
    pm.viewFit()

    # PNG is 32 in the imageFormat enum.
    pm.setAttr("defaultRenderGlobals.imageFormat", 32)
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
        self.listWidget.setIconSize(QSize(64,64))
        self.listWidget.setGridSize(QSize(64, 64))

        self.layout().addWidget(self.listWidget)

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
            item = CurveItem(self.listWidget, name=data[0], params=data[1])

            iconPath = os.path.join(save_folder, "{}.png".format(data[0]))
            icon = QIcon(iconPath)
            item.setIcon(icon)

            item.setToolTip(parse(data[1]))

            item.setSizeHint(QSize(64, 64))

            self.listWidget.addItem(item)

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
        # TODO Look into why item.params doesn't cut it - is it that they are unicode strings and not strings?
        params = {}
        params['degree'] = item.params['degree']
        params['periodic'] = item.params['periodic']
        params['point'] = item.params['point']
        params['knot'] = item.params['knot']
        pm.curve(**params)

class CurveItem(QListWidgetItem):
    def __init__(self, parent, name, params):
        super(CurveItem, self).__init__(parent=parent)
        self.params = params
        self.name = name

def getUI():
    window = Window()
    window.show()
    return window