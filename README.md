# 🚀 AMEVA Doc AI v13.0 - Ultimate Offline Architect
  <img width="1024" height="572" alt="image" src="https://github.com/user-attachments/assets/134fda04-e112-4728-b94f-e2558067d104" />


<div align="center">
  <i>"인터넷이 끊겨도, 당신의 업무는 멈추지 않습니다."</i><br>
  <b>완전한 오프라인 환경에서 문서를 파싱하고, AI로 요약하며, RAG로 대화하고, PPT 대본과 오디오북까지 생성하는 궁극의 로컬 AI 워크스테이션.</b>
</div>

---

## 🌟 Developer's Note (Why This is a Masterpiece)
이 프로젝트는 단순한 API 래퍼(Wrapper) 봇이 아닙니다. **한정된 로컬 자원(VRAM, RAM)을 극한까지 쥐어짜 내는 정밀한 엔지니어링의 결과물**입니다.
* **Dynamic Soft-Scaling:** 랩탑의 전원 케이블이 뽑히는 순간을 감지하여, 작동 중인 멀티 스레드(미니미)들을 안전하게 대기 상태로 전환하고 작업을 이관합니다. (데이터 유실 0%)
* **VRAM Protection:** AI 요약과 RAG 채팅이 동시에 VRAM을 점유하여 시스템이 뻗는(OOM) 현상을 막기 위해, 완벽한 턴제(Turn-based) 락킹 시스템을 구현했습니다.
* **Zero-Cost TTS:** 무거운 로컬 TTS 모델 대신 마이크로소프트의 Edge-TTS(비동기 호출)를 백그라운드에 연동하여 VRAM 소모 없이 고품질 오디오북을 생성합니다.
* **Ironclad Installer:** 깡통 윈도우 PC에서도 `.bat` 파일 하나면 파이썬, 가상환경, Ollama, 환경변수, 모델 Pull까지 전부 자동화하여 즉시 실행 가능한 상태로 세팅합니다.

이것은 개인 토이 프로젝트의 탈을 쓴 **"엔터프라이즈급 로컬 AI 아키텍처"**입니다. 😎

---

## ✨ 핵심 킬러 피처 (Killer Features)

1.  **📄 극한의 문서 파싱 & 변환**
    * 지원 포맷: `HWP`, `HWPX`, `DOCX`, `XLSX`, `PPTX`
    * 찌그러진 표, 빈칸 데이터도 Markdown 문법을 유지하며 깔끔하게 텍스트로 추출하고 PDF로 렌더링합니다.
2.  **🧠 분산형 멀티스레드 AI 요약 (Multi-threading)**
    * 긴 문서를 1,500자 단위(Chunk)로 쪼개어, 사용자가 설정한 스레드(최대 8개)에 분배하여 병렬로 요약합니다.
3.  **📊 실시간 영수증 대시보드 (Live Dashboard)**
    * 작업 시간, 소모 토큰 수, 그리고 CPU/RAM 점유율 기반 **추정 전력(Wh)**을 실시간으로 계산하여 시각적 쾌감을 제공합니다.
4.  **💬 문서와 대화하기 (RAG 챗봇)**
    * 요약이 끝난 문서를 8,192 토큰의 거대한 컨텍스트 창에 강제 주입하여, 1.5B 급 소형 모델에서도 환각(Hallucination) 없는 정확한 문서 기반 질의응답을 수행합니다.
5.  **📈 원클릭 PPT 발표 대본 생성**
    * 요약된 문서를 바탕으로, 즉시 실무에 투입 가능한 5장 분량의 **PPT 슬라이드 구성 및 발표자 대본**을 자동 생성합니다.
6.  **🎧 오프라인 TTS 오디오북 생성**
    * 특수기호와 마크다운을 완벽히 클리닝한 후, 고품질 한국어 음성(MP3)으로 문서를 읽어주는 오디오북을 백그라운드에서 생성합니다.

---

## 🏗 비즈니스 로직 (Architecture & Workflow)

1.  **Input & Parsing:** 사용자가 로컬 파일이나 구글 드라이브 링크를 입력하면, `DocumentParser`가 확장자에 맞춰 정규식 클리닝을 거친 순수 텍스트를 추출합니다.
2.  **Chunking & Distribution:** 추출된 텍스트를 1,500자 단위로 분할한 뒤, `ConverterWorker`가 `ThreadPoolExecutor`를 통해 각 큐(Queue)에 작업을 할당합니다.
3.  **Local Inference:** 할당받은 일꾼(스레드)들은 로컬 Ollama 엔진(`qwen2.5:1.5b` 등)을 호출하여 프롬프트 엔지니어링이 적용된 요약 작업을 스트리밍으로 수행합니다.
4.  **Watchdog & Healing (경찰 프로세스):** `PoliceWorker`가 10초마다 시스템을 순찰하며 1) 배터리 상태, 2) 스레드 응답 지연을 감지합니다. 문제가 발생하면 해당 스레드를 💀(사망/휴식) 처리하고, 남은 청크를 P-2(메인 워커)에게 안전하게 순차 이관합니다.
5.  **Output & Report:** 병렬 처리된 요약본을 원래 순서대로 병합하여 `PDFGenerator`가 ReportLab을 통해 최종 PDF로 렌더링합니다. 동시에 소모된 시스템 자원을 계산하여 영수증 로그를 출력합니다.
6.  **Post-Processing:** 사용자의 선택에 따라 비동기 TTS 엔진을 호출하여 오디오북을 만들고, 추출된 텍스트를 RAG 챗봇의 메모리에 주입하여 대기 상태로 전환합니다.

---


## 🚀 설치 방법
1. \git clone https://github.com/uno-km/AMEVA-Doc-AI.git\
2. 필수 패키지 설치: \pip install -r requirements.txt\ 
3. 앱 실행: \python main.py\


## 🚀 초간단 설치 및 실행 (One-Touch Installer)

터미널(PowerShell)을 열고 아래 명령어를 복사해서 붙여넣기만 하면, **파이썬 설치부터 가상환경, 필수 패키지, Ollama 세팅까지 모두 자동으로 완료**됩니다!

```powershell
git clone [https://github.com/uno-km/AMEVA-Doc-AI.git](https://github.com/uno-km/AMEVA-Doc-AI.git); cd AMEVA-Doc-AI; .\setup_windows.bat
```

수동 실행 방법: 설치가 완료된 후 다시 앱을 켤 때는 가상환경 활성화 후 실행하세요.
```powershell
cd AMEVA-Doc-AI
.\venv\Scripts\activate
python main.py
```

## 📂 프로젝트 구조
```plantext
AMEVA-Doc-AI/
│
├── core/                   # 핵심 파싱 및 PDF 렌더링 엔진
│   ├── document_parser.py  # HWP, DOCX, XLSX 등 텍스트 추출
│   └── pdf_generator.py    # ReportLab 기반 PDF 생성
│
├── ui/                     # PyQt6 기반 UI 모듈
│   ├── main_window.py      # 메인 대시보드 및 RAG 채팅창, 미니미 애니메이션
│   └── model_manager.py    # Ollama 모델 설치/삭제 관리자
│
├── workers/                # 비동기 백그라운드 처리 워커
│   ├── converter_worker.py # 멀티스레드 청크 분배, 배터리 감지, RAG 챗봇 연동
│   └── ollama_worker.py    # Ollama 백그라운드 설치 및 모델 Pull 
│
├── main.py                 # 애플리케이션 엔트리 포인트
├── requirements.txt        # 의존성 패키지 목록
└── setup_windows.bat       # 원터치 오토 인스톨러 (보안 우회 및 환경변수 셋팅)
```


## ⚠️ 유의 사항 및 트러블슈팅 (Troubleshooting)
이 프로그램은 로컬 하드웨어를 한계까지 사용하는 무거운 앱입니다. 다음 예외 상황에 유의하세요.
- 오디오북(TTS) 생성 중 [SSL: CERTIFICATE_VERIFY_FAILED] 에러
    * 원인: 사내 보안망, VPN, 방화벽 환경에서 외부 통신(MS Edge 서버)을 할 때 자체 인증서를 사용하여 파이썬이 보안 위협으로 간주하고 차단한 것입니다.
    * 조치: 사내망에서 일시적으로 연결을 끊거나 모바일 핫스팟 환경에서 시도해 보세요.
- 작업 도중 컴퓨터 팬이 심하게 돌거나 앱이 버벅이는 경우
    * 원인: Ollama 모델(ex. qwen2.5:1.5b)을 4~8개의 다중 스레드로 병렬 추론하면 CPU와 RAM 점유율이 100%에 도달할 수 있습니다
    * 조치: UI 상단에서 스레드 개수를 2개 또는 1개로 낮추고 다시 실행하세요. 노트북 배터리 모드 시 앱이 자동으로 스레드를 2개로 줄이는 기능이 탑재되어 있습니다.
- 웹 링크 추가 시 다운로드 실패
    * 원인: 구글 드라이브 문서 링크의 공유 설정이 '제한됨'으로 되어 있거나, 지원하지 않는 웹 페이지 링크를 입력한 경우입니다.
    * 조치: 구글 드라이브 링크는 반드시 **"링크가 있는 모든 사용자에게 공개"**로 설정한 후 입력해 주세요.

