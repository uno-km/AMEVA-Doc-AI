import os, time, psutil, math, re, asyncio
import concurrent.futures
from datetime import datetime
from PyQt6.QtCore import QThread, pyqtSignal
import ollama
import edge_tts
from core.document_parser import DocumentParser
from core.pdf_generator import PDFGenerator

class PoliceWorker(QThread):
    log_signal = pyqtSignal(str)
    alert_signal = pyqtSignal(str)

    def __init__(self, states, shared_data):
        super().__init__()
        self.states = states
        self.shared = shared_data
        self.running = True

    def run(self):
        process = psutil.Process(os.getpid())
        while self.running:
            time.sleep(10)
            if not self.running: break
            
            battery = psutil.sensors_battery()
            if battery and not battery.power_plugged and self.shared['active_threads'] > 2:
                self.log_signal.emit("<font color='red'>🚨 [경찰] 배터리 모드 감지! VRAM/전력 보호를 위해 P-3~8 프로세서를 강제 대기(휴식)시킵니다.</font>")
                moved_chunks = 0
                for i in range(3, self.shared['initial_threads'] + 1):
                    if not self.shared['retire_flags'][i]:
                        self.shared['retire_flags'][i] = True
                        self.states[i]['dead'] = True
                        while self.shared['chunk_queues'][i]:
                            c_idx, c_text = self.shared['chunk_queues'][i].pop(0)
                            self.shared['chunk_queues'][2].append((c_idx, c_text))
                            moved_chunks += 1
                if moved_chunks > 0:
                    self.shared['chunk_queues'][2].sort(key=lambda x: x[0])
                    self.states[2]['total'] += moved_chunks
                    self.log_signal.emit(f"<font color='#f39c12'>🔄 [경찰] P-3 이상의 잔여 청크 {moved_chunks}개를 P-2로 이관 완료.</font>")
                self.shared['active_threads'] = 2

            active_counts = 0
            reports = []
            for t_id, state in self.states.items():
                if state.get('dead', False): pass
                elif state['do']:
                    active_counts += 1
                    reports.append(f"P-{t_id}: [{state['current']}/{state['total']}]")
                    if time.time() - state['time'] > 300:
                        self.states[t_id]['dead'] = True
                        self.alert_signal.emit(f"🚨 프로세서 P-{t_id} 타임아웃 (사망)")
            
            try: mem_usage = process.memory_info().rss / (1024 * 1024)
            except: mem_usage = 0.0
            
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            elapsed = time.time() - self.shared['start_time']
            power_w = 15.0 + (cpu * 0.4) + (ram * 0.1)
            power_wh = power_w * (elapsed / 3600.0)
            curr_tokens = self.shared['total_tokens']
            
            if active_counts > 0 or reports:
                report_str = " | ".join(reports)
                self.log_signal.emit(f"<font color='#f1c40f'>[보고] ➔ {report_str}<br>&nbsp;&nbsp;&nbsp;╰─ (앱: {mem_usage:.1f}MB | ⚡전력: {power_wh:.4f}Wh | 🪙토큰: {curr_tokens:,}T)</font>")

class ConverterWorker(QThread):
    progress_signal = pyqtSignal(int)
    log_signal = pyqtSignal(str)
    stream_signal = pyqtSignal(int, str)
    status_msg_signal = pyqtSignal(str)
    file_done_signal = pyqtSignal(int, dict) 
    file_start_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(int)
    worker_state_signal = pyqtSignal(int, bool, int, int, bool)
    rag_ready_signal = pyqtSignal(str)

    def __init__(self, files_data, dest, model, thread_count=2, do_tts=False):
        super().__init__()
        self.files_data = files_data  
        self.dest = dest
        self.model = model
        self.chunk_size = 1500
        self.thread_count = thread_count
        self.do_tts = do_tts
        self.is_aborted = False
        
        self.worker_states = {
            i: {'do': False, 'time': time.time(), 'chunk_id': -1, 'current': 0, 'total': 0, 'dead': False} 
            for i in range(1, self.thread_count + 1)
        }
        
        self.shared_data = {
            'initial_threads': thread_count,
            'active_threads': thread_count,
            'start_time': time.time(),
            'total_tokens': 0,
            'chunk_queues': {i: [] for i in range(1, thread_count + 1)},
            'retire_flags': {i: False for i in range(1, thread_count + 1)}
        }

    def format_size(self, size_bytes):
        if size_bytes == 0: return "0 B"
        size_name = ("B", "KB", "MB", "GB")
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_name[i]}"

    def abort_task(self, reason):
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

    def generate_audio(self, text, path):
        """비동기 edge-tts를 동기 방식으로 호출하는 래퍼 함수"""
        async def _generate():
            communicate = edge_tts.Communicate(text, "ko-KR-SunHiNeural")
            await communicate.save(path)
        asyncio.run(_generate())

    def run(self):
        success = 0
        police = PoliceWorker(self.worker_states, self.shared_data)
        police.log_signal.connect(self.log_signal)
        police.alert_signal.connect(self.abort_task)
        police.start()

        for file_idx, file_item in enumerate(self.files_data):
            if self.is_aborted: break
            if file_item.get('is_done', False): continue
                
            try:
                self.file_start_signal.emit(file_idx)
                target_file = file_item['path']
                do_summary = file_item['summarize']
                filename = os.path.basename(target_file)
                name_only = os.path.splitext(filename)[0]
                
                self.shared_data['start_time'] = time.time()
                self.shared_data['total_tokens'] = 0
                output_paths = {'base': None, 'summary': None, 'audio': None}
                
                self.log_signal.emit(f"<hr><b>[{file_idx+1}/{len(self.files_data)}] {filename}</b> 분석 시작")
                raw_text = DocumentParser.extract_all_text(target_file)
                total_chars = len(raw_text)
                
                if total_chars == 0:
                    raise Exception("텍스트를 추출하지 못했습니다.")

                self.status_msg_signal.emit(f"📄 [{filename}] 기본 PDF 변환 중...")
                base_pdf_path = os.path.normpath(os.path.join(self.dest, f"{name_only}_Converted.pdf"))
                PDFGenerator.save_to_pdf(raw_text, base_pdf_path)
                output_paths['base'] = base_pdf_path
                self.log_signal.emit(f"<font color='#00ff00'>✔ 기본 PDF 변환 완료</font>")

                full_refined_text = raw_text[:3000]

                if do_summary:
                    chunks = self.split_text(raw_text, self.chunk_size)
                    total_chunks = len(chunks)
                    chunks_per_thread = math.ceil(total_chunks / self.thread_count)
                    
                    for i in range(1, self.thread_count + 1):
                        self.shared_data['chunk_queues'][i] = []
                        self.shared_data['retire_flags'][i] = False
                        self.worker_states[i]['dead'] = False
                        
                    for i in range(self.thread_count):
                        start_idx = i * chunks_per_thread
                        end_idx = min(start_idx + chunks_per_thread, total_chunks)
                        if start_idx < total_chunks:
                            group = [(start_idx + j, chunks[start_idx + j]) for j in range(end_idx - start_idx)]
                            self.shared_data['chunk_queues'][i+1] = group
                            self.worker_states[i+1]['total'] = len(group)
                            
                    self.log_signal.emit(f"📊 총 {total_chars:,}자 | {total_chunks}개 청크 분배 완료.")
                    
                    results_dict = {} 
                    completed_chunks = 0
                    
                    def process_queue(t_id):
                        nonlocal completed_chunks
                        group_results = []
                        idx_in_group = 0
                        
                        while True:
                            if self.is_aborted or self.shared_data['retire_flags'][t_id]: break
                            if len(self.shared_data['chunk_queues'][t_id]) == 0: break
                                
                            c_idx, c_text = self.shared_data['chunk_queues'][t_id].pop(0)
                            curr = idx_in_group + 1
                            total = self.worker_states[t_id]['total']
                            self.worker_states[t_id]['do'] = True
                            self.worker_states[t_id]['time'] = time.time()
                            self.worker_states[t_id]['chunk_id'] = c_idx
                            self.worker_states[t_id]['current'] = curr
                            
                            self.worker_state_signal.emit(t_id, True, curr, total, False)
                            self.stream_signal.emit(t_id, f"\n\n▶ [P-{t_id}] 청크 {c_idx+1}/{total_chunks} 요약 시작...\n")

                            res_text = ""
                            try:
                                prompt = f"너는 최고 수준의 학술 문서 요약 전문가야. 아래 [문서 내용]이 아무리 복잡한 논문이거나 빈칸, 표 데이터로 가득 차 있더라도 절대 핑계대지 말고 핵심을 정리해서 한국어로 요약해. 사과문 금지. 표 데이터는 마크다운 유지.\n\n[문서 내용]\n{c_text}"
                                stream = ollama.chat(model=self.model, messages=[{'role': 'user', 'content': prompt}], stream=True)
                                
                                for chunk_res in stream:
                                    content = chunk_res.get('message', {}).get('content', '')
                                    res_text += content
                                    self.stream_signal.emit(t_id, content)
                                    if chunk_res.get('done'):
                                        self.shared_data['total_tokens'] += chunk_res.get('prompt_eval_count', 0) + chunk_res.get('eval_count', 0)
                                
                                self.stream_signal.emit(t_id, f"\n✅ [P-{t_id}] 완료!\n")
                            except Exception as e:
                                res_text = f"\n[오류: {str(e)}]\n"
                                self.stream_signal.emit(t_id, f"\n❌ [P-{t_id}] 오류: {str(e)}\n")
                                self.worker_states[t_id]['dead'] = True
                                self.worker_state_signal.emit(t_id, False, curr, total, True)

                            group_results.append((c_idx, res_text))
                            completed_chunks += 1
                            idx_in_group += 1
                            
                            self.progress_signal.emit(int((file_idx / len(self.files_data)) * 100 + (completed_chunks / total_chunks) * (100 / len(self.files_data))))
                            
                            if not self.worker_states[t_id].get('dead', False):
                                self.worker_states[t_id]['do'] = False
                                self.worker_states[t_id]['time'] = time.time()
                                self.worker_state_signal.emit(t_id, False, curr, total, False)

                        return t_id, group_results

                    with concurrent.futures.ThreadPoolExecutor(max_workers=self.thread_count) as executor:
                        futures = [executor.submit(process_queue, i) for i in range(1, self.thread_count + 1)]
                        for future in concurrent.futures.as_completed(futures):
                            if self.is_aborted: break
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
                    summary_pdf_path = os.path.normpath(os.path.join(self.dest, f"{name_only}_AI_Summary.pdf"))
                    PDFGenerator.save_to_pdf(full_refined_text, summary_pdf_path)
                    output_paths['summary'] = summary_pdf_path

                # ★ [핵심] 외부 명령어(subprocess)가 아닌 파이썬 자체 API로 MP3 생성
                if self.do_tts:
                    self.status_msg_signal.emit(f"🎧 [{filename}] 오디오북(MP3) 생성 중...")
                    self.log_signal.emit(f"<font color='#3498db'>🎧 오디오북(MP3) 추출을 시작합니다. (VRAM 미사용)</font>")
                    
                    audio_path = os.path.normpath(os.path.join(self.dest, f"{name_only}_Audio.mp3"))
                    
                    # 텍스트에서 특수문자 완벽 클리닝
                    clean_text_for_tts = re.sub(r'[*#|_|\[\]<>]', ' ', full_refined_text)
                    clean_text_for_tts = re.sub(r'[^\w\s\.\,\?\!가-힣]', ' ', clean_text_for_tts)
                    clean_text_for_tts = re.sub(r'\s+', ' ', clean_text_for_tts)
                    
                    try:
                        self.generate_audio(clean_text_for_tts, audio_path)
                        output_paths['audio'] = audio_path
                        self.log_signal.emit(f"<font color='#00ff00'>✔ 오디오북(MP3) 생성 완료</font>")
                    except Exception as e:
                        self.log_signal.emit(f"<font color='#e74c3c'>✘ 오디오북 생성 실패 (내부 API 에러: {str(e)})</font>")

                file_end_time = time.time()
                duration = file_end_time - self.shared_data['start_time']
                avg_cpu = psutil.cpu_percent()
                avg_ram = psutil.virtual_memory().percent
                
                est_power_w = 15.0 + (avg_cpu * 0.4) + (avg_ram * 0.1)
                est_energy_wh = est_power_w * (duration / 3600.0)

                orig_size = self.format_size(os.path.getsize(target_file))
                base_size = self.format_size(os.path.getsize(output_paths['base'])) if output_paths['base'] else "N/A"
                summary_size = self.format_size(os.path.getsize(output_paths['summary'])) if output_paths['summary'] else "N/A"
                audio_size = self.format_size(os.path.getsize(output_paths['audio'])) if output_paths['audio'] else "N/A"
                
                timestamp_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                
                report = f"""<br><div style='background-color:#1e272e; padding:10px; border-radius:5px; border-left:4px solid #2ecc71;'>
                <b style='color:#f39c12; font-size:14px;'>[🧾 파일 작업 완료 리포트]</b><br><br>
                • <b>⏰ 완료시간:</b> {timestamp_str} (총 {duration:.2f}초 소요)<br>
                • <b>🧠 구동모델:</b> {self.model} (초기 스레드 {self.thread_count}개 ➔ 최종 {self.shared_data['active_threads']}개)<br>
                • <b>⚡ 소모토큰:</b> 총 {self.shared_data['total_tokens']:,} Tokens<br>
                • <b>🔋 추정전력:</b> 약 {est_energy_wh:.5f} Wh 소모<br><hr style='border:1px dashed #555;'>
                • <b>📁 원본파일:</b> {filename} ({orig_size})<br>
                • <b>📄 기본결과:</b> {os.path.basename(output_paths['base'])} ({base_size})<br>"""
                
                if do_summary: report += f"• <b>📑 요약결과:</b> {os.path.basename(output_paths['summary'])} ({summary_size})<br>"
                if self.do_tts and output_paths['audio']: report += f"• <b>🎧 오디오북:</b> {os.path.basename(output_paths['audio'])} ({audio_size})<br>"
                    
                report += f"• <b>💾 저장위치:</b> {self.dest}<br><br>"
                report += f"<b>💡 상태코드:</b> <font color='#2ecc71'>[200 OK] 성공적으로 완료되었습니다.</font></div><br>"
                
                self.log_signal.emit(report)
                self.rag_ready_signal.emit(full_refined_text)
                
                success += 1
                self.file_done_signal.emit(file_idx, output_paths)
                
            except Exception as e:
                timestamp_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                error_report = f"""<br><div style='background-color:#2c3e50; padding:10px; border-radius:5px; border-left:4px solid #e74c3c;'>
                <b style='color:#e74c3c; font-size:14px;'>[🚨 치명적 오류 리포트]</b><br><br>
                • <b>⏰ 발생시간:</b> {timestamp_str}<br>
                • <b>📁 대상파일:</b> {os.path.basename(target_file)}<br><br>
                <b>💡 에러코드:</b> <font color='#f1c40f'>[500 ERROR] {str(e)}</font></div><br>"""
                
                self.log_signal.emit(error_report)
                self.status_msg_signal.emit("🔴 에러 발생: 작업 중지")
                break

        police.running = False
        police.wait()
        
        self.status_msg_signal.emit("✅ 모든 할당 작업 완료")
        self.finished_signal.emit(success)

class OllamaChatWorker(QThread):
    stream_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()
    
    def __init__(self, model, messages):
        super().__init__()
        self.model = model
        self.messages = messages
        
    def run(self):
        try:
            stream = ollama.chat(model=self.model, messages=self.messages, stream=True, options={'num_ctx': 8192})
            for chunk in stream:
                content = chunk.get('message', {}).get('content', '')
                self.stream_signal.emit(content)
        except Exception as e:
            self.stream_signal.emit(f"\n[오류 발생: {str(e)}]")
        finally:
            self.finished_signal.emit()
