import webbrowser
import threading
import time
import uvicorn

def open_browser():
    # Wait for the server to spin up
    time.sleep(1.5)
    webbrowser.open("http://127.0.0.1:8000")

if __name__ == '__main__':
    print("[SYSTEM] Starting AMEVA Doc AI Web Application...")
    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run("server:app", host="127.0.0.1", port=8000, log_level="info")