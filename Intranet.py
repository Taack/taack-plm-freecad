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

        # Restore saved workspace directory
        workspace = self.po.settings.value("workspace", "")
        if workspace:
            self.form.workspaceEdit.setText(workspace)
            self.set_freecad_working_directory(workspace)

        # Save workspace whenever the user changes it
        QtCore.QObject.connect(
            self.form.workspaceEdit,
            QtCore.SIGNAL("textChanged(QString)"),
            self.save_workspace
        )

        # Select the Login tab when we are not connected.
        if not self.po.connected:
            self.form.tabWidget.setCurrentWidget(
                self.form.loginTab
            )
        self.form.userEdit.insert(po.user)
        self.form.passEdit.insert(po.passwd)
        self.form.urlEdit.insert(po.url)
        QtCore.QObject.connect(self.form.connectButton, QtCore.SIGNAL("pressed()"), self.login_intranet)
        QtCore.QObject.connect(self.form.disconnectButton, QtCore.SIGNAL("pressed()"), self.logout_intranet)
        QtCore.QObject.connect(self.form.forkButton, QtCore.SIGNAL("pressed()"), self.fork)

        QtCore.QObject.connect(
            self.form.uploadButton,
            QtCore.SIGNAL("pressed()"),
            self.upload_current_active_doc
        )
        QtCore.QObject.connect(
            self.form.browseByTagButton,
            QtCore.SIGNAL("pressed()"),
            self.browse_by_tag
        )
        QtCore.QObject.connect(
            self.form.browseTree,
            QtCore.SIGNAL("itemClicked(QTreeWidgetItem*, int)"),
            self.browse_tag_selected
        )
        QtCore.QObject.connect(
            self.form.addToWorkspaceButton,
            QtCore.SIGNAL("pressed()"),
            self.add_to_workspace
        )

        QtCore.QObject.connect(
            self.form.openInFreeCADButton,
            QtCore.SIGNAL("pressed()"),
            self.open_in_freecad
        )

        QtCore.QObject.connect(
            self.form.addSearchPartButton,
            QtCore.SIGNAL("pressed()"),
            self.add_to_workspace
        )

        QtCore.QObject.connect(
            self.form.openSearchPartButton,
            QtCore.SIGNAL("pressed()"),
            self.open_in_freecad
        )
        QtCore.QObject.connect(
            self.form.searchPartButton,
            QtCore.SIGNAL("pressed()"),
            self.search_parts
        )
        QtCore.QObject.connect(
            self.form.partSearchEdit,
            QtCore.SIGNAL("returnPressed()"),
            self.search_parts
        )
        QtCore.QObject.connect(
            self.form.workspaceBrowseButton,
            QtCore.SIGNAL("pressed()"),
            self.browse_workspace
        )
        QtCore.QObject.connect(
            self.form.tabWidget,
            QtCore.SIGNAL("currentChanged(int)"),
            self.tab_changed
        )
        QtCore.QObject.connect(
            self.form.addToAssemblyButton,
            QtCore.SIGNAL("pressed()"),
            self.add_to_assembly
        )
        QtCore.QObject.connect(
            self.form.addSearchPartToAssemblyButton,
            QtCore.SIGNAL("pressed()"),
            self.add_to_assembly
        )
        self.form.uploadProgress.setValue(0)
        self.form.uploadProgress.setVisible(True)
        self.browseShowingParts = False
        self.update_add_to_assembly_button()

        if self.po.connected:
            self.form.connectButton.setStyleSheet('QPushButton {color: green;}')
            self.form.connectButton.setEnabled(False)
            self.form.connectButton.setText('Connected')

    def tab_changed(self, index):
        """Run actions when a tab is selected."""
        if self.form.tabWidget.currentWidget() == self.form.loginTab:
            self.get_server_info()
        elif self.form.tabWidget.currentWidget() == self.form.browseTab:
            self.browse_by_tag()

    def set_freecad_working_directory(self, workspace):
        if not workspace:
            return

        param = FreeCAD.ParamGet(
            "User parameter:BaseApp/Preferences/General"
        )

        param.SetString("WorkingDir", workspace)
        param.SetString("FileOpenSavePath", workspace)

    def update_add_to_assembly_button(self):
        """
        Enable Add to Assembly only when the active document
        contains a FreeCAD 1.1 Assembly.
        """

        enabled = self.is_active_assembly()

        if hasattr(self.form, "addToAssemblyButton"):
            self.form.addToAssemblyButton.setEnabled(enabled)

            if enabled:
                self.form.addToAssemblyButton.setToolTip(
                    "Add the selected PLM part to the active Assembly."
                )
            else:
                self.form.addToAssemblyButton.setToolTip(
                    "Available only when a FreeCAD 1.1 Assembly is active."
                )

        if hasattr(self.form, "addSearchPartToAssemblyButton"):
            self.form.addSearchPartToAssemblyButton.setEnabled(enabled)

            if enabled:
                self.form.addSearchPartToAssemblyButton.setToolTip(
                    "Add the selected PLM part to the active Assembly."
                )
            else:
                self.form.addSearchPartToAssemblyButton.setToolTip(
                    "Available only when a FreeCAD 1.1 Assembly is active."
                )

    def get_active_assembly(self):
        """
        Return the active FreeCAD 1.1 Assembly::AssemblyObject.

        Returns None when the active document is not a FreeCAD Assembly.
        """
        doc = FreeCAD.ActiveDocument

        if doc is None:
            return None

        for obj in doc.Objects:
            try:
                if obj.isDerivedFrom("Assembly::AssemblyObject"):
                    return obj
            except Exception:
                pass

        return None

    def add_to_assembly(self):

        assembly_doc = FreeCAD.ActiveDocument
        assembly = self.get_active_assembly()

        if assembly_doc is None or assembly is None:
            FreeCAD.Console.PrintWarning(
                "Add to Assembly cancelled: "
                "the active document is not a FreeCAD 1.1 Assembly.\n"
            )
            return

        try:
            # Remember the assembly before downloading/opening anything.
            assembly_doc_name = assembly_doc.Name

            # Download the selected PLM part using the existing code.
            freecad_file = self.add_to_workspace()

            if not freecad_file:
                return

            if not os.path.isfile(freecad_file):
                raise ValueError(
                    "The downloaded FreeCAD file does not exist:\n"
                    + freecad_file
                )

            # Open the downloaded part.
            part_doc = FreeCAD.openDocument(freecad_file)

            if part_doc is None:
                raise ValueError(
                    "Could not open the downloaded FreeCAD part."
                )

            # Find a suitable object to use as the component.
            part_object = None

            # Prefer an Assembly, Part, or Body as the component root.
            for obj in part_doc.Objects:
                try:
                    if obj.isDerivedFrom("Assembly::AssemblyObject"):
                        part_object = obj
                        break

                    if obj.isDerivedFrom("App::Part"):
                        part_object = obj
                        break

                    if obj.isDerivedFrom("PartDesign::Body"):
                        part_object = obj
                        break

                except Exception:
                    pass

            # If none of the preferred containers exists, look for a
            # normal geometric object.
            if part_object is None:
                for obj in part_doc.Objects:
                    try:
                        if obj.isDerivedFrom("Part::Feature"):
                            part_object = obj
                            break
                    except Exception:
                        pass

            if part_object is None:
                raise ValueError(
                    "Could not find a suitable component in the downloaded part."
                )

            # Restore the assembly document as the active document.
            FreeCAD.setActiveDocument(assembly_doc_name)

            assembly_doc = FreeCAD.getDocument(assembly_doc_name)

            if assembly_doc is None:
                raise ValueError(
                    "Could not restore the active Assembly document."
                )

            # Create the Assembly component link.
            link_name = "PLM_" + part_object.Name

            link = assembly_doc.addObject(
                "App::Link",
                link_name
            )

            link.Label = part_object.Label
            link.setLink(part_object)

            # Assembly::AssemblyObject derives from App::Part,
            # so the link can be added directly to the assembly.
            assembly.addObject(link)

            assembly_doc.recompute()

            FreeCAD.Console.PrintMessage(
                "Added PLM part to Assembly: "
                + part_object.Label
                + "\n"
            )

            if self.form.tabWidget.currentWidget() == self.form.searchPartTab:
                self.form.searchPartMessageLabel.setText(
                    "Part added to Assembly."
                )
            else:
                self.form.browseMessageLabel.setText(
                    "Part added to Assembly."
                )

        except Exception as e:

            message = "Error adding part to Assembly: " + str(e)

            if self.form.tabWidget.currentWidget() == self.form.searchPartTab:
                self.form.searchPartMessageLabel.setText(message)
            else:
                self.form.browseMessageLabel.setText(message)

            FreeCAD.Console.PrintError(message + "\n")

    def is_active_assembly(self):
        """
        Return True only when the active document contains
        a FreeCAD 1.1 Assembly workbench assembly.
        """
        return self.get_active_assembly() is not None

    def save_workspace(self, workspace):
        self.po.settings.setValue("workspace", workspace)
        self.po.settings.sync()
        # Make FreeCAD use the PLM workspace as its default directory
        self.set_freecad_working_directory(workspace)

    def browse_workspace(self):
        current_workspace = self.form.workspaceEdit.text().strip()

        if current_workspace and os.path.isdir(current_workspace):
            start_directory = current_workspace
        else:
            start_directory = os.path.expanduser("~")

        workspace = QtGui.QFileDialog.getExistingDirectory(
            self.form,
            "Select Workspace Directory",
            start_directory,
            QtGui.QFileDialog.ShowDirsOnly
        )

        if workspace:
            workspace = os.path.abspath(workspace)

            self.form.workspaceEdit.setText(workspace)

            self.po.settings.setValue(
                "workspace",
                workspace
            )
            self.po.settings.sync()
            self.form.workspaceEdit.setText(workspace)
            self.save_workspace(workspace)

            FreeCAD.Console.PrintMessage(
                "Workspace directory: "
                + workspace
                + "\n"
            )

    def compute_file_shaOne(self, filePath):
        sha1 = hashlib.sha1()
        with open(filePath, 'rb') as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                sha1.update(data)

        return sha1.hexdigest()

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

    def save_preferences(self):
        self.po.user = self.form.userEdit.text()
        self.po.settings.setValue("username", self.po.user)
        self.po.url = self.form.urlEdit.text()
        self.po.settings.setValue("url", self.po.url)

    def accept(self):
        print("Closing Taack PLM panel")
        FreeCADGui.Control.closeDialog()


    def add_to_workspace(self):
        try:
            current_widget = self.form.tabWidget.currentWidget()

            # ---------------------------------------------------------
            # Get the selected part depending on which tab is active
            # ---------------------------------------------------------
            if current_widget == self.form.searchPartTab:
                # Search Part uses QListWidgetItem.
                item = self.form.partSearchList.currentItem()

                if item is None:
                    raise ValueError("Select a part to add to the workspace.")

                # QListWidgetItem.data() takes only the role.
                part_id = item.data(QtCore.Qt.UserRole)
                part_data = item.data(QtCore.Qt.UserRole + 1)

                message_label = self.form.searchPartMessageLabel

            else:
                # Browse by Tag uses QTreeWidgetItem.
                selected_items = self.form.browseTree.selectedItems()

                if not selected_items:
                    raise ValueError("Select a part to add to the workspace.")

                item = selected_items[0]

                if not self.browseShowingParts:
                    raise ValueError("Select a part, not a tag.")

                # QTreeWidgetItem.data() requires:
                #   data(column, role)
                part_id = item.data(0, QtCore.Qt.UserRole)
                part_data = item.data(0, QtCore.Qt.UserRole + 1)

                message_label = self.form.browseMessageLabel

            # ---------------------------------------------------------
            # Validate the selected part
            # ---------------------------------------------------------
            if part_id is None:
                raise ValueError("The selected part does not have a valid PLM ID.")

            if not self.po.connected:
                raise ValueError("Not connected to the PLM server.")

            # ---------------------------------------------------------
            # Get workspace
            # ---------------------------------------------------------
            workspace = self.po.settings.value("workspace", "")

            if not workspace:
                raise ValueError("Please select a working directory first.")

            workspace = os.path.abspath(os.path.expanduser(workspace))

            if not os.path.isdir(workspace):
                os.makedirs(workspace, exist_ok=True)

            # ---------------------------------------------------------
            # Try to determine the original FreeCAD filename
            # ---------------------------------------------------------
            expected_name = None

            if isinstance(part_data, dict):
                expected_name = (
                        part_data.get("originalName") or
                        part_data.get("name") or
                        part_data.get("label")
                )

            # ---------------------------------------------------------
            # If the part is already in the workspace, don't download it
            # ---------------------------------------------------------
            if expected_name:
                expected_name = os.path.basename(str(expected_name))

                if not expected_name.lower().endswith(".fcstd"):
                    expected_name += ".FCStd"

                existing_file = os.path.join(
                    workspace,
                    expected_name
                )

                if os.path.isfile(existing_file):
                    message_label.setText(
                        "Part is already in the workspace."
                    )

                    FreeCAD.Console.PrintMessage(
                        "Part already exists in workspace: "
                        + existing_file
                        + "\n"
                    )

                    return existing_file

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

            FreeCAD.Console.PrintMessage(
                "Downloaded PLM part to: "
                + zip_path
                + "\n"
            )

            # ---------------------------------------------------------
            # Find the FreeCAD file inside the ZIP
            # ---------------------------------------------------------
            message_label.setText("Extracting part...")

            freecad_file = None

            with zipfile.ZipFile(zip_path, "r") as zip_file:

                members = zip_file.namelist()

                fcstd_members = [
                    member
                    for member in members
                    if member.lower().endswith(".fcstd")
                ]

                if len(fcstd_members) == 0:
                    raise ValueError(
                        "No FreeCAD .FCStd file was found in the downloaded part."
                    )

                if len(fcstd_members) > 1:
                    FreeCAD.Console.PrintWarning(
                        "Multiple FCStd files found in ZIP. "
                        "Using the first one.\n"
                    )

                fcstd_member = fcstd_members[0]

                FreeCAD.Console.PrintMessage(
                    "FCStd file in ZIP: "
                    + fcstd_member
                    + "\n"
                )

                # Extract the ZIP into the workspace.
                zip_file.extractall(workspace)

                # ZIP entries can begin with '/'.
                # Remove the leading slash before joining with workspace.
                relative_fcstd = fcstd_member.lstrip("/\\")

                freecad_file = os.path.abspath(
                    os.path.join(
                        workspace,
                        relative_fcstd
                    )
                )

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

            FreeCAD.Console.PrintError(
                message + "\n"
            )

            return None

        except Exception as e:

            message = "Error adding part to workspace: " + str(e)

            try:
                message_label.setText(message)
            except Exception:
                pass

            FreeCAD.Console.PrintError(
                message + "\n"
            )

            return None

    def open_in_freecad(self):

        try:

            # Search Part tab
            if self.form.tabWidget.currentWidget() == self.form.searchPartTab:

                if self.form.partSearchList.currentItem() is None:
                    self.form.searchPartMessageLabel.setText(
                        "Please select a part first."
                    )
                    return

            # Browse by Tags tab
            else:

                selected_items = self.form.browseTree.selectedItems()

                if not selected_items:
                    self.form.browseMessageLabel.setText(
                        "Please select a part first."
                    )
                    return

                if not self.browseShowingParts:
                    self.form.browseMessageLabel.setText(
                        "Please select a part, not a tag."
                    )
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
        """
        Search for PLM parts by originalName and display
        the results in the Search Part list.
        """

        self.form.partSearchList.clear()
        self.form.searchPartMessageLabel.clear()

        search_text = self.form.partSearchEdit.text().strip()

        if not search_text:
            self.form.searchPartMessageLabel.setText(
                "Please enter a part name to search."
            )
            return

        if not self.po.connected:
            self.form.searchPartMessageLabel.setText(
                "Not connected to the PLM server."
            )
            return

        try:
            base_url = self.form.urlEdit.text().strip()

            if not base_url.endswith("/"):
                base_url += "/"

            url = base_url + "plmJson/searchParts"

            response = self.po.taackIntranetSession.get(
                url,
                params={"originalName": search_text},
                timeout=30
            )

            response.raise_for_status()

            parts = response.json()

            if not isinstance(parts, list):
                raise ValueError(
                    "The server returned an invalid parts list."
                )

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

                item = QtGui.QListWidgetItem(
                    str(part_name)
                )

                # Store the PLM part ID in the list item.
                item.setData(
                    QtCore.Qt.UserRole,
                    part_id
                )

                # Keep the complete server result available.
                item.setData(
                    QtCore.Qt.UserRole + 1,
                    part
                )

                self.form.partSearchList.addItem(item)

            if self.form.partSearchList.count() == 0:
                self.form.searchPartMessageLabel.setText(
                    "No parts found."
                )
            else:
                self.form.searchPartMessageLabel.setText(
                    str(self.form.partSearchList.count()) +
                    " part(s) found."
                )

        except requests.exceptions.RequestException as e:

            self.form.searchPartMessageLabel.setText(
                "Unable to search for parts: " + str(e)
            )

            FreeCAD.Console.PrintWarning(
                "Unable to search for parts: " +
                str(e) +
                "\n"
            )

        except ValueError as e:

            self.form.searchPartMessageLabel.setText(
                "Invalid response from server: " +
                str(e)
            )

        except Exception as e:

            self.form.searchPartMessageLabel.setText(
                "Error searching for parts: " +
                str(e)
            )

            FreeCAD.Console.PrintWarning(
                "Error searching for parts: " +
                str(e) +
                "\n"
            )

    def browse_tag_selected(self, item, column):

        self.form.browseMessageLabel.clear()
        # If the tree is currently showing parts, do not treat
        # the selected part as a tag.

        if self.browseShowingParts:
            return

        try:
            tag_id = item.data(0, QtCore.Qt.UserRole)

            if tag_id is None:
                return

            if not self.po.connected:
                QtGui.QMessageBox.warning(
                    self.form,
                    "Not Connected",
                    "Not connected to the server."
                )
                return

            base_url = self.po.url.rstrip("/") + "/"
            url = base_url + "plmJson/partsByTag"

            response = self.po.taackIntranetSession.get(
                url,
                params={"tagId": tag_id},
                timeout=10
            )

            response.raise_for_status()

            parts = response.json()

            if not isinstance(parts, list):
                raise ValueError("Server returned an invalid parts list.")

            # We are now displaying parts instead of tags.
            self.browseShowingParts = True

            # Clear the tag list
            self.form.browseTree.clear()

            # Add parts
            for part in parts:
                if not isinstance(part, dict):
                    continue

                part_name = (
                        part.get("name")
                        or part.get("originalName")
                        or part.get("label")
                        or str(part.get("id", ""))
                )

                tree_item = QtGui.QTreeWidgetItem(
                    [str(part_name)]
                )

                if part.get("id") is not None:
                    tree_item.setData(
                        0,
                        QtCore.Qt.UserRole,
                        part.get("id")
                    )

                self.form.browseTree.addTopLevelItem(tree_item)

        except requests.RequestException as e:
            QtGui.QMessageBox.warning(
                self.form,
                "Browse Error",
                "Could not retrieve parts from the server:\n" + str(e)
            )

        except ValueError as e:
            QtGui.QMessageBox.warning(
                self.form,
                "Browse Error",
                str(e)
            )

        except Exception as e:
            QtGui.QMessageBox.warning(
                self.form,
                "Browse Error",
                "An error occurred while retrieving parts:\n" + str(e)
            )

    def browse_by_tag(self):
        """
        Load all PLM tags from /plmJson/tags and display them
        in the Browse tree using the parent/name hierarchy.
        """

        # Clear the existing tree

        self.browseShowingParts = False

        self.form.browseTree.clear()
        self.form.browseMessageLabel.clear()
        if not self.po.connected:
            FreeCAD.Console.PrintWarning(
                translate("TaackPlm", "Not connected to the PLM server.") + "\n"
            )
            self.get_server_info()
            return

        try:
            # Make sure the URL ends with /
            base_url = self.form.urlEdit.text().strip()

            if not base_url.endswith("/"):
                base_url += "/"

            url = base_url + "plmJson/tags"

            print("Loading PLM tags from: " + url)

            response = self.po.taackIntranetSession.get(
                url=url,
                timeout=10
            )

            response.raise_for_status()

            tags = response.json()

            print("Received PLM tags:")
            print(tags)

            if not isinstance(tags, list):
                FreeCAD.Console.PrintWarning(
                    translate(
                        "TaackPlm",
                        "Invalid tag response from server."
                    ) + "\n"
                )
                return

            # ---------------------------------------------------------
            # First pass:
            # Create a tree item for every tag.
            #
            # We use the tag NAME as the key because the JSON parent
            # field contains the parent's name.
            # ---------------------------------------------------------

            tag_items = {}

            for tag in tags:

                if not isinstance(tag, dict):
                    continue

                tag_id = tag.get("id")
                tag_name = tag.get("name")

                if tag_name is None:
                    continue

                tag_name = str(tag_name)

                item = QtGui.QTreeWidgetItem()
                item.setText(0, tag_name)

                # Store the PLM tag ID in the tree item.
                item.setData(
                    0,
                    QtCore.Qt.UserRole,
                    tag_id
                )

                tag_items[tag_name] = item

            # ---------------------------------------------------------
            # Second pass:
            # Connect each tag to its parent.
            #
            # Example:
            #
            # {
            #     "name": "BC250_case_3",
            #     "parent": "Project"
            # }
            #
            # becomes:
            #
            # Project
            #   └── BC250_case_3
            # ---------------------------------------------------------

            for tag in tags:

                if not isinstance(tag, dict):
                    continue

                tag_name = tag.get("name")

                if tag_name is None:
                    continue

                tag_name = str(tag_name)

                item = tag_items.get(tag_name)

                if item is None:
                    continue

                parent_name = tag.get("parent")

                # No parent means this is a top-level tag.
                if parent_name is None or str(parent_name).strip() == "":
                    self.form.browseTree.addTopLevelItem(item)
                    continue

                parent_name = str(parent_name)

                # Find the parent by name.
                parent_item = tag_items.get(parent_name)

                if parent_item is not None:
                    parent_item.addChild(item)
                else:
                    # Parent does not exist in the response.
                    # Keep the tag visible as a top-level item.
                    print(
                        "Parent tag not found: " +
                        parent_name +
                        " for tag: " +
                        tag_name
                    )

                    self.form.browseTree.addTopLevelItem(item)

            # Expand the complete tree.
            self.form.browseTree.expandAll()

            print(
                "Loaded " +
                str(len(tag_items)) +
                " PLM tags."
            )

        except requests.exceptions.RequestException as e:

            FreeCAD.Console.PrintWarning(
                translate(
                    "TaackPlm",
                    "Unable to load PLM tags: "
                ) + str(e) + "\n"
            )

        except ValueError as e:

            FreeCAD.Console.PrintWarning(
                translate(
                    "TaackPlm",
                    "Invalid JSON returned by PLM tag endpoint: "
                ) + str(e) + "\n"
            )

        except Exception as e:

            FreeCAD.Console.PrintWarning(
                translate(
                    "TaackPlm",
                    "Error loading PLM tags: "
                ) + str(e) + "\n"
            )

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
                self.get_server_info()
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
                self.get_server_info()
        except:
            FreeCAD.Console.PrintWarning(translate("TaackPlm", "Can't connect to the intranet.") + "\n")

    def upload_current_active_doc(self):

        self.form.uploadProgress.setValue(0)
        self.form.uploadButton.setEnabled(False)
        self.form.uploadButton.setText("Uploading...")

        if not self.po.connected:
            FreeCAD.Console.PrintWarning(translate("TaackPlm", "Not connected.") + "\n")
            self.get_server_info()
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
                            self.get_server_info()
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

    def get_server_info(self):
        try:
            url = self.po.url + 'plmJson/serverInfo'

            response = self.po.taackIntranetSession.get(url, timeout=10)
            response.raise_for_status()

            server_info = response.json()

            server_version = server_info.get("serverVersion", "Unknown")
            protocol_version = server_info.get("messagingProtocolVersion", "Unknown")
            maximum_upload_size = server_info.get("maximumFileUploadSize")

            self.form.serverVersionValue.setText(str(server_version))
            self.form.messagingProtocolVersionValue.setText(str(protocol_version))

            if maximum_upload_size is not None:
                # Convert bytes to MB
                size_mb = maximum_upload_size / (1024 * 1024)

                if size_mb >= 1024:
                    size_text = f"{size_mb / 1024:.1f} GB"
                else:
                    size_text = f"{size_mb:.0f} MB"

                self.form.maximumFileUploadSizeValue.setText(size_text)
            else:
                self.form.maximumFileUploadSizeValue.setText("Unknown")

        except Exception as e:
            print("Unable to get server information:", e)

            self.form.serverVersionValue.setText("Unknown")
            self.form.messagingProtocolVersionValue.setText("Unknown")
            self.form.maximumFileUploadSizeValue.setText("Unknown")


if FreeCAD.GuiUp:
    FreeCADGui.addCommand('TaackPLM_Intranet', CommandTaackPlm())
