from faster_whisper import WhisperModel
import logging
import sys

logger = logging.getLogger(__name__)

class WhisperEngine:
    """Whisper Speech Recognition Engine

    Role: Initializes and manages Whisper model for audio transcription with VAD filtering.

    Methods:
        __init__(self, mode, lang) : Initialize Whisper model with GPU or CPU backend.
        transcribe(self, audio) : Transcribe audio file and return cleaned text segments.
        load(self) : Load model into VRAM/RAM if not already loaded.
        unload(self) : Unload model from VRAM/RAM to free memory.
    """

    def __init__(self, mode, lang):
        self.lang = lang
        self.mode = mode
        self.model = None
        self.loaded = False
        self.load()

    def load(self):
        if self.loaded:
            return
        if self.mode == "GPU":
            self.model = WhisperModel(
                "large-v3",
                device="cuda",
                compute_type="float16"
            )
        else:
            self.model = WhisperModel(
                "medium",
                device="cpu",
                compute_type="int8",
                cpu_threads=4,
                num_workers=1
            )
        self.vad_params = dict(
            threshold=0.35,
            min_speech_duration_ms=250
        )
        self.loaded = True
        logger.info("Whisper model loaded (%s mode)", self.mode)

    def unload(self):
        if not self.loaded:
            return
        del self.model
        self.model = None
        self.loaded = False
        logger.info("Whisper model unloaded")

    def transcribe(self, audio):
        self.load()
        if self.model is None:
            self.unload()
            self.loaded = False
            raise RuntimeError("Whisper model failed to load")
        segments, _ = self.model.transcribe(
            audio,
            language=self.lang,
            vad_filter=True,
            initial_prompt="Alisu, Touhou, Playlist, VLC, Japanese, Mail-moi."
        )
        return "".join([s.text for s in segments]).strip()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", help="Path to audio file")
    parser.add_argument("--mode", choices=["GPU", "CPU"], default="GPU")
    parser.add_argument("--lang", default="fr")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    engine = WhisperEngine(args.mode, args.lang)
    try:
        text = engine.transcribe(args.audio)
        print(f"Transcription: {text}")
    except RuntimeError as e:
        logger.error(f"Failed: {e}")
        sys.exit(1)
    finally:
        engine.unload()
