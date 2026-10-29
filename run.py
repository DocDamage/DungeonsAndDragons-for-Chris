import uvicorn
import webbrowser
import threading
import time

def open_browser():
    time.sleep(1.2)
    webbrowser.open("http://127.0.0.1:8000")

if __name__ == "__main__":
    print("==================================================")
    print("      ⚔️  DUNGEONFORGE AI RPG ENGINE  ⚔️")
    print("==================================================")
    print("Backend & UI starting at: http://127.0.0.1:8000")
    print("Press Ctrl+C to stop.")
    print("--------------------------------------------------")

    # Open browser automatically on launch
    threading.Thread(target=open_browser, daemon=True).start()

    uvicorn.run("dungeonforge.main:app", host="127.0.0.1", port=8000, reload=False)
