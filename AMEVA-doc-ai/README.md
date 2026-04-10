# AMEVA Doc AI

Ollama 기반 오프라인 통합 문서 처리 및 AI 요약 애플리케이션입니다. 인터넷 연결 없이 로컬 환경에서 안전하게 문서를 변환하고 요약합니다.

## ✨ 주요 기능
- **다양한 문서 지원**: HWP, HWPX, Word, Excel, PPT 파일을 완벽하게 텍스트로 추출 및 파싱합니다.
- **오프라인 PDF 변환**: 추출된 데이터를 깔끔한 양식의 PDF로 로컬 환경에서 즉시 렌더링합니다.
- **AI 문서 요약**: 선택한 모델을 이용해 긴 문서를 2,000자 청크 단위로 나누어 지능적으로 요약합니다.
- **Ollama 환경 구축**: Ollama 코어 설치 유무를 감지하고, 버튼 클릭만으로 설치 및 모델 관리를 할 수 있는 UI를 제공합니다.

## 🚀 설치 방법
1. \git clone https://github.com/uno-km/AMEVA-Doc-AI.git\
2. 필수 패키지 설치: \pip install -r requirements.txt\ (또는 \pip install PyQt6 reportlab docx openpyxl python-pptx olefile ollama psutil gputil\)
3. 앱 실행: \python main.py\

## 🛠 구조
- \core/\: 문서 파싱 및 PDF 생성 관련 코어 로직
- \ui/\: 모듈화된 UI 디자인 (메인 윈도우, 모델 매니저)
- \workers/\: PyQt 비동기 처리를 위한 Thread 기반 워커 클래스 모음
