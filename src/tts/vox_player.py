"""VOICEVOX TTS Synthesizer."""

import json
import logging
import uuid
from pathlib import Path
from urllib.parse import quote
from typing import Optional

import requests

from src.config import (VOICEVOX_URL, VOICEVOX_SPEAKER_ID, VOICEVOX_SPEED,
                        VOICEVOX_PITCH, VOICEVOX_VOLUME, VOICEVOX_INTONATION, paths)

log = logging.getLogger("vox-radio.tts")


class VoxSynthesizer:
    """Wrapper around VOICEVOX ENGINE API."""

    def __init__(self, speaker_id: int = VOICEVOX_SPEAKER_ID):
        self.speaker_id = speaker_id

    def init_speaker(self, speaker_id: int) -> bool:
        try:
            r = requests.post(f"{VOICEVOX_URL}/initialize_speaker?speaker={speaker_id}", timeout=30)
            return r.status_code == 204
        except Exception as e:
            log.error("Speaker init failed: %s", e)
            return False

    def audio_query(self, text: str) -> Optional[dict]:
        if not text.strip():
            return None
        self.init_speaker(self.speaker_id)
        r = requests.post(f"{VOICEVOX_URL}/audio_query?text={quote(text)}&speaker={self.speaker_id}", timeout=10)
        r.raise_for_status()
        q = r.json()
        q["speedScale"] = VOICEVOX_SPEED
        q["pitchScale"] = VOICEVOX_PITCH
        q["intonationScale"] = VOICEVOX_INTONATION
        q["volumeScale"] = VOICEVOX_VOLUME
        return q

    def synthesize(self, text: str, speaker_id: Optional[int] = None) -> Optional[bytes]:
        q = self.audio_query(text)
        if not q:
            return None
        r = requests.post(f"{VOICEVOX_URL}/synthesis_hack?speaker={speaker_id or self.speaker_id}",
                          json=q, headers={"Content-Type": "application/json"}, timeout=30)
        r.raise_for_status()
        return r.content

    def save_synthesis(self, text: str, speaker_id: Optional[int] = None,
                       output_dir: Optional[str] = None) -> str:
        wav_bytes = self.synthesize(text, speaker_id)
        if not wav_bytes:
            return ""
        d = Path(output_dir or paths()["wav_dir"])
        d.mkdir(parents=True, exist_ok=True)
        out = d / f"synth_{uuid.uuid4().hex[:8]}.wav"
        out.write_bytes(wav_bytes)
        log.info("TTS WAV: %s (%d B)", out, len(wav_bytes))
        return str(out)
