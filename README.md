# Taack PLM workbench for FreeCAD

This workbench contains tools to interact with Taack Plm Intranet server app you can find under the https://github.com/Taack/plm  

## Installation

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

![enter credential](https://github.com/Taack/taack-plm-freecad/blob/main/screenshot-plm-credential.png)

Clicking on **Connect** Button.

If the **Connect** Button turns disabled, you are connected to your Intranet Server.

### Upload a model with its Links

Once you are connected

* Ensure a file is selected (if not already done, save it before)
* click on the **Taack** icon
* click on the **Accept** Button

All linked files will be uploaded. There are 2 situations from here, for each file:
* Either the file Uid does not exists on the server
  * The model will be uploaded as a new one
* Either the file Uid does exists on the server
  * The existing model will be updated

### Download a previous version

From your Intranet, click on PLM icon, then you will see a list of model.

![Filtering model](https://github.com/Taack/taack-plm-freecad/blob/main/sc-filter.png)

Search using filters the one you are interested in, click on the **eye** icon.

![Download model](https://github.com/Taack/taack-plm-freecad/blob/main/sc-open.png)

Here you can either:

* Download the latest version
* Add comment OR change model status
* Download a previous version

![Access History](https://github.com/Taack/taack-plm-freecad/blob/main/sc-prev.png)


For more complex model, you can access linked files:

![See linked data](https://github.com/Taack/taack-plm-freecad/blob/main/sc-linked.png)

Or links pointing to this model:

![See parent deps](https://github.com/Taack/taack-plm-freecad/blob/main/sc-pointing.png)

That's it !

Next version should add download latest version directly from FreeCAD.


