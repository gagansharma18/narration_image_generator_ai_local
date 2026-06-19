import threading
import time
import os
from pathlib import Path
from huggingface_hub import HfApi, snapshot_download
from backend.config import MODELS_CACHE_DIR, load_config
import tqdm

# Monkey-patch tqdm to safely track download progress without scanning files on Windows
_original_update = tqdm.tqdm.update

# Mappings from thread ID to repo ID and downloaded byte counts
thread_active_repo = {}
thread_downloaded_bytes = {}
download_status = {}

def patched_update(self, n=1):
    _original_update(self, n)
    try:
        thread_id = threading.get_ident()
        if thread_id in thread_downloaded_bytes:
            thread_downloaded_bytes[thread_id] += n
            repo_id = thread_active_repo.get(thread_id)
            if repo_id and repo_id in download_status:
                downloaded = thread_downloaded_bytes[thread_id]
                total = download_status[repo_id]["total_size"]
                if total > 0:
                    progress = (downloaded / total) * 100
                    download_status[repo_id]["progress"] = min(99.0, progress)
                    download_status[repo_id]["downloaded"] = downloaded
    except Exception:
        pass

tqdm.tqdm.update = patched_update

def get_repo_folder_name(repo_id: str) -> str:
    # huggingface_hub caches in hub/models--org--repo_name
    safe_name = repo_id.replace("/", "--")
    return f"models--{safe_name}"

def get_directory_size(path: Path) -> int:
    total_size = 0
    if not path.exists():
        return 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            # Skip symlinks to avoid duplicate counting
            if not os.path.islink(fp):
                try:
                    total_size += os.path.getsize(fp)
                except OSError:
                    pass
    return total_size

def download_worker(repo_id: str, hf_token: str):
    thread_id = threading.get_ident()
    thread_active_repo[thread_id] = repo_id
    thread_downloaded_bytes[thread_id] = 0
    try:
        download_status[repo_id]["status"] = "fetching_info"
        
        # Get repository files info to calculate total size
        api = HfApi()
        model_info = api.model_info(repo_id, token=hf_token if hf_token else None)
        
        # Calculate total size of all files in repository
        total_size = sum(sibling.size for sibling in model_info.siblings if sibling.size is not None)
        # Fallback if size not available
        if total_size == 0:
            total_size = 3 * 1024 * 1024 * 1024  # Estimate 3GB if unknown
            
        download_status[repo_id]["total_size"] = total_size
        download_status[repo_id]["status"] = "downloading"
        
        # Perform actual download
        # snapshot_download will check cache and download missing files
        snapshot_download(
            repo_id=repo_id,
            token=hf_token if hf_token else None,
            local_files_only=False
        )
        
        # Success!
        download_status[repo_id]["status"] = "completed"
        download_status[repo_id]["progress"] = 100.0
        download_status[repo_id]["downloaded"] = total_size
        
    except Exception as e:
        download_status[repo_id]["status"] = "failed"
        download_status[repo_id]["error"] = str(e)
        print(f"Error downloading {repo_id}: {e}")
    finally:
        # Clean up thread variables
        thread_active_repo.pop(thread_id, None)
        thread_downloaded_bytes.pop(thread_id, None)

def trigger_download(repo_id: str):
    config = load_config()
    hf_token = config.get("hf_token", "")
    
    if repo_id in download_status and download_status[repo_id]["status"] in ["downloading", "fetching_info"]:
        return download_status[repo_id]
        
    download_status[repo_id] = {
        "progress": 0.0,
        "status": "queued",
        "total_size": 0,
        "downloaded": 0,
        "error": None
    }
    
    thread = threading.Thread(target=download_worker, args=(repo_id, hf_token), daemon=True)
    thread.start()
    return download_status[repo_id]

def get_download_status(repo_id: str):
    # Check if directory exists and download_status does not have it, we can say it is completed
    repo_dir = MODELS_CACHE_DIR / "hub" / get_repo_folder_name(repo_id)
    
    if repo_id not in download_status:
        # Check if snapshots exist and are populated
        snapshots_dir = repo_dir / "snapshots"
        if snapshots_dir.exists() and any(snapshots_dir.iterdir()):
            return {
                "progress": 100.0,
                "status": "completed",
                "total_size": get_directory_size(repo_dir),
                "downloaded": get_directory_size(repo_dir),
                "error": None
            }
        else:
            return {
                "progress": 0.0,
                "status": "not_started",
                "total_size": 0,
                "downloaded": 0,
                "error": None
            }
            
    return download_status[repo_id]

