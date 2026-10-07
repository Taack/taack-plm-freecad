import FreeCAD
import json
import os
import re
import requests
import time
import zipfile
import math
import uuid
import time
import time
import tempfile
import hashlib
from PySide import QtCore, QtGui
from io import BytesIO

import freecad_plm_pb2 as PlmBuf

if FreeCAD.GuiUp:
    import FreeCADGui
    from DraftTools import translate
    from PySide.QtCore import QT_TRANSLATE_NOOP
else:
    # \cond
    def translate(ctxt, txt):
        return txt


    def QT_TRANSLATE_NOOP(ctxt, txt):
        return txt
    # \endcond

__title__ = "FreeCAD Taack PLM commands"
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
        return {'Pixmap': os.path.join(os.path.dirname(__file__), "icons", 'logo_taack.svg'),
                'MenuText': QtCore.QT_TRANSLATE_NOOP("TaackPlm_Intranet", "Plm"),
                'ToolTip': QtCore.QT_TRANSLATE_NOOP("TaackPlm_Intranet", "Manages the current document with Taack PLM")}

    def IsActive(self):
        """Here you can define if the command must be active or not (greyed) if certain conditions
        are met or not. This function is optional."""
        # if FreeCAD.activeDocument():
        #     return True
        # else:
        #     return False
        return True

    def Activated(self):
        FreeCADGui.Control.showDialog(TaackPlmTaskPanel(self))


class TaackPlmTaskPanel(object):
    '''The TaskPanel for the Taack PLM command'''

    def __init__(self, po):

        self.uuidVersion = None
        self.docLabelsForked = None
        self.shaOneMap = None
        self.forkMode = 'Active'
        self.po = po
        self.avoidLoop = set()
        self.form = FreeCADGui.PySideUic.loadUi(os.path.join(os.path.dirname(__file__), 'taack-plm.ui'))

        # Select the Login tab when we are not connected.
        if not self.po.connected:
            self.form.tabWidget.setCurrentWidget(
                self.form.loginTab
            )

        # Restore saved workspace directory
        workspace = self.po.settings.value("workspace", "")
        if workspace:
            self.form.guiFileChooser.setFileName(workspace)
            self.set_freecad_working_directory(workspace)
        # Save workspace whenever the user changes it
        QtCore.QObject.connect(self.form.guiFileChooser, QtCore.SIGNAL("fileNameChanged(QString)"), self.save_workspace)

        self.form.userEdit.insert(po.user)
        self.form.passEdit.insert(po.passwd)
        self.form.urlEdit.insert(po.url)
        self.form.modelTable.setColumnCount(5)
        self.form.modelTable.verticalHeader().setVisible(False)
        self.form.modelTable.itemClicked.connect(self.open_in_freecad)
        QtCore.QObject.connect(self.form.connectButton, QtCore.SIGNAL("pressed()"), self.login_intranet)
        QtCore.QObject.connect(self.form.disconnectButton, QtCore.SIGNAL("pressed()"), self.logout_intranet)
        QtCore.QObject.connect(self.form.forkButton, QtCore.SIGNAL("pressed()"), self.fork)
        QtCore.QObject.connect(self.form.uploadButton, QtCore.SIGNAL("pressed()"), self.upload_current_active_doc)
        QtCore.QObject.connect(self.form.searchPartButton, QtCore.SIGNAL("pressed()"), self.search_parts)
        self.form.uploadProgress.setValue(0)
        self.form.uploadProgress.setVisible(True)
        self.browseShowingParts = False

        if self.po.connected:
            self.form.connectButton.setStyleSheet('QPushButton {color: green;}')
            self.form.connectButton.setEnabled(False)
            self.form.connectButton.setText('Connected')

    def set_freecad_working_directory(self, workspace):
        if not workspace:
            return

        param = FreeCAD.ParamGet(
            "User parameter:BaseApp/Preferences/General"
        )

        param.SetString("WorkingDir", workspace)
        param.SetString("FileOpenSavePath", workspace)

    def save_workspace(self, workspace):
        print("save_workspace: " + str(workspace))
        self.po.settings.setValue("workspace", workspace)
        self.po.settings.sync()
        # Make FreeCAD use the PLM workspace as its default directory
        self.set_freecad_working_directory(workspace)

    def compute_file_shaOne(self, filePath):
        sha1 = hashlib.sha1()
        with open(filePath, 'rb') as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                sha1.update(data)

        return sha1.hexdigest()

    def save_preferences(self):
        self.po.user = self.form.userEdit.text()
        self.po.settings.setValue("username", self.po.user)
        self.po.url = self.form.urlEdit.text()
        self.po.settings.setValue("url", self.po.url)

    def accept(self):
        print("Closing Taack PLM panel")
        FreeCADGui.Control.closeDialog()

    def add_to_workspace(self):
        global message_label
        try:
            item = self.form.modelTable.currentItem()

            if item is None:
                raise ValueError("Select a part to add to the workspace.")
            part = item.data(QtCore.Qt.UserRole)
            part_id = part.get("id")
            message_label = self.form.searchPartMessageLabel

            if not self.po.connected:
                raise ValueError("Not connected to the PLM server.")

            workspace = self.po.settings.value("workspace", "")

            if not workspace:
                raise ValueError("Please select a working directory first.")

            workspace = os.path.abspath(os.path.expanduser(workspace))

            if not os.path.isdir(workspace):
                os.makedirs(workspace, exist_ok=True)

            # ---------------------------------------------------------
            # Try to determine the original FreeCAD filename
            # ---------------------------------------------------------
            expected_name = part.get("pathOnHost")

            # ---------------------------------------------------------
            # If the part is already in the workspace, don't download it
            # ---------------------------------------------------------
            if expected_name:
                expected_name = os.path.basename(str(expected_name))

                if not expected_name.lower().endswith(".fcstd"):
                    expected_name += ".FCStd"

            # ---------------------------------------------------------
            # Build download URL
            # ---------------------------------------------------------
            base_url = self.form.urlEdit.text().strip()

            if not base_url.endswith("/"):
                base_url += "/"

            url = base_url + "plm/downloadBinPart"

            message_label.setText("Downloading part...")

            FreeCAD.Console.PrintMessage(
                "Downloading PLM part "
                + str(part_id)
                + " from: "
                + url
                + "\n"
            )

            # ---------------------------------------------------------
            # Download the ZIP
            # ---------------------------------------------------------
            response = self.po.taackIntranetSession.get(
                url,
                params={"id": part_id},
                timeout=120
            )

            response.raise_for_status()

            # ---------------------------------------------------------
            # Determine ZIP filename
            # ---------------------------------------------------------
            if expected_name:
                zip_base_name = os.path.splitext(expected_name)[0]
            else:
                zip_base_name = "plm_part_" + str(part_id)

            zip_path = os.path.join(
                workspace,
                zip_base_name + "-" + str(part_id) + ".zip"
            )

            # Avoid accidentally overwriting another downloaded ZIP.
            if os.path.exists(zip_path):
                timestamp = str(int(time.time()))
                zip_path = os.path.join(
                    workspace,
                    zip_base_name + "-" + timestamp + ".zip"
                )

            # ---------------------------------------------------------
            # Save ZIP
            # ---------------------------------------------------------
            with open(zip_path, "wb") as f:
                f.write(response.content)

            FreeCAD.Console.PrintMessage("Downloaded PLM part to: " + zip_path + "\n")

            # ---------------------------------------------------------
            # Find the FreeCAD file inside the ZIP
            # ---------------------------------------------------------
            message_label.setText("Extracting part...")

            freecad_file = None

            with zipfile.ZipFile(zip_path, "r") as zip_file:
                zip_file.extractall(workspace)
                freecad_file = os.path.abspath(os.path.join(workspace, expected_name))

            # ---------------------------------------------------------
            # Remove the downloaded ZIP
            # ---------------------------------------------------------
            try:
                os.remove(zip_path)
            except OSError:
                FreeCAD.Console.PrintWarning(
                    "Could not remove downloaded ZIP: "
                    + zip_path
                    + "\n"
                )

            # ---------------------------------------------------------
            # Verify the extracted FreeCAD file
            # ---------------------------------------------------------
            if not os.path.isfile(freecad_file):
                raise ValueError(
                    "The downloaded FreeCAD file does not exist:\n"
                    + freecad_file
                )

            # ---------------------------------------------------------
            # Success
            # ---------------------------------------------------------
            message_label.setText(
                "Part added to workspace."
            )

            FreeCAD.Console.PrintMessage(
                "Part added to workspace: "
                + freecad_file
                + "\n"
            )

            return freecad_file

        except requests.exceptions.RequestException as e:

            message = "Download failed: " + str(e)
            try:
                message_label.setText(message)
            except Exception:
                pass

            FreeCAD.Console.PrintError(message + "\n")

            return None

        except Exception as e:

            message = "Error adding part to workspace: " + str(e)
            try:
                message_label.setText(message)
            except Exception:
                pass

            FreeCAD.Console.PrintError(message + "\n")
            return None

    def open_in_freecad(self):
        try:
            if self.form.modelTable.currentItem() is None:
                self.form.searchPartMessageLabel.setText("Please select a part first.")
                return

            # Use the same download/workspace function
            freecad_file = self.add_to_workspace()

            if not freecad_file:
                return

            if not os.path.exists(freecad_file):
                raise ValueError(
                    "The downloaded FreeCAD file does not exist:\n" +
                    freecad_file
                )

            FreeCAD.openDocument(freecad_file)

            if self.form.tabWidget.currentWidget() == self.form.searchPartTab:
                self.form.searchPartMessageLabel.setText(
                    "Opened part in FreeCAD."
                )
            else:
                self.form.browseMessageLabel.setText(
                    "Opened part in FreeCAD."
                )

            FreeCAD.Console.PrintMessage(
                "Opened FreeCAD document: " +
                freecad_file +
                "\n"
            )

        except Exception as e:

            if self.form.tabWidget.currentWidget() == self.form.searchPartTab:
                self.form.searchPartMessageLabel.setText(
                    "Error opening part in FreeCAD: " +
                    str(e)
                )
            else:
                self.form.browseMessageLabel.setText(
                    "Error opening part in FreeCAD: " +
                    str(e)
                )

            FreeCAD.Console.PrintWarning(
                "Error opening part in FreeCAD: " +
                str(e) +
                "\n"
            )

    def search_parts(self):

        self.form.modelTable.clear()
        self.form.searchPartMessageLabel.clear()

        search_text = self.form.partSearchEdit.text().strip()
        tag_name = self.form.tagName.text().strip()
        is_my_model = self.form.myModel.isChecked()
        is_top_assemblies = self.form.topAssemblies.isChecked()
        model_status = self.form.modelStatus.currentText().strip()

        if not self.po.connected:
            self.form.searchPartMessageLabel.setText(
                "Not connected to the PLM server."
            )
            return

        try:
            base_url = self.form.urlEdit.text().strip()

            if not base_url.endswith("/"):
                base_url += "/"

            url = base_url + "plmJson/queryModel"

            response = self.po.taackIntranetSession.get(
                url,
                params={
                    "label": search_text,
                    "documentCategory.tags.name": tag_name,
                    "status": model_status,
                    "isMyModel": is_my_model,
                    "isTopAssembly": is_top_assemblies,
                },
                timeout=30
            )

            response.raise_for_status()

            parts = response.json()

            if not isinstance(parts, list):
                raise ValueError(
                    "The server returned an invalid parts list."
                )

            row_index = 0
            self.form.modelTable.setHorizontalHeaderLabels(["Name", "Creator", "status", "Version", "Date"])
            self.form.modelTable.setRowCount(len(parts))

            for part in parts:

                if not isinstance(part, dict):
                    continue

                part_id = part.get("id")

                # Prefer originalName for the visible text.
                part_name = (
                        part.get("originalName") or
                        part.get("name") or
                        part.get("label") or
                        str(part_id)
                )

                item = QtGui.QTableWidgetItem(str(part_name))
                item.setData(QtCore.Qt.UserRole, part)
                item.setFlags(QtCore.Qt.ItemIsEnabled)
                item2 = QtGui.QTableWidgetItem(str(part.get("userCreated")))
                item2.setFlags(QtCore.Qt.ItemIsEnabled)
                item3 = QtGui.QTableWidgetItem(str(part.get("status")['name']))
                item3.setFlags(QtCore.Qt.ItemIsEnabled)
                item4 = QtGui.QTableWidgetItem(str(part.get("computedVersion")))
                item4.setFlags(QtCore.Qt.ItemIsEnabled)
                item5 = QtGui.QTableWidgetItem(str(part.get("plmFileLastUpdated")))
                item5.setFlags(QtCore.Qt.ItemIsEnabled)
                self.form.modelTable.setItem(row_index, 0, item)
                self.form.modelTable.setItem(row_index, 1, item2)
                self.form.modelTable.setItem(row_index, 2, item3)
                self.form.modelTable.setItem(row_index, 3, item4)
                self.form.modelTable.setItem(row_index, 4, item5)
                row_index = row_index + 1

        except requests.exceptions.RequestException as e:
            self.form.searchPartMessageLabel.setText("Unable to search for parts: " + str(e))
            FreeCAD.Console.PrintWarning("Unable to search for parts: " + str(e) + "\n")

        except ValueError as e:
            self.form.searchPartMessageLabel.setText("Invalid response from server: " + str(e))

        except Exception as e:
            self.form.searchPartMessageLabel.setText("Error searching for parts: " + str(e))
            FreeCAD.Console.PrintWarning("Error searching for parts: " + str(e) + "\n")


    def logout_intranet(self):
        print('logout Intranet ...')
        self.po.taackIntranetSession.get(url=self.form.urlEdit.text() + 'logout', timeout=5)
        self.form.connectButton.setStyleSheet('QPushButton {color: black;}')
        self.form.connectButton.setEnabled(True)
        self.form.connectButton.setText('Connect')

    def login_intranet(self):
        print('login Intranet ...')
        data = {"username": self.form.userEdit.text(), "password": self.form.passEdit.text(), "ajax": 'true'}
        self.save_preferences()
        try:
            r = self.po.taackIntranetSession.post(url=self.form.urlEdit.text() + 'login/authenticate', data=data,
                                                  timeout=5)
            if r.json()["success"] == True:
                self.po.connected = True
                self.po.user = self.form.userEdit.text()
                self.po.url = self.form.urlEdit.text()
                self.po.passwd = self.form.passEdit.text()
                self.form.connectButton.setStyleSheet('QPushButton {color: green;}')
                self.form.connectButton.setEnabled(False)
                self.form.connectButton.setText('Connected')
                self.form.disconnectButton.setEnabled(True)
            else:
                print(r.json()["message"])
                self.po.connected = False
        except:
            FreeCAD.Console.PrintWarning(translate("TaackPlm", "Can't connect to the intranet.") + "\n")

    def upload_current_active_doc(self):

        self.form.uploadProgress.setValue(0)
        self.form.uploadButton.setEnabled(False)
        self.form.uploadButton.setText("Uploading...")

        if not self.po.connected:
            FreeCAD.Console.PrintWarning(translate("TaackPlm", "Not connected.") + "\n")
            self.form.uploadButton.setEnabled(True)
            self.form.uploadButton.setText("Upload")
            return False

        self.form.uploadProgress.setRange(0, 100)
        self.form.uploadProgress.setValue(0)
        self.form.uploadProgress.setFormat("Uploading...")
        QtGui.QApplication.processEvents()

        self.avoidLoop = set()
        self.shaOneMap = dict()

        b = self.create_bucket_protobuf()

        tmp_zip_dir = tempfile.TemporaryDirectory()
        print("tmp_zip_dir: " + tmp_zip_dir.name)
        tmp_zip_proto = os.path.join(tmp_zip_dir.name, 'proto.zip')
        print("tmp_zip_proto: " + str(tmp_zip_proto))
        with zipfile.ZipFile(tmp_zip_proto, 'w') as zip_proto_archive:

            print("zip_proto_archive: " + str(zip_proto_archive))

            zip_proto_archive.writestr('proto.bin', b.SerializeToString())
            progress = 10
            self.form.uploadProgress.setValue(progress)

        data = {"ajax": 'true'}
        file_tmp_zip_proto = open(tmp_zip_proto, 'rb')
        try:
            r = self.po.taackIntranetSession.post(url=self.po.url + 'plmProto/uploadProto',
                                                  files={'proto.bin': file_tmp_zip_proto}, data=data)
            resp_bytes = BytesIO(r.content).read()
            resp_bucket = PlmBuf.Bucket()
            resp_bucket.ParseFromString(resp_bytes)
            if resp_bucket.status == PlmBuf.ServerStatus.OK_PROTO:
                for serverSha1File in resp_bucket.serverSha1Files:
                    if serverSha1File in self.shaOneMap:
                        print("Removing:" + self.shaOneMap.pop(
                            serverSha1File) + " from files to upload ... " + serverSha1File)
                    else:
                        print("NO KEY:" + serverSha1File + " ... ")

                nbItems = len(self.shaOneMap.items())
                nb16Interval = nbItems // 16
                print("nbItems: " + str(nbItems))
                inc = nbItems // 90

                if nbItems > 0:
                    for i in range(nb16Interval + 1):
                        tmp_zip_files = os.path.join(tmp_zip_dir.name, 'files' + str(i) + '.zip')
                        with zipfile.ZipFile(tmp_zip_files, 'w') as zip_archive:

                            print("zip_archive: " + str(zip_archive))

                            for j in range(16):
                                if len(self.shaOneMap) > 0:
                                    progress += inc
                                    self.form.uploadProgress.setValue(progress)
                                    e_sha_one, filename = self.shaOneMap.popitem()
                                    zip_archive.write(filename, e_sha_one)

                        file_tmp_zip_files = open(tmp_zip_files, 'rb')
                        try:
                            r = self.po.taackIntranetSession.post(url=self.po.url + 'plmProto/uploadZip',
                                                                  files={'proto.bin': file_tmp_zip_files}, data=data)
                            resp_bytes = BytesIO(r.content).read()
                            resp_bucket = PlmBuf.Bucket()
                            resp_bucket.ParseFromString(resp_bytes)
                            if resp_bucket.status != PlmBuf.ServerStatus.OK_FILES:
                                FreeCAD.Console.PrintWarning(
                                    translate("TaackPlm", "Problem uploading zip with files.") + "\n")
                                return None
                        except Exception as ex:
                            FreeCAD.Console.PrintWarning(
                                translate("TaackPlm", "Server seems to be disconnected ... ") + str(ex) + "\n")
                            self.po.connected = False
                        finally:
                            file_tmp_zip_files.close()
                            os.remove(tmp_zip_files)
                r = self.po.taackIntranetSession.post(url=self.po.url + 'plmProto/reset', data=data)
                self.form.uploadProgress.setValue(100)
                self.form.uploadButton.setEnabled(True)
                self.form.uploadButton.setText("Upload")
                self.form.uploadProgress.setFormat("Part Uploaded")
            else:
                FreeCAD.Console.PrintWarning(translate("TaackPlm", "Message not successfully sent ... ") + "\n")
                self.form.uploadProgress.setValue(0)
                self.form.uploadButton.setEnabled(True)
                self.form.uploadButton.setText("Upload")
                self.form.uploadProgress.setFormat("Part NOT Uploaded")
                return None

        except Exception as e:
            FreeCAD.Console.PrintWarning(translate("TaackPlm", "Exception during upload ... ") + str(e) + "\n")
            self.form.connectButton.setEnabled(True)
        finally:
            file_tmp_zip_proto.close()
            os.remove(tmp_zip_proto)
            tmp_zip_dir.cleanup()
        return None

    def create_thumbnail(self, filename):
        try:
            # Read compressed file
            zfile = zipfile.ZipFile(filename)
            files = zfile.namelist()

            # Check whether we have a FreeCAD document
            if "Document.xml" not in files:
                print(input_file, " doesn't look like a FreeCAD file")
                return None

            # Read thumbnail from file or use default icon
            image = "thumbnails/Thumbnail.png"
            if image in files:
                image = zfile.read(image)
            else:
                return None

            return image

        except Exception:
            print("Error creating FreeCAD thumbnail for file ", input_file)

    def fork(self):
        self.docLabelsForked = []
        self.uuidVersion = self.uuidVersion if self.uuidVersion else uuid.uuid4()
        print(str(self.form.forkActive))
        print(str(self.form.forkAll))
        print(str(self.form.forkTouched))
        self.fork_children(FreeCAD.ActiveDocument)
        # self.form.forkButton.setEnabled(False)

    def fork_children(self, part):
        print("Forking ... " + str(part))
        if part.Label in self.docLabelsForked:
            return None
        if (part.isTouched() and self.form.forkTouched.isChecked()) or self.form.forkActive.isChecked() or self.form.forkAll.isChecked():
            print("part.isTouched(): " + str(part.isTouched()))
            if not part.Id.endswith(str(self.uuidVersion)):
                part.Id = (part.Id if part.Id else part.Uid) + '/' + str(self.uuidVersion)
        self.docLabelsForked.append(part.Label)
        if self.form.forkTouched.isChecked() or self.form.forkAll.isChecked():
            linked_objects = iter(part.Objects)
            for l in linked_objects:
                if type(l) == FreeCAD.DocumentObject and l.TypeId == 'App::Link':
                    if self.form.forkAll.isChecked() or l.LinkedObject.Document.isTouched():
                        print("l.LinkedObject.Document.isTouched(): " + str(l.LinkedObject.Document.isTouched()))
                        if not l.LinkedObject.Document.Id.endswith(str(self.uuidVersion)):
                            l.LinkedObject.Document.Id = (l.LinkedObject.Document.Id if l.LinkedObject.Document.Id else l.LinkedObject.Document.Uid) + '/' + str(self.uuidVersion)
                        self.fork_children(l.LinkedObject.Document)
        return None


    def create_bucket_protobuf(self):
        self.shaOneMap = dict()
        bucket = PlmBuf.Bucket()
        self.create_doc_protobuf(FreeCAD.ActiveDocument, bucket)
        return bucket

    def create_doc_protobuf(self, obj, bucket):

        if obj is None:
            return None

        # A document must have FileName.
        if not hasattr(obj, "FileName"):
            raise ValueError(
                "Upload error: object '" + getattr(obj, "Label", "<unknown>") + "' is not a FreeCAD Document. Type: " +
                getattr(obj, "TypeId", "<unknown>"))

        print("createDocProtobuf: " + obj.Name + " / " + obj.Label)

        try:
            if obj.Name in self.avoidLoop:
                return None

            self.avoidLoop.add(obj.Name)
            plm_file = PlmBuf.PlmFile()
            s = os.stat(obj.FileName)
            plm_file.cTimeNs = s.st_ctime_ns
            plm_file.uTimeNs = s.st_mtime_ns
            plm_file.name = obj.Name
            plm_file.id = obj.Id if obj.Id else obj.Uid
            plm_file.label = obj.Label
            plm_file.comment = obj.Comment
            plm_file.fileName = obj.FileName
            plm_file.createdDate = obj.CreationDate
            plm_file.createdBy = obj.CreatedBy
            plm_file.sha1hex = self.compute_file_shaOne(obj.FileName)
            plm_file.lastModifiedDate = obj.LastModifiedDate
            plm_file.lastModifiedBy = obj.LastModifiedBy
            linked_objects = iter(obj.Objects)
            for l in linked_objects:
                if type(l) == FreeCAD.DocumentObject and l.TypeId == 'App::Link':
                    lp = self.create_link_protobuf(l, bucket)
                    if lp is not None:
                        plm_file.externalLink.append(lp)

            # plm_file.fileContent = open(obj.FileName, 'rb').read()
            plm_file.filePreview = self.create_thumbnail(obj.FileName)
            bucket.plmFiles[plm_file.name].CopyFrom(plm_file)
            self.shaOneMap[plm_file.sha1hex] = obj.FileName

        except:
            raise ValueError("Select the file you waant to upload in the tree")

        return obj.Name


    def create_link_protobuf(self, obj, bucket):
        print("createLinkProtobuf " + obj.Name)

        try:
            if obj.TypeId != "App::Link":
                return None

            if obj.LinkedObject is None:
                return None

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

            linked_doc = obj.LinkedObject.Document

            if linked_doc is None:
                return None

            f = self.create_doc_protobuf(linked_doc, bucket)
            if f is None:
                return None

            plm_link.plmFile = f
            bucket.links[linked_doc.Name].CopyFrom(plm_link)

        except Exception as e:
            print("createLinkProtobuf Error: " + str(e))
            raise ValueError("createLinkProtobuf Error: " + str(e))

        return linked_doc.Name


if FreeCAD.GuiUp:
    FreeCADGui.addCommand('TaackPLM_Intranet', CommandTaackPlm())
