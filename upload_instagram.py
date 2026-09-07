"""
Instagram Upload - Entrypoint forwarding to upload.upload_instagram
"""

from upload.upload_instagram import upload_to_instagram

if __name__ == '__main__':
    from pathlib import Path
    import sys
    video_file = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('rn_vl_short.mp4')
    if video_file.exists():
        result = upload_to_instagram(str(video_file), "Test caption")
        print("Result:", result)
    else:
        print(f"Video not found: {video_file}")
