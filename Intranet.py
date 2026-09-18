import FreeCAD, os, requests, uuid
import freecad_plm_pb2 as PlmBuf
from PySide import QtCore, QtGui

if FreeCAD.GuiUp:
    import FreeCADGui
    from DraftTools import translate
    from PySide.QtCore import QT_TRANSLATE_NOOP
else:
    # \cond
    def translate(ctxt,txt):
        return txt
    def QT_TRANSLATE_NOOP(ctxt,txt):
        return txt
    # \endcond

__title__="FreeCAD Taack PLM commands"
__author__ = "Adrien Guichard"
__url__ = "http://taack.org"


class CommandTaackPlm:
    def __init__(self):
        self.taackIntranetSession = requests.session()
        self.settings = QtCore.QSettings("Taack", "TaackPLM")
        self.connected = False
        self.user = self.settings.value("username", "Login")
        self.url = self.settings.value("url", "Server URL")
        self.passwd = ""

    def GetResources(self):
        return {'Pixmap'  : os.path.join(os.path.dirname(__file__),"icons",'logo_taack.svg'),
                'MenuText': QtCore.QT_TRANSLATE_NOOP("TaackPlm_Intranet","Plm"),
                'ToolTip': QtCore.QT_TRANSLATE_NOOP("TaackPlm_Intranet","Manages the current document with Taack PLM")}

    def IsActive(self):
        '''Here you can define if the command must be active or not (greyed) if certain conditions
        are met or not. This function is optional.'''
        if FreeCAD.activeDocument():
            return (True)
        else:
            return (False)

    def Activated(self):
        FreeCADGui.Control.showDialog(TaackPlmTaskPanel(self))



class TaackPlmTaskPanel(object):

    '''The TaskPanel for the Taack PLM command'''

    def __init__(self, po):
        self.po = po
        self.avoidLoop = []
        self.form = FreeCADGui.PySideUic.loadUi(os.path.join(os.path.dirname(__file__),'taack-plm.ui'))
        self.form.userEdit.insert(po.user)
        self.form.passEdit.insert(po.passwd)
        self.form.urlEdit.insert(po.url)
        QtCore.QObject.connect(self.form.connectButton, QtCore.SIGNAL("pressed()"), self.logIntranet)
        QtCore.QObject.connect(self.form.forkButton, QtCore.SIGNAL("pressed()"), self.fork)
        if (self.po.connected):
            self.form.connectButton.setStyleSheet('QPushButton {color: green;}')
            self.form.connectButton.setEnabled(False)
            self.form.forkButton.setEnabled(True)
            self.form.connectButton.setText('Connected')

    def savePreferences(self):
        self.po.user = self.form.userEdit.text()
        self.po.settings.setValue("username", self.po.user)
        self.po.url = self.form.urlEdit.text()
        self.po.settings.setValue("url", self.po.url)

    def accept(self):
        print('Accept')
        if (not self.po.connected):
            FreeCAD.Console.PrintWarning(translate("TaackPlm","Not connected.")+"\n")
            return
        try:
            self.uploadCurrentActiveDoc()
            FreeCADGui.Control.closeDialog()
        except ValueError as e:
            FreeCAD.Console.PrintWarning(translate("TaackPlm","Cannot Upload ... " + str(e))+"\n")
        except:
            FreeCAD.Console.PrintWarning(translate("TaackPlm","Cannot Upload ... Try to reconnect")+"\n")
            self.po.connected = False
            self.form.connectButton.setStyleSheet('QPushButton {color: red;}')
            self.form.connectButton.setEnabled(True)
            self.form.connectButton.setText('DisConnected')


    def fork(self):
        self.uuidVersion = uuid.uuid4()
        obj = FreeCAD.ActiveDocument
        obj.Id = obj.Id if obj.Id else obj.Uid + '/' + str(self.uuidVersion)
        self.form.forkButton.setEnabled(False)


    def logIntranet(self):
        print('login Intranet ...')
        data = {"username": self.form.userEdit.text(), "password": self.form.passEdit.text(), "ajax": 'true'}
        self.savePreferences()
        try:
            r = self.po.taackIntranetSession.post(url=self.form.urlEdit.text() + 'login/authenticate', data=data, timeout=5)
            if r.json()["success"] == True:
                self.po.connected = True
                self.po.user = self.form.userEdit.text()
                self.po.url = self.form.urlEdit.text()
                self.po.passwd = self.form.passEdit.text()
                self.form.connectButton.setStyleSheet('QPushButton {color: green;}')
                self.form.connectButton.setEnabled(False)
                self.form.forkButton.setEnabled(True)
                self.form.connectButton.setText('Connected')
            else:
                print(r.json()["message"])
                self.po.connected = False
        except:
            FreeCAD.Console.PrintWarning(translate("TaackPlm","Can't connect to the intranet.")+"\n")
            return

    def uploadCurrentActiveDoc(self):
        if (self.po.connected == False):
            FreeCAD.Console.PrintWarning(translate("TaackPlm","Not connected.")+"\n")
            return False
        b = self.createBucketProtobuf()
        f = open("fc_proto", 'wb')
        f.write(b.SerializeToString())
        f.close()
        data = {"ajax": 'true'}
        f2 = open("fc_proto", 'rb')
        r = self.po.taackIntranetSession.post(url=self.po.url + 'plm/uploadProto', files={'proto.bin': f2}, data=data)
        f2.close()

        if r.json()["success"] == True:
            # print r.json()["apiToken"]
            return True
        else:
            print(r.json()["message"])
            self.form.connectButton.setStyleSheet('QPushButton {color: red;}')
            self.form.connectButton.setEnabled(True)
            self.form.connectButton.setText('DisConnected')
            return False

    ### FreeCAD <-> protobuf conversion tools

    def createBucketProtobuf(self):
        print("createBucketProtobuf")
        self.avoidLoop = []
        d = FreeCAD.ActiveDocument
        bucket = PlmBuf.Bucket()
        self.createDocProtobuf(d, bucket)
        return bucket

    def createDocProtobuf(self, obj, bucket):
        print("createDocProtobuf " + obj.Name)
        try:
            if (self.avoidLoop.count(obj.Name) > 0):
                return
            self.avoidLoop.append(obj.Name)
            plmFile = PlmBuf.PlmFile()
            s = os.stat(obj.FileName)
            plmFile.cTimeNs = s.st_ctime_ns
            plmFile.uTimeNs = s.st_mtime_ns
            plmFile.name = obj.Name
            plmFile.id = obj.Id if obj.Id else obj.Uid
            print("plmFile.id " + plmFile.id)

            plmFile.label = obj.Label
            plmFile.comment = obj.Comment
            plmFile.fileName = obj.FileName
            plmFile.createdDate = obj.CreationDate
            plmFile.createdBy = obj.CreatedBy
            plmFile.lastModifiedDate = obj.LastModifiedDate
            plmFile.lastModifiedBy = obj.LastModifiedBy
            plmFile.label = obj.Label
            plmFile.comment = obj.Comment
            plmFile.fileName = obj.FileName
            linkedObjects = iter(obj.Objects)
            for l in linkedObjects:
                if (type(l) == FreeCAD.DocumentObject and l.TypeId == 'App::Link'):
                    lp = self.createLinkProtobuf(l, bucket)
                    if (lp != None):
                        plmFile.externalLink.append(lp)

            plmFile.fileContent = open(obj.FileName, 'rb').read()
            bucket.plmFiles[plmFile.name].CopyFrom(plmFile)
        except:
            raise ValueError("Select the file you waant to upload in the tree")

        return obj.Name

    def createLinkProtobuf(self, obj, bucket):
        print("createLinkProtobuf " + obj.Name)
        try:
            plmLink = PlmBuf.PlmLink()
            plmLink.linkedObject = obj.LinkedObject.Name
            plmLink.linkClaimChild = obj.LinkClaimChild
            if (obj.LinkCopyOnChange == 'Disabled'):
                plmLink.linkCopyOnChange = PlmBuf.PlmLink.LinkCopyOnChangeEnum.Disabled
            elif (obj.LinkCopyOnChange == 'Enabled'):
                plmLink.linkCopyOnChange = PlmBuf.PlmLink.LinkCopyOnChangeEnum.Enabled
            elif (obj.LinkCopyOnChange == 'Owned'):
                plmLink.linkCopyOnChange = PlmBuf.PlmLink.LinkCopyOnChangeEnum.Owned
            plmLink.linkTransform = obj.LinkTransform
            f = self.createDocProtobuf(obj.LinkedObject.Document, bucket)
            if (f == None):
                return
            plmLink.plmFile = f
            bucket.links[obj.LinkedObject.Document.Name].CopyFrom(plmLink)
        except:
            print("createLinkProtobuf Error")

        return obj.LinkedObject.Document.Name


if FreeCAD.GuiUp:

    FreeCADGui.addCommand('TaackPLM_Intranet', CommandTaackPlm())
