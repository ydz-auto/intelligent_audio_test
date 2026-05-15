def test_stop_task_audio_by_pattern_handles_non_string_task_ids(monkeypatch):
    import threading
    import pyaudio

    class DummyPyAudio:
        pass

    monkeypatch.setattr(pyaudio, "PyAudio", lambda: DummyPyAudio())

    from backend.utils.audio_engine import audio_service

    audio_service.active_players = {
        123: {"dry": {"thread": None, "stop_event": threading.Event()}},
        "abc": {"dry": {"thread": None, "stop_event": threading.Event()}},
    }

    stopped = audio_service.stop_task_audio_by_pattern("*", "*")
    assert stopped == 2
    assert audio_service.active_players == {}

