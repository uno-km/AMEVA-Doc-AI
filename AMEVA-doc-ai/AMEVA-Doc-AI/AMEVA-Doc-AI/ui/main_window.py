import os, psutil, GPUtil, ollama, subprocess, tempfile, urllib.request, urllib.parse, re, time
from datetime import datetime
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QFileDialog, QLabel, QHBoxLayout, QListWidget, QListWidgetItem, QProgressBar, QTextEdit, QFrame, QComboBox, QMessageBox, QInputDialog)
from PyQt6.QtCore import QTimer, Qt, pyqtSlot, QThread, pyqtSignal
from workers.converter_worker import ConverterWorker
from workers.ollama_worker import OllamaInstallWorker, ModelListWorker
from ui.model_manager import ModelManagerDialog

class DownloadWorker(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(str, bool)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            self.log_signal.emit("<font color='cyan'>[다운로드] 링크 분석 및 파일 가져오는 중...</font>")
            url = self.url
            is_sheet = False
            file_match = re.search(r'/file/d/([a-zA-Z0-9_-]+)', url)
            sheet_match = re.search(r'/spreadsheets/d/([a-zA-Z0-9_-]+)', url)
            
            if file_match:
                file_id = file_match.group(1)
                url = f"https://drive.google.com/uc?export=download&id={file_id}"
            elif sheet_match:
                file_id = sheet_match.group(1)
                url = f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx"
                is_sheet = True
            
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                filename = ""
                cd = response.info().get('Content-Disposition')
                if cd:
                    m = re.search(r'filename="?([^";]+)"?', cd)
                    if m: filename = m.group(1)
                    else:
                        m2 = re.search(r"filename\*\s*=\s*UTF-8''([^;]+)", cd, re.IGNORECASE)
                        if m2: filename = urllib.parse.unquote(m2.group(1))
                if not filename:
                    parsed = urllib.parse.urlparse(url)
                    basename = os.path.basename(parsed.path)
                    if basename and "." in basename: filename = urllib.parse.unquote(basename)
                    else: filename = "다운로드된_웹문서.tmp"

                if is_sheet and not filename.lower().endswith('.xlsx'):
                    filename = filename.replace('.tmp', '') + ".xlsx"
                if filename.lower().endswith('.tmp'):
                    filename = filename.replace('.tmp', '.txt')

                temp_dir = tempfile.gettempdir()
                safe_filename = f"{int(time.time())}_{filename}" 
                file_path = os.path.join(temp_dir, safe_filename)
                with open(file_path, 'wb') as f:
                    f.write(response.read())
            self.finished_signal.emit(file_path, True)
        except Exception as e:
            self.log_signal.emit(f"<font color='red'>✘ 다운로드 실패: {str(e)}</font>")
            self.finished_signal.emit("", False)

class AmebaConverter(QWidget):
    def __init__(self):
        super().__init__()
        self.installed_models = []
        self.is_ollama_installed = False
        self.initUI()
        self.check_pc_specs()
        self.check_ollama_installation()
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_stats)
        self.timer.start(1000)

    def initUI(self):
        self.setWindowTitle('AMEVA Doc AI v6.0')
        self.setFixedSize(650, 760)
        self.setStyleSheet("background-color: #0d0d0d; color: #e0e0e0; font-family: 'Consolas';")
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)

        diag_frame = QFrame()
        diag_frame.setFixedHeight(120)
        diag_frame.setStyleSheet("background-color: #1a1a1a; border-radius: 8px; border: 1px solid #333;")
        diag_layout = QVBoxLayout(diag_frame)
        diag_layout.setContentsMargins(10, 5, 10, 5)
        self.spec_info = QLabel("시스템 분석 중...")
        
        model_selection_layout = QHBoxLayout()
        model_selection_layout.addWidget(QLabel("AI 엔진:"))
        self.model_combo = QComboBox()
        self.model_combo.setStyleSheet("QComboBox { background-color: #222; color: white; border: 1px solid #444; padding: 3px; }")
        self.model_combo.currentIndexChanged.connect(self.analyze_model_suitability)
        model_selection_layout.addWidget(self.model_combo, 1)
        
        model_selection_layout.addWidget(QLabel(" | 프로세서(스레드):"))
        self.thread_combo = QComboBox()
        self.thread_combo.addItems([f"{i}개" for i in range(1, 9)])
        self.thread_combo.setCurrentIndex(1) # 기본값 2개
        self.thread_combo.setStyleSheet("QComboBox { background-color: #222; color: white; border: 1px solid #444; padding: 3px; }")
        model_selection_layout.addWidget(self.thread_combo)

        self.btn_manage_models = QPushButton("모델 관리")
        self.btn_manage_models.setStyleSheet("background-color: #27ae60; padding: 5px; min-width: 80px;")
        self.btn_manage_models.clicked.connect(self.open_model_manager)
        model_selection_layout.addWidget(self.btn_manage_models)

        self.status_light = QLabel("● 엔진 분석 대기 중")
        diag_layout.addWidget(self.spec_info)
        diag_layout.addLayout(model_selection_layout)
        diag_layout.addWidget(self.status_light)
        main_layout.addWidget(diag_frame)

        mon_layout = QHBoxLayout()
        self.cpu_bar = QProgressBar(); self.cpu_bar.setFormat("CPU %p%")
        self.ram_bar = QProgressBar(); self.ram_bar.setFormat("RAM %p%")
        self.gpu_bar = QProgressBar(); self.gpu_bar.setFormat("GPU %p%")
        for b in [self.cpu_bar, self.ram_bar, self.gpu_bar]: 
            b.setStyleSheet("QProgressBar { border: 1px solid #444; height: 10px; font-size: 7pt; text-align: center; }")
            b.setFixedHeight(10)
        mon_layout.addWidget(self.cpu_bar); mon_layout.addWidget(self.ram_bar); mon_layout.addWidget(self.gpu_bar)
        main_layout.addLayout(mon_layout)

        self.file_list_widget = QListWidget()
        self.file_list_widget.setMaximumHeight(150)
        self.file_list_widget.setStyleSheet("background-color: #222; border: 1px solid #444; padding: 5px;")
        main_layout.addWidget(QLabel("작업 대기열 (체크된 항목 요약)"))
        main_layout.addWidget(self.file_list_widget)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(200)
        self.log_view.setStyleSheet("background-color: #050505; color: #00ff00; font-size: 8pt; border: 1px solid #333;")
        main_layout.addWidget(self.log_view)

        self.current_action = QLabel("대기 중...")
        main_layout.addWidget(self.current_action)

        self.pbar = QProgressBar()
        self.pbar.setFixedHeight(15)
        main_layout.addWidget(self.pbar)

        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("파일 추가")
        self.btn_add_link = QPushButton("링크로 넣기")
        self.btn_clear = QPushButton("목록 초기화")
        self.btn_run = QPushButton("AI 변환 시작")
        self.btn_run.setEnabled(False)
        self.btn_run.setStyleSheet("background-color: #333; color: #777; font-weight: bold;")
        
        for btn in [self.btn_add, self.btn_add_link, self.btn_clear, self.btn_run]:
            btn.setFixedHeight(35)
        
        self.btn_add.clicked.connect(self.add_files)
        self.btn_add_link.clicked.connect(self.add_from_link)
        self.btn_clear.clicked.connect(self.clear_files)
        self.btn_run.clicked.connect(self.start_task)
        
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_add_link)
        btn_layout.addWidget(self.btn_clear)
        btn_layout.addWidget(self.btn_run)
        main_layout.addLayout(btn_layout)
        
        self.setLayout(main_layout)

    def add_from_link(self):
        url, ok = QInputDialog.getText(self, "링크 가져오기", "다운로드 URL (Google Drive/Sheets 지원):")
        if ok and url.strip():
            self.download_worker = DownloadWorker(url.strip())
            self.download_worker.log_signal.connect(self.append_log_with_time)
            self.download_worker.finished_signal.connect(self.on_download_finished)
            self.download_worker.start()

    @pyqtSlot(str, bool)
    def on_download_finished(self, file_path, success):
        if success and os.path.exists(file_path):
            item = QListWidgetItem(f"[웹] {os.path.basename(file_path)}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, file_path)
            self.file_list_widget.addItem(item)
            self.append_log_with_time(f"<font color='#00ff00'>✔ 파일 다운로드 완료: {os.path.basename(file_path)}</font>")
            if self.is_ollama_installed:
                self.btn_run.setEnabled(True)
                self.btn_run.setStyleSheet("background-color: #d35400; color: white;")

    def check_ollama_installation(self):
        try:
            subprocess.run(['ollama', '--version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            self.is_ollama_installed = True
            self.load_ollama_models()
        except Exception:
            self.is_ollama_installed = False
            self.model_combo.addItem("Ollama 미설치", None)
            if QMessageBox.question(self, '설치', "Ollama 코어 엔진 설치?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                self.install_worker = OllamaInstallWorker()
                self.install_worker.log_signal.connect(self.append_log_with_time)
                self.install_worker.finished_signal.connect(self.on_ollama_install_finished)
                self.install_worker.start()

    @pyqtSlot(bool)
    def on_ollama_install_finished(self, success):
        if success:
            self.is_ollama_installed = True
            self.load_ollama_models()

    def open_model_manager(self):
        if not self.is_ollama_installed: return
        dialog = ModelManagerDialog(self)
        dialog.models_updated.connect(self.load_ollama_models)
        dialog.exec()

    def load_ollama_models(self):
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        try:
            models_info = ollama.list()
            models_list = models_info.models if hasattr(models_info, 'models') else models_info.get('models', []) if isinstance(models_info, dict) else models_info
            if not models_list: self.model_combo.addItem("설치된 모델 없음", None)
            for m in models_list:
                name = m.get('name', '') if isinstance(m, dict) else getattr(m, 'model', getattr(m, 'name', ''))
                size = m.get('size', 0) if isinstance(m, dict) else getattr(m, 'size', 0)
                self.model_combo.addItem(f"{name} ({(size / (1024**3)):.1f}GB)", name)
        except: self.model_combo.addItem("연결 실패", None)
        self.model_combo.blockSignals(False)
        self.analyze_model_suitability()

    def check_pc_specs(self):
        ram = psutil.virtual_memory().total / (1024**3)
        gpus = GPUtil.getGPUs()
        self.spec_info.setText(f"🖥️ {psutil.cpu_count()} Thrs | {ram:.1f}GB RAM | GPU: {gpus[0].name if gpus else 'None'}")

    def analyze_model_suitability(self):
        name = self.model_combo.currentData()
        if not name: return
        self.status_light.setText("● 스펙 분석 완료")

    def update_stats(self):
        self.cpu_bar.setValue(int(psutil.cpu_percent()))
        self.ram_bar.setValue(int(psutil.virtual_memory().percent))
        gpus = GPUtil.getGPUs()
        if gpus: self.gpu_bar.setValue(int(gpus[0].load * 100))

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "파일 선택", "", "All (*.hwp *.hwpx *.docx *.xlsx *.pptx)")
        if files:
            for f in files:
                item = QListWidgetItem(f"[요약] {os.path.basename(f)}")
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                item.setData(Qt.ItemDataRole.UserRole, f)
                self.file_list_widget.addItem(item)
            if self.is_ollama_installed:
                self.btn_run.setEnabled(True)
                self.btn_run.setStyleSheet("background-color: #d35400; color: white;")

    def clear_files(self):
        self.file_list_widget.clear()
        self.btn_run.setEnabled(False)

    def append_log_with_time(self, text):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_view.append(f"<font color='#7f8c8d'>[{ts}]</font> {text}")

    def start_task(self):
        model = self.model_combo.currentData()
        if not model or self.file_list_widget.count() == 0: return
        dest = QFileDialog.getExistingDirectory(self, "저장")
        if not dest: return
        
        # 프로세서(스레드) 개수 추출 (예: "4개" -> 4)
        selected_thread_count = int(self.thread_combo.currentText().replace("개", ""))
        
        files_data = [{'path': self.file_list_widget.item(i).data(Qt.ItemDataRole.UserRole), 'summarize': self.file_list_widget.item(i).checkState() == Qt.CheckState.Checked} for i in range(self.file_list_widget.count())]
        self.btn_run.setEnabled(False)
        
        self.worker = ConverterWorker(files_data, dest, model, thread_count=selected_thread_count)
        self.worker.progress_signal.connect(self.pbar.setValue)
        self.worker.log_signal.connect(self.append_log_with_time)
        self.worker.stream_signal.connect(lambda t: self.log_view.insertPlainText(t))
        self.worker.status_msg_signal.connect(self.current_action.setText)
        self.worker.finished_signal.connect(lambda r: self.btn_run.setEnabled(True))
        self.worker.start()
