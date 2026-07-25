"""Performance Benchmarks for AIRA Voice Platform.

Measures latency and startup duration.
"""

import time
import structlog
from aira.app import AIRAApplication

logger = structlog.get_logger("aira.benchmark")


def run_benchmark() -> None:
    """Execute end-to-end voice platform benchmarks."""
    logger.info("Starting baseline voice platform benchmarks...")
    
    # 1. Startup latency
    t0 = time.perf_counter()
    app = AIRAApplication()
    app.start()
    startup_duration = time.perf_counter() - t0
    
    # 2. Wake detection latency
    assert app.voice_session is not None
    app.voice_session.start_session()
    
    t0 = time.perf_counter()
    app.voice_session.process_audio(b"HEY_AIRA_TRIGGER")
    wake_duration = time.perf_counter() - t0

    # 3. Speech recognition and request normalization latency
    assert app.speech_recognition is not None
    assert app.intent is not None
    assert app.request_normalization is not None
    active_sess = app.voice_session.active_session
    assert active_sess is not None

    t0 = time.perf_counter()
    result = app.speech_recognition.transcribe_audio(b"DEMO_OPEN_SAFARI")
    intent_res = app.intent.recognize_intent(result.text, active_sess.session_id)
    req = app.request_normalization.create_request(intent_res)
    stt_norm_duration = time.perf_counter() - t0

    app.voice_session.close_session()
    app.stop()

    print("\n==================================================")
    print("           AIRA OS VOICE PLATFORM BENCHMARKS      ")
    print("==================================================")
    print(f"Startup Time:                   {startup_duration * 1000:.2f} ms")
    print(f"Wake Detection Time:            {wake_duration * 1000:.2f} ms")
    print(f"STT + Normalization Time:       {stt_norm_duration * 1000:.2f} ms")
    print("==================================================\n")


if __name__ == "__main__":
    run_benchmark()
