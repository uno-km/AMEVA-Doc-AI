import os, psutil, GPUtil, ollama, subprocess, tempfile, urllib.request, urllib.parse, re, time
from datetime import datetime
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QFileDialog, QLabel, QHBoxLayout, QListWidget, QListWidgetItem, QProgressBar, QTextEdit, QFrame, QComboBox, QMessageBox, QInputDialog)
from PyQt6.QtCore import QTimer, Qt, pyqtSlot, QThread, pyqtSignal, QRect, QPropertyAnimation
from PyQt6.QtGui import QFont
from workers.converter_worker import ConverterWorker
from workers.ollama_worker import OllamaInstallWorker, ModelListWorker
from ui.model_manager import ModelManagerDialog

class WorkerMinimi(QWidget):
    """프로세서 미니미 (상태 표시용 위젯)"""
    def __init__(self, t_id):
        super().__init__()
        self.t_id = t_id
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(2, 2, 2, 2)
        
        self.icon = QLabel("😴")
        self.icon.setFont(QFont("Segoe UI Emoji", 20))
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.label = QLabel(f"P-{t_id}")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("color: #ccc; font-size: 8pt;")
        
        self.layout.addWidget(self.icon)
        self.layout.addWidget(self.label)
        self.setToolTip(f"P-{t_id}: 현재 대기 중입니다.")
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate_work)
        self.working_state = 0
        self.is_working = False

    def set_working(self, working, current, total):
        self.is_working = working
        if working:
            self.setToolTip(f"P-{self.t_id}: [{current}/{total}] 열심히 요약 중!")
            self.setStyleSheet("background-color: rgba(41, 128, 185, 0.4); border-radius: 5px;")
            self.timer.start(300) # 망치질 속도
        else:
            self.timer.stop()
            self.icon.setText("✅")
            self.setToolTip(f"P-{self.t_id}: [{current}/{total}] 완료 및 대기 중")
            self.setStyleSheet("background-color: transparent;")
            
    def animate_work(self):
        frames = ["🔨🤖", "⚡🤖"]
        self.icon.setText(frames[self.working_state % 2])
        self.working_state += 1

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
        self.setWindowTitle('AMEVA Doc AI v7.0 - Minimi Factory')
        self.setFixedSize(650, 850) # 미니미 팩토리를 위해 세로 길이 확장
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
        
        model_selection_layout.addWidget(QLabel(" | 프로세서:"))
        self.thread_combo = QComboBox()
        self.thread_combo.addItems([f"{i}개" for i in range(1, 9)])
        self.thread_combo.setCurrentIndex(1)
        self.thread_combo.setStyleSheet("QComboBox { background-color: #222; color: white; border: 1px solid #444; padding: 3px; }")
        self.thread_combo.currentIndexChanged.connect(self.update_minimis) # 콤보 변경 시 미니미 새로고침
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
        self.file_list_widget.setMaximumHeight(120)
        self.file_list_widget.setStyleSheet("background-color: #222; border: 1px solid #444; padding: 5px;")
        main_layout.addWidget(QLabel("작업 대기열 (체크된 항목 요약)"))
        main_layout.addWidget(self.file_list_widget)

        # ---------------------------------------------------------
        # [신규] 미니미 팩토리 & 경찰 순찰 UI
        # ---------------------------------------------------------
        self.factory_frame = QFrame()
        self.factory_frame.setFixedHeight(95)
        self.factory_frame.setStyleSheet("background-color: #161616; border-radius: 8px; border: 1px solid #444;")
        
        # 경찰 아이콘 (절대 좌표)
        self.police_label = QLabel("👮", self.factory_frame)
        self.police_label.setFont(QFont("Segoe UI Emoji", 18))
        self.police_label.setGeometry(10, 5, 35, 35)
        self.police_label.setToolTip("순찰 경찰: 이상 무! 10초마다 순찰 중입니다.")
        
        # 경찰 애니메이션 (10초 = 10000ms)
        self.police_anim = QPropertyAnimation(self.police_label, b"geometry")
        self.police_anim.setDuration(10000)
        self.police_anim.setKeyValueAt(0.0, QRect(10, 5, 35, 35))
        self.police_anim.setKeyValueAt(0.5, QRect(570, 5, 35, 35)) # 오른쪽 끝으로 이동
        self.police_anim.setKeyValueAt(1.0, QRect(10, 5, 35, 35))  # 다시 제자리
        self.police_anim.setLoopCount(-1) # 무한 반복

        # 프로세서 미니미 컨테이너
        self.workers_widget = QWidget(self.factory_frame)
        self.workers_widget.setGeometry(10, 35, 600, 55)
        self.workers_layout = QHBoxLayout(self.workers_widget)
        self.workers_layout.setContentsMargins(0, 0, 0, 0)
        self.worker_minimis = {}
        
        self.update_minimis() # 초기 미니미 생성
        main_layout.addWidget(self.factory_frame)
        # ---------------------------------------------------------

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

    def update_minimis(self):
        # 기존 미니미 청소
        for i in reversed(range(self.workers_layout.count())): 
            widget = self.workers_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
        self.worker_minimis.clear()
        
        # 콤보박스 개수만큼 미니미 생성
        count = int(self.thread_combo.currentText().replace("개", ""))
        for i in range(1, count + 1):
            minimi = WorkerMinimi(i)
            self.workers_layout.addWidget(minimi)
            self.worker_minimis[i] = minimi

    @pyqtSlot(int, bool, int, int)
    def update_minimi_state(self, t_id, is_working, current, total):
        if t_id in self.worker_minimis:
            self.worker_minimis[t_id].set_working(is_working, current, total)

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
        
        selected_thread_count = int(self.thread_combo.currentText().replace("개", ""))
        files_data = [{'path': self.file_list_widget.item(i).data(Qt.ItemDataRole.UserRole), 'summarize': self.file_list_widget.item(i).checkState() == Qt.CheckState.Checked} for i in range(self.file_list_widget.count())]
        self.btn_run.setEnabled(False)
        
        # 경찰 순찰 애니메이션 시작 및 미니미 초기화
        self.police_anim.start()
        for m in self.worker_minimis.values():
            m.icon.setText("😴")
            m.setStyleSheet("background-color: transparent;")
            m.setToolTip(f"P-{m.t_id}: 대기 중")
        
        self.worker = ConverterWorker(files_data, dest, model, thread_count=selected_thread_count)
        self.worker.progress_signal.connect(self.pbar.setValue)
        self.worker.log_signal.connect(self.append_log_with_time)
        self.worker.stream_signal.connect(lambda t: self.log_view.insertPlainText(t))
        self.worker.status_msg_signal.connect(self.current_action.setText)
        
        # 미니미 상태 업데이트 시그널 연결
        self.worker.worker_state_signal.connect(self.update_minimi_state)
        self.worker.finished_signal.connect(self.on_task_finished)
        self.worker.start()

    @pyqtSlot(int)
    def on_task_finished(self, success_count):
        self.btn_run.setEnabled(True)
        self.police_anim.stop()
        self.police_label.setGeometry(10, 5, 35, 35) # 경찰 제자리 복귀
        # 작업 종료 시 미니미 축하 파티
        for m in self.worker_minimis.values():
            m.timer.stop()
            m.icon.setText("🎉")
            m.setStyleSheet("background-color: rgba(39, 174, 96, 0.4); border-radius: 5px;")
