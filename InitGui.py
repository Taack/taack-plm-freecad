# FreeCAD init script of the TaackPLM module  

class TaackPLMWorkbench (Workbench):

    "TaackPLM workbench object"

    def __init__(self):
        self.__class__.Icon = FreeCAD.getUserAppDataDir() + "Mod/taack-plm-freecad/icons/taackPLM.xpm"
        self.__class__.MenuText = "TaackPLM"
        self.__class__.ToolTip = "TaackPLM workbench"

    def Initialize(self):
        import Intranet
        self.cmds = ["TaackPLM_Intranet"]
        self.appendToolbar(self.__class__.MenuText, self.cmds)
        self.appendMenu(self.__class__.MenuText, self.cmds)

    def Activated(self):
        '''This function is executed when the workbench is activated'''
        return

    def Deactivated(self):
        '''This function is executed when the workbench is deactivated'''
        return

    def ContextMenu(self, recipient):
        '''This is executed whenever the user right-clicks on screen'''
        # 'recipient' will be either 'view' or 'tree'
        self.appendContextMenu(self.__class__.MenuText, self.list) # add commands to the context menu

    def GetClassName(self):
        return "Gui::PythonWorkbench"

Gui.addWorkbench(TaackPLMWorkbench())
