import base64

import FreeCADGui
import io
import os
from PySide import QtWidgets
from PySide.QtUiTools import QUiLoader
from PySide.QtCore import QFile, QByteArray
from PySide.QtGui import QImage, QPixmap

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

        self.resize(720, 640)

        buf = io.StringIO(html)
        prop = 0
        for line in buf.readlines():
            if line == "":
                break
            elif "property-value" in line:
                if prop == 0:
                    self.labelVersionValue.setText(self.cleanProp(line))
                elif prop == 1:
                    self.labelDateCreatedValue.setText(self.cleanProp(line))
                elif prop == 2:
                    self.labelUserUpdatedValue.setText(self.cleanProp(line))
                elif prop == 3:
                    self.labelPartNameValue.setText(self.cleanProp(line))
                elif prop == 4:
                    self.labelFileDateValue.setText(self.cleanProp(line))
                elif prop == 5:
                    self.labelFileCreatedValue.setText(self.cleanProp(line))
                elif prop == 6:
                    self.labelStatusValue.setText(self.cleanProp(line))
                elif prop == 7:
                    self.labelLockedBy.setText(self.cleanProp(line))
                elif prop == 8:
                    self.labelTagsValue.setText(self.cleanProp(line))
                elif prop == 9:
                    self.labelCommentValue.setText(self.cleanProp(line))
                prop += 1
            elif "data:image/png;base64, " in line:
                i = line.index("data:image/png;base64, ") + len("data:image/png;base64, ")
                base64str = QByteArray.fromStdString(line[i:-1-len("\"></div></div></div></div></div>")])
                # base64buf = base64.b64decode(base64str)
                image = QImage()
                image.loadFromData(QByteArray.fromBase64(base64str))
                # image = QImage.loadFromData(base64buf)
                self.imageLabel.setPixmap(QPixmap.fromImage(image))


        self.show()


    def cleanProp(self, propHtml):
        propHtml = propHtml.strip()
        i = propHtml.index(">")
        return propHtml[i:-7]

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