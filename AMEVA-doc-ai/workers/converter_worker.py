import os, time, ollama
from PyQt6.QtCore import QThread, pyqtSignal
from core.document_parser import DocumentParser
from core.pdf_generator import PDFGenerator

class ConverterWorker(QThread):
    progress_signal = pyqtSignal(int)
    log_signal = pyqtSignal(str)
    stream_signal = pyqtSignal(str)
    status_msg_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(int)

    def __init__(self, files_data, dest, model):
        super().__init__()
        self.files_data = files_data  
        self.dest = dest
        self.model = model
        self.chunk_size = 2000

    def split_text(self, text, size):
        chunks = []
        while len(text) > size:
            idx = text.rfind('\n', 0, size)
            if idx == -1: idx = size 
            chunks.append(text[:idx].strip())
            text = text[idx:].strip()
        if text: chunks.append(text)
        return chunks

    def run(self):
        success = 0
        for i, file_item in enumerate(self.files_data):
            try:
                target_file = file_item['path']
                do_summary = file_item['summarize']
                filename = os.path.basename(target_file)
                name_only = os.path.splitext(filename)[0]
                
                self.log_signal.emit(f"<b>[{i+1}/{len(self.files_data)}] {filename}</b> 분석 및 변환 시작")
                raw_text = DocumentParser.extract_all_text(target_file)
                total_chars = len(raw_text)
                
                if total_chars == 0:
                    self.log_signal.emit(f"<font color='red'>✘ 텍스트를 추출하지 못했습니다.</font>")
                    continue

                self.status_msg_signal.emit(f"📄 [{filename}] 기본 PDF 변환 중...")
                base_pdf_path = os.path.join(self.dest, f"{name_only}_Converted.pdf")
                PDFGenerator.save_to_pdf(raw_text, base_pdf_path)
                self.log_signal.emit(f"<font color='#00ff00'>✔ 기본 PDF 변환 완료</font>")

                if do_summary:
                    chunks = self.split_text(raw_text, self.chunk_size)
                    total_chunks = len(chunks)
                    self.log_signal.emit(f"📊 [요약 작업] 총 {total_chars:,}자 | {total_chunks}개 행렬로 분할됨")
                    full_refined_text = f"# {name_only} AI 요약 보고서\n\n"
                    
                    for idx, chunk in enumerate(chunks):
                        current_chunk_num = idx + 1
                        self.status_msg_signal.emit(f"🧠 [{filename}] 요약 추출 중... ({current_chunk_num}/{total_chunks})")
                        self.log_signal.emit(f"<font color='#3498db'>--- 섹션 {current_chunk_num}/{total_chunks} 요약 중 ---</font>")
                        
                        prompt = f"너는 전문 문서 정제 및 요약 전문가야. 핵심만 요약해줘.\n\n원문 데이터:\n{chunk}"
                        max_retries = 3
                        for attempt in range(max_retries):
                            try:
                                stream = ollama.chat(model=self.model, messages=[{'role': 'user', 'content': prompt}], stream=True, options={'num_ctx': 2048, 'temperature': 0.3})
                                for chunk_res in stream:
                                    content = chunk_res['message']['content']
                                    full_refined_text += content
                                    self.stream_signal.emit(content)
                                full_refined_text += "\n\n"
                                break 
                            except Exception as stream_e:
                                if attempt < max_retries - 1:
                                    self.log_signal.emit(f"<font color='#f39c12'>⚠ 엔진 과부하 (500 에러). 5초 대기 후 재시도... ({attempt+1}/{max_retries})</font>")
                                    time.sleep(5) 
                                else:
                                    self.log_signal.emit(f"<font color='red'>✘ 섹션 {current_chunk_num} 요약 실패.</font>")
                                    full_refined_text += f"\n\n[{current_chunk_num}번 섹션 요약 누락]\n\n"

                    self.status_msg_signal.emit(f"📄 [{filename}] 통합 요약본 PDF 렌더링 중...")
                    summary_pdf_path = os.path.join(self.dest, f"{name_only}_AI_Summary.pdf")
                    PDFGenerator.save_to_pdf(full_refined_text, summary_pdf_path)
                    self.log_signal.emit(f"<font color='#00ff00'>✔ AI 요약본 PDF 생성 완료</font>")
                
                success += 1
                self.progress_signal.emit(int(((i + 1) / len(self.files_data)) * 100))
            except Exception as e:
                self.log_signal.emit(f"<font color='red'><b>✘ 에러 발생 (강제 중지): {str(e)}</b></font>")
                self.status_msg_signal.emit("🔴 에러 발생: 작업 중지")
                break

        if success == len(self.files_data): self.status_msg_signal.emit("✅ 작업 완료")
        self.finished_signal.emit(success)