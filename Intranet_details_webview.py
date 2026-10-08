
class TaackPlmDetailsWebview(object):
    def __init__(self, po):
        self.form = FreeCADGui.PySideUic.loadUi(os.path.join(os.path.dirname(__file__), 'taack-plm-webviewdetails.ui'))