import sys


def _run_yt_dlp_if_requested() -> None:
    """The packaged exe doubles as the yt-dlp CLI when the queue spawns it with --run-yt-dlp."""
    if len(sys.argv) > 1 and sys.argv[1] == "--run-yt-dlp":
        import yt_dlp

        sys.argv = ["yt-dlp", *sys.argv[2:]]
        yt_dlp.main()
        raise SystemExit(0)


_run_yt_dlp_if_requested()

from PySide6.QtWidgets import QApplication

from ui import DesktopApp, load_stylesheet


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    load_stylesheet(app)
    window = DesktopApp()
    app.aboutToQuit.connect(window.research.interrupt)
    app.aboutToQuit.connect(window.manager.stop)
    window.show()
    window.offer_resume()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
