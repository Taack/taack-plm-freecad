import FreeCAD
import json
import os
import requests
import zipfile
import math
import uuid
import time
import hashlib
from PySide import QtCore, QtGui

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
        self.passwd = "ChangeIt"

    def GetResources(self):
        return {'Pixmap': os.path.join(os.path.dirname(__file__), "icons", 'logo_taack.svg'),
                'MenuText': QtCore.QT_TRANSLATE_NOOP("TaackPlm_Intranet", "Plm"),
                'ToolTip': QtCore.QT_TRANSLATE_NOOP("TaackPlm_Intranet", "Manages the current document with Taack PLM")}

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
        self.refresh_part_list()
        self.form.userEdit.insert(po.user)
        self.form.passEdit.insert(po.passwd)
        self.form.urlEdit.insert(po.url)
        QtCore.QObject.connect(self.form.connectButton, QtCore.SIGNAL("pressed()"), self.login_intranet)
        QtCore.QObject.connect(self.form.forkButton, QtCore.SIGNAL("pressed()"), self.fork)
        QtCore.QObject.connect(self.form.forkActive, QtCore.SIGNAL("toggled(bool)"), self.refresh_part_list)
        QtCore.QObject.connect(self.form.forkAll, QtCore.SIGNAL("toggled(bool)"), self.refresh_part_list)

        QtCore.QObject.connect(
            self.form.forkTouched,
            QtCore.SIGNAL("toggled(bool)"),
            self.refresh_part_list
        )
        QtCore.QObject.connect(
            self.form.uploadButton,
            QtCore.SIGNAL("pressed()"),
            self.upload_current_active_doc
        )

        self.form.uploadProgress.setValue(0)
        self.form.uploadProgress.setVisible(True)

        if self.po.connected:
            self.form.connectButton.setStyleSheet('QPushButton {color: green;}')
            self.form.connectButton.setEnabled(False)
            self.form.forkButton.setEnabled(True)
            self.form.connectButton.setText('Connected')

    def compute_file_shaOne(self, filePath):
        sha1 = hashlib.sha1()
        with open(filePath, 'rb') as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                sha1.update(data)

        return sha1.hexdigest()

    def add_upload_part_to_list(self, doc):
        if doc is None:
            return

        try:
            label = doc.Label
        except Exception:
            return

        for i in range(self.form.List.count()):
            if self.form.List.item(i).text() == label:
                return

        self.form.List.addItem(label)


    def get_upload_parts(self):
        """
        Return the documents selected for upload.
        Never return doc.Objects.
        """
        return self.get_upload_documents()

    def _record_modified_baseline(self, assembly_doc, documents):
        assembly_file = getattr(assembly_doc, "FileName", "")

        if not assembly_file:
            return

        assembly_file = os.path.abspath(assembly_file)

        baseline = self._get_modified_baseline()

        assembly_baseline = baseline.setdefault(
            assembly_file,
            {}
        )

        for doc in documents:
            filename = getattr(doc, "FileName", "")
            if not filename:
                continue
            filename = os.path.abspath(filename)
            mtime = self._get_file_mtime_ns(filename)
            if mtime is not None:
                assembly_baseline[filename] = mtime

        self._save_modified_baseline(baseline)

    def get_upload_documents(self):
        doc = FreeCAD.ActiveDocument
        if doc is None:
            return []

        # Active document only
        if self.form.forkActive.isChecked():
            return [doc]

        # Discover linked documents.
        all_documents = []
        visited_docs = set()
        visited_objects = set()
        visited_docs.add(
            getattr(doc, "Name", str(id(doc)))
        )
        for obj in getattr(doc, "Objects", []):
            self.scan_object_for_links(obj, all_documents, visited_docs, visited_objects)

        # All parts
        if self.form.forkAll.isChecked():
            return all_documents

        # Modified parts
        if self.form.forkTouched.isChecked():
            modified_documents = []

            for linked_doc in all_documents:
                if self._document_was_modified(linked_doc, doc):
                    modified_documents.append(linked_doc)
            return modified_documents

        return []

    def get_linked_documents_recursive(
            self,
            doc,
            documents,
            visited_documents):

        if doc is None:
            return

        try:
            doc_name = doc.Name
        except Exception:
            return

        if doc_name in visited_documents:
            return

        visited_documents.add(doc_name)

        print("")
        print("Scanning document: " + doc_name + " / " + doc.Label)

        try:
            objects = list(doc.Objects)
        except Exception as e:
            print("Unable to read document objects: " + str(e)
            )

            return

        for obj in objects:
            self.scan_object_for_links(
                obj,
                documents,
                visited_documents
            )

    def _is_link_object(self, obj):
        if obj is None:
            return False

        try:
            if obj.isDerivedFrom("App::Link"):
                return True
        except Exception:
            pass

        try:
            if obj.isDerivedFrom("Assembly::AssemblyLink"):
                return True
        except Exception:
            pass

        return False

    def _get_linked_document(self, obj):
        if obj is None:
            return None

        try:
            linked = getattr(obj, "LinkedObject", None)

            if linked is not None:
                return linked.Document
        except Exception:
            pass

        try:
            linked = obj.getLinkedObject()

            if linked is not None:
                return linked.Document
        except Exception:
            pass

        return None

    def scan_object_for_links(
            self,
            obj,
            documents,
            visited_docs=None,
            visited_objects=None
    ):
        if obj is None:
            return

        if visited_docs is None:
            visited_docs = set()

        if visited_objects is None:
            visited_objects = set()

        try:
            obj_key = (
                getattr(obj.Document, "Name", ""),
                getattr(obj, "Name", "")
            )
        except Exception:
            obj_key = id(obj)

        if obj_key in visited_objects:
            return

        visited_objects.add(obj_key)

        # ------------------------------------------------------------
        # Linked document
        # ------------------------------------------------------------

        if self._is_link_object(obj):

            linked_doc = self._get_linked_document(obj)

            if linked_doc is not None:

                doc_key = getattr(linked_doc, "Name", str(id(linked_doc)))

                if doc_key not in visited_docs:
                    visited_docs.add(doc_key)
                    documents.append(linked_doc)

                    # Scan the linked document for subassemblies/parts.
                    self.scan_document_for_links(
                        linked_doc,
                        documents,
                        visited_docs,
                        visited_objects
                    )

            return

        # ------------------------------------------------------------
        # Groups / assembly hierarchy
        # ------------------------------------------------------------

        children = []

        try:
            children.extend(getattr(obj, "Group", []) or [])
        except Exception:
            pass

        try:
            claimed = obj.claimChildren()

            if claimed:
                children.extend(claimed)
        except Exception:
            pass

        for child in children:
            self.scan_object_for_links(
                child,
                documents,
                visited_docs,
                visited_objects
            )

    def scan_document_for_links(
            self,
            doc,
            documents,
            visited_docs=None,
            visited_objects=None
    ):
        if doc is None:
            return

        if visited_docs is None:
            visited_docs = set()

        if visited_objects is None:
            visited_objects = set()

        doc_key = getattr(doc, "Name", str(id(doc)))

        if doc_key in visited_docs:
            return

        visited_docs.add(doc_key)

        for obj in getattr(doc, "Objects", []):
            self.scan_object_for_links(
                obj,
                documents,
                visited_docs,
                visited_objects
            )

    def scan_children_for_links(
            self,
            obj,
            documents,
            visited_documents):

        # ---------------------------------------------------------------
        # Group
        # ---------------------------------------------------------------

        try:
            group = obj.Group
        except Exception:
            group = None

        if group:

            for child in group:
                self.scan_object_for_links(
                    child,
                    documents,
                    visited_documents
                )

        # ---------------------------------------------------------------
        # claimChildren()
        # ---------------------------------------------------------------

        try:
            children = obj.claimChildren()
        except Exception:
            children = None

        if children:

            for child in children:
                self.scan_object_for_links(
                    child,
                    documents,
                    visited_documents
                )

    def add_linked_document(
            self,
            link,
            documents,
            visited_documents):

        if link is None:
            return

        try:
            linked_object = link.LinkedObject
        except Exception:

            # Some Assembly links may expose getLinkedObject()
            try:
                linked_object = link.getLinkedObject()
            except Exception:
                linked_object = None

        if linked_object is None:
            return

        try:
            linked_doc = linked_object.Document
        except Exception:
            linked_doc = None

        if linked_doc is None:
            return

        print(
            "FOUND LINK: " +
            getattr(link, "Name", "<unknown>") +
            " [" +
            getattr(link, "TypeId", "<unknown>") +
            "] -> " +
            linked_doc.Name +
            " / " +
            linked_doc.Label
        )

        if linked_doc.Name in visited_documents:
            return

        documents.append(linked_doc)

        self.get_linked_documents_recursive(
            linked_doc,
            documents,
            visited_documents
        )

    def refresh_part_list(self):

        self.form.List.clear()
        self.form.uploadProgress.setValue(0)

        documents = self.get_upload_documents()

        print("")
        print("======================================")
        print("DOCUMENTS SHOWN IN UPLOAD LIST")
        print("======================================")

        for doc in documents:
            print(
                doc.Name +
                " / " +
                doc.Label
            )

            self.add_upload_part_to_list(doc)

        print(
            "TOTAL SHOWN: " +
            str(len(documents))
        )

        print("======================================")

    def save_preferences(self):
        self.po.user = self.form.userEdit.text()
        self.po.settings.setValue("username", self.po.user)
        self.po.url = self.form.urlEdit.text()
        self.po.settings.setValue("url", self.po.url)

    def accept(self):
        print('Accept')
        #    if not self.po.connected:
        #        FreeCAD.Console.PrintWarning(translate("TaackPlm","Not connected.")+"\n")
        #        return
        #    try:
        #        self.upload_current_active_doc()
        #        FreeCADGui.Control.closeDialog()
        #    except ValueError as e:
        #        FreeCAD.Console.PrintWarning(translate("TaackPlm","Cannot Upload ... " + str(e))+"\n")
        #    except:
        #        FreeCAD.Console.PrintWarning(translate("TaackPlm","Cannot Upload ... Try to reconnect")+"\n")
        #        self.po.connected = False
        #        self.form.connectButton.setStyleSheet('QPushButton {color: red;}')
        #        self.form.connectButton.setEnabled(True)
        #        self.form.connectButton.setText('DisConnected')

        print("Closing Taack PLM panel")
        FreeCADGui.Control.closeDialog()

    def fork(self):

        self.docLabelsForked = []
        self.uuidVersion = (
            self.uuidVersion
            if self.uuidVersion
            else uuid.uuid4()
        )

        documents = self.get_upload_documents()

        print("")
        print("======================================")
        print("FORK DOCUMENTS")
        print("======================================")

        for doc in documents:
            if doc.Name in self.docLabelsForked:
                continue
            self.docLabelsForked.append(doc.Name)
            print("Forking: " +doc.Name + " / " + doc.Label)

        print("======================================")

    def login_intranet(self):
        print('login Intranet ...')
        data = {"username": self.form.userEdit.text(), "password": self.form.passEdit.text(), "ajax": 'true'}
        self.save_preferences()
        try:
            r = self.po.taackIntranetSession.post(url=self.form.urlEdit.text() + 'login/authenticate', data=data,timeout=5)
            if r.json()["success"] == True:
                self.po.connected = True
                self.po.user = self.form.userEdit.text()
                self.po.url = self.form.urlEdit.text()
                self.po.passwd = self.form.passEdit.text()
                self.form.connectButton.setStyleSheet('QPushButton {color: green;}')
                self.form.connectButton.setEnabled(False)
                self.form.forkButton.setEnabled(True)
                self.form.connectButton.setText('Connected')
                QtCore.QTimer.singleShot(1000, lambda: self.form.tabWidget.setCurrentWidget(self.form.checkInTab))
            else:
                print(r.json()["message"])
                self.po.connected = False
        except:
            FreeCAD.Console.PrintWarning(translate("TaackPlm", "Can't connect to the intranet.") + "\n")

    def upload_current_active_doc(self):

        self.form.List.clear()
        self.form.uploadProgress.setValue(0)
        self.form.uploadButton.setEnabled(False)
        self.form.uploadButton.setText("Uploading...")

        if not self.po.connected:
            FreeCAD.Console.PrintWarning(translate("TaackPlm", "Not connected.") + "\n")
            self.form.uploadButton.setEnabled(True)
            self.form.uploadButton.setText("Upload")
            return False
          
        documents = self.get_upload_documents()

        if not self.confirm_large_upload(documents):
            self.form.uploadButton.setEnabled(True)
            self.form.uploadButton.setText("Upload")
            return False

        # b = self.create_bucket_protobuf()
        #
        #  # Serialize the protobuf to disk.
        # with open("fc_proto", "wb") as f:
        #     f.write(b.SerializeToString())

        # # Open the file for upload.
        # f2 = open("fc_proto", "rb")

        # Do not change the progress bar while preparing the upload.
        self.form.uploadProgress.setRange(0, 100)
        self.form.uploadProgress.setValue(0)
        self.form.uploadProgress.setFormat("Uploading...")
        QtGui.QApplication.processEvents()

        # try:
        #     self.form.uploadProgress.setValue(30)
        #     QtGui.QApplication.processEvents()
        #     r = self.po.taackIntranetSession.post(
        #         url=self.po.url + 'plm/uploadProto',
        #         files={'proto.bin': f2},
        #         data={"ajax": "true"}
        #     )
        # finally:
        #     f2.close()
        #     self.form.uploadProgress.setValue(60)
        #     QtGui.QApplication.processEvents()
        #
        # if r.json()["success"]:
        #     self.form.uploadProgress.setValue(100)
        #     self.form.uploadProgress.setFormat("Upload complete")
        #     QtGui.QApplication.processEvents()

        self.avoidLoop = set()
        self.shaOneMap = dict()

        b = self.create_bucket_protobuf()

        zip_filename = "tmp-fc-" + str(round(time.time() * 1000)) + ".zip"
        with zipfile.ZipFile(file=zip_filename, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
                             ) as zip_archive:

            zip_archive.writestr("proto.bin", b.SerializeToString())
            progress = 10
            self.form.uploadProgress.setValue(progress)
            inc = math.floor(len(self.shaOneMap.items()) / 90)
            for eShaOne, filename in self.shaOneMap.items():
                progress += inc
                self.form.uploadProgress.setValue(progress)
                zip_archive.write(filename, eShaOne)

        data = {"ajax": 'true'}
        f2 = open(zip_filename, 'rb')
        r = self.po.taackIntranetSession.post(url=self.po.url + 'plm/uploadProto', files={'proto.bin': f2}, data=data)
        f2.close()

        try:
            if r.json()["success"]:

                # The upload succeeded.
                # Record the exact files that were included in this upload
                # as the new modification baseline.

                documents = self.get_upload_documents()

                self._record_modified_baseline(
                    FreeCAD.ActiveDocument,
                    documents
                )

                self.form.uploadProgress.setValue(100)
                self.form.uploadButton.setEnabled(True)
                self.form.uploadButton.setText("Upload")

                return True
            else:
                print(r.json()["message"])
                self.form.connectButton.setStyleSheet('QPushButton {color: red;}')
                self.form.connectButton.setEnabled(True)
                self.form.connectButton.setText('DisConnected')
                self.form.uploadButton.setEnabled(True)
                self.form.uploadButton.setText("Upload")
        except Exception:
            self.form.connectButton.setEnabled(True)

        return False


    def confirm_large_upload(self, documents):
        total_bytes = 0

        for doc in documents:
            filename = getattr(doc, "FileName", "")
            if not filename:
                continue

            try:
                total_bytes += os.path.getsize(filename)
            except OSError:
                pass

        total_mb = total_bytes / (1024 * 1024)

        # Warn about uploads large uploads. This is set to 500mb
        if total_mb <= 500:
            return True

        message = (
            "This upload contains approximately "
            f"{total_mb:.2f} MB of FreeCAD files.\n\n"
            "This may require a significant amount of RAM to upload\n\n"
            "Do you want to continue?"
        )

        result = QtGui.QMessageBox.warning(self.form, "Large Upload", message, QtGui.QMessageBox.Yes | QtGui.QMessageBox.No, QtGui.QMessageBox.No)

        return result == QtGui.QMessageBox.Yes



    ### FreeCAD <-> protobuf conversion tools

    def create_bucket_protobuf(self):

        print("createBucketProtobuf")
        self.shaOneMap = dict()
        parts = self.get_upload_documents()
        bucket = PlmBuf.Bucket()

        for part in parts:
            self.create_doc_protobuf(part, bucket)

        return bucket

    def create_doc_protobuf(self, obj, bucket):

        if obj is None:
            return None

        # A document must have FileName.
        if not hasattr(obj, "FileName"):
            raise ValueError(
                "Upload error: object '" + getattr(obj, "Label", "<unknown>") + "' is not a FreeCAD Document. Type: " +
                getattr(obj, "TypeId", "<unknown>"))

        print("createDocProtobuf: " +obj.Name + " / " + obj.Label)

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
            bucket.plmFiles[plm_file.name].CopyFrom(plm_file)
            self.shaOneMap[plm_file.sha1hex] = obj.FileName

        except:
            raise ValueError("Select the file you waant to upload in the tree")

        return obj.Name

    def _get_modified_baseline(self):
        """
        Persistent baseline of the last successfully uploaded file timestamps.

        Key:
            assembly filename

        Value:
            {
                part_filename: mtime_ns
            }
        """
        param = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/TaackPLM")
        raw = param.GetString("ModifiedFileBaseline", "{}")
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def _save_modified_baseline(self, baseline):
        param = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/TaackPLM")
        param.SetString("ModifiedFileBaseline", json.dumps(baseline))

    def _get_assembly_baseline(self, assembly_doc):
        baseline = self._get_modified_baseline()
        assembly_file = getattr(assembly_doc, "FileName", "")
        if not assembly_file:
            return {}

        return baseline.get(os.path.abspath(assembly_file), {})

    def _get_file_mtime_ns(self, filename):
        try:
            return os.stat(filename).st_mtime_ns
        except (OSError, TypeError):
            return None

    def _document_was_modified(self, doc, assembly_doc):
        """
        Returns True when the saved FCStd file is newer than the
        timestamp recorded after the last successful PLM upload.
        """
        filename = getattr(doc, "FileName", "")
        if not filename:
            return False
        filename = os.path.abspath(filename)
        current_mtime = self._get_file_mtime_ns(filename)
        if current_mtime is None:
            return False

        baseline = self._get_assembly_baseline(assembly_doc)
        previous_mtime = baseline.get(filename)

        # No baseline means this document has never been successfully
        # uploaded as part of this assembly.
        #
        # Treat it as modified so it is not silently skipped.
        if previous_mtime is None:
            return True

        return current_mtime > int(previous_mtime)

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
