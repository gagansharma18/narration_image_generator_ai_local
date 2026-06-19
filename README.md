# Paint Storyboard AI — Local YouTube Script Image Generator

Paint Storyboard AI is a full-stack local web application designed to help creators turn timestamped YouTube scripts into funny, intentionally amateur "MS Paint" style storyboards. It runs completely locally on your machine, leveraging local LLMs and diffusion models downloaded from Hugging Face Hub.

---

## Features

- **Local LLM Scene Parsing**: Parses YouTube scripts (with or without timestamps) and automatically generates visual scene descriptions utilizing lightweight, fast local text models.
- **Local Text-to-Image Pipeline**: Uses single-step diffusion models (like `SD-Turbo` / `SDXL-Turbo`) or standard models to produce 16:9 widescreen drawings on CPU or GPU.
- **Configurable Settings**: Quick sidebar settings to paste Hugging Face credentials, adjust inference steps, or tune guidance scales.
- **Model Download Manager**: Live downloads monitor showing repository sizes and real-time download status.
- **Storyboard Output Grid**: Inspect individual scene frames, expand to full-screen preview, and compile your final storyboard as a unified ZIP archive.

---

## File Structure

```
narration_image_generator_ai_local/
├── backend/
│   ├── config.py         # Config loader and caches setup
│   ├── downloader.py     # tqdm monkey-patched HF download manager
│   ├── llm_handler.py    # Local text LLM parsing
│   ├── image_handler.py  # Local Diffusers image generator
│   └── main.py           # FastAPI single-port router and static files host
├── frontend/
│   ├── src/
│   │   ├── App.jsx       # Workspace steps, modals, and settings controls
│   │   ├── index.css     # Dark glassmorphism layout & theme styles
│   │   └── main.jsx      # React entrypoint
│   ├── index.html        # SEO Title configuration
│   └── vite.config.js    # Local dev proxy configurations
├── config.example.json   # Template configurations file
├── .gitignore            # Excludes caches, builds, and keys
└── README.md             # Setup guide
```

---

## Installation & Setup

### 1. Prerequisites
- **Python**: 3.10+ (tested up to 3.14)
- **Node.js**: 18+ (with `npm`)

### 2. Install Python Dependencies
Install required packages for deep learning, diffusers, and web servers:
```bash
pip install torch diffusers transformers accelerate fastapi uvicorn huggingface_hub pillow safetensors
```

### 3. Setup Configuration
To prevent your credentials from being committed to source control, `config.json` is excluded via git. Create a local copy from the example template:
```bash
cp config.example.json config.json
```
Edit `config.json` and insert your **Hugging Face User Token** in `"hf_token"`. You can grab yours at [https://huggingface.co/settings/tokens](https://huggingface.co/settings/tokens).

### 4. Build Frontend Assets
Navigate to the frontend folder, install dependencies, and build the static assets:
```bash
cd frontend
npm install
npm run build
cd ..
```

---

## Running the Application

Start the unified server from the root of the project:
```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
This boots uvicorn on port `8000`. Since it mounts the React build, the entire application is served at:
**[http://localhost:8000](http://localhost:8000)**

---

## Models Guidelines & Hardware Recommendations

All default models are fully open-source/open-weights models hosted on Hugging Face (no external paid APIs required). They are selected to run comfortably within a **10GB VRAM limit** when GPU acceleration is active.

### Running on CPU (Lightweight Default)
- **Image Generation**: `stabilityai/sd-turbo` (Size: 2.0 GB, runs in 1 step, generating images in ~10–20 seconds on CPU).
- **Text Generation**: `Qwen/Qwen2.5-0.5B-Instruct` (Size: 0.9 GB, extremely fast CPU execution) or `TinyLlama/TinyLlama-1.1B-Chat-v1.0` (Size: 2.2 GB).

### Running on GPU (CUDA Acceleration, < 10GB VRAM)
If CUDA is available on your machine (`torch.cuda.is_available()`), the backend will automatically load models in half-precision `float16` and partition model layers onto the GPU VRAM for fast generation:
- **Text Generation Models**: 
  - `meta-llama/Llama-3.2-1B-Instruct` [Download Size: 2.2 GB]
  - `TinyLlama/TinyLlama-1.1B-Chat-v1.0` [Download Size: 2.2 GB]
  - `Qwen/Qwen2.5-1.5B-Instruct` [Download Size: 2.8 GB]
  - `Qwen/Qwen2.5-3B-Instruct` [Download Size: 5.8 GB]
  - `meta-llama/Llama-3.2-3B-Instruct` [Download Size: 6.2 GB]
- **Image Generation Models**:
  - `stabilityai/sd-turbo` (Fastest 1-step) [Download Size: 2.0 GB]
  - `runwayml/stable-diffusion-v1-5` (Standard) [Download Size: 4.2 GB]
  - `Lykon/dreamshaper-8` (Stylized) [Download Size: 4.2 GB]
  - `stabilityai/sdxl-turbo` (High Quality 1-step) [Download Size: 6.9 GB]


