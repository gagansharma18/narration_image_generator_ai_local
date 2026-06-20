import threading
import time
import os
import json
from pathlib import Path
from huggingface_hub import HfApi, snapshot_download
import huggingface_hub.utils.tqdm
from backend.config import MODELS_CACHE_DIR, load_config
import tqdm
from backend.logger import add_log

# Monkey-patch tqdm to safely track download progress without scanning files on Windows
_original_update = tqdm.tqdm.update

# Global trackers for active download repository and accumulated bytes
active_download_repo = None
downloaded_bytes_accumulator = 0
download_status = {}
last_saved_time = 0
cancelled_repos = set()

REGISTRY_FILE = MODELS_CACHE_DIR / "download_registry.json"

def cancel_download(repo_id: str):
    global cancelled_repos
    cancelled_repos.add(repo_id)
    if repo_id in download_status:
        download_status[repo_id]["status"] = "interrupted"
        download_status[repo_id]["error"] = "Download cancelled by user."
    add_log(f"Received request to cancel download for '{repo_id}'", "downloader", "WARNING")


DEFAULT_MODEL_SIZES = {
    "Qwen/Qwen2.5-0.5B-Instruct": 999604166,
    "meta-llama/Llama-3.2-1B-Instruct": 2420000000,
    "TinyLlama/TinyLlama-1.1B-Chat-v1.0": 2200000000,
    "Qwen/Qwen2.5-1.5B-Instruct": 2800000000,
    "Qwen/Qwen2.5-3B-Instruct": 5800000000,
    "Qwen/Qwen3-4B-Instruct": 7900000000,
    "meta-llama/Llama-3.2-3B-Instruct": 6200000000,
    "stabilityai/sd-turbo": 2000000000,
    "runwayml/stable-diffusion-v1-5": 4270000000,
    "Lykon/dreamshaper-8": 4270000000,
    "stabilityai/sdxl-turbo": 6900000000
}

def load_registry() -> dict:
    if not REGISTRY_FILE.exists():
        return {}
    try:
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading download registry: {e}")
        return {}

def save_registry(registry: dict):
    try:
        MODELS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        temp_file = REGISTRY_FILE.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=4)
        os.replace(temp_file, REGISTRY_FILE)
    except Exception as e:
        print(f"Error saving download registry: {e}")

def patched_update(self, n=1):
    global downloaded_bytes_accumulator, last_saved_time
    _original_update(self, n)
    try:
        # Avoid crashing if n is None
        if n is None:
            n = 0
        repo = active_download_repo
        if repo and repo in cancelled_repos:
            raise RuntimeError(f"Download of model '{repo}' was cancelled by the user.")
        if repo and repo in download_status:
            downloaded_bytes_accumulator += n
            downloaded = downloaded_bytes_accumulator
            total = download_status[repo]["total_size"]
            if total > 0:
                progress = (downloaded / total) * 100
                download_status[repo]["progress"] = min(99.0, progress)
                download_status[repo]["downloaded"] = downloaded
                
                # Periodically save progress to the persistent registry file
                current_time = time.time()
                if current_time - last_saved_time > 5.0:
                    last_saved_time = current_time
                    registry = load_registry()
                    registry[repo] = {
                        "status": "downloading",
                        "progress": min(99.0, progress),
                        "downloaded": downloaded,
                        "total_size": total
                    }
                    save_registry(registry)
                    add_log(f"Downloading '{repo}': {downloaded / 1024 / 1024:.1f}MB of {total / 1024 / 1024:.1f}MB ({progress:.2f}%)", "downloader")
    except Exception as e:
        if repo and repo in cancelled_repos:
            raise e
        print(f"Exception in tqdm monkey-patch update: {e}")

tqdm.tqdm.update = patched_update
huggingface_hub.utils.tqdm.update = patched_update

def get_repo_folder_name(repo_id: str) -> str:
    # huggingface_hub caches in hub/models--org--repo_name
    safe_name = repo_id.replace("/", "--")
    return f"models--{safe_name}"

def get_directory_size(path: Path) -> int:
    total_size = 0
    if not path.exists():
        return 0
    seen_real_paths = set()
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            try:
                # Resolve symlinks to get the real file in blobs and avoid duplicate counting
                real_fp = os.path.realpath(fp)
                if real_fp not in seen_real_paths:
                    seen_real_paths.add(real_fp)
                    if os.path.exists(real_fp) and not real_fp.endswith(".incomplete"):
                        total_size += os.path.getsize(real_fp)
            except OSError:
                pass
    return total_size

def download_worker(repo_id: str, hf_token: str):
    global active_download_repo, downloaded_bytes_accumulator
    active_download_repo = repo_id
    
    # Calculate size of already completed files in cache to set the initial accumulator
    repo_dir = MODELS_CACHE_DIR / "hub" / get_repo_folder_name(repo_id)
    snapshots_dir = repo_dir / "snapshots"
    downloaded_bytes_accumulator = get_directory_size(snapshots_dir)
    
    add_log(f"Starting background download thread for model '{repo_id}'...", "downloader")
    if downloaded_bytes_accumulator > 0:
        add_log(f"Found {downloaded_bytes_accumulator / 1024 / 1024:.1f}MB already completed in snapshots cache.", "downloader")
        
    try:
        download_status[repo_id]["status"] = "fetching_info"
        add_log(f"Fetching metadata for '{repo_id}' from Hugging Face Hub...", "downloader")
        
        # Save initial state in registry
        registry = load_registry()
        registry[repo_id] = {
            "status": "fetching_info",
            "progress": 0.0,
            "downloaded": 0,
            "total_size": 0
        }
        save_registry(registry)
        
        # Get repository files info to calculate total size
        api = HfApi()
        model_info = api.model_info(repo_id, token=hf_token if hf_token else None, files_metadata=True)
        
        # Calculate total size of all files in repository
        total_size = sum(sibling.size for sibling in model_info.siblings if sibling.size is not None)
        # Fallback if size not available
        if total_size == 0:
            if repo_id in DEFAULT_MODEL_SIZES:
                total_size = DEFAULT_MODEL_SIZES[repo_id]
            else:
                total_size = 3 * 1024 * 1024 * 1024  # Estimate 3GB if unknown
            
        download_status[repo_id]["total_size"] = total_size
        download_status[repo_id]["status"] = "downloading"
        
        add_log(f"Total model size to download/verify is {total_size / 1024 / 1024:.1f}MB.", "downloader")
        
        # Update registry with total size
        registry = load_registry()
        registry[repo_id]["status"] = "downloading"
        registry[repo_id]["total_size"] = total_size
        save_registry(registry)
        
        # Perform actual download
        # snapshot_download will check cache and download missing files
        add_log(f"Starting Hugging Face Hub download (this checks cached files and fetches remaining chunks)...", "downloader")
        snapshot_download(
            repo_id=repo_id,
            token=hf_token if hf_token else None,
            local_files_only=False
        )
        
        # Success!
        download_status[repo_id]["status"] = "completed"
        download_status[repo_id]["progress"] = 100.0
        download_status[repo_id]["downloaded"] = total_size
        
        add_log(f"Successfully finished downloading and verifying model '{repo_id}'!", "downloader")
        
        registry = load_registry()
        registry[repo_id] = {
            "status": "completed",
            "progress": 100.0,
            "downloaded": total_size,
            "total_size": total_size
        }
        save_registry(registry)
        
    except Exception as e:
        is_cancelled = repo_id in cancelled_repos
        status = "interrupted" if is_cancelled else "failed"
        err_msg = "Download cancelled by user." if is_cancelled else str(e)
        
        download_status[repo_id]["status"] = status
        download_status[repo_id]["error"] = err_msg
        
        if is_cancelled:
            add_log(f"Model download for '{repo_id}' was cancelled by the user.", "downloader", "WARNING")
        else:
            add_log(f"Error downloading model '{repo_id}': {e}", "downloader", "ERROR")
        
        registry = load_registry()
        registry[repo_id] = {
            "status": status,
            "progress": download_status[repo_id].get("progress", 0.0),
            "downloaded": download_status[repo_id].get("downloaded", 0),
            "total_size": download_status[repo_id].get("total_size", 0),
            "error": err_msg
        }
        save_registry(registry)
    finally:
        if active_download_repo == repo_id:
            active_download_repo = None
            downloaded_bytes_accumulator = 0

def trigger_download(repo_id: str):
    config = load_config()
    hf_token = config.get("hf_token", "")
    
    if repo_id in cancelled_repos:
        cancelled_repos.remove(repo_id)
        
    if repo_id in download_status and download_status[repo_id]["status"] in ["downloading", "fetching_info"]:
        add_log(f"Model '{repo_id}' is already actively downloading/fetching metadata.", "downloader", "WARNING")
        return download_status[repo_id]
        
    download_status[repo_id] = {
        "progress": 0.0,
        "status": "queued",
        "total_size": 0,
        "downloaded": 0,
        "error": None
    }
    
    add_log(f"Queued model download for '{repo_id}'. Initializing download thread...", "downloader")
    thread = threading.Thread(target=download_worker, args=(repo_id, hf_token), daemon=True)
    thread.start()
    return download_status[repo_id]

def get_download_status(repo_id: str):
    repo_dir = MODELS_CACHE_DIR / "hub" / get_repo_folder_name(repo_id)
    snapshots_dir = repo_dir / "snapshots"
    
    # 1. If active in memory
    if repo_id in download_status:
        return download_status[repo_id]
        
    # 2. Look up in persistent registry
    registry = load_registry()
    if repo_id in registry:
        entry = registry[repo_id]
        status = entry.get("status", "not_started")
        
        # If it was left in downloading/fetching_info state but we are not active, it's interrupted
        if status in ["downloading", "fetching_info"]:
            status = "interrupted"
            
        # Verify if files still exist
        if status == "completed":
            if not (snapshots_dir.exists() and any(snapshots_dir.iterdir())):
                status = "not_started"
                entry["progress"] = 0.0
                entry["downloaded"] = 0
                entry["total_size"] = 0
                
        return {
            "progress": entry.get("progress", 0.0),
            "status": status,
            "total_size": entry.get("total_size", 0),
            "downloaded": entry.get("downloaded", 0),
            "error": entry.get("error", None)
        }
        
    # 3. Fallback for pre-cached directories (not in registry)
    if snapshots_dir.exists() and any(snapshots_dir.iterdir()):
        folder_size = get_directory_size(snapshots_dir)
        
        # Check if it's a default model and matches expected size
        if repo_id in DEFAULT_MODEL_SIZES:
            expected_size = DEFAULT_MODEL_SIZES[repo_id]
            if folder_size > 0.9 * expected_size:
                # Add to registry to save state
                registry[repo_id] = {
                    "status": "completed",
                    "progress": 100.0,
                    "downloaded": folder_size,
                    "total_size": folder_size
                }
                save_registry(registry)
                return {
                    "progress": 100.0,
                    "status": "completed",
                    "total_size": folder_size,
                    "downloaded": folder_size,
                    "error": None
                }
            else:
                progress = min(99.0, (folder_size / expected_size) * 100)
                registry[repo_id] = {
                    "status": "interrupted",
                    "progress": progress,
                    "downloaded": folder_size,
                    "total_size": expected_size
                }
                save_registry(registry)
                return {
                    "progress": progress,
                    "status": "interrupted",
                    "total_size": expected_size,
                    "downloaded": folder_size,
                    "error": None
                }
        else:
            # Custom model downloaded before this feature - default to completed
            registry[repo_id] = {
                "status": "completed",
                "progress": 100.0,
                "downloaded": folder_size,
                "total_size": folder_size
            }
            save_registry(registry)
            return {
                "progress": 100.0,
                "status": "completed",
                "total_size": folder_size,
                "downloaded": folder_size,
                "error": None
            }
            
    # Default fallback
    return {
        "progress": 0.0,
        "status": "not_started",
        "total_size": 0,
        "downloaded": 0,
        "error": None
    }

