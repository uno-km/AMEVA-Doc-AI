import os, time, psutil, math
import concurrent.futures
from PyQt6.QtCore import QThread, pyqtSignal
import ollama
from core.document_parser import DocumentParser
from core.pdf_generator import PDFGenerator

class PoliceWorker(QThread):
    log_signal = pyqtSignal(str)
    alert_signal = pyqtSignal(str)

    def __init__(self, states, thread_count):
        super().__init__()
        self.states = states
        self.thread_count = thread_count
        self.running = True

    def run(self):
        process = psutil.Process(os.getpid())
        while self.running:
            time.sleep(10)
            if not self.running: break
            
            self.log_signal.emit("<font color='#e67e22'>[경찰] 👮 진행점검중...</font>")
            
            active_threads = 0
            reports = [] # 각 프로세서별 상세 보고를 담을 리스트
            
            for t_id, state in self.states.items():
                if state['do']:
                    active_threads += 1
                    # 현재 몇 번째 청크를 작업 중인지 리포트 생성 (예: P-1: [2/5] 작업중)
                    reports.append(f"P-{t_id}: [{state['current']}/{state['total']}]")
                    
                    if time.time() - state['time'] > 300:
                        self.alert_signal.emit(f"프로세서 {t_id} 응답 없음 (작업 강제 중단)")
                        self.running = False
                        return
            
            try: mem_usage = process.memory_info().rss / (1024 * 1024)
            except: mem_usage = 0.0
            
            if active_threads > 0:
                report_str = " | ".join(reports)
                self.log_signal.emit(f"<font color='#f1c40f'>[보고] ➔ {report_str} (앱 메모리: {mem_usage:.1f}MB)</font>")
            else:
                self.log_signal.emit(f"<font color='#f1c40f'>[보고] ➔ 모든 프로세서 대기 중 (앱 메모리: {mem_usage:.1f}MB)</font>")

class ConverterWorker(QThread):
    progress_signal = pyqtSignal(int)
    log_signal = pyqtSignal(str)
    stream_signal = pyqtSignal(str)
    status_msg_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(int)

    def __init__(self, files_data, dest, model, thread_count=2):
        super().__init__()
        self.files_data = files_data  
        self.dest = dest
        self.model = model
        self.chunk_size = 1500
        self.thread_count = thread_count
        self.is_aborted = False
        
        # 프로세서별 상태 (current: 현재 진행 중인 인덱스, total: 할당된 총 개수 추가)
        self.worker_states = {
            i: {'do': False, 'time': time.time(), 'chunk_id': -1, 'current': 0, 'total': 0} 
            for i in range(1, self.thread_count + 1)
        }

    def abort_task(self, reason):
        self.is_aborted = True
        self.log_signal.emit(f"<font color='red'>[긴급] {reason}</font>")

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
        police = PoliceWorker(self.worker_states, self.thread_count)
        police.log_signal.connect(self.log_signal)
        police.alert_signal.connect(self.abort_task)
        police.start()

        for file_idx, file_item in enumerate(self.files_data):
            if self.is_aborted: break
            try:
                target_file = file_item['path']
                do_summary = file_item['summarize']
                filename = os.path.basename(target_file)
                name_only = os.path.splitext(filename)[0]
                
                self.log_signal.emit(f"<hr><b>[{file_idx+1}/{len(self.files_data)}] {filename}</b> 분석 및 변환 시작")
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
                    
                    chunks_per_thread = math.ceil(total_chunks / self.thread_count)
                    chunk_groups = []
                    
                    # 각 프로세서에 할당량 지정
                    for i in range(self.thread_count):
                        start_idx = i * chunks_per_thread
                        end_idx = min(start_idx + chunks_per_thread, total_chunks)
                        if start_idx < total_chunks:
                            group = [(start_idx + j, chunks[start_idx + j]) for j in range(end_idx - start_idx)]
                            chunk_groups.append((i + 1, group))
                            # 상태 객체에 본인이 처리해야 할 총 할당량(total) 저장!
                            self.worker_states[i + 1]['total'] = len(group)
                            
                    self.log_signal.emit(f"📊 [요약] 총 {total_chars:,}자 | {total_chunks}개 청크를 {len(chunk_groups)}개 묶음으로 나누어 동시 처리합니다.")
                    
                    results_dict = {} 
                    completed_chunks = 0
                    
                    def process_group(group_data):
                        nonlocal completed_chunks
                        thread_id, group = group_data
                        group_results = []
                        
                        # 그룹 내의 청크를 순서대로 처리
                        for idx_in_group, (c_idx, c_text) in enumerate(group):
                            if self.is_aborted: break
                            
                            # 경찰 보고용 상태 업데이트 (현재 n번째 작업 중)
                            self.worker_states[thread_id]['do'] = True
                            self.worker_states[thread_id]['time'] = time.time()
                            self.worker_states[thread_id]['chunk_id'] = c_idx
                            self.worker_states[thread_id]['current'] = idx_in_group + 1
                            
                            self.stream_signal.emit(f"  ▶ [P-{thread_id}] 청크 {c_idx+1}/{total_chunks} ➔ 요약 중...\n")

                            res_text = ""
                            try:
                                prompt = f"너는 최고 수준의 학술 문서 요약 전문가야. 아래 [문서 내용]이 아무리 복잡한 논문이거나 빈칸, 표 데이터로 가득 차 있더라도 절대 핑계대지 말고 핵심을 정리해서 한국어로 요약해. 사과문 금지. 표 데이터는 마크다운 유지.\n\n[문서 내용]\n{c_text}"
                                response = ollama.chat(model=self.model, messages=[{'role': 'user', 'content': prompt}])
                                if 'message' in response and 'content' in response['message']:
                                    res_text = response['message']['content']
                                    self.stream_signal.emit(f"  ✅ [P-{thread_id}] 청크 {c_idx+1} 완료!\n")
                                else:
                                    res_text = f"\n[AI 빈 응답]\n"
                            except Exception as e:
                                res_text = f"\n[오류: {str(e)}]\n"
                                self.stream_signal.emit(f"  ❌ [P-{thread_id}] 청크 {c_idx+1} 오류: {str(e)}\n")

                            group_results.append((c_idx, res_text))
                            completed_chunks += 1
                            
                            base_prog = (file_idx / len(self.files_data)) * 100
                            chunk_prog = (completed_chunks / total_chunks) * (100 / len(self.files_data))
                            self.progress_signal.emit(int(base_prog + chunk_prog))
                            
                            self.worker_states[thread_id]['do'] = False
                            self.worker_states[thread_id]['time'] = time.time()

                        return thread_id, group_results

                    with concurrent.futures.ThreadPoolExecutor(max_workers=self.thread_count) as executor:
                        futures = [executor.submit(process_group, g) for g in chunk_groups]
                        for future in concurrent.futures.as_completed(futures):
                            if self.is_aborted: 
                                executor.shutdown(wait=False, cancel_futures=True)
                                break
                            try:
                                t_id, g_results = future.result()
                                results_dict[t_id] = g_results
                            except Exception as exc: pass

                    if self.is_aborted: break
                    
                    final_ordered_chunks = []
                    for t_id in sorted(results_dict.keys()):
                        for c_idx, text in results_dict[t_id]:
                            final_ordered_chunks.append(text)

                    full_refined_text = f"# {name_only} AI 요약 보고서\n\n" + "\n\n".join(filter(None, final_ordered_chunks))

                    self.status_msg_signal.emit(f"📄 [{filename}] 통합 요약본 PDF 렌더링 중...")
                    summary_pdf_path = os.path.join(self.dest, f"{name_only}_AI_Summary.pdf")
                    PDFGenerator.save_to_pdf(full_refined_text, summary_pdf_path)
                    self.log_signal.emit(f"<font color='#00ff00'>✔ AI 요약본 PDF 생성 완료 (순서 병합 성공)</font>")
                
                success += 1
                self.progress_signal.emit(int(((file_idx + 1) / len(self.files_data)) * 100))
            except Exception as e:
                self.log_signal.emit(f"<font color='red'><b>✘ 에러 발생: {str(e)}</b></font>")
                self.status_msg_signal.emit("🔴 에러 발생: 작업 중지")
                break

        police.running = False
        police.wait()
        
        if success == len(self.files_data): self.status_msg_signal.emit("✅ 작업 완료")
        self.finished_signal.emit(success)
