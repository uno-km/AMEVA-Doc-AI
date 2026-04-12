import os, psutil, GPUtil, ollama, subprocess, tempfile, urllib.request, urllib.parse, re, time
from datetime import datetime
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QFileDialog, QLabel, QHBoxLayout, QListWidget, QListWidgetItem, QProgressBar, QTextEdit, QFrame, QComboBox, QMessageBox, QInputDialog, QStackedWidget, QMenu, QCheckBox, QLineEdit)
from PyQt6.QtCore import QTimer, Qt, pyqtSlot, QThread, pyqtSignal, QRect, QPropertyAnimation
from PyQt6.QtGui import QFont, QTextCursor, QAction, QColor
from workers.converter_worker import ConverterWorker, OllamaChatWorker
from workers.ollama_worker import OllamaInstallWorker, ModelListWorker
from ui.model_manager import ModelManagerDialog

class WorkerMinimi(QWidget):
    clicked = pyqtSignal(int)
    
    def __init__(self, t_id):
        super().__init__()
        self.t_id = t_id
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        self.icon = QLabel("😴")
        self.icon.setFont(QFont("Segoe UI Emoji", 16))
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.label = QLabel(f"P-{t_id}")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("color: #ccc; font-size: 7pt; background: transparent;")
        
        self.layout.addWidget(self.icon)
        self.layout.addWidget(self.label)
        self.setToolTip(f"P-{t_id}: 대기 중 (클릭하여 스트리밍 로그 보기)")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate_work)
        self.working_state = 0

    def mousePressEvent(self, event):
        self.clicked.emit(self.t_id)

    def set_working(self, working, current, total, is_dead=False):
        if is_dead:
            self.timer.stop()
            self.icon.setText("💀")
            self.setToolTip(f"P-{self.t_id}: 서버 다운으로 사망함")
            self.setStyleSheet("background-color: rgba(231, 76, 60, 0.4); border-radius: 4px;")
        elif working:
            self.setToolTip(f"P-{self.t_id}: [{current}/{total}] 요약 중 (클릭하여 훔쳐보기)")
            progress_ratio = current / total if total > 0 else 0
            intensity = int(progress_ratio * 150)
            self.setStyleSheet(f"background-color: rgba(39, 174, 96, {intensity}); border-radius: 4px;")
            self.timer.start(300)
        else:
            self.timer.stop()
            self.icon.setText("✅")
            self.setToolTip(f"P-{self.t_id}: [{current}/{total}] 완료/대기 중")
            self.setStyleSheet("background-color: rgba(39, 174, 96, 180); border-radius: 4px;")
            
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

                if is_sheet and not filename.lower().endswith('.xlsx'): filename = filename.replace('.tmp', '') + ".xlsx"
                if filename.lower().endswith('.tmp'): filename = filename.replace('.tmp', '.txt')

                temp_dir = tempfile.gettempdir()
                safe_filename = f"{int(time.time())}_{filename}" 
                file_path = os.path.join(temp_dir, safe_filename)
                with open(file_path, 'wb') as f: f.write(response.read())
            self.finished_signal.emit(file_path, True)
        except Exception as e:
            self.log_signal.emit(f"<font color='red'>✘ 다운로드 실패: {str(e)}</font>")
            self.finished_signal.emit("", False)

class AmebaConverter(QWidget):
    def __init__(self):
        super().__init__()
        self.installed_models = []
        self.is_ollama_installed = False
        self.current_view_idx = 0 
        self.rag_context = "" 
        self.chat_history = []
        self.current_ai_reply = "" 
        
        self.is_task_running = False
        self.task_start_time = None
        self.total_energy_wh = 0.0
        self.live_tokens = 0
        
        self.initUI()
        self.check_pc_specs()
        self.check_ollama_installation()
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_stats)
        self.timer.start(1000)

    def initUI(self):
        self.setWindowTitle('AMEVA Doc AI v12.3 - Flawless Execution')
        self.setFixedSize(1050, 780) 
        self.setStyleSheet("background-color: #0d0d0d; color: #e0e0e0; font-family: 'Consolas';")
        
        global_layout = QHBoxLayout(self)
        global_layout.setSpacing(15)
        
        left_widget = QWidget()
        left_widget.setFixedWidth(650)
        main_layout = QVBoxLayout(left_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(5)

        diag_frame = QFrame()
        diag_frame.setFixedHeight(100) 
        diag_frame.setStyleSheet("background-color: #1a1a1a; border-radius: 8px; border: 1px solid #333;")
        diag_layout = QVBoxLayout(diag_frame)
        diag_layout.setContentsMargins(10, 2, 10, 2)
        
        self.spec_info = QLabel("시스템 분석 중...")
        
        model_selection_layout = QHBoxLayout()
        model_selection_layout.addWidget(QLabel("AI 엔진:"))
        self.model_combo = QComboBox()
        self.model_combo.setStyleSheet("QComboBox { background-color: #222; color: white; border: 1px solid #444; padding: 2px; }")
        self.model_combo.currentIndexChanged.connect(self.analyze_model_suitability)
        model_selection_layout.addWidget(self.model_combo, 1)
        
        model_selection_layout.addWidget(QLabel(" | 스레드:"))
        self.thread_combo = QComboBox()
        self.thread_combo.addItems([f"{i}개" for i in range(1, 9)])
        self.thread_combo.setCurrentIndex(1)
        self.thread_combo.setStyleSheet("QComboBox { background-color: #222; color: white; border: 1px solid #444; padding: 2px; }")
        self.thread_combo.currentIndexChanged.connect(self.update_minimis)
        model_selection_layout.addWidget(self.thread_combo)

        self.btn_manage_models = QPushButton("모델 관리")
        self.btn_manage_models.setStyleSheet("background-color: #27ae60; padding: 3px; min-width: 60px;")
        self.btn_manage_models.clicked.connect(self.open_model_manager)
        model_selection_layout.addWidget(self.btn_manage_models)

        self.status_light = QLabel("● 대기 중")
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

        dash_frame = QFrame()
        dash_frame.setFixedHeight(30)
        dash_frame.setStyleSheet("background-color: #000; border: 1px solid #333; border-radius: 4px;")
        dash_layout = QHBoxLayout(dash_frame)
        dash_layout.setContentsMargins(10, 0, 10, 0)
        
        self.lbl_time = QLabel("⏱️ 00:00")
        self.lbl_time.setStyleSheet("color: #ecf0f1; font-weight: bold; font-size: 9pt;")
        
        self.lbl_power = QLabel("⚡ 0.0000 Wh (0.0W)")
        self.lbl_power.setStyleSheet("color: #f1c40f; font-weight: bold; font-size: 9pt;")
        
        self.lbl_tokens = QLabel("🪙 0 Tokens")
        self.lbl_tokens.setStyleSheet("color: #2ecc71; font-weight: bold; font-size: 9pt;")
        
        dash_layout.addWidget(self.lbl_time)
        dash_layout.addWidget(self.lbl_power)
        dash_layout.addWidget(self.lbl_tokens)
        main_layout.addWidget(dash_frame)

        self.file_list_widget = QListWidget()
        self.file_list_widget.setMaximumHeight(70) 
        self.file_list_widget.setStyleSheet("background-color: #222; border: 1px solid #444; padding: 3px;")
        self.file_list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_list_widget.customContextMenuRequested.connect(self.show_context_menu)
        self.file_list_widget.itemDoubleClicked.connect(self.open_folder)
        main_layout.addWidget(QLabel("작업 대기열 (우클릭하여 결과 보기)"))
        main_layout.addWidget(self.file_list_widget)

        self.factory_frame = QFrame()
        self.factory_frame.setFixedHeight(85)
        self.factory_frame.setStyleSheet("background-color: #161616; border-radius: 8px; border: 1px solid #444;")
        
        self.police_label = QLabel("👮", self.factory_frame)
        self.police_label.setFont(QFont("Segoe UI Emoji", 16))
        self.police_label.setGeometry(10, 2, 30, 30)
        self.police_label.setToolTip("경찰: 10초마다 순찰 중")
        
        self.police_anim = QPropertyAnimation(self.police_label, b"geometry")
        self.police_anim.setDuration(10000)
        self.police_anim.setKeyValueAt(0.0, QRect(10, 2, 30, 30))
        self.police_anim.setKeyValueAt(0.5, QRect(590, 2, 30, 30))
        self.police_anim.setKeyValueAt(1.0, QRect(10, 2, 30, 30))
        self.police_anim.setLoopCount(-1)

        self.workers_widget = QWidget(self.factory_frame)
        self.workers_widget.setGeometry(10, 32, 600, 50)
        self.workers_layout = QHBoxLayout(self.workers_widget)
        self.workers_layout.setContentsMargins(0, 0, 0, 0)
        self.worker_minimis = {}
        
        self.update_minimis()
        main_layout.addWidget(self.factory_frame)

        self.log_header_layout = QHBoxLayout()
        self.log_title = QLabel("📝 전체 진행 로그")
        self.log_title.setStyleSheet("font-weight: bold; color: #f1c40f;")
        self.btn_back_to_main = QPushButton("🔙 전체 로그로 돌아가기")
        self.btn_back_to_main.setStyleSheet("background-color: #34495e; color: white; padding: 2px 10px; border-radius: 4px;")
        self.btn_back_to_main.hide()
        self.btn_back_to_main.clicked.connect(self.show_main_log)
        
        self.log_header_layout.addWidget(self.log_title)
        self.log_header_layout.addStretch()
        self.log_header_layout.addWidget(self.btn_back_to_main)
        main_layout.addLayout(self.log_header_layout)

        self.log_stack = QStackedWidget()
        self.log_stack.setMinimumHeight(170)
        
        self.main_log_view = QTextEdit()
        self.main_log_view.setReadOnly(True)
        self.main_log_view.setStyleSheet("background-color: #050505; color: #dcdde1; font-size: 8pt; border: 1px solid #333;")
        self.log_stack.addWidget(self.main_log_view)
        
        self.thread_log_views = {}
        for i in range(1, 9):
            tv = QTextEdit()
            tv.setReadOnly(True)
            tv.setStyleSheet("background-color: #050510; color: #3498db; font-size: 8pt; border: 1px solid #333;")
            self.log_stack.addWidget(tv)
            self.thread_log_views[i] = tv

        main_layout.addWidget(self.log_stack)

        self.current_action = QLabel("대기 중...")
        main_layout.addWidget(self.current_action)

        self.pbar = QProgressBar()
        self.pbar.setFixedHeight(12)
        main_layout.addWidget(self.pbar)

        self.cb_tts = QCheckBox("🎧 완료 후 요약본 오디오(MP3) 자동 생성 (VRAM 미사용)")
        self.cb_tts.setStyleSheet("color: #e67e22; font-weight: bold;")
        main_layout.addWidget(self.cb_tts)

        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("파일 추가")
        self.btn_add_link = QPushButton("링크 추가")
        self.btn_clear = QPushButton("초기화")
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
        
        right_widget = QWidget()
        right_widget.setStyleSheet("background-color: #161616; border-radius: 8px; border: 1px solid #444;")
        right_layout = QVBoxLayout(right_widget)
        
        rag_title = QLabel("💬 문서와 대화하기 (RAG)")
        rag_title.setStyleSheet("font-size: 12pt; font-weight: bold; color: #3498db;")
        right_layout.addWidget(rag_title)
        
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setStyleSheet("background-color: #050505; color: #e0e0e0; font-size: 9pt; border: none;")
        self.chat_display.append("<i>[안내] 요약이 완료된 문서를 기반으로 AI에게 질문할 수 있습니다. VRAM 보호를 위해 요약 작업 중에는 채팅이 일시 차단됩니다.</i><br>")
        right_layout.addWidget(self.chat_display)
        
        chat_input_layout = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("요약된 문서에 대해 질문하세요...")
        self.chat_input.setStyleSheet("background-color: #222; color: white; border: 1px solid #444; padding: 5px; border-radius: 4px;")
        self.chat_input.returnPressed.connect(self.send_chat)
        
        self.btn_send_chat = QPushButton("전송")
        self.btn_send_chat.setStyleSheet("background-color: #2980b9; color: white; padding: 5px 15px; border-radius: 4px;")
        self.btn_send_chat.clicked.connect(self.send_chat)
        
        chat_input_layout.addWidget(self.chat_input)
        chat_input_layout.addWidget(self.btn_send_chat)
        right_layout.addLayout(chat_input_layout)
        
        global_layout.addWidget(left_widget)
        global_layout.addWidget(right_widget)

    def update_minimis(self):
        for i in reversed(range(self.workers_layout.count())): 
            widget = self.workers_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
        self.worker_minimis.clear()
        
        count = int(self.thread_combo.currentText().replace("개", ""))
        for i in range(1, count + 1):
            minimi = WorkerMinimi(i)
            minimi.clicked.connect(self.show_thread_log)
            self.workers_layout.addWidget(minimi)
            self.worker_minimis[i] = minimi

    @pyqtSlot(int)
    def show_thread_log(self, t_id):
        self.current_view_idx = t_id
        self.log_stack.setCurrentIndex(t_id)
        self.log_title.setText(f"🤖 [P-{t_id}] 실시간 스트리밍 시청 중...")
        self.log_title.setStyleSheet("font-weight: bold; color: #3498db;")
        self.btn_back_to_main.show()

    @pyqtSlot()
    def show_main_log(self):
        self.current_view_idx = 0
        self.log_stack.setCurrentIndex(0)
        self.log_title.setText("📝 전체 진행 로그")
        self.log_title.setStyleSheet("font-weight: bold; color: #f1c40f;")
        self.btn_back_to_main.hide()

    @pyqtSlot(int, bool, int, int, bool)
    def update_minimi_state(self, t_id, is_working, current, total, is_dead):
        if t_id in self.worker_minimis:
            self.worker_minimis[t_id].set_working(is_working, current, total, is_dead)

    @pyqtSlot(str)
    def append_log_html(self, html_text):
        self.main_log_view.append(html_text)

    def append_log_with_time(self, text):
        ts = datetime.now().strftime("%H:%M:%S")
        self.main_log_view.append(f"<font color='#7f8c8d'>[{ts}]</font> {text}")

    @pyqtSlot(int, str)
    def append_stream_with_tid(self, t_id, text):
        if "▶" not in text and "✅" not in text and "❌" not in text:
            self.live_tokens += 1 

        if t_id in self.thread_log_views:
            view = self.thread_log_views[t_id]
            cursor = view.textCursor()
            cursor.clearSelection()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            view.setTextCursor(cursor)
            view.insertPlainText(text)
            view.moveCursor(QTextCursor.MoveOperation.End)
            view.ensureCursorVisible()

    def show_context_menu(self, pos):
        item = self.file_list_widget.itemAt(pos)
        if item is None: return
        data = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict) or not data.get('is_done'): return

        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #222; color: white; border: 1px solid #444; } QMenu::item:selected { background-color: #2980b9; }")
        
        if data.get('summary_path'):
            action_summary = QAction("📄 AI 요약본 PDF 열기", self)
            action_summary.triggered.connect(lambda: os.startfile(data['summary_path']))
            menu.addAction(action_summary)
            
        if data.get('base_path'):
            action_base = QAction("📄 기본 변환 PDF 열기", self)
            action_base.triggered.connect(lambda: os.startfile(data['base_path']))
            menu.addAction(action_base)
            
        menu.exec(self.file_list_widget.mapToGlobal(pos))

    def open_folder(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, dict) and data.get('is_done'):
            folder_path = os.path.dirname(data.get('base_path', '') or data.get('summary_path', ''))
            if folder_path: os.startfile(folder_path)

    @pyqtSlot(int, dict)
    def on_file_done(self, list_index, output_paths):
        item = self.file_list_widget.item(list_index)
        if item:
            font = item.font()
            font.setStrikeOut(True)
            item.setFont(font)
            item.setForeground(QColor("#2ecc71"))
            item.setText(item.text().replace("[요약]", "[완료]").replace("[웹]", "[완료]"))
            
            old_path = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(old_path, dict):
                item.setData(Qt.ItemDataRole.UserRole, {
                    'original_path': old_path,
                    'is_done': True,
                    'base_path': output_paths.get('base'),
                    'summary_path': output_paths.get('summary')
                })

    @pyqtSlot(int)
    def on_file_start(self, file_idx):
        for tv in self.thread_log_views.values(): tv.clear()
        for m in self.worker_minimis.values():
            m.icon.setText("😴")
            m.setStyleSheet("background-color: transparent;")
            m.setToolTip(f"P-{m.t_id}: 대기 중")

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

    def add_from_link(self):
        url, ok = QInputDialog.getText(self, "링크 가져오기", "다운로드 URL:")
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
            self.append_log_html(f"<font color='#00ff00'>✔ 파일 다운로드 완료: {os.path.basename(file_path)}</font>")
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
        
        if self.is_task_running and self.task_start_time:
            elapsed = time.time() - self.task_start_time
            m, s = divmod(int(elapsed), 60)
            self.lbl_time.setText(f"⏱️ 시간: {m:02d}:{s:02d}")
            
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            power_w = 15.0 + (cpu * 0.4) + (ram * 0.1)
            self.total_energy_wh += power_w / 3600.0 
            
            self.lbl_power.setText(f"⚡ 전력: {self.total_energy_wh:.4f} Wh ({power_w:.1f}W)")
            self.lbl_tokens.setText(f"🪙 토큰: {self.live_tokens:,} T")

    def clear_files(self):
        self.file_list_widget.clear()
        self.btn_run.setEnabled(False)

    def start_task(self):
        model = self.model_combo.currentData()
        if not model or self.file_list_widget.count() == 0: return
        dest = QFileDialog.getExistingDirectory(self, "저장")
        if not dest: return
        
        selected_thread_count = int(self.thread_combo.currentText().replace("개", ""))
        do_tts_flag = self.cb_tts.isChecked()
        
        files_data = []
        for i in range(self.file_list_widget.count()):
            item = self.file_list_widget.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            is_checked = item.checkState() == Qt.CheckState.Checked
            
            if isinstance(data, dict):
                files_data.append({'path': data['original_path'], 'summarize': is_checked, 'is_done': data.get('is_done', False)})
            else:
                files_data.append({'path': data, 'summarize': is_checked, 'is_done': False})
                
        self.btn_run.setEnabled(False)
        self.chat_input.setEnabled(False)
        self.btn_send_chat.setEnabled(False)
        self.chat_input.setPlaceholderText("요약 중에는 VRAM 보호를 위해 채팅이 제한됩니다...")
        
        for tv in self.thread_log_views.values(): tv.clear()
        self.main_log_view.clear()
        self.show_main_log()
        self.police_anim.start()
        
        self.is_task_running = True
        self.task_start_time = time.time()
        self.total_energy_wh = 0.0
        self.live_tokens = 0
        
        self.worker = ConverterWorker(files_data, dest, model, thread_count=selected_thread_count, do_tts=do_tts_flag)
        self.worker.progress_signal.connect(self.pbar.setValue)
        
        self.worker.log_signal.connect(self.append_log_html)
        self.worker.stream_signal.connect(self.append_stream_with_tid) 
        self.worker.status_msg_signal.connect(self.current_action.setText)
        
        self.worker.file_done_signal.connect(self.on_file_done)
        self.worker.file_start_signal.connect(self.on_file_start)
        
        self.worker.worker_state_signal.connect(self.update_minimi_state)
        self.worker.rag_ready_signal.connect(self.on_rag_ready)
        self.worker.finished_signal.connect(self.on_task_finished)
        self.worker.start()

    @pyqtSlot(str)
    def on_rag_ready(self, context_text):
        self.rag_context = context_text
        self.chat_history = [] 
        self.chat_display.append("<br><hr><b>[시스템]</b> 🧠 RAG 메모리 최적화 완료! 이제 문서에 대해 질문해 보세요.")

    @pyqtSlot(int)
    def on_task_finished(self, success_count):
        self.is_task_running = False 
        self.btn_run.setEnabled(True)
        self.chat_input.setEnabled(True)
        self.btn_send_chat.setEnabled(True)
        self.chat_input.setPlaceholderText("학습된 문서에 대해 자유롭게 질문하세요...")
        
        self.police_anim.stop()
        self.police_label.setGeometry(10, 2, 30, 30)
        for m in self.worker_minimis.values():
            if m.icon.text() != "💀": 
                m.timer.stop()
                m.icon.setText("🎉")
                m.setStyleSheet("background-color: rgba(39, 174, 96, 0.4); border-radius: 4px;")

    def send_chat(self):
        user_text = self.chat_input.text().strip()
        if not user_text: return
        if not self.rag_context:
            QMessageBox.warning(self, "알림", "아직 요약된 문서가 없습니다. 변환을 먼저 진행해 주세요!")
            return
        model = self.model_combo.currentData()
        if not model: return
        
        self.chat_display.append(f"<br><b style='color:#3498db;'>나:</b> {user_text}")
        self.chat_input.clear()
        self.chat_input.setEnabled(False)
        self.btn_send_chat.setEnabled(False)
        
        # 1.5B 소형 모델도 말을 잘 듣도록 강제 Context 멱살잡기 방식
        if len(self.chat_history) == 0:
            prompt = f"다음은 내가 제공하는 [문서 내용]이야. 이 내용을 바탕으로 내 [질문]에 답변해줘. 문서에 없는 내용은 모른다고 대답해.\n\n[문서 내용]\n{self.rag_context}\n\n[질문]\n{user_text}"
            self.chat_history.append({'role': 'user', 'content': prompt})
        else:
            self.chat_history.append({'role': 'user', 'content': user_text})
            
        self.chat_display.append("<b style='color:#2ecc71;'>AI:</b> ")
        self.current_ai_reply = ""
        
        self.chat_worker = OllamaChatWorker(model, self.chat_history)
        self.chat_worker.stream_signal.connect(self.append_chat_stream)
        self.chat_worker.finished_signal.connect(self.on_chat_finished)
        self.chat_worker.start()

    @pyqtSlot(str)
    def append_chat_stream(self, text):
        self.current_ai_reply += text 
        cursor = self.chat_display.textCursor()
        cursor.clearSelection()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.chat_display.setTextCursor(cursor)
        self.chat_display.insertPlainText(text)
        self.chat_display.moveCursor(QTextCursor.MoveOperation.End)
        self.chat_display.ensureCursorVisible()

    @pyqtSlot()
    def on_chat_finished(self):
        self.chat_history.append({'role': 'assistant', 'content': self.current_ai_reply})
        self.chat_input.setEnabled(True)
        self.btn_send_chat.setEnabled(True)
        self.chat_input.setFocus()
