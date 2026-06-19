import threading
from datetime import datetime

LOGS_HISTORY = []
LOGS_LOCK = threading.Lock()
MAX_LOGS = 200

def add_log(message: str, category: str = "system", level: str = "INFO"):
    try:
        global LOGS_HISTORY
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = {
            "timestamp": timestamp,
            "category": category,
            "level": level,
            "message": message
        }
        
        # Print to console for server logs, replacing unencodable characters safely
        import sys
        log_str = f"[{timestamp}] [{level.upper()}] [{category.upper()}] {message}"
        try:
            enc = sys.stdout.encoding or "utf-8"
            print(log_str.encode(enc, errors="replace").decode(enc), flush=True)
        except (UnicodeEncodeError, OSError):
            try:
                # Fallback to ascii replacing if console raises charmap error
                print(log_str.encode("ascii", errors="replace").decode("ascii"), flush=True)
            except Exception:
                pass
        except Exception:
            pass
        
        with LOGS_LOCK:
            LOGS_HISTORY.append(log_entry)
            if len(LOGS_HISTORY) > MAX_LOGS:
                LOGS_HISTORY.pop(0)
    except Exception as e:
        # Ensure logging failures never crash the caller
        try:
            print(f"LOGGER ERROR: {e}", flush=True)
        except Exception:
            pass

def get_logs() -> list:
    with LOGS_LOCK:
        return list(LOGS_HISTORY)

def clear_logs():
    global LOGS_HISTORY
    with LOGS_LOCK:
        LOGS_HISTORY.clear()
        # Add initial clear confirmation log
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        LOGS_HISTORY.append({
            "timestamp": timestamp,
            "category": "system",
            "level": "INFO",
            "message": "Log window cleared."
        })
