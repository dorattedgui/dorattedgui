#!/usr/bin/env python3
"""
Scripted Reels Editor - Silence-based video editing pipeline.

Uses FFmpeg silencedetect to find precise silence boundaries,
then applies a keep-segment list to produce a clean cut via
a single filter_complex command (trim + concat).

Usage:
    python edit.py <clip_path> --segments <segments_json> [--output <output_path>]
    python edit.py <clip_path> --detect  # Just run silence detection
"""

import argparse
import json
import subprocess
import sys
import re
from pathlib import Path


# --- Configuration ---

TAIL_TRIM_S = 0.08   # Trim trailing silence/breath from each segment end
CRF = 18             # Quality (18 = visually lossless)
PRESET = "fast"


# --- Silence Detection ---

def detect_silence(clip_path, noise_db=-30, min_duration=0.4):
    """Run FFmpeg silencedetect and parse output."""
    cmd = [
        "ffmpeg", "-i", clip_path,
        "-af", f"silencedetect=noise={noise_db}dB:d={min_duration}",
        "-f", "null", "-"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    silences = []
    starts = {}
    for line in result.stderr.split("\n"):
        if "silence_start:" in line:
            m = re.search(r"silence_start:\s*([\d.]+)", line)
            if m:
                starts["pending"] = float(m.group(1))
        elif "silence_end:" in line:
            m = re.search(r"silence_end:\s*([\d.]+)\s*\|\s*silence_duration:\s*([\d.]+)", line)
            if m and "pending" in starts:
                silences.append({
                    "start": starts["pending"],
                    "end": float(m.group(1)),
                    "duration": float(m.group(2)),
                })
                del starts["pending"]
    return silences


def get_speech_segments(silences, total_duration):
    """Invert silence regions to get speech segments."""
    segments = []
    pos = 0.0

    for s in silences:
        if s["start"] > pos + 0.05:
            segments.append({
                "start": round(pos, 3),
                "end": round(s["start"], 3),
                "duration": round(s["start"] - pos, 3),
            })
        pos = s["end"]

    if pos < total_duration - 0.05:
        segments.append({
            "start": round(pos, 3),
            "end": round(total_duration, 3),
            "duration": round(total_duration - pos, 3),
        })
    return segments


def get_duration(clip_path):
    """Get video duration via ffprobe."""
    result = subprocess.run([
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", clip_path
    ], capture_output=True, text=True)
    return float(json.loads(result.stdout)["format"]["duration"])


# --- FFmpeg Filter Generation ---

def build_filtergraph(segments):
    """Build FFmpeg filter_complex for trimming and concatenating segments."""
    n = len(segments)
    lines = []

    for i, seg in enumerate(segments):
        s, e = seg["start"], seg["end"] - TAIL_TRIM_S
        lines.append(f"[0:v]trim=start={s}:end={e},setpts=PTS-STARTPTS[v{i}];")
        lines.append(f"[0:a]atrim=start={s}:end={e},asetpts=PTS-STARTPTS[a{i}];")

    va_inputs = "".join(f"[v{i}][a{i}]" for i in range(n))
    lines.append(f"{va_inputs}concat=n={n}:v=1:a=1[outv_raw][outa];")
    lines.append("[outv_raw]setpts=PTS-STARTPTS[outv]")
    return "\n".join(lines)


# --- Render ---

def ensure_h264(clip_path):
    """Convert HEVC/10-bit source to H.264 for frame-accurate trimming."""
    probe = subprocess.run([
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", clip_path
    ], capture_output=True, text=True)
    streams = json.loads(probe.stdout)["streams"]
    vs = [s for s in streams if s["codec_type"] == "video"][0]

    if vs["codec_name"] == "h264" and vs.get("pix_fmt") == "yuv420p":
        return clip_path

    h264_path = str(Path(clip_path).with_suffix(".h264.mp4"))
    if Path(h264_path).exists():
        print(f"  Using cached H.264 conversion: {Path(h264_path).name}")
        return h264_path

    print(f"  Converting {vs['codec_name']} ({vs.get('pix_fmt')}) to H.264...")
    result = subprocess.run([
        "ffmpeg", "-y", "-i", clip_path,
        "-c:v", "libx264", "-crf", "16", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-g", "15",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        h264_path
    ], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR: H.264 conversion failed!")
        print(result.stderr[-1000:])
        sys.exit(1)
    return h264_path


def render(clip_path, segments, output_path):
    """Render the edit using a single FFmpeg filter_complex command."""
    clip_path = ensure_h264(clip_path)
    filtergraph = build_filtergraph(segments)

    fg_path = Path(output_path).with_suffix(".filtergraph.txt")
    fg_path.write_text(filtergraph)

    temp_path = output_path + ".tmp.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-i", clip_path,
        "-filter_complex", filtergraph,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-crf", str(CRF), "-preset", PRESET,
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        temp_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"\n  ERROR: FFmpeg render failed!")
        print(result.stderr[-2000:])
        sys.exit(1)

    # Re-mux to strip the edit list (fixes black first frame)
    print(f"  Stripping edit list...")
    remux = subprocess.run([
        "ffmpeg", "-y",
        "-fflags", "+genpts+igndts",
        "-i", temp_path,
        "-c", "copy",
        "-movflags", "+faststart",
        output_path
    ], capture_output=True, text=True)

    Path(temp_path).unlink(missing_ok=True)

    if remux.returncode != 0:
        print(f"\n  ERROR: Re-mux failed!")
        print(remux.stderr[-1000:])
        sys.exit(1)
    return output_path


def verify_output(output_path):
    """Run post-render checks."""
    dur = get_duration(output_path)
    size_mb = Path(output_path).stat().st_size / 1024 / 1024
    print(f"  Duration: {dur:.1f}s")
    print(f"  Size: {size_mb:.1f}MB")

    result = subprocess.run([
        "ffmpeg", "-i", output_path,
        "-af", "silencedetect=noise=-30dB:d=0.5",
        "-f", "null", "-"
    ], capture_output=True, text=True)

    silence_lines = [l for l in result.stderr.split("\n") if "silence_start" in l or "silence_end" in l]
    if silence_lines:
        print(f"  WARNING: {len(silence_lines)//2} silence gaps > 0.5s in output")
    else:
        print(f"  No silence gaps > 0.5s detected")


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="Scripted Reels Editor")
    parser.add_argument("clip", help="Path to source video clip")
    parser.add_argument("--segments", "-s", help="Path to keep-segments JSON file")
    parser.add_argument("--detect", action="store_true", help="Just run silence detection")
    parser.add_argument("--output", "-o", help="Output path")
    args = parser.parse_args()

    clip_path = args.clip
    total_duration = get_duration(clip_path)
    clip_name = Path(clip_path).stem

    print(f"\n{'='*60}")
    print(f"  Scripted Reels Editor")
    print(f"  Clip: {clip_name} ({total_duration:.1f}s)")
    print(f"{'='*60}\n")

    if args.detect:
        print("[1/1] Running silence detection...")
        silences = detect_silence(clip_path)
        print(f"  Found {len(silences)} silence gaps\n")

        speech = get_speech_segments(silences, total_duration)
        print(f"  Speech segments ({len(speech)}):")
        for i, seg in enumerate(speech):
            print(f"    [{i:2d}] {seg['start']:7.2f}s - {seg['end']:7.2f}s  ({seg['duration']:.1f}s)")

        total_speech = sum(s["duration"] for s in speech)
        total_silence = total_duration - total_speech
        print(f"\n  Speech: {total_speech:.1f}s | Silence: {total_silence:.1f}s ({total_silence/total_duration*100:.0f}%)")

        out_json = Path(clip_path).parent / "final" / f"{clip_name}-speech-segments.json"
        out_json.parent.mkdir(parents=True, exist_ok=True)
        with open(out_json, "w") as f:
            json.dump({"speech": speech, "silences": silences}, f, indent=2)
        print(f"  Saved: {out_json}")
        return

    if not args.segments:
        print("ERROR: Provide --segments <json> or use --detect first")
        sys.exit(1)

    with open(args.segments) as f:
        segments = json.load(f)

    if isinstance(segments, dict) and "keep" in segments:
        segments = segments["keep"]

    print(f"  Loaded {len(segments)} keep segments")

    kept = sum(s["end"] - s["start"] for s in segments)
    cut = total_duration - kept
    print(f"  Original: {total_duration:.1f}s")
    print(f"  Keeping:  {kept:.1f}s")
    print(f"  Cutting:  {cut:.1f}s ({cut/total_duration*100:.0f}%)\n")

    for i, seg in enumerate(segments):
        dur = seg["end"] - seg["start"]
        label = seg.get("label", "")
        print(f"  [{i+1:2d}] {seg['start']:7.2f}s - {seg['end']:7.2f}s ({dur:.1f}s) {label}")

    if args.output:
        output_path = args.output
    else:
        output_path = str(Path(clip_path).parent / "final" / f"{clip_name}-edit.mp4")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    print(f"\n  Rendering...")
    render(clip_path, segments, output_path)

    print(f"\n  Output: {output_path}")
    verify_output(output_path)

    print(f"\n  Done!")


if __name__ == "__main__":
    main()
