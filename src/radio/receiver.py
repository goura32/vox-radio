"""HeartFM WebSocket receiver (JCBA FMラダリオ API).

Receives Ogg/Opus audio from JCBA/FMラダリオ's WebSocket stream.
Handles:
- JWT token acquisition (15s expiry — auto-refresh)
- WebSocket connection with subprotocol
- Ogg/Opus packet collection
- Stream → WAV via ffmpeg pipe
"""
import asyncio
import json
import logging
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from io import BytesIO
from typing import Optional

import requests
import websockets

from src.config import JCBA_API_URL, HEARTFM_STATION_ID, paths

log = logging.getLogger("vox-radio.receiver")


@dataclass
class StreamInfo:
    url: str
    token: str
    expires_at: float  # epoch timestamp


@dataclass
class AudioFrame:
    frame_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: Optional[float] = None
    raw_data: bytes = b""
    duration_sec: float = 0.0


class Receiver:
    """Manage WebSocket stream to HeartFM.
    Auto-renews JWT tokens every 10 seconds.
    Collects Ogg/Opus chunks.
    """

    def __init__(self, station_id: str = HEARTFM_STATION_ID):
        self.station_id = station_id
        self.ws = None
        self.stream: Optional[StreamInfo] = None
        self._chunks: list[bytes] = []
        self._running = False
        self._refresh_task: Optional[asyncio.Task] = None

    async def open(self) -> StreamInfo:
        """Connect to HeartFM stream. Returns StreamInfo."""
        log.info("Opening stream for station=%s", self.station_id)

        # 1) Get streaming URL + token
        resp = requests.post(
            JCBA_API_URL,
            params={
                "station": self.station_id,
                "channel": "0",
                "quality": "high",
                "burst": "5",
            },
            json={"station": self.station_id},
            timeout=10,
        )
        resp.raise_for_status()
        body = resp.json()
        self.stream = StreamInfo(
            url=body["location"],
            token=body["token"],
            expires_at=time.time() + 15,
        )

        # 2) Open WebSocket
        self.ws = await websockets.connect(
            self.stream.url,
            subprotocols=["listener.fmplapla.com"],
            additional_headers={
                "Authorization": f"Bearer {self.stream.token}",
            },
        )
        await self.ws.send(self.stream.token)
        log.info("WebSocket connected to %s", self.stream.url)

        # 3) Start token-refresh background task
        self._running = True
        self._refresh_task = asyncio.create_task(self._refresh_loop())
        return self.stream

    async def close(self):
        """Stop and disconnect."""
        self._running = False
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
        if self.ws:
            await self.ws.close()
            self.ws = None
        log.info("Stream closed")

    async def receive_frames(self, duration: float = 5.0) -> list[AudioFrame]:
        """Receive audio for `duration` seconds. Returns list of AudioFrame."""
        if not self.ws:
            raise RuntimeError("Call open() first")

        frames: list[AudioFrame] = []
        end = time.monotonic() + duration
        current_chunk = b""
        start = time.monotonic()

        while time.monotonic() < end and self._running:
            try:
                data = await asyncio.wait_for(
                    self.ws.recv(), timeout=min(0.5, end - time.monotonic())
                )
                if isinstance(data, bytes):
                    current_chunk += data

                # Flush every 100ms of audio (approx)
                elapsed_mono = time.monotonic() - start
                if current_chunk and len(current_chunk) > 0:
                    frame = AudioFrame(
                        timestamp=time.time(),
                        raw_data=current_chunk,
                        duration_sec=elapsed_mono,
                    )
                    frames.append(frame)
                    self._chunks.append(current_chunk)
                    current_chunk = b""
                    start = time.monotonic()

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                log.error("Receive error: %s", e)
                break

        # Remaining buffered data
        if current_chunk:
            frames.append(AudioFrame(
                timestamp=time.time(),
                raw_data=current_chunk,
            ))

        return frames

    def save_raw_to_wav(self, output_path: str) -> str:
        """Save collected raw Ogg data to WAV via ffmpeg."""
        raw_ogg = b"".join(self._chunks)
        ogg_path = output_path.replace(".wav", ".ogg")
        with open(ogg_path, "wb") as f:
            f.write(raw_ogg)

        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", ogg_path,
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                output_path,
            ],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            log.error("ffmpeg WAV conversion failed: %s", result.stderr)

        meta_path = output_path.replace(".wav", "_meta.json")
        with open(meta_path, "w") as f:
            json.dump({
                "station": self.station_id,
                "duration_sec": sum(fr.duration_sec for fr in frames) if frames else 0,
                "channels": 1,
                "sample_rate": 48000,
                "codec": "Opus",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }, f, indent=2)

        return output_path

    async def _refresh_loop(self):
        """Refresh JWT every 10s while stream is active."""
        while self._running:
            await asyncio.sleep(10)
            if not self._running:
                break
            await self._recreate_stream()

    async def _recreate_stream(self):
        """Get a new token and reconnect."""
        resp = requests.post(
            JCBA_API_URL,
            params={
                "station": self.station_id,
                "channel": "0",
                "quality": "high",
                "burst": "5",
            },
            json={"station": self.station_id},
            timeout=10,
        )
        resp.raise_for_status()
        body = resp.json()

        self.stream = StreamInfo(
            url=body["location"],
            token=body["token"],
            expires_at=time.time() + 15,
        )

        if self.ws:
            await self.ws.close()
        self.ws = await websockets.connect(
            self.stream.url,
            subprotocols=["listener.fmplapla.com"],
            additional_headers={"Authorization": f"Bearer {self.stream.token}"},
        )
        await self.ws.send(self.stream.token)
        self._chunks.clear()
        log.info("Token refreshed, new stream connected")
