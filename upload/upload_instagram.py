import os
import requests
import time
import base64
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path, override=True)

try:
    from upload.video_host import get_public_video_url
except ImportError:
    from video_host import get_public_video_url


def upload_to_instagram(video_path, caption, is_story=False, video_url=None):
    media_type = 'STORIES' if is_story else 'REELS'
    
    print("\n" + "=" * 60)
    print(f"INSTAGRAM {media_type} UPLOAD STARTING")
    print("=" * 60)
    
    access_token = os.getenv('INSTAGRAM_ACCESS_TOKEN') or os.getenv('FACEBOOK_ACCESS_TOKEN')
    user_id = os.getenv('INSTAGRAM_ACCOUNT_ID') or os.getenv('IG_USER_ID')
    
    def mask(s): return f"{s[:10]}...{s[-4:]}" if s and len(s) > 10 else ("PLACEHOLDER" if s == "***" else "MISSING")
    print(f"[instagram] User ID Provided: {user_id}")
    print(f"[instagram] Access Token: {mask(access_token)}")

    if not access_token:
        print("[instagram] Skipping - no token")
        return {'status': 'skipped', 'reason': 'Missing credentials', 'platform': 'instagram'}
    
    if access_token.startswith('EAAM'):
        print("[instagram] EAAM token detected, resolving Instagram Business Account ID...")
        try:
            # /me returns the Page info for EAAM tokens
            me_resp = requests.get(f"https://graph.facebook.com/me?fields=id,name&access_token={access_token}", timeout=10)
            if me_resp.status_code == 200:
                page_id = me_resp.json().get('id')
                print(f"[instagram] Facebook Page ID: {page_id}")
                # Fetch connected Instagram account
                ig_resp = requests.get(f"https://graph.facebook.com/{page_id}?fields=instagram_business_account&access_token={access_token}", timeout=10)
                if ig_resp.status_code == 200:
                    ig_account = ig_resp.json().get('instagram_business_account')
                    if ig_account:
                        ig_id = ig_account.get('id')
                        if ig_id != user_id:
                            print(f"[instagram] Found IG Business Account: {ig_id} (was: {user_id})")
                            user_id = ig_id
                    else:
                        print("[instagram] No Instagram Business Account connected to this Page")
                else:
                    print(f"[instagram] IG account fetch failed: {ig_resp.text[:200]}")
            else:
                print(f"[instagram] Page fetch failed: {me_resp.text[:200]}")
        except Exception as e:
            print(f"[instagram] IG ID fetch error: {e}")
    elif access_token.startswith('IGAA'):
        try:
            me_resp = requests.get(f"https://graph.facebook.com/me?fields=id,username&access_token={access_token}", timeout=10)
            if me_resp.status_code == 200:
                detected_id = me_resp.json().get('id')
                if detected_id and detected_id != user_id:
                    print(f"[instagram] Using detected ID: {detected_id}")
                    user_id = detected_id
        except Exception as e:
            print(f"[instagram] ID verify error: {e}")

    if not user_id:
        print("[instagram] Skipping - no user ID")
        return {'status': 'skipped', 'reason': 'Missing credentials', 'platform': 'instagram'}
    
    print(f"[instagram] Credentials loaded")
    
    video_path_obj = Path(video_path)
    if not video_path_obj.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")
    
    file_size_mb = video_path_obj.stat().st_size / (1024 * 1024)
    print(f"[instagram] Video: {video_path} ({file_size_mb:.2f} MB)")
    
    caption_limited = caption[:2200] if len(caption) > 2200 else caption
    print(f"[instagram] Caption: {len(caption_limited)} chars")
    
    try:
        print(f"[instagram] Step 1: Acquiring public video URL...")
        if not video_url:
            video_url = get_public_video_url(video_path_obj)
        print(f"[instagram] Video URL: {video_url}")
        
        print(f"[instagram] Step 2: Creating {media_type} container...")
        
        api_base = "https://graph.facebook.com/v21.0"
        container_params = {
            'media_type': media_type,
            'video_url': video_url,
            'access_token': access_token
        }
        
        if not is_story:
            container_params['share_to_feed'] = 'false'
            container_params['caption'] = caption_limited
        
        container_resp = requests.post(f"{api_base}/{user_id}/media", params=container_params, timeout=60)
        if container_resp.status_code != 200:
            error_msg = container_resp.json().get('error', {}).get('message', 'Unknown')
            raise Exception(f"Container creation failed: {error_msg}")
        
        container_id = container_resp.json().get('id')
        print(f"[instagram] Container: {container_id}")
        
        print(f"[instagram] Step 3: Processing...")
        max_wait = 300
        waited = 0
        
        while waited < max_wait:
            status_resp = requests.get(f"{api_base}/{container_id}", params={
                'fields': 'status_code,status', 'access_token': access_token
            }, timeout=30)
            
            status_data = status_resp.json()
            status_code = status_data.get('status_code') or status_data.get('status', 'UNKNOWN')
            
            print(f"[instagram] Status: {status_code} (waited {waited}s)")
            
            if status_code == 'FINISHED':
                print(f"[instagram] Processing complete!")
                break
            elif status_code == 'ERROR':
                error_msg = status_data.get('error_message', 'Video processing failed')
                error_code = status_data.get('error_code', 'N/A')
                print(f"[instagram] Error: {error_msg} (code: {error_code})")
                print(f"[instagram] Full response: {status_data}")
                raise Exception(f"{error_msg}")
            
            time.sleep(10)
            waited += 10
        
        if waited >= max_wait:
            raise Exception("Video processing timed out")
        
        time.sleep(5)
        
        print(f"[instagram] Step 4: Publishing...")
        max_retries = 3
        publish_resp = None
        
        for attempt in range(max_retries):
            publish_resp = requests.post(f"{api_base}/{user_id}/media_publish", params={
                'creation_id': container_id, 'access_token': access_token
            }, timeout=60)
            
            if publish_resp.status_code == 200:
                break
            print(f"[instagram] Publish attempt {attempt+1} failed, retrying...")
            time.sleep(10)
        
        if not publish_resp or publish_resp.status_code != 200:
            error_msg = publish_resp.json().get('error', {}).get('message', 'Unknown') if publish_resp else 'No response'
            raise Exception(f"Publish failed: {error_msg}")
        
        media_id = publish_resp.json().get('id')
        print(f"[instagram] SUCCESS! Media ID: {media_id}")
        
        return {'id': media_id, 'platform': 'instagram', 'status': 'success'}
        
    except Exception as e:
        print(f"[instagram] Error: {e}")
        raise


if __name__ == '__main__':
    video_file = Path('ielts_short.mp4')
    if video_file.exists():
        try:
            result = upload_to_instagram(str(video_file), "Test caption")
            print(f"Result: {result}")
        except Exception as e:
            print(f"Failed: {e}")
    else:
        print(f"Video not found: {video_file}")
