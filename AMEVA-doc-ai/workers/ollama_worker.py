import subprocess, ollama
from PyQt6.QtCore import QThread, pyqtSignal

class ModelListWorker(QThread):
    # 메인 창으로 모델 리스트(list)를 전달할 신호
    models_signal = pyqtSignal(list)

    def run(self):
        try:
            # 내 컴퓨터에 설치된 모델 목록 가져오기
            response = ollama.list()
            
            # response['models'] 안에는 여러 정보가 들어있는데, 그중 'name'만 쏙 뽑아냅니다.
            # 예: ['gemma2:2b', 'qwen2.5:1.5b']
            model_names = [model['name'] for model in response.get('models', [])]
            
            # 결과 전달
            self.models_signal.emit(model_names)
        except Exception as e:
            # Ollama가 안 켜져 있거나 오류가 나면 빈 리스트 전달
            print(f"모델 목록 로드 실패: {e}")
            self.models_signal.emit([])

class OllamaInstallWorker(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool)

    def run(self):
        try:
            self.log_signal.emit("<font color='cyan'>[SYSTEM] Ollama 설치 시작...</font>")
            process = subprocess.Popen(['winget', 'install', '-e', '--id', 'Ollama.Ollama'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            for line in process.stdout: self.log_signal.emit(f"<font color='#7f8c8d'>[Winget] {line.strip()}</font>")
            process.wait()
            if process.returncode == 0:
                self.log_signal.emit("<font color='#00ff00'>✔ Ollama 설치 완료!</font>")
                self.finished_signal.emit(True)
            else:
                self.log_signal.emit(f"<font color='red'>✘ Ollama 설치 실패 (코드: {process.returncode})</font>")
                self.finished_signal.emit(False)
        except Exception as e:
            self.log_signal.emit(f"<font color='red'>✘ 오류 발생: {str(e)}</font>")
            self.finished_signal.emit(False)

class ModelPullWorker(QThread):
    progress_signal = pyqtSignal(str, float)
    finished_signal = pyqtSignal(str, bool)

    def __init__(self, model_name):
        super().__init__()
        self.model_name = model_name

    def run(self):
        try:
            for progress in ollama.pull(self.model_name, stream=True):
                if 'total' in progress and 'completed' in progress:
                    self.progress_signal.emit(self.model_name, (progress['completed'] / progress['total']) * 100)
                elif 'status' in progress and progress['status'] == 'success':
                    self.progress_signal.emit(self.model_name, 100.0)
            self.finished_signal.emit(self.model_name, True)
        except Exception:
            self.finished_signal.emit(self.model_name, False)
