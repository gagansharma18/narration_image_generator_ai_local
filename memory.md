# Project Memory — Paint Storyboard AI

This file serves as a memory snapshot and developer context guide for the **Paint Storyboard AI** project. If another AI agent or developer takes over this workspace, this document provides the complete state of the codebase, architectural highlights, and design decisions.

---

## 1. Project Overview & Objective

The goal is to build a local, web-based tool that:
1. Takes a timestamped YouTube script (e.g. `0:00 - Introduction`).
2. Leverages a local Text-generation model (LLM) downloaded from Hugging Face to parse each segment and write a descriptive visual scene description matching a specific MS Paint drawing profile.
3. Automatically triggers a local image diffusion pipeline (using models like `SD-Turbo` or `SDXL-Turbo` from Hugging Face via the `diffusers` library) to generate funny, stick-figure storyboard frames.
4. Allows adjusting configurations (token, steps, guidance scale) and downloading the finished storyboards as a ZIP.

---

## 2. Tech Stack & Architecture

- **Backend (Python / FastAPI)**:
  - Hugging Face model caching and management via `huggingface_hub`.
  - Local LLM prompt generation using `transformers` (`AutoModelForCausalLM`).
  - Local image generation using `diffusers` (`AutoPipelineForText2Image`).
  - Threaded generation queue tracking job status and segment progress.
- **Frontend (Vite / React / Vanilla CSS)**:
  - Interactive stepper-based dashboard.
  - Multi-state configuration controller (HF user tokens, inference parameters, and VRAM options).
  - Modern, dark glassmorphism theme using Vanilla CSS variables.
- **Unified Hosting Setup**:
  - The React frontend compiles static assets into `frontend/dist/`.
  - The FastAPI backend is configured to mount this `dist` folder at root `/`.
  - The entire application runs on **a single unified port** (`8000`), proxying all API requests and output images under the same port context.

---

## 3. Core Directory Layout & Roles

- [backend/config.py](file:///c:/Users/gagan/stash/narration_image_generator_ai_local/backend/config.py): Manages local paths (`outputs/` and `models_cache/`), reads/writes configurations in `config.json`, and overrides environment variable paths (`HF_HOME`).
- [backend/downloader.py](file:///c:/Users/gagan/stash/narration_image_generator_ai_local/backend/downloader.py): Handles asynchronous background downloads of HF repositories. Features custom global monkey-patching of the `tqdm` module to report exact download progress percentages directly from chunk headers.
- [backend/llm_handler.py](file:///c:/Users/gagan/stash/narration_image_generator_ai_local/backend/llm_handler.py): Handles text parsing. Features automatic GPU check; if CUDA is available, it maps text models in half-precision (`float16`) to GPU VRAM using `device_map="auto"`.
- [backend/image_handler.py](file:///c:/Users/gagan/stash/narration_image_generator_ai_local/backend/image_handler.py): Runs text-to-image pipelines with optimized dimensions, attention slicing, step limits, and device mapping.
- [backend/main.py](file:///c:/Users/gagan/stash/narration_image_generator_ai_local/backend/main.py): Exposes API routes and mounts static directories. Serves the compiled React frontend at `/`.
- [frontend/src/App.jsx](file:///c:/Users/gagan/stash/narration_image_generator_ai_local/frontend/src/App.jsx): Stepper state machine handling configurations, model caches, inputs, storyboard editing, progress tracking, and media modals.
- [frontend/src/index.css](file:///c:/Users/gagan/stash/narration_image_generator_ai_local/frontend/src/index.css): Core design tokens, layout grids, scrollbar layouts, and modern glass cards.
- [config.example.json](file:///c:/Users/gagan/stash/narration_image_generator_ai_local/config.example.json): Configuration template file.
- [.gitignore](file:///c:/Users/gagan/stash/narration_image_generator_ai_local/.gitignore): Excludes large weights repositories, generated static PNG files, raw node modules, and active user tokens.

---

## 4. Key Engineering Decisions & Workarounds

### A. Windows File Access Locks (`WinError 32`)
- **Problem**: Scanning the cache directory size recursively via `os.walk` to compute download progress held locks on directories, which caused the downloader process to fail with file access errors when renaming `.incomplete` files on Windows.
- **Solution**: Patched `tqdm.tqdm.update` globally at startup in `downloader.py` to accumulate downloaded byte counts. Folder recursive scanning is completely bypassed during active downloads.

### B. GPU/CPU Scaling & 10GB VRAM Constraint
- All selectable Hugging Face models are fully open weights (free, run locally, no API keys).
- Text and Image generation modules check `torch.cuda.is_available()`. If GPU acceleration is enabled, models are loaded using `device_map="auto"` in `float16`.
- Models are capped at <= 3B params for Text models and <= 7B params for Image models (like SDXL-Turbo) to fit comfortably within **10GB of VRAM**.
- **Model Menu**:
  - `Qwen 2.5 0.5B Instruct` `[Disk: 0.9 GB | VRAM: ~1.5 GB]`
  - `Llama 3.2 1B Instruct` `[Disk: 2.2 GB | VRAM: ~2.5 GB]`
  - `TinyLlama 1.1B Chat` `[Disk: 2.2 GB | VRAM: ~2.5 GB]`
  - `Qwen 2.5 1.5B Instruct` `[Disk: 2.8 GB | VRAM: ~3.5 GB]`
  - `Qwen 2.5 3B Instruct` `[Disk: 5.8 GB | VRAM: ~6.5 GB]`
  - `Llama 3.2 3B Instruct` `[Disk: 6.2 GB | VRAM: ~7.0 GB]`
  - `SD Turbo` `[Disk: 2.0 GB | VRAM: ~3.0 GB]`
  - `Stable Diffusion v1.5` `[Disk: 4.2 GB | VRAM: ~4.5 GB]`
  - `DreamShaper 8` `[Disk: 4.2 GB | VRAM: ~4.5 GB]`
  - `SDXL Turbo` `[Disk: 6.9 GB | VRAM: ~7.5 GB]`

### C. Real-Time Status via Server-Sent Events (SSE)
- **Problem**: Client-side interval polling (`setInterval`) for model downloads and image generation jobs was chatty, resource-intensive, and out-of-sync.
- **Solution**: Replaced polling with standard Server-Sent Events (`SSE`). The backend in `main.py` exposes a single `/api/stream` endpoint returning a `StreamingResponse` (yielding JSON-serialized states). The React frontend binds to it using `EventSource`. This provides smooth, low-latency, real-time progress updates without client-side query loops.

### D. Download Registry & Resume Flow
- **Problem**: Large model downloads (0.5GB to 5GB+) were lost if the application closed or the backend server crashed mid-download, requiring a complete download restart.
- **Solution**: Added `models_cache/download_registry.json`. On start, the server queries snapshot directories to see what files are already fully downloaded (skipping them). During resume, progress accumulator starts at the size of completed files, and the monkey-patched `tqdm` automatically registers resumed ranges, allowing the UI progress bar to jump directly to the correct starting offset.
- **Robustness**: Writes to registry are saved atomically using a temporary file and `os.replace` to prevent file corruption/truncation on sudden shutdowns.

### E. Real-Time System Log Terminal Console
- **Problem**: Generation jobs and local model loads take significant time, and the user had no visual cues of what the model was doing at any given second.
- **Solution**: Created a thread-safe global in-memory log buffer (`backend/logger.py`) and injected log statements in all pipelines (downloader, prompt parser, image renderer, config updater). The logs are serialized and pushed to the frontend via the `/api/stream` SSE channel. The React frontend visualizes them in a glassmorphic monospaced terminal at the bottom of the workspace, complete with category-specific coloring and filter controls.
- **Robustness (Unicode print error safety)**: The logging function is fully wrapped in exception handlers. When printing logs to standard output, CP1252-based Windows terminals can throw `UnicodeEncodeError` or `OSError` if messages contain emojis (like clipboard `📋`) or foreign characters. `add_log` intercepts print failures and falls back to printing ASCII replacement strings, keeping the main generation pipeline completely uninterrupted.

---

## 5. Next Steps & Ideas for Enhancement

1. **Quantization Support**: Add `bitsandbytes` or `llama.cpp` wrapper bindings in Python to load larger text models (e.g. 7B or 8B) on CPU/GPU using 4-bit or 8-bit quantization.
2. **Audio Overlays**: Integrate a local Text-to-Speech (TTS) engine (like `coqui-tts` or simple `pyttsx3`) to generate narration voiceovers for each timestamp segment.
3. **Storyboard Video Compiler**: Use `ffmpeg` on the backend to combine the generated storyboard images and narration audio overlays into a finished horizontal MP4 storyboard video automatically!
