import os, psutil, GPUtil, ollama, subprocess
import urllib.request, urllib.parse, tempfile, re # URL 다운로드용 추가
from datetime import datetime
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QFileDialog, QLabel, QHBoxLayout, QListWidget, QListWidgetItem, QProgressBar, QTextEdit, QFrame, QComboBox, QMessageBox, QInputDialog) # QInputDialog 추가
from PyQt6.QtCore import QTimer, Qt, pyqtSlot, QThread, pyqtSignal
from workers.converter_worker import ConverterWorker
from workers.ollama_worker import ModelListWorker, OllamaInstallWorker
from ui.model_manager import ModelManagerDialog

# 문서 추출 클래스 (DocumentParser) 는 기존 위치에 그대로 두시면 됩니다.

# ---------------------------------------------------------
# [신규] URL 다운로드를 위한 백그라운드 워커 클래스
# ---------------------------------------------------------
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
            
            # 구글 드라이브 공유 링크 -> 직접 다운로드 링크로 자동 변환
            if "drive.google.com" in url:
                match = re.search(r'/file/d/([a-zA-Z0-9_-]+)', url)
                if match:
                    file_id = match.group(1)
                    url = f"https://drive.google.com/uc?export=download&id={file_id}"
            
            # 봇 차단 방지를 위한 User-Agent 헤더 추가
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                filename = "downloaded_document.tmp"
                
                # 구글 드라이브 등에서 보내주는 파일명(확장자 포함) 추출
                cd = response.info().get('Content-Disposition')
                if cd:
                    # 일반 파일명 추출
                    m = re.search(r'filename="?([^";]+)"?', cd)
                    if m: 
                        filename = m.group(1)
                    else:
                        # 한글 파일명 (UTF-8) 추출
                        m2 = re.search(r"filename\*\s*=\s*UTF-8''([^;]+)", cd, re.IGNORECASE)
                        if m2: 
                            filename = urllib.parse.unquote(m2.group(1))
                else:
                    # URL 끝부분에서 파일명 유추
                    parsed = urllib.parse.urlparse(url)
                    basename = os.path.basename(parsed.path)
                    if basename and "." in basename: 
                        filename = urllib.parse.unquote(basename)

                # 윈도우 임시 폴더에 파일 저장 (프로그램 종료 후 찌꺼기 방지)
                temp_dir = tempfile.gettempdir()
                file_path = os.path.join(temp_dir, filename)
                
                with open(file_path, 'wb') as f:
                    f.write(response.read())
                    
            self.finished_signal.emit(file_path, True)
        except Exception as e:
            self.log_signal.emit(f"<font color='red'>✘ 다운로드 실패: 올바른 직접 링크인지 확인하세요. ({str(e)})</font>")
            self.finished_signal.emit("", False)

# ---------------------------------------------------------
# 기존 AmebaConverter 클래스 업데이트
# ---------------------------------------------------------
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
        self.setWindowTitle('AMEVA Doc AI v5.0')
        self.setFixedSize(650, 720) 
        self.setStyleSheet("background-color: #0d0d0d; color: #e0e0e0; font-family: 'Consolas';")
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)

        # 상단 시스템 정보 & 엔진 선택 (기존과 동일)
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
        
        self.btn_manage_models = QPushButton("모델 관리")
        self.btn_manage_models.setStyleSheet("background-color: #27ae60; padding: 5px; min-width: 80px;")
        self.btn_manage_models.clicked.connect(self.open_model_manager)
        model_selection_layout.addWidget(self.btn_manage_models)

        self.status_light = QLabel("● 엔진 분석 대기 중")
        diag_layout.addWidget(self.spec_info)
        diag_layout.addLayout(model_selection_layout)
        diag_layout.addWidget(self.status_light)
        main_layout.addWidget(diag_frame)

        # 실시간 모니터링 바 (기존과 동일)
        mon_layout = QHBoxLayout()
        self.cpu_bar = QProgressBar(); self.cpu_bar.setFormat("CPU %p%")
        self.ram_bar = QProgressBar(); self.ram_bar.setFormat("RAM %p%")
        self.gpu_bar = QProgressBar(); self.gpu_bar.setFormat("GPU %p%")
        for b in [self.cpu_bar, self.ram_bar, self.gpu_bar]: 
            b.setStyleSheet("QProgressBar { border: 1px solid #444; height: 10px; font-size: 7pt; text-align: center; }")
            b.setFixedHeight(10)
        mon_layout.addWidget(self.cpu_bar); mon_layout.addWidget(self.ram_bar); mon_layout.addWidget(self.gpu_bar)
        main_layout.addLayout(mon_layout)

        # 작업 대기열
        self.file_list_widget = QListWidget()
        self.file_list_widget.setMaximumHeight(150)
        self.file_list_widget.setStyleSheet("background-color: #222; border: 1px solid #444; padding: 5px;")
        main_layout.addWidget(QLabel("작업 대기열 (체크된 항목 요약)"))
        main_layout.addWidget(self.file_list_widget)

        # 로그 뷰
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

        # 하단 버튼부 (링크로 넣기 버튼 추가)
        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("파일 추가")
        self.btn_add_link = QPushButton("링크로 넣기") # 신규 버튼
        self.btn_clear = QPushButton("목록 초기화")
        self.btn_run = QPushButton("AI 변환 시작")
        self.btn_run.setEnabled(False)
        self.btn_run.setStyleSheet("background-color: #333; color: #777; font-weight: bold;")
        
        for btn in [self.btn_add, self.btn_add_link, self.btn_clear, self.btn_run]:
            btn.setFixedHeight(35)
        
        self.btn_add.clicked.connect(self.add_files)
        self.btn_add_link.clicked.connect(self.add_from_link) # 이벤트 연결
        self.btn_clear.clicked.connect(self.clear_files)
        self.btn_run.clicked.connect(self.start_task)
        
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_add_link) # 레이아웃에 추가
        btn_layout.addWidget(self.btn_clear)
        btn_layout.addWidget(self.btn_run)
        main_layout.addLayout(btn_layout)
        
        self.setLayout(main_layout)

    # ---------------------------------------------------------
    # [신규] 링크에서 파일 추가하는 함수
    # ---------------------------------------------------------
    def add_from_link(self):
        url, ok = QInputDialog.getText(self, "링크로 파일 가져오기", "다운로드 URL을 입력하세요 (Google Drive 링크 지원):")
        if ok and url.strip():
            # 다운로드 작업 스레드 실행 (UI 멈춤 방지)
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

    # 아래는 기존 함수들 유지 (생략 없이 그대로 사용하시면 됩니다)
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
        
    def refresh_models(self):
        self.list_worker = ModelListWorker()
        self.list_worker.models_signal.connect(self.update_combo_box)
        self.list_worker.start()
        
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

    def update_combo_box(self, model_names):
        self.combo_box.clear()
        if not model_names:
            self.combo_box.addItem("설치된 모델 없음")
        else:
            self.combo_box.addItems(model_names)

    def update_stats(self):
        self.cpu_bar.setValue(int(psutil.cpu_percent()))
        self.ram_bar.setValue(int(psutil.virtual_memory().percent))
        gpus = GPUtil.getGPUs()
        if gpus: self.gpu_bar.setValue(int(gpus[0].load * 100))

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "파일 선택", "", "All (*.hwp *.hwpx *.docx *.xlsx *.pptx)")
        if files:
            for f in files:
                item = QListWidgetItem(f"[로컬] {os.path.basename(f)}")
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
        files_data = [{'path': self.file_list_widget.item(i).data(Qt.ItemDataRole.UserRole), 'summarize': self.file_list_widget.item(i).checkState() == Qt.CheckState.Checked} for i in range(self.file_list_widget.count())]
        self.btn_run.setEnabled(False)
        self.worker = ConverterWorker(files_data, dest, model)
        self.worker.progress_signal.connect(self.pbar.setValue)
        self.worker.log_signal.connect(self.append_log_with_time)
        self.worker.stream_signal.connect(lambda t: self.log_view.insertPlainText(t))
        self.worker.status_msg_signal.connect(self.current_action.setText)
        self.worker.finished_signal.connect(lambda: self.btn_run.setEnabled(True))
        self.worker.start()