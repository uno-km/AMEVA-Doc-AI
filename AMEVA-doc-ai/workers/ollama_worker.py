import subprocess, ollama
from PyQt6.QtCore import QThread, pyqtSignal

class ModelListWorker(QThread):
    """현재 내 컴퓨터에 설치된 모델 목록을 가져오는 워커"""
    models_signal = pyqtSignal(list)

    def run(self):
        try:
            response = ollama.list()
            # 최신 ollama 라이브러리 대응 (객체 형태일 경우와 딕셔너리 형태일 경우 모두 처리)
            models_list = response.models if hasattr(response, 'models') else response.get('models', [])
            
            model_names = []
            for m in models_list:
                name = m.get('name', '') if isinstance(m, dict) else getattr(m, 'model', getattr(m, 'name', ''))
                model_names.append(name)
            
            self.models_signal.emit(model_names)
        except Exception as e:
            print(f"모델 목록 로드 실패: {e}")
            self.models_signal.emit([])

class OllamaInstallWorker(QThread):
    """Ollama 엔진 자체를 winget으로 설치하는 워커"""
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool)

    def run(self):
        try:
            self.log_signal.emit("<font color='cyan'>[SYSTEM] Ollama 코어 엔진 이식 시작...</font>")
            # 윈도우 패키지 매니저(winget) 호출
            process = subprocess.Popen(
                ['winget', 'install', '-e', '--id', 'Ollama.Ollama', '--accept-source-agreements', '--accept-package-agreements'], 
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, 
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            for line in process.stdout:
                if line.strip():
                    self.log_signal.emit(f"<font color='#7f8c8d'>[Winget] {line.strip()}</font>")
            
            process.wait()
            if process.returncode == 0:
                self.log_signal.emit("<font color='#00ff00'>✔ Ollama 엔진 설치 성공!</font>")
                self.finished_signal.emit(True)
            else:
                self.log_signal.emit(f"<font color='red'>✘ 설치 실패 (코드: {process.returncode})</font>")
                self.finished_signal.emit(False)
        except Exception as e:
            self.log_signal.emit(f"<font color='red'>✘ 설치 프로세스 오류: {str(e)}</font>")
            self.finished_signal.emit(False)

class ModelPullWorker(QThread):
    """특정 AI 모델을 온라인에서 내려받는(pull) 워커"""
    progress_signal = pyqtSignal(str, float)
    log_signal = pyqtSignal(str) # 로그 출력을 위해 추가
    finished_signal = pyqtSignal(str, bool)

    def __init__(self, model_name):
        super().__init__()
        self.model_name = model_name

    def run(self):
        try:
            self.log_signal.emit(f"<font color='yellow'>[소환] {self.model_name} 모델 다운로드 시작...</font>")
            
            # stream=True를 사용해 실시간으로 진행률 수신
            for progress in ollama.pull(self.model_name, stream=True):
                if 'total' in progress and 'completed' in progress:
                    percent = (progress['completed'] / progress['total']) * 100
                    self.progress_signal.emit(self.model_name, percent)
                
                # 상태 메시지가 바뀔 때마다 로그 전송 (다운로드 중, 파일 병합 중 등)
                if 'status' in progress:
                    status_msg = progress['status']
                    if status_msg == 'success':
                        self.progress_signal.emit(self.model_name, 100.0)
                        self.log_signal.emit(f"<font color='#00ff00'>✔ {self.model_name} 소환 완료!</font>")
                    
            self.finished_signal.emit(self.model_name, True)
        except Exception as e:
            self.log_signal.emit(f"<font color='red'>✘ {self.model_name} 소환 실패: {str(e)}</font>")
            self.finished_signal.emit(self.model_name, False)