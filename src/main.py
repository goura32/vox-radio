"""Pipeline orchestrator — main entry point."""
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

from src.radio.receiver import Receiver
from src.transcription.transcriber import Transcriber
from src.summarization.summarizer import Summarizer
from src.tts.vox_player import VoxSynthesizer
from src.vr_renderer.vrm_generator import VRMVisualizer


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("output/pipeline.log"),
    ],
)
log = logging.getLogger("vox-radio.pipeline")


async def run_batch():
    """Run one complete pipeline cycle."""
    log.info("=== Pipeline batch start ===")

    # 1. Receive audio
    receiver = Receiver()
    await receiver.open()
    log.info("Receiving for %d seconds...", 10)
    frames = await receiver.receive_frames(10)
    log.info("Received %d frames", len(frames))

    wav_path = receiver.save_raw_to_wav(f"output/raw/batch_{int(time.time())}.wav")
    log.info("Raw audio: %s", wav_path)

    # 2. Transcribe
    transcriber = Transcriber()
    result = transcriber.transcribe_file(wav_path)
    log.info("Transcribed (%d segments): %s", len(result.segments), result.raw_transcript[:100])

    # 3. Summarize
    summarizer = Summarizer()
    summary = summarizer.summarize(result.raw_transcript)
    log.info("Summary: %s", summary.summary[:80])
    log.info(
        "Sentiment: %s (score=%.2f)",
        summary.sentiment.get("label", "neutral"),
        summary.sentiment.get("score", 0),
    )
    if summary.emotions:
        log.info("Dominant emotion: %s", summary.emotions.dominant())
        log.info("Emotions: %s", summary.emotions)

    # 4. VOICEVOX synthesis
    if summary.summary:
        synth = VoxSynthesizer()
        wav_file = synth.save_synthesis(summary.summary)
        log.info("Synthesized: %s", wav_file)
    else:
        wav_file = ""
        log.warning("No summary text — skipping synthesis")

    # 5. VRM blend shapes
    vrm = VRMVisualizer()
    emotion = "happy" if summary.sentiment.get("score", 0.5) > 0.6 else "neutral"
    weight = min(1.0, summary.sentiment.get("score", 0.5))
    expr_frame = vrm.set_expression(emotion, weight)
    expr_frame.save_frame()
    motion_frame = vrm.set_body_motion(breath_scale=0.02)
    motion_frame.save_frame()
    log.info("VRM frames saved")

    # Save batch record
    record = {
        "batch_id": result.batch_id,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "transcript_file": result.raw_transcript,
        "summary_file": summary.summary,
        "synth_file": wav_file,
    }
    with open(f"output/batch_record_{result.batch_id}.json", "w") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    await receiver.close()
    log.info("=== Pipeline batch end ===\n")


async def main():
    """Main loop — continuous pipeline."""
    log.info("=== VOX-Radio Pipeline starting ===")
    log.info("Station: HeartFM")
    log.info("Whisper: large-v3-turbo")
    log.info("LLM: Ollama (gemma4:e4b)")

    for i in range(5):
        try:
            await run_batch()
        except Exception as e:
            log.error("Batch %d failed: %s", i, e, exc_info=True)
        time.sleep(1)

    log.info("=== Pipeline complete! ===")


if __name__ == "__main__":
    asyncio.run(main())
