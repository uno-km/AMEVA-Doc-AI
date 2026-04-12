import sys
from PyQt6.QtWidgets import QApplication
from ui.main_window import AmebaConverter

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = AmebaConverter()
    ex.show()
    sys.exit(app.exec())
