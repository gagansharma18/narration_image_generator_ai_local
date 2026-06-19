import re
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from backend.config import load_config

# Global variable to hold the loaded model and tokenizer to avoid reloading
_loaded_model_id = None
_tokenizer = None
_model = None

def load_llm_model(model_id: str, hf_token: str = None):
    global _loaded_model_id, _tokenizer, _model
    
    if _loaded_model_id == model_id and _model is not None:
        return _tokenizer, _model
        
    print(f"Loading local LLM: {model_id}...")
    _tokenizer = AutoTokenizer.from_pretrained(model_id, token=hf_token if hf_token else None)
    
    # Check if GPU is available
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda":
        # Load on GPU with device_map auto and float16 for speed and VRAM saving
        _model = AutoModelForCausalLM.from_pretrained(
            model_id,
            token=hf_token if hf_token else None,
            torch_dtype=torch.float16,
            device_map="auto"
        )
    else:
        # Load on CPU with float32
        _model = AutoModelForCausalLM.from_pretrained(
            model_id,
            token=hf_token if hf_token else None,
            torch_dtype=torch.float32,
            low_cpu_mem_usage=True
        )
        
    _loaded_model_id = model_id
    print(f"Local LLM loaded successfully on {device}.")
    return _tokenizer, _model

def parse_script_timestamps(script_text: str):
    """
    Parses a script and extracts lines with timestamps.
    Supports formats like:
    - 00:05 - Hello
    - 0:10 Hello
    - [0:15] Hello
    - 5s - Hello
    - 5 seconds: Hello
    """
    lines = script_text.strip().split("\n")
    parsed_segments = []
    
    # Regular expressions for timestamps
    # 1. Matches formats like 00:00, 0:00, [00:00], etc.
    time_format_1 = re.compile(r'(?:\[)?(\d{1,2}:)?(\d{1,2}):(\d{2})(?:\])?')
    # 2. Matches formats like 5s, 10s, 15 seconds, etc.
    time_format_2 = re.compile(r'^(\d+)\s*(?:s|sec|second|seconds)\b')
    
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
            
        timestamp = None
        content = line
        
        # Try format 1
        m1 = time_format_1.search(line)
        if m1:
            timestamp_str = m1.group(0)
            # Remove brackets if present
            timestamp = timestamp_str.replace("[", "").replace("]", "")
            content = line.replace(timestamp_str, "").strip(" -:")
        else:
            # Try format 2
            m2 = time_format_2.match(line)
            if m2:
                timestamp = f"{m2.group(1)}s"
                content = line[m2.end():].strip(" -:")
                
        # If no timestamp found, make one up or treat as general script line
        if not timestamp:
            # Create a simple default timestamp (e.g., scene 1, scene 2) if it contains text
            if len(content) > 3:
                timestamp = f"Scene {len(parsed_segments) + 1}"
                
        if timestamp:
            parsed_segments.append({
                "id": len(parsed_segments),
                "timestamp": timestamp,
                "text": content,
                "visual_prompt": "",
                "status": "pending",
                "image_url": None
            })
            
    return parsed_segments

def generate_visual_prompt_for_line(script_line: str, tokenizer, model, model_id: str) -> str:
    """
    Uses the local LLM to generate a visual scene description from a script line.
    """
    system_prompt = (
        "You are an AI assistant that reads a line from a YouTube script and outputs a simple visual scene description. "
        "The scene will be drawn in an amateur MS Paint stick-figure style. "
        "Describe what objects and stick figures should be in the scene, where they are, and what action they are doing. "
        "Keep the description brief and direct. Output ONLY the scene description. Do not write introductory words or conversational replies."
    )
    
    user_prompt = f"Script line: \"{script_line}\"\n\nScene description:"
    
    # Try using the standard chat template if available, fallback otherwise
    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )
    except Exception:
        if "TinyLlama" in model_id:
            text = f"<|system|>\n{system_prompt}</s>\n<|user|>\n{user_prompt}</s>\n<|assistant|>\n"
        else:
            text = f"System: {system_prompt}\nUser: {user_prompt}\nAssistant:"
        
    inputs = tokenizer([text], return_tensors="pt")
    
    # Place inputs on the model's device
    inputs = {k: v.to(model.device) for k, v in inputs.items()}
    
    # Set pad token ID if it is not set (llama and others sometimes lack one)
    pad_token = tokenizer.pad_token_id or tokenizer.eos_token_id
    
    with torch.no_grad():
        generated_ids = model.generate(
            **inputs,
            max_new_tokens=60,
            do_sample=True,
            temperature=0.7,
            top_p=0.9,
            pad_token_id=pad_token
        )
        
    generated_ids = [
        output_ids[len(input_ids):] for input_ids, output_ids in zip(inputs["input_ids"], generated_ids)
    ]
    
    response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
    
    # Strip any extra quotes
    response = response.strip('"\'')
    return response

def process_script(script_text: str, custom_model_id: str = None) -> list:
    """
    Parses the script and fills in the visual prompts using the local LLM.
    """
    config = load_config()
    model_id = custom_model_id or config.get("selected_text_model", "Qwen/Qwen2.5-0.5B-Instruct")
    hf_token = config.get("hf_token", "")
    
    segments = parse_script_timestamps(script_text)
    if not segments:
        return []
        
    try:
        tokenizer, model = load_llm_model(model_id, hf_token)
        for segment in segments:
            text = segment["text"]
            if text:
                visual_prompt = generate_visual_prompt_for_line(text, tokenizer, model, model_id)
                segment["visual_prompt"] = visual_prompt
            else:
                segment["visual_prompt"] = "A blank white screen."
    except Exception as e:
        print(f"Error running local LLM: {e}")
        # Fallback to simple description if model loading/generation fails
        for segment in segments:
            segment["visual_prompt"] = segment["text"]
            
    return segments
