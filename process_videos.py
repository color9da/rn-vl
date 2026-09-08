"""
Video Processor - Quality Enhancement (Video + Audio)
1. Upscale video to 1080x1920 with quality enhancement
2. Remove watermark (bottom-right corner)
3. ENHANCE AUDIO (normalize volume, improve clarity) - if audio exists
4. Loop short videos (< 10s) twice to make them longer (e.g., 6s → 12s)
"""
import os
import subprocess
import sys
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

input_dir = "Videos"
output_dir = "Processed_Videos"

if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Threshold for looping: videos shorter than this will be looped twice
SHORT_VIDEO_THRESHOLD = 10  # seconds


def process_single_video(video_path):
    if not os.path.exists(video_path):
        print(f"Error: Video not found: {video_path}")
        return None

    filename = os.path.basename(video_path)
    out_path = os.path.join(output_dir, filename)

    if os.path.exists(out_path):
        print(f"Skipping {filename} - already processed")
        return out_path

    cmd_probe = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=s=x:p=0",
        video_path
    ]
    try:
        res = subprocess.check_output(cmd_probe).decode("utf-8").strip()
        width, height = map(int, res.split("x"))
    except Exception as e:
        print(f"Failed to get resolution for {video_path}: {e}")
        return None

    cmd_audio = [
        "ffprobe", "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_type",
        "-of", "csv=p=0",
        video_path
    ]
    try:
        audio_check = subprocess.check_output(cmd_audio).decode("utf-8").strip()
        has_audio = bool(audio_check)
    except:
        has_audio = False

    # Get video duration
    cmd_duration = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        video_path
    ]
    try:
        duration = float(subprocess.check_output(cmd_duration).decode("utf-8").strip())
    except:
        duration = 0

    # Determine if video should be looped
    should_loop = duration < SHORT_VIDEO_THRESHOLD and duration > 0
    loop_count = 2 if should_loop else 1

    print(f"Original size: {width}x{height}")
    print(f"Duration: {duration:.2f}s")
    print(f"Has audio: {'Yes' if has_audio else 'No'}")
    if should_loop:
        print(f"Looping: Yes (will play {loop_count}x → {duration * loop_count:.2f}s)")
    else:
        print(f"Looping: No (video is {duration:.2f}s)")

    w_delogo = 180
    h_delogo = 80
    x_delogo = 1080 - w_delogo - 5
    y_delogo = 1920 - h_delogo - 5

    print(f"Processing {filename}...")
    print(f"  Upscaling to: 1080x1920 (proportional zoom & crop to 9:16 - no stretching)")
    print(f"  Removing watermark at: x={x_delogo}, y={y_delogo}, w={w_delogo}, h={h_delogo}")
    print(f"  Video: ENHANCED (sharpen + clarity boost)")
    if has_audio:
        print(f"  Audio: ENHANCED (normalize volume + improve clarity)")
    else:
        print(f"  Audio: No audio in original video")

    # Proportional scale (zoom to fill 9:16) + center crop + square pixel aspect ratio (no stretching)
    video_filter = (
        f"scale='if(gt(a,9/16),-2,1080)':'if(gt(a,9/16),1920,-2)':flags=lanczos,"
        f"crop=1080:1920,setsar=1,"
        f"unsharp=5:5:1.0:5:5:0.0,cas=0.7,"
        f"delogo=x={x_delogo}:y={y_delogo}:w={w_delogo}:h={h_delogo}"
    )

    # Build the filter complex
    if should_loop:
        # For looping: split video, process each, then concat
        # Use aloop for audio (simpler and more efficient)
        vf_base = f"[0:v]split={loop_count}" + "".join([f"[v{i}]" for i in range(loop_count)]) + ";" + \
                  ";".join([f"[v{i}]{video_filter}[lv{i}]" for i in range(loop_count)]) + ";" + \
                  f"{'' .join([f'[lv{i}]' for i in range(loop_count)])}concat=n={loop_count}:v=1:a=0[v]"
    else:
        vf_base = f"[0:v]{video_filter}[v]"

    if has_audio:
        if should_loop:
            # Loop audio using aloop filter, then enhance
            # loop=1 means play twice (original + 1 loop)
            af_filter = f"[0:a]aloop=loop={loop_count-1}:size=2e+09[a1];[a1]loudnorm=I=-16:TP=-1.5:LRA=11,dynaudnorm=50:3:0.5[a]"
        else:
            af_filter = f"[0:a]loudnorm=I=-16:TP=-1.5:LRA=11,dynaudnorm=50:3:0.5[a]"
        
        # Combine video and audio filters
        full_filter = f"{vf_base};{af_filter}"

        cmd_ffmpeg = [
            "ffmpeg", "-y", "-i", video_path,
            "-filter_complex", full_filter,
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", "libx264", "-preset", "slow", "-crf", "16",
            "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            out_path
        ]
    else:
        cmd_ffmpeg = [
            "ffmpeg", "-y", "-i", video_path,
            "-filter_complex", vf_base,
            "-map", "[v]",
            "-c:v", "libx264", "-preset", "slow", "-crf", "16",
            "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-an",
            out_path
        ]

    print("  Processing... (enhancement in progress)")
    result = subprocess.run(cmd_ffmpeg, capture_output=True, text=True)

    if result.returncode == 0:
        print(f"✅ Saved: {out_path} (ENHANCED)")
        return out_path
    else:
        print(f"❌ Failed: {result.stderr[-500:]}")
        return None


def main():
    specific_video = sys.argv[1] if len(sys.argv) > 1 else None

    if specific_video:
        result = process_single_video(specific_video)
        if result:
            print("\n" + "=" * 60)
            print("PROCESSING COMPLETE - VIDEO & AUDIO ENHANCED")
            print("=" * 60)
        else:
            sys.exit(1)
    else:
        videos = [f for f in os.listdir(input_dir) if f.endswith('.mp4')]
        print(f"Found {len(videos)} videos to process.")

        for filename in videos:
            vid_path = os.path.join(input_dir, filename)
            process_single_video(vid_path)

        print("\n" + "=" * 60)
        print("PROCESSING COMPLETE")
        print("=" * 60)


if __name__ == "__main__":
    main()
