import ollama
from PyQt6.QtWidgets import (QVBoxLayout, QPushButton, QLabel, QHBoxLayout, QWidget, QMessageBox, QDialog, QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar)
from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt
from PyQt6.QtGui import QColor, QFont
from workers.ollama_worker import ModelPullWorker

class ModelManagerDialog(QDialog):
    models_updated = pyqtSignal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ollama 모델 매니저")
        self.setFixedSize(650, 450)
        self.setStyleSheet("background-color: #1a1a1a; color: #e0e0e0; font-family: 'Consolas';")
        self.available_models = [
            {"name": "gemma2:2b", "desc": "구글 경량 모델", "req": "RAM 4GB 이상"},
            {"name": "qwen2.5:1.5b", "desc": "Qwen 초경량 모델", "req": "RAM 4GB 이상"},
            {"name": "llama3.1:8b", "desc": "Meta 범용 모델", "req": "RAM 16GB, VRAM 6GB 이상"},
            {"name": "qwen2.5-coder:7b", "desc": "코딩/문서 특화", "req": "RAM 16GB, VRAM 6GB 이상"}
        ]
        self.installed_model_names = []
        self.pull_workers = {}
        self.initUI()
        self.refresh_installed_models()

    def initUI(self):
        layout = QVBoxLayout(self)
        title = QLabel("AI 모델 설치/관리")
        title.setStyleSheet("font-size: 14pt; font-weight: bold; color: #f39c12; padding-bottom: 5px;")
        layout.addWidget(title)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["상태", "모델명", "설명/권장사양", "작업"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet("QTableWidget { background-color: #222; gridline-color: #444; border: 1px solid #444; } QHeaderView::section { background-color: #333; color: white; border: 1px solid #444; padding: 4px; }")
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        self.btn_refresh = QPushButton("새로고침")
        self.btn_refresh.clicked.connect(self.refresh_installed_models)
        self.btn_close = QPushButton("닫기")
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

    def refresh_installed_models(self):
        try:
            response = ollama.list()
            models_list = response.models if hasattr(response, 'models') else response.get('models', [])
            self.installed_model_names = [m.get('name', '') if isinstance(m, dict) else getattr(m, 'model', getattr(m, 'name', '')) for m in models_list]
        except Exception: self.installed_model_names = []
        self.populate_table()

    def populate_table(self):
        self.table.setRowCount(len(self.available_models))
        for row, model_data in enumerate(self.available_models):
            m_name = model_data['name']
            is_installed = any(m_name in name for name in self.installed_model_names)
            
            status_item = QTableWidgetItem("✔" if is_installed else "○")
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setForeground(QColor("#2ecc71") if is_installed else QColor("#7f8c8d"))
            status_item.setFont(QFont("Arial", 12, QFont.Weight.Bold))
            self.table.setItem(row, 0, status_item)
            self.table.setItem(row, 1, QTableWidgetItem(m_name))
            self.table.setItem(row, 2, QTableWidgetItem(f"{model_data['desc']} ({model_data['req']})"))

            action_widget = QWidget()
            action_layout = QVBoxLayout(action_widget)
            action_layout.setContentsMargins(5, 2, 5, 2)
            
            if m_name in self.pull_workers:
                pbar = QProgressBar()
                pbar.setRange(0, 100)
                pbar.setStyleSheet("QProgressBar { height: 18px; color: white; border: 1px solid #444; border-radius: 4px; text-align: center; } QProgressBar::chunk { background-color: #3498db; }")
                action_layout.addWidget(pbar)
                self.pull_workers[m_name]['pbar'] = pbar
            elif is_installed:
                btn = QPushButton("삭제")
                btn.setStyleSheet("background-color: #c0392b; color: white; border-radius: 4px; padding: 4px;")
                btn.clicked.connect(lambda checked, name=m_name: self.delete_model(name))
                action_layout.addWidget(btn)
            else:
                btn = QPushButton("설치")
                btn.setStyleSheet("background-color: #2980b9; color: white; border-radius: 4px; padding: 4px;")
                btn.clicked.connect(lambda checked, name=m_name: self.install_model(name))
                action_layout.addWidget(btn)
            self.table.setCellWidget(row, 3, action_widget)

    def install_model(self, model_name):
        if model_name in self.pull_workers: return
        worker = ModelPullWorker(model_name)
        worker.progress_signal.connect(self.update_download_progress)
        worker.finished_signal.connect(self.download_finished)
        if hasattr(self.parent(), 'append_log_with_time'):
            worker.log_signal.connect(self.parent().append_log_with_time)
        self.pull_workers[model_name] = {'worker': worker, 'pbar': None}
        self.populate_table()
        worker.start()

    @pyqtSlot(str, float)
    def update_download_progress(self, model_name, percent):
        if model_name in self.pull_workers and self.pull_workers[model_name]['pbar']:
            self.pull_workers[model_name]['pbar'].setValue(int(percent))

    @pyqtSlot(str, bool)
    def download_finished(self, model_name, success):
        if model_name in self.pull_workers: del self.pull_workers[model_name]
        if success:
            self.models_updated.emit()
            if hasattr(self.parent(), 'load_ollama_models'): self.parent().load_ollama_models()
        else: QMessageBox.critical(self, "설치 실패", f"{model_name} 오류 발생.")
        self.refresh_installed_models()

    def delete_model(self, model_name):
        if QMessageBox.question(self, '삭제', f"{model_name} 삭제하시겠습니까?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            try:
                ollama.delete(model_name)
                self.models_updated.emit()
                if hasattr(self.parent(), 'load_ollama_models'): self.parent().load_ollama_models()
                self.refresh_installed_models()
            except Exception as e: QMessageBox.critical(self, "삭제 실패", f"오류: {e}")
