import sys
from ui import BiliMusicDownloader, QApplication

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = BiliMusicDownloader()
    win.show()
    sys.exit(app.exec())
