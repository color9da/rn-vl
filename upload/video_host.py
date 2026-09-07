"""
Unified Video Hosting Utility
Hosts video files on a public URL for social media APIs (Instagram Reels, Instagram Stories, Threads).
Supports:
1. GitHub raw content (rn_vl_short.mp4 via git push - handles files up to 100MB)
2. tmpfiles.org (fallback 1)
3. catbox.moe (fallback 2)
Caches public URL across platforms in the same run to avoid redundant commits.
"""

import os
import shutil
import subprocess
import requests
from pathlib import Path

_CACHED_VIDEO_URL = None
_CACHED_VIDEO_PATH = None


def host_video_on_github(video_path_obj: Path) -> str:
    """
    Commit the video into the repo at rn_vl_short.mp4 via git push and return its
    raw.githubusercontent.com URL.
    Works for files up to 100MB (unlike GitHub Contents REST API which has a 25MB limit).
    """
    gh_token = os.getenv("GH_TOKEN") or os.getenv("GH_PAT") or os.getenv("GITHUB_TOKEN")
    if not gh_token:
        raise ValueError("GH_TOKEN/GH_PAT/GITHUB_TOKEN not set for GitHub video hosting")

    repo = os.getenv("GITHUB_REPOSITORY", "color9da/rn-vl")
    raw_url = f"https://raw.githubusercontent.com/{repo}/main/rn_vl_short.mp4"

    print("[video_host] Hosting video on GitHub raw (rn_vl_short.mp4)...")
    dest = Path("rn_vl_short.mp4")
    shutil.copyfile(video_path_obj, dest)

    env = dict(os.environ, GH_TOKEN=gh_token)
    cmds = [
        ["git", "config", "--global", "user.email", "github-actions[bot]@users.noreply.github.com"],
        ["git", "config", "--global", "user.name", "github-actions[bot]"],
        ["git", "add", "-f", "rn_vl_short.mp4"],
    ]
    for c in cmds:
        subprocess.run(c, capture_output=True, env=env)

    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True, env=env)
    if diff.returncode == 0:
        print("[video_host] Media unchanged on GitHub, reusing URL")
    else:
        subprocess.run(["git", "commit", "-m", "chore: update media [skip ci]"], capture_output=True, env=env)
        subprocess.run(["git", "config", "http.extraHeader", f"AUTHORIZATION: bearer {gh_token}"], capture_output=True, env=env)
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], capture_output=True, env=env)
        push = subprocess.run(["git", "push", "origin", "HEAD:main"], capture_output=True, env=env, text=True)
        subprocess.run(["git", "config", "--unset", "http.extraHeader"], capture_output=True, env=env)
        if push.returncode != 0:
            raise ValueError(f"git push failed: {push.stderr[-300:] if push.stderr else 'Unknown git error'}")

    print(f"[video_host] GitHub URL ready: {raw_url}")
    return raw_url


def host_video_on_tmpfiles(video_path_obj: Path) -> str:
    """Upload to tmpfiles.org and return a direct download URL (fallback 1)."""
    print("[video_host] Attempting upload to tmpfiles.org...")
    with open(video_path_obj, 'rb') as video_file:
        files = {'file': ('video.mp4', video_file, 'video/mp4')}
        resp = requests.post('https://tmpfiles.org/api/v1/upload', files=files, timeout=180)

    if resp.status_code != 200:
        raise Exception(f"tmpfiles.org upload failed with status {resp.status_code}")

    temp_data = resp.json()
    if temp_data.get('status') != 'success':
        raise Exception(f"tmpfiles.org failed: {temp_data}")

    temp_url = temp_data.get('data', {}).get('url', '')
    video_url = temp_url.replace('tmpfiles.org/', 'tmpfiles.org/dl/').replace('http://', 'https://')
    print(f"[video_host] tmpfiles.org URL ready: {video_url}")
    return video_url


def host_video_on_catbox(video_path_obj: Path) -> str:
    """Upload to catbox.moe and return direct URL (fallback 2)."""
    print("[video_host] Attempting upload to catbox.moe...")
    with open(video_path_obj, 'rb') as f:
        resp = requests.post(
            'https://catbox.moe/user/api.php',
            data={'reqtype': 'fileupload'},
            files={'fileToUpload': f},
            timeout=180
        )
    if resp.status_code == 200 and resp.text.startswith('http'):
        url = resp.text.strip()
        print(f"[video_host] catbox.moe URL ready: {url}")
        return url
    raise Exception(f"catbox.moe upload failed: {resp.text[:200]}")


def get_public_video_url(video_path) -> str:
    """
    Get a public direct URL for the video file.
    Caches the URL during the current process so multiple platforms (Instagram Reel, Story, Threads)
    reuse the exact same URL without uploading or committing multiple times.
    """
    global _CACHED_VIDEO_URL, _CACHED_VIDEO_PATH
    video_path_obj = Path(video_path).resolve()

    if _CACHED_VIDEO_URL and _CACHED_VIDEO_PATH == str(video_path_obj):
        print(f"[video_host] Using cached public video URL: {_CACHED_VIDEO_URL}")
        return _CACHED_VIDEO_URL

    # 1. Preferred: GitHub raw hosting via Git (supports files up to 100MB)
    try:
        url = host_video_on_github(video_path_obj)
        _CACHED_VIDEO_URL = url
        _CACHED_VIDEO_PATH = str(video_path_obj)
        return url
    except Exception as gh_err:
        print(f"[video_host] GitHub raw hosting failed: {gh_err}")

    # 2. Fallback 1: tmpfiles.org
    try:
        url = host_video_on_tmpfiles(video_path_obj)
        _CACHED_VIDEO_URL = url
        _CACHED_VIDEO_PATH = str(video_path_obj)
        return url
    except Exception as tmp_err:
        print(f"[video_host] tmpfiles.org fallback failed: {tmp_err}")

    # 3. Fallback 2: catbox.moe
    try:
        url = host_video_on_catbox(video_path_obj)
        _CACHED_VIDEO_URL = url
        _CACHED_VIDEO_PATH = str(video_path_obj)
        return url
    except Exception as cb_err:
        print(f"[video_host] catbox.moe fallback failed: {cb_err}")

    raise RuntimeError("All video hosting methods failed to obtain a public URL")
