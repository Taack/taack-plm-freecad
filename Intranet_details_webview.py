import FreeCADGui
from PySide6 import QtWidgets
from PySide6.QtWebEngineWidgets import QWebEngineView

class TaackPlmDetailsWebview(QtWidgets.QDialog):
    def __init__(self, html, base_url):
        self.hasApplied = False
        super().__init__(FreeCADGui.getMainWindow())
        # self.window = QtWidgets.QDialog()
        self.window = self
        self.window.resize(720, 640)
        layout = QtWidgets.QVBoxLayout(self.window)
        self.webview = QWebEngineView(self.window)
        self.btnClose = QtWidgets.QPushButton("Close")
        self.btnApply = QtWidgets.QPushButton("Apply")
        # self.btn.clicked.connect(self.accept)
        layout.addWidget(self.webview)
        layout.addWidget(self.btnClose)
        layout.addWidget(self.btnApply)
        self.btnApply.clicked.connect(self.accept)
        self.btnClose.clicked.connect(self.closing)
        self.webview.setHtml(html, base_url)
        self.webview.show()

    def accept(self):
        self.hasApplied = True
        self.webview.hide()
        self.close()

    def closing(self):
        self.hasApplied = False
        self.webview.hide()
        self.close()