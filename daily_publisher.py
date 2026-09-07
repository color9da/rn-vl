import os
import json
import glob
import requests
import shutil
import sys
from datetime import datetime, timezone
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
load_dotenv()

# Import upload functions
try:
    from upload.upload_instagram import upload_to_instagram
    from upload.upload_threads import upload_to_threads
    from upload.upload_facebook import upload_to_facebook, upload_to_facebook_story
    from upload.upload_to_youtube import upload_to_youtube
except ImportError as e:
    print(f"Error importing upload modules: {e}")
    # Still want to proceed or stop?
    pass

PROCESSED_DIR = "Processed_Videos"
PUBLISHED_LOG = "published_videos.json"

def get_already_published():
    if os.path.exists(PUBLISHED_LOG):
        with open(PUBLISHED_LOG, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []

def mark_as_published(video_name, metadata):
    published = get_already_published()
    # Add timestamp for fair rotation tracking
    metadata["published_at"] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    published.append({
        "video_name": video_name,
        "metadata": metadata
    })
    with open(PUBLISHED_LOG, 'w', encoding='utf-8') as f:
        json.dump(published, f, indent=4)

def select_video(specific_video=None):
    published_entries = get_already_published()
    published_names = [item["video_name"] for item in published_entries]
    all_videos = sorted(glob.glob(os.path.join(PROCESSED_DIR, "*.mp4")))

    if specific_video:
        # specific_video might be a full path or just a filename
        if os.path.exists(specific_video):
            # It's a full path
            vid_path = specific_video
            name = os.path.basename(specific_video)
        else:
            # It's just a filename, join with PROCESSED_DIR
            vid_path = os.path.join(PROCESSED_DIR, specific_video)
            name = specific_video

        if os.path.exists(vid_path):
            if name in published_names:
                print(f"🔄 Video {name} was already published - Re-publishing (recycling)")
            return vid_path, name
        else:
            print(f"❌ Error: Specific video {name} not found")
            return None, None

    # Find first unpublished video
    for vid in all_videos:
        name = os.path.basename(vid)
        if name not in published_names:
            return vid, name
    
    # All videos are published - use FAIR ROTATION
    if all_videos:
        print(f"\n⚠️  All videos have been published. Recycling with fair rotation...")

        # Build a mapping of video name -> last published timestamp
        # We want to find the video that was published LEAST recently (oldest)
        video_last_published = {}
        for entry in published_entries:
            video_name = entry.get('video_name', '')
            if video_name:
                # Get the timestamp from metadata
                timestamp = entry.get('metadata', {}).get('published_at', '')
                # Store/update with the latest timestamp for this video
                video_last_published[video_name] = timestamp

        # Find the video with the oldest (or missing) timestamp
        # Videos without timestamps are prioritized, then oldest first
        video_to_recycle = None
        oldest_timestamp = None

        for vid_path in all_videos:
            vid_name = os.path.basename(vid_path)
            if vid_name not in video_last_published:
                # This video has no timestamp - prioritize it
                video_to_recycle = vid_path
                break
            else:
                ts = video_last_published[vid_name]
                if oldest_timestamp is None or ts < oldest_timestamp:
                    oldest_timestamp = ts
                    video_to_recycle = vid_path

        # Fallback to first video if nothing found
        if not video_to_recycle:
            video_to_recycle = all_videos[0]

        name = os.path.basename(video_to_recycle)
        print(f"🔄 Re-publishing (fair rotation): {name}")
        return video_to_recycle, name
    
    return None, None

def generate_caption():
    import random
    import time

    api_key = os.getenv("POLLINATIONS_API_KEY")
    model = os.getenv("AI_MODEL", "openai")
    if not api_key:
        print("Warning: POLLINATIONS_API_KEY not found. Using default captions.")
        return "Living my wildest dreams ✨", "Dancing through life's beautiful moments 💃 #wildandfree #dancing #soulful #livingmybestlife"

    vibes = [
        "wild and dreamy",
        "soulful and free-spirited",
        "radiant and untamed",
        "graceful and magical",
        "bold and enchanting"
    ]
    chosen_vibe = random.choice(vibes)

    prompt = (
        f"Write a completely unique, deeply emotional, and engaging title and LONG description for a short video "
        f"of me, Reena Veloria. In the video, I am a beautiful model living my wildest dreams, "
        f"dancing through life, and enjoying every beautiful moment. I'm a free spirit who loves "
        f"the beauty of life, expressing my soul through movement and embracing the magic of "
        f"being a wild, authentic woman. Speak in the first person. "
        f"Make the vibe {chosen_vibe}. Make it deeply personal and emotional - describe the feelings, "
        f"the desires, the freedom, the joy of being alive and wild. Write at least 4-5 sentences "
        f"that really express the soul and heart behind the moment. Make people FEEL something. "
        f"Make it interaction-bait to gain followers. "
        f"Include relevant hashtags in ALL LOWERCASE like #wildandfree #dancing #soulful #livingmybestlife "
        f"#wildestdreams #dance #beautiful #moments #freeSpirit. "
        f"Return ONLY a valid JSON object in this format: {{\"title\": \"<title>\", \"description\": \"<description>\"}} "
        f"Do not include any other text or markdown block backticks."
    )

    url = "https://gen.pollinations.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.9,
        "seed": random.randint(1, 999999)
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        content = data.get('choices', [{}])[0].get('message', {}).get('content', '')

        # Clean up any potential markdown block markers
        content = content.replace("```json", "").replace("```", "").strip()
        result = json.loads(content)

        return result.get("title", "Living my wildest dreams ✨"), result.get("description", "Dancing through life's beautiful moments 💃 #wildandfree #dancing #soulful")
    except Exception as e:
        print(f"Error generating caption: {e}")
        return "Living my wildest dreams ✨", "Dancing through life's beautiful moments 💃 #wildandfree #dancing #soulful #wildestdreams"

def main():
    print("=" * 60)
    print("🚀 DAILY AUTOMATION STARTING")
    print("=" * 60)
    
    specific_video = sys.argv[1] if len(sys.argv) > 1 else None
    video_path, video_name = select_video(specific_video)
    if not video_path:
        print("✅ No videos found in Processed_Videos folder.")
        print("   (Download new videos from Google Drive first)")
        return
        
    print(f"👉 Selected Video: {video_name}")
    print("🧠 Generating caption via Pollination AI...")
    title, description = generate_caption()
    
    print(f"📝 Title: {title}")
    print(f"📝 Description:\n{description}")
    
    # Combined caption for platforms that use a single text field
    combined_caption = f"{title}\n\n{description}"
    
    success_flags = {
        "instagram_reel": False,
        "instagram_story": False,
        "facebook_reel": False,
        "facebook_story": False,
        "threads": False,
        "youtube": False
    }
    
    # Acquire public video URL once so Instagram Reels, Instagram Stories, and Threads reuse it
    public_video_url = None
    try:
        from upload.video_host import get_public_video_url
        print("\n🌐 Preparing public video URL for social platforms...")
        public_video_url = get_public_video_url(video_path)
    except Exception as e:
        print(f"⚠️ Pre-hosting video URL warning: {e}")

    # Instagram Reels (Direct Resumable)
    try:
        ig_res = upload_to_instagram(video_path, combined_caption, is_story=False)
        if isinstance(ig_res, dict) and ig_res.get('status') == 'success':
            success_flags["instagram_reel"] = True
        elif isinstance(ig_res, dict) and ig_res.get('status') == 'skipped':
            print(f"⚠️ Instagram Reel skipped: {ig_res.get('reason')}")
        else:
            raise Exception(ig_res.get('error', 'Instagram Reel failed') if isinstance(ig_res, dict) else 'Failed')
    except Exception as e:
        print(f"❌ Instagram Reel upload failed: {e}")
        
    # Instagram Stories (Direct Resumable)
    try:
        ig_story_res = upload_to_instagram(video_path, combined_caption, is_story=True)
        if isinstance(ig_story_res, dict) and ig_story_res.get('status') == 'success':
            success_flags["instagram_story"] = True
        elif isinstance(ig_story_res, dict) and ig_story_res.get('status') == 'skipped':
            print(f"⚠️ Instagram Story skipped: {ig_story_res.get('reason')}")
        else:
            raise Exception(ig_story_res.get('error', 'Instagram Story failed') if isinstance(ig_story_res, dict) else 'Failed')
    except Exception as e:
        print(f"❌ Instagram Story upload failed: {e}")
        
    # Facebook Reels
    try:
        upload_to_facebook(video_path, description, title=title)
        success_flags["facebook_reel"] = True
    except Exception as e:
        print(f"❌ Facebook Reel upload failed: {e}")
        
    # Facebook Stories
    try:
        upload_to_facebook_story(video_path)
        success_flags["facebook_story"] = True
    except Exception as e:
        print(f"❌ Facebook Story upload failed: {e}")
        
    # Threads
    try:
        upload_to_threads(video_path, combined_caption, video_url=public_video_url)
        success_flags["threads"] = True
    except Exception as e:
        print(f"❌ Threads upload failed: {e}")
        
    # YouTube Shorts
    try:
        upload_to_youtube(video_path, title, description, tags=["dancing", "fitness", "model", "lifestyle", "soulful", "empowerment"])
        success_flags["youtube"] = True
    except Exception as e:
        print(f"❌ YouTube upload failed: {e}")
        
    # Record as published regardless of partial success,
    # to avoid repeating the same video. Alternatively, only record if fully successful.
    print("\n✅ Marking video as published.")

    # Check if this is a recycled video (already in published_videos.json)
    published_list = get_already_published()
    is_recycled = any(item["video_name"] == video_name for item in published_list)

    if is_recycled:
        print(f"   🔄 This is a recycled video (re-publishing)")

    mark_as_published(video_name, {
        "title": title,
        "description": description,
        "success_flags": success_flags,
        "recycled": is_recycled
    })
    
    # Move the published video to Published_Videos folder
    published_dir = "Published_Videos"
    if not os.path.exists(published_dir):
        os.makedirs(published_dir)
        
    try:
        dest_path = os.path.join(published_dir, video_name)
        shutil.move(video_path, dest_path)
        print(f"📦 Moved published video to {dest_path}")
    except Exception as e:
        print(f"❌ Failed to move published video: {e}")
    
    print("🎉 DAILY AUTOMATION COMPLETE")

if __name__ == "__main__":
    main()
