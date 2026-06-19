import torch
import gc
from pathlib import Path
from diffusers import AutoPipelineForText2Image
from backend.config import load_config, OUTPUT_DIR
from backend.logger import add_log

# Global variable to hold the loaded image pipeline
_loaded_model_id = None
_pipeline = None

STYLE_PREFIX = (
    "A horizontal 16:9 widescreen composition of an intentionally bad, amateur MS Paint drawing. "
    "Simple childish stick-man drawing style, wobbly hand-drawn thick uneven black outlines, flat colors only, "
    "completely white background, mostly empty space, centered composition. Extremely basic facial expressions, "
    "dot eyes, simple stick figure humans with round heads and line bodies. Drawn with basic shapes like squares "
    "and circles. Zero shading, zero 3D elements, zero cinematic lighting. Generate a 16:9 frame depicting: "
)

def unload_image_pipeline():
    global _loaded_model_id, _pipeline
    if _pipeline is not None:
        add_log(f"Unloading Image Model '{_loaded_model_id}' from VRAM to free GPU memory...", "image")
        _pipeline = None
        _loaded_model_id = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        add_log("Image Model successfully unloaded and CUDA memory cache flushed.", "image")

def load_image_pipeline(model_id: str, hf_token: str = None):
    global _loaded_model_id, _pipeline
    
    if _loaded_model_id == model_id and _pipeline is not None:
        add_log(f"Image Model '{model_id}' is already loaded in memory.", "image")
        return _pipeline
        
    # Unload LLM model to free VRAM before loading the image pipeline
    try:
        from backend.llm_handler import unload_llm
        unload_llm()
    except Exception as e:
        print(f"Exception unloading LLM: {e}")
        
    config = load_config()
    use_gpu = config.get("use_gpu", False)
    device = "cuda" if (use_gpu and torch.cuda.is_available()) else "cpu"
    
    add_log(f"Loading Image Model '{model_id}' on {device.upper()} (this may take a few minutes)...", "image")
    
    # Load pipeline with appropriate data type (float16 on GPU is faster and saves VRAM)
    dtype = torch.float16 if device == "cuda" else torch.float32
    
    pipe = AutoPipelineForText2Image.from_pretrained(
        model_id,
        token=hf_token if hf_token else None,
        torch_dtype=dtype,
        use_safetensors=True
    )
    
    pipe.to(device)
    
    if device == "cpu":
        # CPU memory optimizations
        add_log("CPU mode detected. Enabling attention slicing to save memory.", "image")
        pipe.enable_attention_slicing()
        
    _loaded_model_id = model_id
    _pipeline = pipe
    add_log(f"Image Model '{model_id}' loaded successfully on {device.upper()}.", "image")
    return _pipeline

def generate_image_for_prompt(visual_prompt: str, filename: str, custom_model_id: str = None) -> Path:
    config = load_config()
    model_id = custom_model_id or config.get("selected_image_model", "stabilityai/sd-turbo")
    hf_token = config.get("hf_token", "")
    
    # Load model
    pipe = load_image_pipeline(model_id, hf_token)
    
    # Assemble the full prompt incorporating the style guidelines
    full_prompt = f"{STYLE_PREFIX}{visual_prompt}"
    
    # Configuration details
    num_steps = config.get("num_inference_steps", 1)
    # Check if the model is sd-turbo or sdxl-turbo; standard SD models need more steps (e.g. 20)
    if "turbo" not in model_id.lower() and "schnell" not in model_id.lower():
        # Fallback to standard 20 steps if config is still 1 step but the model is not a fast one
        if num_steps == 1:
            num_steps = 20
            
    guidance_scale = config.get("guidance_scale", 0.0)
    if "turbo" not in model_id.lower() and "schnell" not in model_id.lower():
        if guidance_scale == 0.0:
            guidance_scale = 7.5
            
    # Set 16:9 dimensions optimized for speed on CPU
    # 768x432 is a great balance of 16:9 ratio and pixel count (~330k pixels, comparable to 512x512)
    # For SDXL based models, we might want 512x288 to run faster on CPU, or 1024x576 on GPU.
    is_sdxl = "xl" in model_id.lower() or "flux" in model_id.lower()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    
    if device == "cpu":
        width, height = 512, 288  # Faster on CPU
    else:
        width, height = 768, 432  # Standard 16:9
        
    add_log(f"Running image inference for prompt: '{visual_prompt[:60]}...' using '{model_id}' (Steps: {num_steps}, Size: {width}x{height})", "image")
    
    # Run pipeline
    output = pipe(
        prompt=full_prompt,
        num_inference_steps=num_steps,
        guidance_scale=guidance_scale,
        width=width,
        height=height
    )
    
    image = output.images[0]
    
    # Ensure save path exists
    save_path = OUTPUT_DIR / filename
    image.save(save_path)
    add_log(f"Image successfully generated and saved to '{filename}'", "image")
    
    return save_path
