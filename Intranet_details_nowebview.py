import FreeCADGui
import os
from PySide import QtWidgets
from PySide.QtUiTools import QUiLoader
from PySide.QtCore import QFile

class UiLoader(QUiLoader):
    def __init__(self, baseinstance):
        super().__init__()
        self.baseinstance = baseinstance

    def createWidget(self, classname, parent=None, name=""):
        if parent is None and self.baseinstance:
            return self.baseinstance
        return super().createWidget(classname, parent, name)



class TaackPlmDetailsNoWebview(QtWidgets.QDialog):
    def __init__(self, ro, html, base_url):
        self.hasApplied = False
        self.hasCheckIn = False
        # super().__init__(FreeCADGui.getMainWindow())
        super().__init__()
        loader = UiLoader(self)
        ui_file = QFile(os.path.join(str(os.path.dirname(__file__)), 'taack-plm-nowebviewdetails.ui'))
        ui_file.open(QFile.ReadOnly)
        loader.load(ui_file)
        ui_file.close()

        # FreeCADGui.PySideUic.loadUi(os.path.join(str(os.path.dirname(__file__)), 'taack-plm-nowebviewdetails.ui'), self)
        self.resize(720, 640)
        self.show()


    def checkIn(self):
        self.hasApplied = True
        self.hasCheckIn = True
        self.close()

    def downloadReadOnly(self):
        self.hasApplied = True
        self.hasCheckIn = False
        self.close()

    def closing(self):
        self.hasApplied = False
        self.hasCheckIn = False
        self.close()