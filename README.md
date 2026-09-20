# Taack PLM workbench for FreeCAD

This workbench contains tools to interact with Taack Plm Intranet server app you can find under the https://github.com/Taack/plm

## Installation

Workbench dependencies should be managed directly with FreeCAD, install both protobuf and requests Python modules.

This Workbench is part of the [FreeCAD addons](https://github.com/FreeCAD/FreeCAD-addons) collection and can be simply installed from the Addons manager.

To install the server, follow instructions under [Taack PLM page](https://taack.org/en/app/Plm).

Forum entry:
https://forum.freecad.org/viewtopic.php?t=75937

## Usage

### Connect to the Server

Under Freecad:

* Select the Taack PLM Workbench
* Select a file you need to upload (if not already done, save it before)
* Click on the **Taack** icon

The first time, you will be prompted for entering the server URL, along with your user credentials:

![enter credential](https://raw.githubusercontent.com/Taack/taack-plm-freecad/refs/heads/main/freecad-taack-plm-gui.webp)

1. Workbench Icon
2. Main Command
3. Server URL Input
4. User Login Input
5. User Password Input
6. Connect Button
7. Duplicate History Options
8. Duplicate History Button

Clicking on **Connect** Button.

If the **Connect** Button turns disabled, you are connected to your Intranet Server.

### Duplicate Options

#### Duplicate Active Part

Only the main part history will be duplicated. Dependencies will have only one history. Both, modifications on primary part and duplicated part will **modify dependency history**.

#### Duplicate All Parts

Main Parts and its dependencies will have a new history. Modifications on primary part and duplicated part will be independent

#### Duplicate Modified Parts

Main Parts and modified dependencies will have a new history.

The part duplicated appear in details view:

![Duplicated models](https://raw.githubusercontent.com/Taack/taack-plm-freecad/refs/heads/main/freecad-taack-plm-server-part-details-duplicated.webp)



### Upload a model and Links to other features from other files

Once you are connected

* Ensure a file is selected (if not already done, save it before uploading)
* click on the **Taack** icon
* click on the **Ok** Button

All linked files will be uploaded. There are 2 situations from here, for each file:
* Either the file Uid does not exist on the server
  * The model will be uploaded as a new one
* Either the file Uid does exist on the server
  * The existing model will be updated

### Download a previous version

From your Intranet, click on PLM icon, then you will see a list of model.

![Filtering model](https://raw.githubusercontent.com/Taack/taack-plm-freecad/refs/heads/main/freecad-taack-plm-server-part-list.webp)

1. Help
2. Filter
3. Model Table
4. Main Menu 
   1. **Parts**: Either in CREATED or FREE Status
   2. **Top Assemblies**: Flat table of Files with Links, in CREATED or FREE Status
   3. **Locked Parts**: Either OBSOLETED or LOCKED Status

Search using filters the one you are interested in, then click on the **eye** icon.

![Download model](https://raw.githubusercontent.com/Taack/taack-plm-freecad/refs/heads/main/freecad-taack-plm-server-part-details.webp)

1. Selected Model preview (When the model was uploaded)
2. Hierarchical Features Linked from other files with versions
3. Part Data
4. Download Last Part version, with its dependencies, in a zip file
5. 3D Viewer
6. Edit Access Right / Status
7. Edit Tags (tags are managed in Attachment app)

Here you can either:

* Download the latest version
* Add comment OR change model status
* Download a previous version
* Attach a file (in Attachments tab)

![Access History](https://raw.githubusercontent.com/Taack/taack-plm-freecad/refs/heads/main/freecad-taack-plm-server-part-details-history.webp)

1. Differences between versions
2. Current Status
3. Status Changes date
4. Preview a precise version

For more complex model, you can access linked files or links pointing to this model via Hierarchy tab.

That's it !


