
import argparse
import os
import sys
import time

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
parent_dir = os.path.dirname(backend_dir)
sys.path.insert(0, backend_dir)
sys.path.insert(0, parent_dir)

from backend.utils.audio_engine import audio_service


def _default_audio_path():
    candidate = os.path.join(backend_dir, "static", "audios", "temp_test.wav")
    if os.path.exists(candidate):
        return candidate
    return None


def main():
    parser = argparse.ArgumentParser(description="Play audio on a specific output device/channel")
    parser.add_argument("--device", default="Analog (3+4)", help="Device name substring, e.g. 'Analog (3+4)'")
    parser.add_argument("--ch", type=int, default=1, help="1-based channel index, e.g. 1")
    parser.add_argument("--file", default=_default_audio_path(), help="WAV file path to play")
    parser.add_argument("--gain", type=float, default=1.0, help="Linear gain (before GLOBAL_SAFE_GAIN)")
    parser.add_argument("--seconds", type=float, default=5.0, help="Seconds to play when loop is enabled")
    parser.add_argument("--loop", action="store_true", help="Loop playback until stopped")
    args = parser.parse_args()

    if not args.file:
        raise SystemExit("No default audio found. Please pass --file <wav_path>.")
    if not os.path.isabs(args.file):
        args.file = os.path.abspath(args.file)
    if not os.path.exists(args.file):
        raise SystemExit(f"Audio file not found: {args.file}")

    if args.ch <= 0:
        raise SystemExit("--ch must be >= 1")

    candidates = audio_service.get_all_physical_devices()
    target_sub = args.device.strip().lower()
    target_ch_suffix = f"[ch {args.ch}]"

    matched = [
        c
        for c in candidates
        if target_sub in (c.get("name") or "").lower() and target_ch_suffix in (c.get("name") or "").lower()
    ]

    if not matched:
        print(f"No device match for device~='{args.device}' and ch={args.ch}. Available candidates:")
        for c in candidates[:80]:
            print(f"  - {c.get('name')}")
        raise SystemExit(2)

    selected = matched[0]
    device_unique_id = selected["unique_id"]
    channel_index = selected["channel_index"]
    device_index = audio_service.get_device_index(device_unique_id)

    if device_index is None:
        raise SystemExit(f"Failed to resolve device_index for: {device_unique_id}")

    task_id = f"manual_{int(time.time())}"
    player_type = "manual"

    print("Selected output:")
    print(f"  device_unique_id: {device_unique_id}")
    print(f"  device_index:     {device_index}")
    print(f"  channel_index:    {channel_index} (0-based)")
    print(f"  file:            {args.file}")
    print(f"  gain:            {args.gain} (linear, before GLOBAL_SAFE_GAIN)")
    print(f"  loop:            {args.loop}")

    thread = audio_service.play_audio(
        task_id=task_id,
        file_path=args.file,
        device_index=device_index,
        channel_index=channel_index,
        gain=args.gain,
        loop=args.loop,
        player_type=player_type,
    )

    if args.loop:
        time.sleep(max(args.seconds, 0.1))
        audio_service.stop_task_audio(task_id, player_type=player_type)
        thread.join(timeout=2.0)
        print("Stopped.")
    else:
        thread.join()
        print("Done.")


if __name__ == "__main__":
    main()

