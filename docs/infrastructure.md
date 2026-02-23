# Infrastructure

## Services

The system requires several services running locally or remotely.

### LiveKit Server

WebRTC media server for real-time audio/video.

```yaml
# compose.yml
livekit:
  image: livekit/livekit-server:v1.9
  container_name: eta-livekit
  ports:
    - "7880:7880"
    - "7881:7881"
```

### STT Service (Whisper)

Speech-to-text using Faster Whisper.

```yaml
stt:
  image: fedirz/faster-whisper-server:latest-cuda
  container_name: eta-stt
  ports:
    - "4100:8000"
  environment:
    WHISPER__MODEL: Systran/faster-whisper-small
```

### TTS Service (Piper)

Text-to-speech using Wyoming/Piper.

```yaml
tts:
  image: lscr.io/linuxserver/piper:latest
  container_name: eta-tts
  ports:
    - "10200:10200"
```

### Redis

Required by LiveKit for room state.

```yaml
redis:
  image: redis/redis-stack:latest
  container_name: eta-redis
  ports:
    - "6380:6379"
```

## Starting Infrastructure

```bash
make infra        # Start all services
make infra-down   # Stop all services
```

## Configuration

All service URLs are configured via environment variables in `.env`:

```env
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret

STT_BASE_URL=http://localhost:4100
TTS_HOST=localhost
TTS_PORT=10200

GOOGLE_API_KEY=your-api-key
```

## GPU Support

For GPU-accelerated STT:

```yaml
stt:
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
```
