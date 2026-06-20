import os
import zipfile
import json
import asyncio
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import List, Optional

from backend.config import load_config, save_config, OUTPUT_DIR, WORKSPACE_DIR
from backend.downloader import trigger_download, get_download_status
from backend.llm_handler import process_script
from backend.image_handler import generate_image_for_prompt
from backend.logger import add_log, get_logs, clear_logs

app = FastAPI(title="YouTube Script Image Generator API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify front-end origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount outputs directory to serve generated images
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")

# In-memory generation jobs tracking
# Format: { "status": "idle"|"running"|"completed"|"failed", "progress": float, "segments": List }
generation_jobs = {
    "status": "idle",
    "progress": 0.0,
    "current_segment_index": 0,
    "total_segments": 0,
    "segments": [],
    "error": None
}
cancel_generation = False

class ConfigModel(BaseModel):
    hf_token: Optional[str] = None
    selected_text_model: Optional[str] = None
    selected_image_model: Optional[str] = None
    num_inference_steps: Optional[int] = None
    guidance_scale: Optional[float] = None
    use_gpu: Optional[bool] = None
    llm_provider: Optional[str] = None
    ollama_url: Optional[str] = None
    ollama_model: Optional[str] = None
    openai_url: Optional[str] = None
    openai_model: Optional[str] = None

class ScriptInput(BaseModel):
    script_text: str
    custom_text_model: Optional[str] = None

class SegmentItem(BaseModel):
    id: int
    timestamp: str
    text: str
    visual_prompt: str

class GenerateInput(BaseModel):
    segments: List[SegmentItem]
    custom_image_model: Optional[str] = None

@app.get("/api/config")
def get_config():
    return load_config()

@app.post("/api/config")
def update_config(config: ConfigModel):
    updated = save_config(config.model_dump(exclude_unset=True))
    add_log(f"System configuration updated: {config.model_dump(exclude_unset=True)}", "system")
    return updated

@app.get("/api/ollama/models")
def get_ollama_models(url: str):
    import urllib.request
    import json
    endpoint = f"{url.rstrip('/')}/api/tags"
    try:
        req = urllib.request.Request(endpoint, method="GET")
        with urllib.request.urlopen(req, timeout=5) as response:
            res_data = response.read().decode("utf-8")
            data = json.loads(res_data)
            models = [m.get("name") for m in data.get("models", []) if m.get("name")]
            return {"models": models}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch models from Ollama at '{endpoint}': {e}")

@app.get("/api/openai/models")
def get_openai_models(url: str):
    import urllib.request
    import json
    endpoint = f"{url.rstrip('/')}/models"
    try:
        req = urllib.request.Request(endpoint, method="GET")
        with urllib.request.urlopen(req, timeout=5) as response:
            res_data = response.read().decode("utf-8")
            data = json.loads(res_data)
            models = [m.get("id") for m in data.get("data", []) if m.get("id")]
            return {"models": models}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch models from OpenAI API at '{endpoint}': {e}")

@app.get("/api/script/sample")
def get_sample_script():
    sample_path = WORKSPACE_DIR / "sample_script.md"
    if sample_path.exists():
        with open(sample_path, "r", encoding="utf-8") as f:
            return {"content": f.read()}
    return {"content": ""}

@app.get("/api/models/status")
def get_models_status(text_model: str, image_model: str):
    text_status = get_download_status(text_model)
    image_status = get_download_status(image_model)
    return {
        "text_model": text_status,
        "image_model": image_status
    }

@app.get("/api/stream")
async def stream_status(request: Request, text_model: str, image_model: str):
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            
            # Fetch status
            text_status = get_download_status(text_model)
            image_status = get_download_status(image_model)
            
            payload = {
                "models": {
                    "text_model": text_status,
                    "image_model": image_status
                },
                "job": generation_jobs,
                "logs": get_logs()
            }
            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(1.0)
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/api/logs")
def fetch_logs():
    return get_logs()

@app.post("/api/logs/clear")
def clear_logs_endpoint():
    clear_logs()
    return {"status": "success"}


@app.post("/api/models/download")
def download_model(repo_id: str):
    try:
        status = trigger_download(repo_id)
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/models/cancel")
def cancel_model_download(repo_id: str):
    try:
        from backend.downloader import cancel_download
        cancel_download(repo_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/jobs/cancel")
def cancel_generation_job():
    global cancel_generation
    if generation_jobs["status"] != "running":
        raise HTTPException(status_code=400, detail="No active generation job to cancel.")
    cancel_generation = True
    add_log("Cancellation request received for the running generation job.", "system", "WARNING")
    return {"status": "cancelled"}

@app.post("/api/script/parse")
def parse_script(input_data: ScriptInput):
    if not input_data.script_text.strip():
        raise HTTPException(status_code=400, detail="Script text cannot be empty.")
    try:
        segments = process_script(input_data.script_text, input_data.custom_text_model)
        return {"segments": segments}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/script/cancel")
def cancel_script_parse():
    try:
        from backend.llm_handler import cancel_script_parsing
        cancel_script_parsing()
        add_log("Cancellation request received for script parsing.", "system", "WARNING")
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def run_image_generation(segments: List[SegmentItem], custom_image_model: Optional[str]):
    global generation_jobs, cancel_generation
    cancel_generation = False
    generation_jobs["status"] = "running"
    generation_jobs["total_segments"] = len(segments)
    generation_jobs["current_segment_index"] = 0
    generation_jobs["progress"] = 0.0
    generation_jobs["error"] = None
    generation_jobs["segments"] = [s.model_dump() for s in segments]
    
    # Reset segment image URLs and states
    for s in generation_jobs["segments"]:
        s["status"] = "pending"
        s["image_url"] = None

    add_log(f"Starting batch image generation job for {len(segments)} scenes...", "system")
    try:
        for idx, segment in enumerate(segments):
            if cancel_generation:
                add_log("Image generation cancelled by user request.", "system", "WARNING")
                generation_jobs["status"] = "failed"
                generation_jobs["error"] = "Cancelled by user."
                break
                
            generation_jobs["current_segment_index"] = idx
            generation_jobs["progress"] = (idx / len(segments)) * 100
            generation_jobs["segments"][idx]["status"] = "generating"
            
            # Make a clean filename
            safe_timestamp = "".join([c if c.isalnum() else "_" for c in segment.timestamp])
            filename = f"scene_{segment.id}_{safe_timestamp}.png"
            
            add_log(f"Processing Scene {segment.id} of {len(segments)} ({segment.timestamp})...", "system")
            # Generate the image
            generate_image_for_prompt(
                visual_prompt=segment.visual_prompt,
                filename=filename,
                custom_model_id=custom_image_model
            )
            
            # Update segment completion
            generation_jobs["segments"][idx]["status"] = "completed"
            generation_jobs["segments"][idx]["image_url"] = f"/outputs/{filename}"
            add_log(f"Scene {segment.id} image rendering complete.", "system")
            
        generation_jobs["status"] = "completed"
        generation_jobs["progress"] = 100.0
        add_log(f"Batch image generation job completed successfully for all {len(segments)} scenes.", "system")
        
    except Exception as e:
        generation_jobs["status"] = "failed"
        generation_jobs["error"] = str(e)
        if idx < len(generation_jobs["segments"]):
            generation_jobs["segments"][idx]["status"] = "failed"
        add_log(f"Batch image generation job failed: {e}", "system", "ERROR")

@app.post("/api/generate")
def start_generation(input_data: GenerateInput, background_tasks: BackgroundTasks):
    global generation_jobs
    if generation_jobs["status"] == "running":
        raise HTTPException(status_code=400, detail="A generation job is already running.")
        
    add_log(f"Received generation request for {len(input_data.segments)} scenes. Scheduling background job...", "system")
    background_tasks.add_task(
        run_image_generation,
        input_data.segments,
        input_data.custom_image_model
    )
    return {"status": "started"}

@app.get("/api/jobs")
def get_jobs_status():
    return generation_jobs

@app.post("/api/jobs/reset")
def reset_jobs():
    global generation_jobs
    if generation_jobs["status"] == "running":
        raise HTTPException(status_code=400, detail="Cannot reset while generation is running.")
    generation_jobs = {
        "status": "idle",
        "progress": 0.0,
        "current_segment_index": 0,
        "total_segments": 0,
        "segments": [],
        "error": None
    }
    add_log("Generation status and scene states reset.", "system")
    return {"status": "reset"}

@app.post("/api/images/download-all")
def download_all_images():
    """
    Creates a zip archive of all generated images in the outputs folder and returns it.
    """
    add_log("Received archive request. Creating ZIP package of all generated images...", "system")
    zip_path = OUTPUT_DIR / "generated_storyboard.zip"
    
    # Find all PNGs in OUTPUT_DIR
    png_files = list(OUTPUT_DIR.glob("*.png"))
    if not png_files:
        add_log("Archive creation failed: No generated images found.", "system", "WARNING")
        raise HTTPException(status_code=400, detail="No generated images found to archive.")
        
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file in png_files:
                zipf.write(file, arcname=file.name)
                
        add_log(f"ZIP package created successfully containing {len(png_files)} images. Triggering download...", "system")
        return FileResponse(
            path=str(zip_path),
            filename="storyboard_images.zip",
            media_type="application/zip"
        )
    except Exception as e:
        add_log(f"ZIP package creation failed: {str(e)}", "system", "ERROR")
        raise HTTPException(status_code=500, detail=f"Failed to create ZIP: {str(e)}")

# Serve frontend static assets from dist folder if it exists
frontend_dist = WORKSPACE_DIR / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
else:
    @app.get("/")
    def index():
        return {"message": "YouTube Script Image Generator API is running. Build the frontend to view the UI on this port."}

