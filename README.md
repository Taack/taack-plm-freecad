# WebTools workbench for FreeCAD

This workbench contains tools to interact with different web services. Current webservices include:

<img src="https://www.freecadweb.org/wiki/images/e/e3/Arch_Git.png" width="20" height="20" alt="git logo"> [Git](https://www.freecadweb.org/wiki/Arch_Git): Manages the current document with [Git](https://en.wikipedia.org/wiki/Git).  

<img src="https://www.freecadweb.org/wiki/images/3/30/Arch_BimServer.png" width="20" height="20" alt="bimserver logo">  [BimServer](https://www.freecadweb.org/wiki/Arch_BimServer): Connects and interacts with a [BIM server](http://www.bimserver.org) instance.  

<img src="https://www.freecadweb.org/wiki/images/f/f8/Web_Sketchfab.png" width="20" height="20" alt="sketchfab logo"> [Sketchfab](https://www.freecadweb.org/wiki/Web_Sketchfab): Connects and uploads a model to a [Sketchfab](http://www.sketchfab.com) account. 

## Installation

This Workbench is part of the [FreeCAD addons](https://github.com/FreeCAD/FreeCAD-addons) collection and can be simply installed from the Addons manager.

Alternatively, it can also be installed manually by downloading and copying its contents in a folder inside your FreeCAD Mod directory (see the [addons page](https://github.com/yorikvanhavre/WebTools.git) for detailed instructions)


https://forum.freecadweb.org/viewtopic.php?t=52158&start=10
[o.Label for o in App.ActiveDocument.Objects if (hasattr(o, 'Shape') and o.Shape.Solids and not o.isDerivedFrom('PartDesign::Feature'))]

Debugging
https://forum.freecadweb.org/viewtopic.php?f=10&t=35383

https://forum.freecadweb.org/viewtopic.php?t=25157

import sys
sys.path.append('/home/auo/git/taack-plm-freecad')
import Intranet
import importlib
importlib.reload(Intranet)
Intranet.login(
Intranet.createBucketProtobuf()
