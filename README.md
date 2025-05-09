# Media Asset Management (MAM)
Media Asset Management (MAM) solution that fully integrates both transcoding and Image/Video-On-Demand features using OpenSource technologies

---
**!!!IMPORTANT!!!**

This is an old repository for the Media Asset Management solution. This one rely solely on FastAPI servers and single separated docker images for MinIO and Redis.
There is a new repository which is an all-in-one solution which fully integrates everything in a single ```docker-compose``` for the Media Asset Management solution.
So it's highly suggested to pull this repository ```https://github.com/fpcsa/media-asset-mgmt``` instead of this one which will not be maintained anymore.

---

# Video Transcoding and VoD FastAPI Services

This repository provides two FastAPI-based microservices for handling video transcoding and video/image streaming (VoD - Video on Demand). The system integrates with **MinIO** for object storage, **FFmpeg** for video conversion to HLS format, and **Redis** for playlist caching.

## Architecture Overview

- `video_transcoding_main_server.py`: Transcodes `.mp4` videos to HLS (`.m3u8` and `.ts` segments) and uploads to MinIO.
- `vod_main_server.py`: Serves signed HLS playlists with lazy transcoding support and Redis caching.
- `redis_adapter.py`: Utility for managing Redis-based caching of playlists.

![Architecture](media_MAM.png)

## Features

- 🔁 **On-Demand Video Transcoding** (Remux or Re-encode to HLS format)
- 🎞️ **Video Streaming** using HLS (.m3u8 + signed .ts segments)
- ☁️ **MinIO Integration** for object storage
- 🔐 **Signed URL Generation** for secure segment delivery
- ⚡ **Lazy Transcoding Support** for missing HLS playlists
- 🧠 **Redis Playlist Caching** to reduce load and increase performance
- 🔐 **API Key Protection** for transcoding and cache invalidation endpoints

---

## Prerequisites

- Python 3.8+
- FFmpeg (bundled via `imageio-ffmpeg`)
- Docker (for MinIO and Redis, if needed)
- Redis (local or cloud-hosted)

## Dependencies

Install Python packages using:

```bash
pip install -r requirements.txt
```

**Required Packages:**
- fastapi
- uvicorn
- python-dotenv
- pydantic
- requests
- ffmpeg-python
- imageio-ffmpeg
- minio
- redis

---

## Environment Variables

Create a `.env` file in the root with the following:

```env
# MinIO configuration
MINIO_ENDPOINT=localhost:9000
MINIO_USR=<your_username>
MINIO_PWD=<your_pwd>
MINIO_BUCKET_VOD=vod

# Transcoding server API key and URL (used by VoD server)
TRANSCODE_API_KEY=your_secret_api_key
TRANSCODE_API_URL=http://localhost:<port>/transcode

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

```

---

## Running the Services

### Start Redis (optional if using local Redis)

```bash
docker run -d --name redis-server -p 6379:6379 redis:alpine
```

### Start MinIO

```bash
docker run -d --name minio-server \
  -p 9000:9000 \
  -p 9001:9001 \
  -v /mnt/minio-data:/data \
  -e "MINIO_ROOT_USER=<your_username>" \
  -e "MINIO_ROOT_PASSWORD=<your_password>" \
  minio/minio server /data --console-address ":9001"
```

### Run Video Transcoding Service in background

```bash
nohup uvicorn video_transcoding_main_server:app --host 0.0.0.0 --port 8001 &
```

### Run VoD Playlist Server in background

```bash
nohup uvicorn vod_main_server:app --host 0.0.0.0 --port 8002 &
```

---

## API Endpoints

### 🎥 Video Transcoding Server (`video_transcoding_main_server.py`)

#### `POST /transcode`

Transcodes a video into HLS format and uploads it to MinIO.

**Headers:**
- `x-api-key: <TRANSCODE_API_KEY>`

**Body:**
```json
{
  "asset_bucket": "myvideos",
  "asset_object": "sample.mp4",
  "reencode": false
}
```

**Response:**
```json
{
  "status": "success",
  "video": "sample"
}
```

---

### 📺 VoD Playlist Server (`vod.py`)

#### `GET /video/{video_name}/playlist.m3u8`

Returns signed `.m3u8` playlist with `.ts` segments signed for 1 hour (if already transcoded).

#### `GET /stream/{video_bucket}/{video_path}/playlist.m3u8`

Lazy-transcodes the requested video if `.m3u8` playlist is missing, then serves it with signed URLs.

#### `DELETE /cache/video/{video_name}`

Invalidates Redis cache for the given playlist.

#### `DELETE /stream/{video_stream_bucket}/{video_path}/playlist.m3u8`

Deletes the video HLS stream folder and automatically invalidates cache to avoid synchronization issues

#### `GET /asset/{bucket_name}/{img_path}/thumbnail`

Serves a signed URL to an image thumbnail stored in MinIO. It hits Redis caching to reduce MinIO access

#### `GET /stream/{bucket_name}/{img_path}/thumbnail`

Streams the actual thumbnail image using a MinIO signed URL. It hits Redis caching to reduce MinIO access

#### `DELETE /cache/img/{img_path}`

Invalidates Redis cache for the img path.

**Headers:**
- `x-api-key: <TRANSCODE_API_KEY>`

**Response:**
```json
{
  "message": "Cache cleared for 'sample'"
}
```

---

## Redis Cache Adapter

The `redis_adapter.py` utility manages playlist caching with TTL:

- `get_cached_playlist(video_name: str) -> str | None`
- `set_cached_playlist(video_name: str, m3u8_text: str)`
- `invalidate_playlist_cache(video_name: str)`
- `get_cached_thumbnail(img_key: str) -> str | None`
- `set_cached_thumbnail(img_key: str, url: str)`
- `invalidate_thumbnail_cache(img_key: str)`

---

## Example Curl Request

### Trigger Transcoding

```bash
curl -X POST http://localhost:8001/transcode \
  -H "x-api-key: your_secret_api_key" \
  -H "Content-Type: application/json" \
  -d '{"asset_bucket": "myvideos", "asset_object": "video.mp4", "reencode": false}'
```

### Fetch Signed Playlist

```bash
curl http://localhost:8002/stream/myvideos/video.mp4/playlist.m3u8
```

---

## Notes

- `.m3u8` playlists and `.ts` segments are stored in MinIO under `vod/<video_name>/`.
- The `reencode` flag controls whether FFmpeg does H.264 + AAC re-encoding or just remuxing.
- You can integrate a frontend player like `hls.js` or `video.js` for browser playback.

---

## License

This project is licensed under the MIT License.

---

## Contributing

Pull requests are welcome. Open an issue to discuss major changes before submitting.

---
