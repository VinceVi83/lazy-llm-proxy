from pathlib import Path
from collections import deque
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import ollama
import threading
import subprocess
import requests
import tempfile
import os
from whisper_engine import WhisperEngine
from common.conf_manager import cfg, setup_logging
import logging

setup_logging()
logger = logging.getLogger(__name__)
ACTIVITY_FILE = Path("/tmp/activity.lock")

app = FastAPI()

class LLMRequest(BaseModel):
    system_prompt: str = ""
    profile: str = "default"
    model: Optional[str] = None
    prompt: str = ""
    attachments: Optional[List[str]] = None
    options: Optional[dict] = None
    audio_url: Optional[str] = None
    audio_language: str = "fr"

class LLMResponse(BaseModel):
    result: str

class LLMService:
    """
    Thread-safe service for queued LLM requests via Ollama.

    Operates as follows:
        1. submit_task enqueues requests with config, Event for synchronization, and result container.
        2. A single daemon thread processes the queue sequentially via _process_queue.
        3. Each request calls Ollama's chat API through _call_ollama with model, prompts, and options.
        4. Results or errors are propagated back through the result container and Event.

    Methods:
        __init__(self) : Initializes the queue, lock, and processing flag.
        submit_task(self, config: dict) -> str : Adds a task to the queue and returns its result, with 300s timeout.
        _process_queue(self) : Processes queued tasks in FIFO order.
        _call_ollama(self, config: dict) -> str : Invokes Ollama chat API with the given configuration.

    Usage:
        llm_service = LLMService()
        response = llm_service.submit_task({"model": "llama3", "text": "Hello"})
    """
    def __init__(self):
        self.queue = deque()
        self.lock = threading.Lock()
        self.processing = False
    
    def submit_task(self, config: dict) -> str:
        event = threading.Event()
        result_container = {"result": None, "error": None}
        with self.lock:
            self.queue.append((config, event, result_container))
        if not self.processing:
            threading.Thread(target=self._process_queue, daemon=True).start()
        if not event.wait(timeout=300):
            raise TimeoutError("LLM request timed out")
        if result_container["error"]:
            raise result_container["error"]
        result = result_container["result"]
        if result is None:
            return "LLM request completed without a result"
        return result

    def _process_queue(self):
        self.processing = True
        while True:
            with self.lock:
                if not self.queue:
                    self.processing = False
                    return
                config, event, result_container = self.queue.popleft()
            try:
                result = self._call_ollama(config)
                result_container["result"] = result
            except Exception as e:
                result_container["error"] = e
            finally:
                event.set()

    def _call_ollama(self, config: dict) -> str:
        options = {}
        user_options = config.get("options", {})
        
        option_mapping = {
            "temperature": "temperature",
            "top_p": "top_p",
            "top_k": "top_k",
            "num_predict": "num_predict",
            "max_tokens": "num_predict",
            "think": "think"
        }
        for key, ollama_key in option_mapping.items():
            if key in user_options and user_options[key] is not None:
                options[ollama_key] = user_options[key]
        logger.info(f"Calling Ollama with model: {config.get('model', '????')}, options: {options}")
        response = ollama.chat(
            model=config.get("model", "qwen2.5:3b"),
            messages=[
                {"role": "system", "content": config.get("system_prompt", "")},
                {"role": "user", "content": config.get("text", "")}
            ],
            options=options
        )
        return response["message"]["content"]

def init_whisper(mode="CPU", lang="fr"):
    global whisper
    whisper = WhisperEngine(mode, lang)

def download_audio(url: str) -> str:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    try:
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        tmp.write(r.content)
        tmp.close()
        return tmp.name
    except:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        raise

llm_service = LLMService()

@app.get("/health")
async def health():
    ACTIVITY_FILE.write_text("")
    return {"status": "ok"}

@app.post("/wol-ack")
def wol_ack():
    ACTIVITY_FILE.write_text("")
    try:
        script_path = Path(__file__).parent / "auto-suspend.py"
        subprocess.Popen([cfg.conf.python_path, str(script_path)], 
                         stdout=subprocess.DEVNULL, 
                         stderr=subprocess.DEVNULL)
        logger.info(f"Launched auto-suspend.py via wol-ack using {cfg.conf.python_path}")
    except Exception as e:
        logger.error(f"Failed to launch auto-suspend.py: {str(e)}")
    return {"status": "ok"}

@app.get("/models")
def list_models():
    try:
        models = ollama.list()
        return {"models": models}
    except Exception as e:
        logger.error(f"Error listing models: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/transcribe")
def transcribe(req: LLMRequest):
    if whisper is None or not req.audio_url:
        raise HTTPException(status_code=400, detail="audio_url required")
    filepath = download_audio(req.audio_url)
    try:
        text = whisper.transcribe(filepath)
        return LLMResponse(result=text)
    finally:
        os.unlink(filepath)

@app.post("/transcribe-and-call", response_model=LLMResponse)
def transcribe_and_call(req: LLMRequest):
    if whisper is None or not req.audio_url:
        raise HTTPException(status_code=400, detail="audio_url required")
    filepath = download_audio(req.audio_url)
    try:
        transcribed = whisper.transcribe(filepath)
    finally:
        os.unlink(filepath)
    if not transcribed:
        return LLMResponse(result="(empty transcription)")

    config = {
        "system_prompt": req.system_prompt,
        "profile": req.profile,
        "model": req.model or "qwen2.5:7b-instruct-q8_0",
        "text": transcribed,
        "attachments": req.attachments or [],
        "options": req.options or {}
    }
    output = llm_service.submit_task(config)
    return LLMResponse(result=output)

@app.post("/call-llm", response_model=LLMResponse)
def call_llm(req: LLMRequest):
    try:
        config = {
            "system_prompt": req.system_prompt,
            "profile": req.profile,
            "model": req.model or "qwen2.5:7b-instruct-q8_0",
            "text": req.prompt,
            "attachments": req.attachments or [],
            "options": req.options or {}
        }
        ACTIVITY_FILE.write_text("")
        output = llm_service.submit_task(config)
        return LLMResponse(result=output)
    except TimeoutError as te:
        logger.error(f"LLM Call Timeout: {str(te)}")
        raise HTTPException(status_code=504, detail=str(te))
    except Exception as e:
        logger.error(f"LLM Call Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"LLM Call Error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    init_whisper(mode="GPU", lang="fr")
    uvicorn.run(app, host="0.0.0.0", port=cfg.llm_gateway.port)

