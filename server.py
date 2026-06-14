import os
import re
import time
import json
import asyncio
import threading
import tempfile
import urllib.request
import urllib.parse
import psutil
import GPUtil
import ollama
import edge_tts
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Form, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from core.document_parser import DocumentParser
from core.pdf_generator import PDFGenerator

app = FastAPI(title="AMEVA Doc AI Backend")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables for system stats and tracking
current_rag_context = ""
active_websocket = None

# System profiling utility
def get_hardware_specs():
    try:
        ram = psutil.virtual_memory().total / (1024**3)
        cpu_cores = psutil.cpu_count()
        gpus = GPUtil.getGPUs()
        gpu_name = gpus[0].name if gpus else "None"
        vram = gpus[0].memoryTotal if gpus else 0
    except Exception:
        ram = 8.0
        cpu_cores = 4
        gpu_name = "None"
        vram = 0

    # Auto mapping models based on hardware profile
    if gpu_name != "None" and vram >= 6000:
        recommended_pm = "llama3.1:8b"
        recommended_dev = "qwen2.5-coder:7b"
        mode = "GPU 가속 활성 (NVIDIA GPU)"
    else:
        recommended_pm = "qwen2.5:1.5b"
        recommended_dev = "gemma2:2b"
        mode = "CPU 전용 모드"

    return {
        "cpu_cores": cpu_cores,
        "ram_gb": round(ram, 1),
        "gpu_name": gpu_name,
        "vram_mb": vram,
        "mode": mode,
        "recommended_pm": recommended_pm,
        "recommended_dev": recommended_dev
    }

@app.get("/api/specs")
def api_specs():
    return get_hardware_specs()

@app.get("/api/models")
def list_models():
    try:
        models_info = ollama.list()
        models_list = models_info.models if hasattr(models_info, 'models') else models_info.get('models', [])
        installed = []
        for m in models_list:
            name = m.get('name', '') if isinstance(m, dict) else getattr(m, 'model', getattr(m, 'name', ''))
            size = m.get('size', 0) if isinstance(m, dict) else getattr(m, 'size', 0)
            installed.append({"name": name, "size_gb": round(size / (1024**3), 2)})
        return {"installed": installed}
    except Exception as e:
        return {"installed": [], "error": str(e)}

@app.post("/api/models/pull")
async def pull_model(model_name: str = Form(...)):
    async def event_generator():
        try:
            yield f"data: {json.dumps({'status': 'start', 'message': f'{model_name} 다운로드 시작...'})}\n\n"
            # Since ollama.pull is blocking, run in executor
            loop = asyncio.get_event_loop()
            def sync_pull():
                return list(ollama.pull(model_name, stream=True))
            
            # Streaming pull response
            stream = await loop.run_in_executor(None, lambda: ollama.pull(model_name, stream=True))
            for progress in stream:
                percent = 0.0
                if 'total' in progress and 'completed' in progress:
                    percent = (progress['completed'] / progress['total']) * 100
                
                status_msg = progress.get('status', 'Downloading')
                yield f"data: {json.dumps({'status': 'progress', 'percent': percent, 'message': status_msg})}\n\n"
                await asyncio.sleep(0.1)
            
            yield f"data: {json.dumps({'status': 'success', 'message': f'{model_name} 설치 완료!'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'message': f'설치 에러: {str(e)}'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/models/delete")
def delete_model(model_name: str = Form(...)):
    try:
        ollama.delete(model_name)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        temp_dir = tempfile.gettempdir()
        filename = file.filename
        safe_filename = f"{int(time.time())}_{filename}"
        file_path = os.path.join(temp_dir, safe_filename)
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())
        return {"filename": filename, "path": file_path, "size": os.path.getsize(file_path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/download-link")
def download_link(url: str = Form(...)):
    try:
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
                else: filename = "downloaded_document.tmp"

            if is_sheet and not filename.lower().endswith('.xlsx'):
                filename = filename.replace('.tmp', '') + ".xlsx"
            if filename.lower().endswith('.tmp'):
                filename = filename.replace('.tmp', '.txt')

            temp_dir = tempfile.gettempdir()
            safe_filename = f"{int(time.time())}_{filename}"
            file_path = os.path.join(temp_dir, safe_filename)
            with open(file_path, 'wb') as f:
                f.write(response.read())
        return {"filename": filename, "path": file_path, "size": os.path.getsize(file_path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# RAG Chat Stream Endpoint
@app.post("/api/chat")
async def chat_with_docs(model: str = Form(...), messages: str = Form(...)):
    msg_list = json.loads(messages)
    
    async def chat_stream():
        try:
            # Injecting RAG context to the first prompt
            global current_rag_context
            if len(msg_list) > 0 and msg_list[0]['role'] == 'user' and current_rag_context:
                # If first message, prepend context
                first_prompt = msg_list[0]['content']
                if "다음은 내가 제공하는 [문서 내용]이야" not in first_prompt:
                    msg_list[0]['content'] = f"다음은 내가 제공하는 [문서 내용]이야. 이 내용을 바탕으로 내 [질문]에 답변해줘. 문서에 없는 내용은 모른다고 대답해.\n\n[문서 내용]\n{current_rag_context}\n\n[질문]\n{first_prompt}"
            
            loop = asyncio.get_event_loop()
            stream = await loop.run_in_executor(None, lambda: ollama.chat(model=model, messages=msg_list, stream=True, options={'num_ctx': 8192}))
            
            for chunk in stream:
                content = chunk.get('message', {}).get('content', '')
                yield content
                await asyncio.sleep(0.01)
        except Exception as e:
            yield f"\n[채팅 에러: {str(e)}]"
            
    return StreamingResponse(chat_stream(), media_type="text/plain")

# Task Management via WebSockets
@app.websocket("/ws/process")
async def process_websocket(websocket: WebSocket):
    await websocket.accept()
    global active_websocket
    active_websocket = websocket
    
    # Process management state variables
    shared_data = {
        "is_running": False,
        "aborted": False,
        "start_time": 0,
        "total_tokens": 0,
        "active_threads": 2,
        "initial_threads": 2,
        "retire_flags": {},
        "chunk_queues": {}
    }
    
    worker_states = {}

    def format_size(size_bytes):
        import math
        if size_bytes == 0: return "0 B"
        size_name = ("B", "KB", "MB", "GB")
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_name[i]}"

    async def send_to_client(data_type, payload):
        try:
            await websocket.send_json({"type": data_type, "payload": payload})
        except Exception:
            pass

    def tts_generate_wrapper(text, path):
        async def _generate():
            communicate = edge_tts.Communicate(text, "ko-KR-SunHiNeural")
            await communicate.save(path)
        try:
            asyncio.run(_generate())
        except Exception as e:
            pass

    async def stats_monitor_loop():
        # Periodically monitor resources & send updates
        process = psutil.Process(os.getpid())
        while shared_data["is_running"] and not shared_data["aborted"]:
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            gpus = GPUtil.getGPUs()
            gpu_val = int(gpus[0].load * 100) if gpus else 0
            
            # Energy / Token updates
            elapsed = time.time() - shared_data["start_time"]
            m, s = divmod(int(elapsed), 60)
            time_str = f"{m:02d}:{s:02d}"
            
            power_w = 15.0 + (cpu * 0.4) + (ram * 0.1)
            power_wh = power_w * (elapsed / 3600.0)
            
            await send_to_client("stats", {
                "cpu": cpu,
                "ram": ram,
                "gpu": gpu_val,
                "time_str": time_str,
                "power_wh": round(power_wh, 4),
                "power_w": round(power_w, 1),
                "tokens": shared_data["total_tokens"]
            })
            
            # SRE Safeguard: Memory Protection (RAM > 98%)
            if ram > 98.0:
                await send_to_client("log", "<font color='red'>🚨 [SRE 경보] 시스템 메모리(RAM)가 98%를 초과했습니다. 데이터 유실 및 크래시를 보호하기 위해 작업을 강제 중단합니다.</font>")
                shared_data["aborted"] = True
                
            await asyncio.sleep(2)

    async def police_patrol_loop():
        # Police worker simulation
        while shared_data["is_running"] and not shared_data["aborted"]:
            await asyncio.sleep(10)
            if not shared_data["is_running"] or shared_data["aborted"]: break
            
            # Check battery mode
            battery = psutil.sensors_battery()
            if battery and not battery.power_plugged and shared_data['active_threads'] > 2:
                await send_to_client("log", "<font color='red'>🚨 [경찰] 배터리 모드 감지! VRAM/전력 보호를 위해 P-3 이상의 프로세서를 강제 대기시킵니다.</font>")
                moved_chunks = 0
                for i in range(3, shared_data['initial_threads'] + 1):
                    if not shared_data['retire_flags'].get(i, False):
                        shared_data['retire_flags'][i] = True
                        worker_states[i]['dead'] = True
                        while shared_data['chunk_queues'].get(i):
                            c_idx, c_text = shared_data['chunk_queues'][i].pop(0)
                            shared_data['chunk_queues'][2].append((c_idx, c_text))
                            moved_chunks += 1
                if moved_chunks > 0:
                    shared_data['chunk_queues'][2].sort(key=lambda x: x[0])
                    worker_states[2]['total'] += moved_chunks
                    await send_to_client("log", f"<font color='#f39c12'>🔄 [경찰] P-3 이상의 잔여 청크 {moved_chunks}개를 P-2로 이관 완료.</font>")
                shared_data['active_threads'] = 2

            # Active threads progress reporting
            reports = []
            for t_id, state in list(worker_states.items()):
                if state.get('dead', False):
                    pass
                elif state['do']:
                    reports.append(f"P-{t_id}: [{state['current']}/{state['total']}]")
            
            try:
                mem_usage = psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
            except Exception:
                mem_usage = 0.0
            
            elapsed = time.time() - shared_data["start_time"]
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            power_w = 15.0 + (cpu * 0.4) + (ram * 0.1)
            power_wh = power_w * (elapsed / 3600.0)
            
            if reports:
                report_str = " | ".join(reports)
                await send_to_client("log", f"<font color='#f1c40f'>[보고] ➔ {report_str}<br>&nbsp;&nbsp;&nbsp;╰─ (앱: {mem_usage:.1f}MB | ⚡전력: {power_wh:.4f}Wh | 🪙토큰: {shared_data['total_tokens']:,}T)</font>")

    def process_file_conversion(files_data, dest, model, thread_count, do_tts):
        global current_rag_context
        import math
        import concurrent.futures
        
        shared_data["is_running"] = True
        shared_data["start_time"] = time.time()
        shared_data["total_tokens"] = 0
        shared_data["initial_threads"] = thread_count
        shared_data["active_threads"] = thread_count
        shared_data["chunk_queues"] = {i: [] for i in range(1, thread_count + 1)}
        shared_data["retire_flags"] = {i: False for i in range(1, thread_count + 1)}
        
        for i in range(1, thread_count + 1):
            worker_states[i] = {'do': False, 'time': time.time(), 'chunk_id': -1, 'current': 0, 'total': 0, 'dead': False}

        # Run async monitoring loops in background
        loop = asyncio.get_event_loop()
        stats_task = asyncio.run_coroutine_threadsafe(stats_monitor_loop(), loop)
        police_task = asyncio.run_coroutine_threadsafe(police_patrol_loop(), loop)

        success_count = 0
        
        for file_idx, file_item in enumerate(files_data):
            if shared_data["aborted"]: break
            
            try:
                # Signal file start
                asyncio.run_coroutine_threadsafe(send_to_client("file_start", {"file_idx": file_idx}), loop)
                target_file = file_item['path']
                do_summary = file_item['summarize']
                filename = os.path.basename(target_file)
                name_only = os.path.splitext(filename)[0]
                
                asyncio.run_coroutine_threadsafe(send_to_client("log", f"<hr><b>[{file_idx+1}/{len(files_data)}] {filename}</b> 분석 시작"), loop)
                raw_text = DocumentParser.extract_all_text(target_file)
                total_chars = len(raw_text)
                
                if total_chars == 0:
                    raise Exception("텍스트를 추출하지 못했습니다.")
                
                asyncio.run_coroutine_threadsafe(send_to_client("status_msg", f"📄 [{filename}] 기본 PDF 변환 중..."), loop)
                base_pdf_path = os.path.normpath(os.path.join(dest, f"{name_only}_Converted.pdf"))
                PDFGenerator.save_to_pdf(raw_text, base_pdf_path)
                
                output_paths = {
                    'base': base_pdf_path,
                    'summary': None,
                    'audio': None,
                    'base_url': f"/converted/{os.path.basename(base_pdf_path)}",
                    'summary_url': None
                }
                
                asyncio.run_coroutine_threadsafe(send_to_client("log", "<font color='#00ff00'>✔ 기본 PDF 변환 완료</font>"), loop)
                full_refined_text = raw_text[:3000]
                
                if do_summary:
                    # Split chunks
                    chunk_size = 1500
                    chunks = []
                    text_temp = raw_text
                    while len(text_temp) > chunk_size:
                        idx = text_temp.rfind('\n', 0, chunk_size)
                        if idx == -1: idx = chunk_size
                        chunks.append(text_temp[:idx].strip())
                        text_temp = text_temp[idx:].strip()
                    if text_temp: chunks.append(text_temp)
                    
                    total_chunks = len(chunks)
                    chunks_per_thread = math.ceil(total_chunks / thread_count)
                    
                    for i in range(1, thread_count + 1):
                        shared_data['chunk_queues'][i] = []
                        shared_data['retire_flags'][i] = False
                        worker_states[i]['dead'] = False
                        worker_states[i]['total'] = 0
                        worker_states[i]['current'] = 0
                        
                    for i in range(thread_count):
                        start_idx = i * chunks_per_thread
                        end_idx = min(start_idx + chunks_per_thread, total_chunks)
                        if start_idx < total_chunks:
                            group = [(start_idx + j, chunks[start_idx + j]) for j in range(end_idx - start_idx)]
                            shared_data['chunk_queues'][i+1] = group
                            worker_states[i+1]['total'] = len(group)
                            
                    asyncio.run_coroutine_threadsafe(send_to_client("log", f"📊 총 {total_chars:,}자 | {total_chunks}개 청크 분배 완료."), loop)
                    
                    results_dict = {}
                    completed_chunks = [0] # List for closure mutability
                    
                    def process_queue(t_id):
                        group_results = []
                        idx_in_group = 0
                        
                        while True:
                            if shared_data["aborted"] or shared_data['retire_flags'].get(t_id, False): break
                            if not shared_data['chunk_queues'][t_id]: break
                            
                            c_idx, c_text = shared_data['chunk_queues'][t_id].pop(0)
                            curr = idx_in_group + 1
                            total = worker_states[t_id]['total']
                            
                            worker_states[t_id]['do'] = True
                            worker_states[t_id]['time'] = time.time()
                            worker_states[t_id]['chunk_id'] = c_idx
                            worker_states[t_id]['current'] = curr
                            
                            # Emit worker state to UI
                            asyncio.run_coroutine_threadsafe(send_to_client("worker_state", {
                                "t_id": t_id, "is_working": True, "current": curr, "total": total, "is_dead": False
                            }), loop)
                            asyncio.run_coroutine_threadsafe(send_to_client("worker_stream", {
                                "t_id": t_id, "text": f"\n\n▶ [P-{t_id}] 청크 {c_idx+1}/{total_chunks} 요약 시작...\n"
                            }), loop)
                            
                            res_text = ""
                            try:
                                prompt = f"너는 최고 수준의 학술 문서 요약 전문가야. 아래 [문서 내용]이 아무리 복잡한 논문이거나 빈칸, 표 데이터로 가득 차 있더라도 절대 핑계대지 말고 핵심을 정리해서 한국어로 요약해. 사과문 금지. 표 데이터는 마크다운 유지.\n\n[문서 내용]\n{c_text}"
                                stream = ollama.chat(model=model, messages=[{'role': 'user', 'content': prompt}], stream=True)
                                
                                for chunk_res in stream:
                                    content = chunk_res.get('message', {}).get('content', '')
                                    res_text += content
                                    asyncio.run_coroutine_threadsafe(send_to_client("worker_stream", {
                                        "t_id": t_id, "text": content
                                    }), loop)
                                    if chunk_res.get('done'):
                                        shared_data['total_tokens'] += chunk_res.get('prompt_eval_count', 0) + chunk_res.get('eval_count', 0)
                                        
                                asyncio.run_coroutine_threadsafe(send_to_client("worker_stream", {
                                    "t_id": t_id, "text": f"\n✅ [P-{t_id}] 완료!\n"
                                }), loop)
                            except Exception as e:
                                res_text = f"\n[오류: {str(e)}]\n"
                                asyncio.run_coroutine_threadsafe(send_to_client("worker_stream", {
                                    "t_id": t_id, "text": f"\n❌ [P-{t_id}] 오류: {str(e)}\n"
                                }), loop)
                                worker_states[t_id]['dead'] = True
                                asyncio.run_coroutine_threadsafe(send_to_client("worker_state", {
                                    "t_id": t_id, "is_working": False, "current": curr, "total": total, "is_dead": True
                                }), loop)
                                
                            group_results.append((c_idx, res_text))
                            completed_chunks[0] += 1
                            idx_in_group += 1
                            
                            # Update global progress bar
                            progress_val = int((file_idx / len(files_data)) * 100 + (completed_chunks[0] / total_chunks) * (100 / len(files_data)))
                            asyncio.run_coroutine_threadsafe(send_to_client("progress", progress_val), loop)
                            
                            if not worker_states[t_id].get('dead', False):
                                worker_states[t_id]['do'] = False
                                worker_states[t_id]['time'] = time.time()
                                asyncio.run_coroutine_threadsafe(send_to_client("worker_state", {
                                    "t_id": t_id, "is_working": False, "current": curr, "total": total, "is_dead": False
                                }), loop)
                        return t_id, group_results

                    with concurrent.futures.ThreadPoolExecutor(max_workers=thread_count) as executor:
                        futures = [executor.submit(process_queue, i) for i in range(1, thread_count + 1)]
                        for future in concurrent.futures.as_completed(futures):
                            if shared_data["aborted"]: break
                            try:
                                t_id, g_results = future.result()
                                results_dict[t_id] = g_results
                            except Exception:
                                pass
                                
                    if shared_data["aborted"]: break
                    
                    final_ordered_chunks = []
                    for t_id in sorted(results_dict.keys()):
                        for c_idx, text in results_dict[t_id]:
                            final_ordered_chunks.append(text)
                            
                    full_refined_text = f"# {name_only} AI 요약 보고서\n\n" + "\n\n".join(filter(None, final_ordered_chunks))
                    summary_pdf_path = os.path.normpath(os.path.join(dest, f"{name_only}_AI_Summary.pdf"))
                    PDFGenerator.save_to_pdf(full_refined_text, summary_pdf_path)
                    output_paths['summary'] = summary_pdf_path
                    output_paths['summary_url'] = f"/converted/{os.path.basename(summary_pdf_path)}"
                    asyncio.run_coroutine_threadsafe(send_to_client("log", "<font color='#00ff00'>✔ 요약 PDF 생성 완료</font>"), loop)
                
                # Audio generation (TTS)
                if do_tts:
                    asyncio.run_coroutine_threadsafe(send_to_client("status_msg", f"🎧 [{filename}] 오디오북(MP3) 생성 중..."), loop)
                    asyncio.run_coroutine_threadsafe(send_to_client("log", "<font color='#3498db'>🎧 오디오북(MP3) 추출을 시작합니다. (VRAM 미사용)</font>"), loop)
                    
                    audio_path = os.path.normpath(os.path.join(dest, f"{name_only}_Audio.mp3"))
                    clean_text_for_tts = re.sub(r'[*#|_|\[\]<>]', ' ', full_refined_text)
                    clean_text_for_tts = re.sub(r'[^\w\s\.\,\?\!가-힣]', ' ', clean_text_for_tts)
                    clean_text_for_tts = re.sub(r'\s+', ' ', clean_text_for_tts)
                    
                    try:
                        tts_generate_wrapper(clean_text_for_tts, audio_path)
                        output_paths['audio'] = audio_path
                        output_paths['audio_url'] = f"/converted/{os.path.basename(audio_path)}"
                        asyncio.run_coroutine_threadsafe(send_to_client("log", "<font color='#00ff00'>✔ 오디오북(MP3) 생성 완료</font>"), loop)
                    except Exception as e:
                        asyncio.run_coroutine_threadsafe(send_to_client("log", f"<font color='#e74c3c'>✘ 오디오북 생성 실패: {str(e)}</font>"), loop)

                # Report formatting
                duration = time.time() - shared_data['start_time']
                orig_size = format_size(os.path.getsize(target_file))
                base_size = format_size(os.path.getsize(output_paths['base'])) if output_paths['base'] else "N/A"
                summary_size = format_size(os.path.getsize(output_paths['summary'])) if output_paths['summary'] else "N/A"
                audio_size = format_size(os.path.getsize(output_paths['audio'])) if output_paths['audio'] else "N/A"
                timestamp_str = datetime.now().strftime("%H:%M:%S")
                
                report = f"""<br><div style='background-color:#1e272e; padding:10px; border-radius:5px; border-left:4px solid #2ecc71; margin-bottom: 10px;'>
                <b style='color:#f39c12; font-size:14px;'>[🧾 파일 작업 완료 리포트]</b><br><br>
                • <b>⏰ 완료시간:</b> {timestamp_str} (총 {duration:.2f}초 소요)<br>
                • <b>🧠 구동모델:</b> {model} (초기 스레드 {thread_count}개 ➔ 최종 {shared_data['active_threads']}개)<br>
                • <b>⚡ 소모토큰:</b> 총 {shared_data['total_tokens']:,} Tokens<br><hr style='border:1px dashed #555;'>
                • <b>📁 원본파일:</b> {filename} ({orig_size})<br>
                • <b>📄 기본결과:</b> <a href="{output_paths['base_url']}" target="_blank" style="color:#3498db;">{os.path.basename(output_paths['base'])}</a> ({base_size})<br>"""
                
                if do_summary:
                    report += f"• <b>📑 요약결과:</b> <a href=\"{output_paths['summary_url']}\" target=\"_blank\" style=\"color:#3498db;\">{os.path.basename(output_paths['summary'])}</a> ({summary_size})<br>"
                if do_tts and output_paths['audio']:
                    report += f"• <b>🎧 오디오북:</b> <a href=\"{output_paths['audio_url']}\" target=\"_blank\" style=\"color:#3498db;\">{os.path.basename(output_paths['audio'])}</a> ({audio_size})<br>"
                    
                report += f"• <b>💾 저장위치:</b> {dest}<br><br>"
                report += f"<b>💡 상태코드:</b> <font color='#2ecc71'>[200 OK] 성공적으로 완료되었습니다.</font></div><br>"
                
                asyncio.run_coroutine_threadsafe(send_to_client("log", report), loop)
                
                # Update global RAG context
                current_rag_context = full_refined_text
                asyncio.run_coroutine_threadsafe(send_to_client("rag_ready", {"context": full_refined_text}), loop)
                
                success_count += 1
                asyncio.run_coroutine_threadsafe(send_to_client("file_done", {"file_idx": file_idx, "output_paths": output_paths}), loop)
                
            except Exception as e:
                timestamp_str = datetime.now().strftime("%H:%M:%S")
                error_report = f"""<br><div style='background-color:#2c3e50; padding:10px; border-radius:5px; border-left:4px solid #e74c3c; margin-bottom: 10px;'>
                <b style='color:#e74c3c; font-size:14px;'>[🚨 치명적 오류 리포트]</b><br><br>
                • <b>⏰ 발생시간:</b> {timestamp_str}<br>
                • <b>📁 대상파일:</b> {os.path.basename(target_file)}<br><br>
                <b>💡 에러코드:</b> <font color='#f1c40f'>[500 ERROR] {str(e)}</font></div><br>"""
                asyncio.run_coroutine_threadsafe(send_to_client("log", error_report), loop)
                asyncio.run_coroutine_threadsafe(send_to_client("status_msg", "🔴 에러 발생: 작업 중지"), loop)
                break
                
        shared_data["is_running"] = False
        asyncio.run_coroutine_threadsafe(send_to_client("finished", {"success_count": success_count}), loop)

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            action = msg.get("action")
            
            if action == "start":
                files_data = msg.get("files_data", [])
                dest = msg.get("dest", "")
                model = msg.get("model", "")
                thread_count = int(msg.get("thread_count", 2))
                do_tts = msg.get("do_tts", False)
                
                # Make sure dest exists
                os.makedirs(dest, exist_ok=True)
                
                # Mount the destination folder so user can download converted PDFs/audio files directly from UI
                app.mount("/converted", StaticFiles(directory=dest), name="converted")
                
                # Run conversion in a background native OS thread to not block event loop
                threading.Thread(
                    target=process_file_conversion, 
                    args=(files_data, dest, model, thread_count, do_tts),
                    daemon=True
                ).start()
                
            elif action == "stop":
                shared_data["aborted"] = True
                shared_data["is_running"] = False
                await send_to_client("log", "<font color='orange'>[SYSTEM] 사용자에 의해 작업이 강제 중단되었습니다.</font>")
                await send_to_client("finished", {"success_count": 0})
                
    except WebSocketDisconnect:
        shared_data["aborted"] = True
        shared_data["is_running"] = False
    finally:
        active_websocket = None

# Mount Frontend static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
