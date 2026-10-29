"""Generate the fixed kiosk phrase offline with an explicitly supplied eSpeak NG."""

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import tempfile
import wave
from array import array
from pathlib import Path


def run(command):
    return subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")


def firm_audio(source, destination, ffmpeg):
    # Preserve lexical tones; use gentle presence EQ and compression to make
    # both syllables audible, then normalize with a true-peak ceiling.
    shaping = (
        "silenceremove=start_periods=1:start_duration=0.01:start_threshold=-50dB:start_silence=0.03,"
        "areverse,silenceremove=start_periods=1:start_duration=0.01:start_threshold=-50dB:start_silence=0.08,"
        "areverse,highpass=f=85,lowpass=f=7000,equalizer=f=2200:t=q:w=1.2:g=2,"
        "acompressor=threshold=0.0631:ratio=4:attack=2:release=50:makeup=1"
    )
    target = "loudnorm=I=-11:TP=-1:LRA=5"
    measured = run([str(ffmpeg), "-hide_banner", "-nostdin", "-i", str(source), "-af",
                    shaping+","+target+":print_format=json", "-f", "null", "-"])
    values = json.loads(re.findall(r'\{\s*"input_i".*?\}', measured.stderr, re.S)[-1])
    if not all(math.isfinite(float(values[key])) for key in ("input_i", "input_tp", "input_lra", "input_thresh")):
        raise ValueError("Speech loudness measurement is invalid")
    normalize = (target+f":measured_I={values['input_i']}:measured_TP={values['input_tp']}"
                 +f":measured_LRA={values['input_lra']}:measured_thresh={values['input_thresh']}"
                 +f":offset={values['target_offset']}:linear=true")
    filters = (shaping+","+normalize+",alimiter=limit=0.891251:level=false,"
               "afade=t=in:d=0.005,areverse,afade=t=in:d=0.02,areverse")
    run([str(ffmpeg), "-hide_banner", "-nostdin", "-y", "-i", str(source), "-af", filters,
         "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(destination)])


def audio_info(path):
    with wave.open(str(path)) as audio:
        if audio.getnchannels() != 1 or audio.getsampwidth() != 2 or audio.getnframes() == 0:
            raise ValueError("Invalid kiosk audio output")
        samples = array("h", audio.readframes(audio.getnframes()))
        peak = max(abs(value) for value in samples)/32768
        rms = math.sqrt(sum(value*value for value in samples)/len(samples))/32768
        return {"sample_rate": audio.getframerate(), "duration_seconds": round(len(samples)/audio.getframerate(), 4),
                "peak_dbfs": round(20*math.log10(peak), 2), "rms_dbfs": round(20*math.log10(rms), 2),
                "clipped_samples": sum(abs(value) >= 32767 for value in samples),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", required=True, type=Path)
    parser.add_argument("--data-root", required=True, type=Path,
                        help="Folder containing espeak-ng-data")
    parser.add_argument("--style", choices=("standard", "firm"), default="standard")
    parser.add_argument("--ffmpeg", type=Path, help="Local FFmpeg executable, required for firm style")
    args = parser.parse_args()
    executable = args.executable.resolve(strict=True)
    data_root = args.data_root.resolve(strict=True)
    folder = Path(__file__).resolve().parents[1] / "frontend/public/audio"
    destination = folder / ("hop-le-dut-khoat.wav" if args.style == "firm" else "hop-le.wav")
    ffmpeg = args.ffmpeg.resolve(strict=True) if args.ffmpeg else None
    if args.style == "firm" and ffmpeg is None:
        raise ValueError("Firm style requires a local FFmpeg executable")
    with tempfile.TemporaryDirectory(prefix="chamcong-audio-") as directory:
        temporary = Path(directory)
        # This Windows eSpeak build cannot load its data through the accented
        # workspace path. Run a temporary local copy with an ASCII path.
        portable = temporary / "tts"
        portable.mkdir()
        shutil.copy2(executable, portable / executable.name)
        for library in executable.parent.glob("*.dll"):
            shutil.copy2(library, portable / library.name)
        shutil.copytree(data_root / "espeak-ng-data", portable / "espeak-ng-data")
        phrase = temporary / "phrase.txt"
        output = temporary / "hop-le.wav"
        phrase.write_text("Hợp lệ." if args.style == "firm" else "Hợp lệ", encoding="utf-8")
        command = [str(portable / executable.name), f"--path={portable}", "-v", "vi", "-s",
                   "150" if args.style == "firm" else "155", "-p", "42" if args.style == "firm" else "50"]
        if args.style == "firm":
            command += ["-a", "100", "-g", "6"]
        run(command + ["-f", str(phrase), "-w", str(output)])
        audio_info(output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if args.style == "firm":
            processed = temporary / "firm.wav"
            firm_audio(output, processed, ffmpeg)
            info = audio_info(processed)
            if info["clipped_samples"] or info["peak_dbfs"] > -.8:
                raise ValueError("Speech output exceeds the safe peak ceiling")
            shutil.copyfile(processed, destination)
        else:
            shutil.copyfile(output, destination)
    print(json.dumps({"file": destination.name, "style": args.style, "offline": True, **audio_info(destination)}))


if __name__ == "__main__":
    main()
