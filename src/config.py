"""Configuration for VOX-Radio pipeline."""
import os
from pathlib import Path

# ── Paths ──
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
for subdir in ["raw", "transcripts", "summaries", "wav", "viz"]:
    (OUTPUT_DIR / subdir).mkdir(parents=True, exist_ok=True)


def paths():
    """Return output directory map."""
    return {
        "base": str(BASE_DIR),
        "raw": str(OUTPUT_DIR / "raw"),
        "trans_dir": str(OUTPUT_DIR / "transcripts"),
        "summ_dir": str(OUTPUT_DIR / "summaries"),
        "wav_dir": str(OUTPUT_DIR / "wav"),
        "viz_dir": str(OUTPUT_DIR / "viz"),
    }


# ── Radio Config ───────────────────────────
JCBA_API_URL = os.getenv("JCBA_API_URL", "https://radimo.smen.biz/api/v1/select_stream")
HEARTFM_STATION_ID = os.getenv("HEARTFM_STATION_ID", "heartfm")
PIPELINE_LOOP = os.getenv("PIPELINE_LOOP", "true").lower() == "true"

# Recording: two-stream alternating capture
RECORD_DURATION = int(os.getenv("RECORD_DURATION", "60"))    # seconds per segment
STREAM_SWITCH_OVERLAP = int(os.getenv("STREAM_OVERLAP", "5"))  # seconds of overlap between streams
MAX_STREAMS = int(os.getenv("MAX_STREAMS", "2"))              # alternate between 2 streams

# Pipeline loop
RADIO_MINUTES = int(os.getenv("RADIO_MINUTES", "0"))           # 0 = infinite


# ── Whisper Config ───────────────────────
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "large-v3-turbo")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "float16")
WHISPER_LANG = os.getenv("WHISPER_LANG", "ja")

# Duplicate-aware transcription
OVERLAP_DEDUP_WORDS = int(os.getenv("OVERLAP_DEDUP_WORDS", "5"))  # last N words dedup


# ── Ollama / LLM Config ──────────────────
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e4b")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ubuntu.local:11434")
SUMMARY_MAX_TOKENS = int(os.getenv("SUMMARY_MAX_TOKENS", "1024"))
EMOTION_ANALYSIS = os.getenv("EMOTION_ANALYSIS", "true").lower() == "true"

# Context-aware prompting
USE_CONTEXT = os.getenv("USE_CONTEXT", "true").lower() == "true"
CONTEXT_ROLLBACK_DEPTH = int(os.getenv("CONTEXT_ROLLBACK_DEPTH", "2"))  # last N summaries keep as context


# ── VOICEVOX Config ──────────────────────
VOICEVOX_URL = os.getenv("VOICEVOX_URL", "http://ubuntu.local:50021")
VOICEVOX_SPEAKER_ID = int(os.getenv("VOICEVOX_SPEAKER_ID", "1"))
VOICEVOX_SPEED = float(os.getenv("VOICEVOX_SPEED", "1.0"))
VOICEVOX_PITCH = float(os.getenv("VOICEVOX_PITCH", "0.0"))
VOICEVOX_VOLUME = float(os.getenv("VOICEVOX_VOLUME", "1.0"))
VOICEVOX_INTONATION = float(os.getenv("VOICEVOX_INTONATION", "1.0"))


# ── VRM Config ───────────────────────────
VRM_MODEL_PATH = os.getenv("VRM_MODEL_PATH", str(BASE_DIR / "assets/vrms/hrn0Hk8kxp.glb"))

# Idle animation
IDLE_BLINK_INTERVAL = float(os.getenv("IDLE_BLINK_INTERVAL", "4.0"))  # seconds between blinks
IDLE_BLINK_DURATION = float(os.getenv("IDLE_BLINK_DURATION", "0.15"))  # blink duration
IDLE_BODY_SWAY_MIN = float(os.getenv("IDLE_BODY_SWAY_MIN", "0.02"))
IDLE_BODY_SWAY_MAX = float(os.getenv("IDLE_BODY_SWAY_MAX", "0.06"))
IDLE_BLINK_SWAY_INTERVAL = float(os.getenv("IDLE_BLINK_SWAY_INTERVAL", "6.0"))  # re-randomize sway

# Expression control: change every N seconds
EXPRESSION_INTERVAL = float(os.getenv("EXPRESSION_INTERVAL", "60.0"))  # seconds per expression slot

# Blink: random intervals
IDLE_RANDOM_BLINK_MIN = float(os.getenv("IDLE_RANDOM_BLINK_MIN", "3.0"))
IDLE_RANDOM_BLINK_MAX = float(os.getenv("IDLE_RANDOM_BLINK_MAX", "7.0"))
