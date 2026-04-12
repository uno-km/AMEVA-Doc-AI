import subprocess, ollama
from PyQt6.QtCore import QThread, pyqtSignal

class ModelListWorker(QThread):
    models_signal = pyqtSignal(list)
    def run(self):
        try:
            response = ollama.list()
            models_list = response.models if hasattr(response, 'models') else response.get('models', [])
            model_names = [m.get('name', '') if isinstance(m, dict) else getattr(m, 'model', getattr(m, 'name', '')) for m in models_list]
            self.models_signal.emit(model_names)
        except Exception as e: self.models_signal.emit([])

class OllamaInstallWorker(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool)
    def run(self):
        try:
            self.log_signal.emit("<font color='cyan'>[SYSTEM] Ollama 코어 엔진 이식 시작...</font>")
            process = subprocess.Popen(['winget', 'install', '-e', '--id', 'Ollama.Ollama', '--accept-source-agreements', '--accept-package-agreements'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            for line in process.stdout:
                if line.strip(): self.log_signal.emit(f"<font color='#7f8c8d'>[Winget] {line.strip()}</font>")
            process.wait()
            if process.returncode == 0:
                self.log_signal.emit("<font color='#00ff00'>✔ Ollama 엔진 설치 성공!</font>")
                self.finished_signal.emit(True)
            else:
                self.log_signal.emit(f"<font color='red'>✘ 설치 실패 (코드: {process.returncode})</font>")
                self.finished_signal.emit(False)
        except Exception as e:
            self.log_signal.emit(f"<font color='red'>✘ 프로세스 오류: {str(e)}</font>")
            self.finished_signal.emit(False)

class ModelPullWorker(QThread):
    progress_signal = pyqtSignal(str, float)
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(str, bool)
    def __init__(self, model_name):
        super().__init__()
        self.model_name = model_name
    def run(self):
        try:
            self.log_signal.emit(f"<font color='yellow'>[소환] {self.model_name} 모델 다운로드 시작...</font>")
            for progress in ollama.pull(self.model_name, stream=True):
                if 'total' in progress and 'completed' in progress:
                    self.progress_signal.emit(self.model_name, (progress['completed'] / progress['total']) * 100)
                if 'status' in progress and progress['status'] == 'success':
                    self.progress_signal.emit(self.model_name, 100.0)
                    self.log_signal.emit(f"<font color='#00ff00'>✔ {self.model_name} 소환 완료!</font>")
            self.finished_signal.emit(self.model_name, True)
        except Exception as e:
            self.log_signal.emit(f"<font color='red'>✘ 소환 실패: {str(e)}</font>")
            self.finished_signal.emit(self.model_name, False)
