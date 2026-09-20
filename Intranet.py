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
        """Here you can define if the command must be active or not (greyed) if certain conditions
        are met or not. This function is optional."""
        if FreeCAD.activeDocument():
            return True
        else:
            return False

    def Activated(self):
        FreeCADGui.Control.showDialog(TaackPlmTaskPanel(self))



class TaackPlmTaskPanel(object):

    '''The TaskPanel for the Taack PLM command'''

    def __init__(self, po):
        self.uuidVersion = None
        self.docLabelsForked = None
        self.forkMode = 'Active'
        self.po = po
        self.avoidLoop = []
        self.form = FreeCADGui.PySideUic.loadUi(os.path.join(os.path.dirname(__file__),'taack-plm.ui'))
        self.form.userEdit.insert(po.user)
        self.form.passEdit.insert(po.passwd)
        self.form.urlEdit.insert(po.url)
        QtCore.QObject.connect(self.form.connectButton, QtCore.SIGNAL("pressed()"), self.login_intranet)
        QtCore.QObject.connect(self.form.forkButton, QtCore.SIGNAL("pressed()"), self.fork)
        if self.po.connected:
            self.form.connectButton.setStyleSheet('QPushButton {color: green;}')
            self.form.connectButton.setEnabled(False)
            self.form.forkButton.setEnabled(True)
            self.form.connectButton.setText('Connected')

    def save_preferences(self):
        self.po.user = self.form.userEdit.text()
        self.po.settings.setValue("username", self.po.user)
        self.po.url = self.form.urlEdit.text()
        self.po.settings.setValue("url", self.po.url)

    def accept(self):
        print('Accept')
        if not self.po.connected:
            FreeCAD.Console.PrintWarning(translate("TaackPlm","Not connected.")+"\n")
            return
        try:
            self.upload_current_active_doc()
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
        self.docLabelsForked = []
        self.uuidVersion = uuid.uuid4()
        print(str(self.form.forkActive))
        print(str(self.form.forkAll))
        print(str(self.form.forkTouched))
        self.fork_children(FreeCAD.ActiveDocument)
        self.form.forkButton.setEnabled(False)

    def fork_children(self, part):
        print("Forking ... " + str(part))
        if part.Label in self.docLabelsForked:
            return None
        if (part.isTouched() and self.form.forkTouched.isChecked()) or self.form.forkActive.isChecked():
            part.Id = part.Id if part.Id else part.Uid + '/' + str(self.uuidVersion)
        self.docLabelsForked.append(part.Label)
        if self.form.forkTouched.isChecked() or self.form.forkAll.isChecked():
            linked_objects = iter(part.Objects)
            for l in linked_objects:
                if type(l) == FreeCAD.DocumentObject and l.TypeId == 'App::Link':
                    if self.form.forkAll.isChecked() or l.LinkedObject.Document.isTouched():
                        l.LinkedObject.Document.Id = l.LinkedObject.Document.Id if l.LinkedObject.Document.Id else l.LinkedObject.Document.Uid + '/' + str(self.uuidVersion)
                        self.fork_children(l.LinkedObject.Document)
        return None



    def login_intranet(self):
        print('login Intranet ...')
        data = {"username": self.form.userEdit.text(), "password": self.form.passEdit.text(), "ajax": 'true'}
        self.save_preferences()
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


    def upload_current_active_doc(self):
        if not self.po.connected:
            FreeCAD.Console.PrintWarning(translate("TaackPlm","Not connected.")+"\n")
            return False
        b = self.create_bucket_protobuf()
        f = open("fc_proto", 'wb')
        f.write(b.SerializeToString())
        f.close()
        data = {"ajax": 'true'}
        f2 = open("fc_proto", 'rb')
        r = self.po.taackIntranetSession.post(url=self.po.url + 'plm/uploadProto', files={'proto.bin': f2}, data=data)
        f2.close()

        if r.json()["success"]:
            # print r.json()["apiToken"]
            return True
        else:
            print(r.json()["message"])
            self.form.connectButton.setStyleSheet('QPushButton {color: red;}')
            self.form.connectButton.setEnabled(True)
            self.form.connectButton.setText('DisConnected')
            return False

    ### FreeCAD <-> protobuf conversion tools

    def create_bucket_protobuf(self):
        print("createBucketProtobuf")
        self.avoidLoop = []
        d = FreeCAD.ActiveDocument
        bucket = PlmBuf.Bucket()
        self.create_doc_protobuf(d, bucket)
        return bucket

    def create_doc_protobuf(self, obj, bucket):
        print("createDocProtobuf " + obj.Name)
        try:
            if self.avoidLoop.count(obj.Name) > 0:
                return None
            self.avoidLoop.append(obj.Name)
            plm_file = PlmBuf.PlmFile()
            s = os.stat(obj.FileName)
            plm_file.cTimeNs = s.st_ctime_ns
            plm_file.uTimeNs = s.st_mtime_ns
            plm_file.name = obj.Name
            plm_file.id = obj.Id if obj.Id else obj.Uid
            print("plmFile.id " + plm_file.id)

            plm_file.label = obj.Label
            plm_file.comment = obj.Comment
            plm_file.fileName = obj.FileName
            plm_file.createdDate = obj.CreationDate
            plm_file.createdBy = obj.CreatedBy
            plm_file.lastModifiedDate = obj.LastModifiedDate
            plm_file.lastModifiedBy = obj.LastModifiedBy
            plm_file.label = obj.Label
            plm_file.comment = obj.Comment
            plm_file.fileName = obj.FileName
            linked_objects = iter(obj.Objects)
            for l in linked_objects:
                if type(l) == FreeCAD.DocumentObject and l.TypeId == 'App::Link':
                    lp = self.create_link_protobuf(l, bucket)
                    if lp is not None:
                        plm_file.externalLink.append(lp)

            plm_file.fileContent = open(obj.FileName, 'rb').read()
            bucket.plmFiles[plm_file.name].CopyFrom(plm_file)
        except:
            raise ValueError("Select the file you waant to upload in the tree")

        return obj.Name

    def create_link_protobuf(self, obj, bucket):
        print("createLinkProtobuf " + obj.Name)
        try:
            plm_link = PlmBuf.PlmLink()
            plm_link.linkedObject = obj.LinkedObject.Name
            plm_link.linkClaimChild = obj.LinkClaimChild
            if obj.LinkCopyOnChange == 'Disabled':
                plm_link.linkCopyOnChange = PlmBuf.PlmLink.LinkCopyOnChangeEnum.Disabled
            elif obj.LinkCopyOnChange == 'Enabled':
                plm_link.linkCopyOnChange = PlmBuf.PlmLink.LinkCopyOnChangeEnum.Enabled
            elif obj.LinkCopyOnChange == 'Owned':
                plm_link.linkCopyOnChange = PlmBuf.PlmLink.LinkCopyOnChangeEnum.Owned
            plm_link.linkTransform = obj.LinkTransform
            f = self.create_doc_protobuf(obj.LinkedObject.Document, bucket)
            if f is None:
                return None
            plm_link.plmFile = f
            bucket.links[obj.LinkedObject.Document.Name].CopyFrom(plm_link)
        except:
            raise ValueError("createLinkProtobuf Error")

        return obj.LinkedObject.Document.Name


if FreeCAD.GuiUp:

    FreeCADGui.addCommand('TaackPLM_Intranet', CommandTaackPlm())
