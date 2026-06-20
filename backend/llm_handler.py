import re
import torch
import gc
import json
from transformers import AutoTokenizer, AutoModelForCausalLM
from backend.config import load_config

from backend.logger import add_log

class ScriptParsingCancelled(Exception):
    pass

import urllib.request
import urllib.error

def query_remote_llm(provider: str, config: dict, prompt: str) -> str:
    """
    Sends request to Ollama or LM Studio / OpenAI-compatible local servers.
    """
    if provider == "ollama":
        base_url = config.get("ollama_url", "http://localhost:11434").rstrip("/")
        url = f"{base_url}/api/generate"
        model = config.get("ollama_model", "qwen2.5:3b")
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2
            }
        }
    else: # openai_compatible
        base_url = config.get("openai_url", "http://localhost:1234/v1").rstrip("/")
        url = f"{base_url}/chat/completions"
        model = config.get("openai_model", "qwen2.5-3b-instruct")
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2
        }

    add_log(f"Sending prompt to remote LLM server ({provider.upper()}) at '{url}' using model '{model}'...", "llm")
    
    # Check cancellation before sending request
    if _cancel_parse:
        raise ScriptParsingCancelled("Script parsing cancelled by user.")
        
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    try:
        # Using a timeout to prevent hanging requests
        with urllib.request.urlopen(req, timeout=120) as response:
            res_data = response.read().decode("utf-8")
            res_json = json.loads(res_data)
            
            # Check cancellation right after receiving response
            if _cancel_parse:
                raise ScriptParsingCancelled("Script parsing cancelled by user.")
                
            if provider == "ollama":
                return res_json.get("response", "").strip()
            else: # openai_compatible
                choices = res_json.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "").strip()
                raise ValueError("No response choices found in OpenAI completions output.")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Failed to connect to local LLM server at '{url}': {e.reason}")
    except Exception as e:
        raise RuntimeError(f"Error communicating with local LLM server: {e}")

_cancel_parse = False

def cancel_script_parsing():
    global _cancel_parse
    _cancel_parse = True

# Global variable to hold the loaded model and tokenizer to avoid reloading
_loaded_model_id = None
_tokenizer = None
_model = None

def unload_llm():
    global _loaded_model_id, _tokenizer, _model
    if _model is not None:
        add_log(f"Unloading LLM model '{_loaded_model_id}' from VRAM to free GPU memory...", "llm")
        _model = None
        _tokenizer = None
        _loaded_model_id = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        add_log("LLM model successfully unloaded and CUDA memory cache flushed.", "llm")

def load_llm_model(model_id: str, hf_token: str = None):
    global _loaded_model_id, _tokenizer, _model
    
    if _loaded_model_id == model_id and _model is not None:
        add_log(f"Model '{model_id}' is already loaded in memory.", "llm")
        return _tokenizer, _model
        
    # Unload image pipeline to free VRAM before loading the LLM
    try:
        from backend.image_handler import unload_image_pipeline
        unload_image_pipeline()
    except Exception as e:
        print(f"Exception unloading image pipeline: {e}")
        
    config = load_config()
    use_gpu = config.get("use_gpu", False)
    device = "cuda" if (use_gpu and torch.cuda.is_available()) else "cpu"
    
    add_log(f"Loading LLM model '{model_id}' on {device.upper()} (this may take a few moments)...", "llm")
    _tokenizer = AutoTokenizer.from_pretrained(model_id, token=hf_token if hf_token else None)
    
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
    add_log(f"LLM model '{model_id}' loaded successfully on {device.upper()}.", "llm")
    return _tokenizer, _model

def split_script_into_sections(script_text: str) -> list:
    """
    Partitions the script into logical sections separated by '========================================='
    """
    raw_blocks = script_text.split("=========================================")
    sections = []
    
    # Filter empty blocks and strip whitespaces
    blocks = [b.strip() for b in raw_blocks if b.strip()]
    
    i = 0
    while i < len(blocks):
        if i + 1 < len(blocks):
            header = blocks[i]
            content = blocks[i+1]
            sections.append({
                "header": header,
                "content": content
            })
            i += 2
        else:
            sections.append({
                "header": "Section",
                "content": blocks[i]
            })
            i += 1
            
    # Fallback if no sections could be partitioned
    if not sections:
        sections.append({
            "header": "Full Script",
            "content": script_text
        })
        
    return sections

def extract_json_array(text: str) -> list:
    """
    Extracts and parses a JSON array from LLM response.
    """
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
        
    # Search for the boundaries of the JSON array '[' and ']'
    start = text.find('[')
    end = text.rfind(']')
    if start != -1 and end != -1 and end > start:
        json_str = text[start:end+1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
            
    raise ValueError("No valid JSON array found in LLM output.")

def fallback_regex_parser(script_text: str) -> list:
    """
    Smarter fallback parser:
    - If timestamps are found, extracts scenes by matching lines with timestamps.
    - If no timestamps are found, splits by paragraphs or non-empty sentences, and assigns Scene indices.
    """
    # First check if there are any timestamps in the script text
    timestamp_pattern = re.compile(r'(\d{1,2}:\d{2}\s*[\u2013\u2014-]\s*\d{1,2}:\d{2})|(\d{1,2}:\d{2})')
    has_timestamps = any(timestamp_pattern.search(line) for line in script_text.split("\n"))
    
    segments = []
    
    if has_timestamps:
        # Timestamp-based extraction
        lines = script_text.split("\n")
        for line in lines:
            line = line.strip()
            if not line or line.lower().startswith("[visuals:") or line.startswith("===") or line.startswith("]"):
                continue
                
            m = timestamp_pattern.search(line)
            if m:
                timestamp = m.group(0)
                content = line.replace(timestamp, "")
                content = content.replace("**", "").replace("*", "").strip(" -:*[]\u2013\u2014")
                if content:
                    segments.append({
                        "timestamp": timestamp,
                        "text": content,
                        "visual_prompt": content
                    })
    else:
        # Paragraph or sentence-based extraction for plain scripts
        raw_lines = script_text.split("\n")
        scene_num = 1
        for line in raw_lines:
            line = line.strip()
            # Ignore separators or formatting lines
            if not line or line.startswith("===") or line.lower().startswith("[visuals:") or line.startswith("]"):
                continue
                
            # If line is longer than 15 characters, treat it as a scene
            if len(line) > 15:
                content = line.replace("**", "").replace("*", "").strip(" -:*[]\u2013\u2014")
                segments.append({
                    "timestamp": f"Scene {scene_num}",
                    "text": content,
                    "visual_prompt": content
                })
                scene_num += 1
                
    return segments

def get_llm_analysis_prompt(system_prompt_template: str, header: str, content: str) -> str:
    """
    Assembles the detailed LLM prompt by putting script content inside system_prompt.md instructions.
    """
    prompt = system_prompt_template
    
    section_text = f"Section: {header}\n\n{content}"
    if "{PASTE SCRIPT HERE}" in prompt:
        prompt = prompt.replace("{PASTE SCRIPT HERE}", section_text)
    else:
        prompt = f"{prompt}\n\n### Script Section to Process:\n{section_text}"
        
    json_instructions = (
        "\n\n### IMPORTANT INSTRUCTIONS FOR YOUR RESPONSE:\n"
        "Analyze the script section above and identify every scene that requires a separate image.\n"
        "For each scene, extract the timestamp and narrator line/visual action, and write a specific visual scene description.\n"
        "Output the final list of scenes as a valid JSON array of objects. Each object MUST contain these exact fields:\n"
        '  - "timestamp": the timestamp of the scene (e.g. "0:00 - 0:04")\n'
        '  - "text": a short description of the action or narrator dialogue at that moment\n'
        '  - "visual_prompt": a description of the visual scene to be drawn (e.g. "a prehistoric human shivering in a dark cave corner"). Do not include any style or format prefixes like "MS Paint" or "A 16:9 frame" in this field; only specify the specific characters, actions, and objects.\n\n'
        "Format the output strictly as a JSON array starting with '[' and ending with ']'. "
        "Do not include any conversational text, markdown wrapping (such as ```json ... ```), or HTML tags. Your output must be parseable by python's json.loads()."
    )
    
    return f"{prompt}{json_instructions}"

def process_script(script_text: str, custom_model_id: str = None) -> list:
    """
    Parses the script using system_prompt.md rules and extracts all scenes with timestamps and visual prompts.
    """
    global _cancel_parse
    _cancel_parse = False
    config = load_config()
    llm_provider = config.get("llm_provider", "local")
    
    add_log(f"Received script text ({len(script_text)} characters). Splitting into sections...", "llm")
    sections = split_script_into_sections(script_text)
    add_log(f"Partitioned script into {len(sections)} sections for granular LLM extraction.", "llm")
    
    # Load system prompt template from system_prompt.md
    system_prompt_template = ""
    try:
        from backend.config import WORKSPACE_DIR
        system_prompt_path = WORKSPACE_DIR / "system_prompt.md"
        if system_prompt_path.exists():
            with open(system_prompt_path, "r", encoding="utf-8") as f:
                system_prompt_template = f.read()
    except Exception as e:
        add_log(f"Error reading system_prompt.md: {e}", "llm", "WARNING")
        
    if not system_prompt_template:
        system_prompt_template = (
            "You are an AI assistant that extracts visual scene descriptions from a YouTube script. "
            "For each timestamp, generate a clean visual scene description."
        )
        
    all_scenes = []
    
    try:
        if llm_provider == "local":
            model_id = custom_model_id or config.get("selected_text_model", "Qwen/Qwen2.5-0.5B-Instruct")
            hf_token = config.get("hf_token", "")
            add_log(f"Loading text model '{model_id}' to run full script analysis...", "llm")
            tokenizer, model = load_llm_model(model_id, hf_token)
            add_log("Text model loaded successfully. Starting section analysis...", "llm")
        else:
            add_log(f"Starting remote section analysis using {llm_provider.upper()} provider...", "llm")
            
        for section in sections:
            if _cancel_parse:
                raise ScriptParsingCancelled("Script parsing cancelled by user.")
            header = section["header"]
            content = section["content"]
            
            # Construct the prompt
            full_prompt = get_llm_analysis_prompt(system_prompt_template, header, content)
            
            # Run inference
            if llm_provider == "local":
                try:
                    messages = [
                        {"role": "user", "content": full_prompt}
                    ]
                    text = tokenizer.apply_chat_template(
                        messages,
                        tokenize=False,
                        add_generation_prompt=True
                    )
                except Exception:
                    text = f"User: {full_prompt}\n\nAssistant:"
                    
                inputs = tokenizer([text], return_tensors="pt")
                inputs = {k: v.to(model.device) for k, v in inputs.items()}
                pad_token = tokenizer.pad_token_id or tokenizer.eos_token_id
                
                add_log(f"Running LLM analysis for Section: '{header}'...", "llm")
                
                with torch.no_grad():
                    generated_ids = model.generate(
                        **inputs,
                        max_new_tokens=1500,
                        do_sample=True,
                        temperature=0.2,
                        top_p=0.9,
                        pad_token_id=pad_token
                    )
                    
                generated_ids = [
                    output_ids[len(input_ids):] for input_ids, output_ids in zip(inputs["input_ids"], generated_ids)
                ]
                
                response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
            else:
                response = query_remote_llm(llm_provider, config, full_prompt)
            
            # Parse JSON
            try:
                scenes = extract_json_array(response)
                add_log(f"Successfully extracted {len(scenes)} scenes from section '{header}'.", "llm")
                all_scenes.extend(scenes)
            except Exception as e:
                add_log(f"Failed to parse LLM JSON for section '{header}': {e}. Falling back to regex parser.", "llm", "WARNING")
                fallback_scenes = fallback_regex_parser(content)
                add_log(f"Regex parser extracted {len(fallback_scenes)} scenes from section '{header}'.", "llm")
                all_scenes.extend(fallback_scenes)
                
    except ScriptParsingCancelled as e:
        add_log("Script parsing cancelled by user request.", "llm", "WARNING")
        raise e
    except Exception as e:
        add_log(f"Error running local LLM: {e}. Falling back to pure regex parser for the entire script.", "llm", "ERROR")
        # Run fallback regex parser on the entire script
        all_scenes = fallback_regex_parser(script_text)
        
    # Process final segments
    final_segments = []
    for idx, scene in enumerate(all_scenes):
        final_segments.append({
            "id": idx,
            "timestamp": scene.get("timestamp", f"Scene {idx+1}"),
            "text": scene.get("text", "No narration line."),
            "visual_prompt": scene.get("visual_prompt", "No prompt description."),
            "status": "pending",
            "image_url": None
        })
        
    add_log(f"Completed analysis. Extracted total {len(final_segments)} scenes for storyboard rendering.", "llm")
    return final_segments
