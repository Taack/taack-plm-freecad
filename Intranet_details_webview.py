import FreeCADGui
from PySide import QtWidgets
try:
    from PySide.QtWebEngineWidgets import QWebEngineView
except:
    QWebEngineView = None


class TaackPlmDetailsWebview(QtWidgets.QDialog):
    def __init__(self, ro, html, base_url):
        self.hasApplied = False
        self.hasCheckIn = False
        super().__init__(FreeCADGui.getMainWindow())
        # self.window = QtWidgets.QDialog()
        self.window = self
        self.window.resize(720, 640)
        layout = QtWidgets.QVBoxLayout(self.window)
        if QWebEngineView is not None:
            self.webview = QWebEngineView(self.window)
        self.btnClose = QtWidgets.QPushButton("Close")
        self.btnApplyCheckIn = QtWidgets.QPushButton("CheckIn")
        self.btnApplyDlRO = QtWidgets.QPushButton("Download Read-Only")
        # self.btn.clicked.connect(self.accept)
        if QWebEngineView is not None:
            layout.addWidget(self.webview)
        layout.addWidget(self.btnClose)
        layout.addWidget(self.btnApplyCheckIn)
        layout.addWidget(self.btnApplyDlRO)
        self.btnApplyCheckIn.clicked.connect(self.checkIn)
        self.btnApplyDlRO.clicked.connect(self.downloadReadOnly)
        self.btnClose.clicked.connect(self.closing)
        if QWebEngineView is not None:
            self.webview.setHtml(html, base_url)
        if ro:
            self.btnApplyCheckIn.setEnabled(False)
        if QWebEngineView is not None:
            self.webview.show()

    def checkIn(self):
        self.hasApplied = True
        self.hasCheckIn = True
        if QWebEngineView is not None:
            self.webview.hide()
        self.close()

    def downloadReadOnly(self):
        self.hasApplied = True
        self.hasCheckIn = False
        if QWebEngineView is not None:
            self.webview.hide()
        self.close()

    def closing(self):
        self.hasApplied = False
        self.hasCheckIn = False
        if QWebEngineView is not None:
            self.webview.hide()
        self.close()