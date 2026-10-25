import sys

from PySide6.QtWidgets import QApplication

from ui import DesktopApp, load_stylesheet


def main() -> int:
    app = QApplication(sys.argv)
    load_stylesheet(app)
    window = DesktopApp()
    app.aboutToQuit.connect(window.research.cancel)
    app.aboutToQuit.connect(window.manager.stop)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
