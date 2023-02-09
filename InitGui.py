# FreeCAD init script of the TaackPLM module  

class TaackPLMWorkbench (Workbench):

    "TaackPLM workbench object"

    def __init__(self):
        self.__class__.Icon = FreeCAD.getUserAppDataDir() + "Mod/taack-plm-freecad/icons/taackPLM.xpm"
        self.__class__.MenuText = "TaackPLM"
        self.__class__.ToolTip = "TaackPLM workbench"

    def Initialize(self):
        import Intranet
        cmds = ["TaackPLM_Intranet"]
        self.appendToolbar("Taack PLM",cmds)
        self.appendMenu("Taack PLM",cmds)

    def GetClassName(self):
        return "Gui::PythonWorkbench"

Gui.addWorkbench(TaackPLMWorkbench())
