from fastapi import FastAPI, HTTPException, Header, status
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from minio import Minio
from datetime import timedelta
from dotenv import load_dotenv
import os, logging, time, requests
from pathlib import Path
from redis_adapter import get_cached_playlist, set_cached_playlist, invalidate_playlist_cache

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# MinIO Config
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT")
MINIO_USR = os.getenv("MINIO_USR")
MINIO_PWD = os.getenv("MINIO_PWD")
MINIO_BUCKET_VOD = os.getenv("MINIO_BUCKET_VOD")

# MinIO Client
client_minio = Minio(
    endpoint=MINIO_ENDPOINT.replace("http://", "").replace("https://", ""),
    access_key=MINIO_USR,
    secret_key=MINIO_PWD,
    # secure=MINIO_ENDPOINT.startswith("https")
    secure= False
)

TRANSCODE_API_KEY = os.getenv("TRANSCODE_API_KEY")
TRANSCODE_API_URL = os.getenv("TRANSCODE_API_URL")


def auto_transcode(video_bucket: str, video_name: str) -> bool:
    """
    To allow "lazy-transcoding" or "on-demand processing"
    Useful to do transcoding if a video requested is not already transcoded
    """
    try:
        payload = {
            "asset_bucket": video_bucket,
            "asset_object": f"{video_name}.mp4",
            "reencode": False
        }
        headers = {"x-api-key": TRANSCODE_API_KEY}
        r = requests.post(TRANSCODE_API_URL, json=payload, headers=headers)
        r.raise_for_status()
        return True
    except Exception as e:
        log.info(f"Auto-transcoding failed: {e}")
        return False
    
# FastAPI App
app = FastAPI()

# Allow API to be called from Web App
origins = ['null']         
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/video/{video_name}/playlist.m3u8")
def serve_signed_playlist(video_name: str):
    """
    Gets .m3u8 playlist file from a specific bucket in MinIO
    """
    # Try to return from Redis cache
    cached = get_cached_playlist(video_name)
    if cached:
        log.info(f"cache:hit")
        return PlainTextResponse(content=cached, media_type="application/vnd.apple.mpegurl")

    # Fetch .m3u8 playlist from MinIO
    playlist_key = f"{video_name}/index.m3u8"
    try:
        response = client_minio.get_object(MINIO_BUCKET_VOD, playlist_key)
        m3u8_text = response.read().decode("utf-8")
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Cannot fetch playlist: {e}")

    # Rewrite .ts segment lines with signed URLs
    signed_lines = []
    for line in m3u8_text.splitlines():
        if line.strip().endswith(".ts"):
            ts_key = f"{video_name}/{line.strip()}"
            try:
                signed_url = client_minio.presigned_get_object(
                    MINIO_BUCKET_VOD,
                    ts_key,
                    expires=timedelta(seconds=3600)  # 1 hour signed URL
                )
                signed_lines.append(signed_url)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Error signing {ts_key}: {e}")
        else:
            signed_lines.append(line)

    # Build and cache the final playlist
    final_m3u8 = "\n".join(signed_lines)
    set_cached_playlist(video_name, final_m3u8)

    return PlainTextResponse(content=final_m3u8, media_type="application/vnd.apple.mpegurl")

@app.get("/stream/{video_bucket}/{video_path:path}/playlist.m3u8")
def serve_signed_playlist(video_bucket: str, video_path: str):
    """
    Given video_bucket and video_path
    If any, gets .m3u8 playlist file from a specific bucket in MinIO
    Otherwise, fetches the video itself from the path, does lazy-transcoding, and gets .m3u8 playlist file
    """
    video_name = Path(video_path).stem
    playlist_key = f"{video_name}/index.m3u8"

    # Try cache first
    cached = get_cached_playlist(video_name)
    if cached:
        log.info(f"cache:hit for {video_name}")
        return PlainTextResponse(content=cached, media_type="application/vnd.apple.mpegurl")

    # Try to fetch the playlist
    try:
        response = client_minio.get_object(MINIO_BUCKET_VOD, playlist_key)
        m3u8_text = response.read().decode("utf-8")
    except Exception:
        log.warning(f"Playlist missing, triggering lazy transcode for {video_path}")
        try:
            if not auto_transcode(video_bucket, video_path):
                raise HTTPException(status_code=500, detail="Auto-transcoding failed")

            for _ in range(10):
                try:
                    response = client_minio.get_object(MINIO_BUCKET_VOD, playlist_key)
                    m3u8_text = response.read().decode("utf-8")
                    break
                except:
                    time.sleep(1)
            else:
                raise HTTPException(status_code=504, detail="Playlist still not available after transcoding")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Transcoding exception: {e}")

    # Sign .ts segments
    signed_lines = []
    for line in m3u8_text.splitlines():
        if line.strip().endswith(".ts"):
            ts_key = f"{video_name}/{line.strip()}"
            try:
                signed_url = client_minio.presigned_get_object(
                    MINIO_BUCKET_VOD, ts_key, expires=timedelta(seconds=3600)
                )
                signed_lines.append(signed_url)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Error signing {ts_key}: {e}")
        else:
            signed_lines.append(line)

    final_m3u8 = "\n".join(signed_lines)
    set_cached_playlist(video_name, final_m3u8)
    return PlainTextResponse(content=final_m3u8, media_type="application/vnd.apple.mpegurl")

@app.delete("/cache/{video_name}")
def delete_cache(video_name: str, x_api_key: str = Header(None)):
    if x_api_key != TRANSCODE_API_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized")

    invalidate_playlist_cache(video_name)
    return {"message": f"Cache cleared for '{video_name}'"}
