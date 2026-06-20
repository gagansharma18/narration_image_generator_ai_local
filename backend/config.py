import os
import json
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = WORKSPACE_DIR / "config.json"
OUTPUT_DIR = WORKSPACE_DIR / "outputs"
MODELS_CACHE_DIR = WORKSPACE_DIR / "models_cache"

DEFAULT_CONFIG = {
    "hf_token": "",
    "selected_text_model": "Qwen/Qwen2.5-0.5B-Instruct",
    "selected_image_model": "stabilityai/sd-turbo",
    "num_inference_steps": 1,  # Default for sd-turbo
    "guidance_scale": 0.0,      # Default for sd-turbo (usually 0.0 or 1.0)
    "use_gpu": False,
    "llm_provider": "local",
    "ollama_url": "http://localhost:11434",
    "ollama_model": "qwen2.5:3b",
    "openai_url": "http://localhost:1234/v1",
    "openai_model": "qwen2.5-3b-instruct"
}

def load_config():
    config = DEFAULT_CONFIG
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                loaded = json.load(f)
                config = {**DEFAULT_CONFIG, **loaded}
        except Exception:
            pass
            
    # Set the token environment variable for global authentication
    hf_token = config.get("hf_token", "")
    if hf_token:
        os.environ["HF_TOKEN"] = hf_token
    elif "HF_TOKEN" in os.environ:
        del os.environ["HF_TOKEN"]
        
    return config

def save_config(config_data):
    config = load_config()
    for key, value in config_data.items():
        if key in DEFAULT_CONFIG:
            config[key] = value
            
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)
        
    # Keep the environment variable in sync after saving
    hf_token = config.get("hf_token", "")
    if hf_token:
        os.environ["HF_TOKEN"] = hf_token
    elif "HF_TOKEN" in os.environ:
        del os.environ["HF_TOKEN"]
        
    return config

# Ensure directories exist
OUTPUT_DIR.mkdir(exist_ok=True)
MODELS_CACHE_DIR.mkdir(exist_ok=True)

# Set HF cache dir env variable to our local models_cache folder
os.environ["HF_HOME"] = str(MODELS_CACHE_DIR)
