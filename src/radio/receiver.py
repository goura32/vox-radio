"""Dual-stream HeartFM receiver with overlapping capture.

Maintains two WebSocket connections to JCBA FMラダリオ and alternates
them every RECORD_DURATION seconds with STREAM_SWITCH_OVERLAP seconds
of overlap to prevent audio gaps.

Pipeline output:
  - Queue[AudioSegment]: each item is (stream_index, overlap_flag, wav_path, meta)
  - Saves raw/ogg, meta.json, raw→WAV conversion
"""
import asyncio
import json
import logging
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

import requests

import websockets

from src.config import (JCBA_API_URL, HEARTFM_STATION_ID, RECORD_DURATION,
                        STREAM_SWITCH_OVERLAP, MAX_STREAMS, paths)

log = logging.getLogger("vox-radio.receiver")


@dataclass
class AudioSegment:
    """One contiguous audio segment captured from one stream."""
    segment_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    stream_index: int = 0
    capture_start: float = 0.0
    duration_sec: float = 0.0
    wav_path: str = ""
    meta_path: str = ""
    raw_ogg_path: str = ""
    is_duplicate: bool = False
    metadata: dict = field(default_factory=dict)


@dataclass
class _StreamState:
    ws: Optional[object] = None
    url: str = ""
    token: str = ""
    expires_at: float = 0.0
    chunks: list[bytes] = field(default_factory=list)
    alive: bool = False
    _refresh_task: Optional[asyncio.Task] = None


class DualStreamReceiver:
    """Capture via two alternating WebSocket streams (overlap = no gaps)."""

    def __init__(self, station_id: str = HEARTFM_STATION_ID):
        self.station_id = station_id
        self._a = _StreamState(stream_index=0)
        self._b = _StreamState(stream_index=1)
        self._active: _StreamState = self._a
        self._output_q: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._task: Optional[asyncio.Task] = None

    # ── public API ────────────────────────────

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._capture_loop())
        log.info("DualStreamReceiver started  duration=%ds overlap=%ds streams=%d",
                 RECORD_DURATION, STREAM_SWITCH_OVERLAP, MAX_STREAMS)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        for s in (self._active, self._b):
            if s.ws:
                await s.ws.close()
                s.ws = None
            s.alive = False

    async def get_segment(self, timeout=None):
        if timeout:
            return await asyncio.wait_for(self._output_q.get(), timeout)
        return await self._output_q.get()

    # ── capture loop ──────────────────────────

    async def _capture_loop(self):
        self._a.url, self._a.token = await self._get_token()
        self._a.ws = await self._open_ws(self._a.url, self._a.token)
        self._a._refresh_task = asyncio.create_task(self._refresh_loop(self._a))
        self._a.alive = True

        self._b.url, self._b.token = await self._get_token()
        self._b.ws = await self._open_ws(self._b.url, self._b.token)
        self._b._refresh_task = asyncio.create_task(self._refresh_loop(self._b))
        self._b.alive = True

        active = self._a
        while self._running:
            # 1. Collect audio for RECORD_DURATION+OVERLAP (new stream starts during overlap)
            start = time.monotonic()
            overlap = STREAM_SWITCH_OVERLAP
            duration = RECORD_DURATION - overlap  # pure-new portion
            await asyncio.sleep(duration)  # wait for new-capture duration

            # 2. Connect new stream as backup (start during overlap)
            other = self._active
            other_url, other_token = await self._get_token()
            other.ws = await self._open_ws(other_url, other_token)
            other._refresh_task = asyncio.create_task(self._refresh_loop(other))
            other.alive = True

            # 3. Finish overlap and dump old stream
            elapsed = time.monotonic() - start
            await asyncio.sleep(overlap - elapsed)

            chunked_bytes = b"".join(active.chunks)
            seg = await self._dump_segment(active)
            active.alive = False
            await active.ws.close()
            active.ws = None
            if active._refresh_task:
                active._refresh_task.cancel()
            active.chunks = []

            self._output_q.put_nowait(seg)

            # 4. Swap roles
            self._active = other

    async def _dump_segment(self, stream: _StreamState) -> AudioSegment:
        raw_ogg_path = f"{paths()['raw']}/rec_{stream.stream_index}_{uuid.uuid4().hex[:8]}.ogg"
        with open(raw_ogg_path, "wb") as f:
            f.write(stream.chunks[-100000:] if len(stream.chunks) > 100000 else
                    b"".join(stream.chunks[-1000:]) or b"".join(stream.chunks))

        wav_path = raw_ogg_path.rsplit(".", 1)[0] + ".wav"
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", raw_ogg_path,
             "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", wav_path],
            capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            log.error("ffmpeg failed: %s", result.stderr)

        meta = {"station": self.station_id, "stream_index": stream.stream_index,
                "codec": "Opus", "sample_rate": 48000,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}
        meta_path = wav_path + "_meta.json"
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)

        # detect overlap by timestamp diff
        is_dup = False  # TODO: compare last N chars with previous segments
        return AudioSegment(
            stream_index=stream.stream_index, duration_sec=RECORD_DURATION,
            wav_path=wav_path, raw_ogg_path=raw_ogg_path,
            meta_path=meta_path, is_duplicate=is_dup, metadata=meta)

    # ── helpers ─────────────────────────────────

    async def _get_token(self):
        resp = requests.post(JCBA_API_URL,
                             params={"station": self.station_id, "channel": "0",
                                     "quality": "high", "burst": "5"},
                             json={"station": self.station_id}, timeout=10)
        resp.raise_for_status()
        body = resp.json()
        return body["location"], body["token"]

    async def _open_ws(self, url, token):
        ws = await websockets.connect(url,
                                      subprotocols=["listener.fmplapla.com"],
                                      additional_headers={"Authorization": f"Bearer {token}"})
        await ws.send(token)
        log.info("Stream WebSocket connected to %s", url)
        return ws

    async def _refresh_loop(self, stream: _StreamState):
        while stream.alive and self._running:
            await asyncio.sleep(10)
            try:
                tok_url, tok_token = await self._get_token()
                stream.token = tok_token
                stream.expires_at = time.time() + 15
                await stream.ws.send(tok_token)
                log.info("Stream %d token refreshed", stream.stream_index)
            except Exception as e:
                log.warning("Stream %d refresh failed: %s", stream.stream_index, e)
