from fastapi import FastAPI, Request, status, HTTPException, Depends, Header, WebSocket, WebSocketDisconnect, UploadFile, Form
from fastapi.responses import StreamingResponse, Response, PlainTextResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import uuid
import asyncio
import os
import time
import random
import warnings
import logging
from dotenv import load_dotenv
from slowapi import Limiter
from collections import deque
from datetime import datetime, timedelta
from typing import List, Dict, Any, Callable, Optional
from pydantic import BaseModel

from batch_and_files_api import router as batch_files_router

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded


# Preloaded audio in three sizes: small, medium, large
# Structure: _PRELOADED_AUDIO[format][size] = bytes
_PRELOADED_AUDIO: Dict[str, Dict[str, bytes]] = {}

# Size definitions in bytes
AUDIO_SIZES = {
    "small": 20_000,   # ~20 KB - for short inputs (< 100 chars)
    "medium": 100_000, # ~100 KB - for medium inputs (100-1000 chars)
    "large": 400_000,  # ~400 KB - for large inputs (> 1000 chars)
}


def generate_minimal_audio(format: str = "mp3") -> bytes:
    """Generate minimal valid audio data for different formats."""
    if format == "mp3":
        # Minimal valid MP3 frame (silent audio, ~1 second)
        # This is a minimal MP3 header + frame
        mp3_header = bytes([
            0xFF, 0xFB, 0x90, 0x00,  # MP3 sync word + header
        ])
        # Add some minimal frame data using a non-zero pattern
        frame_data = bytes([0x55] * 100)  # 0x55 pattern instead of all zeros
        return mp3_header + frame_data
    elif format == "opus":
        # Minimal Opus header (OggS)
        opus_header = b"OggS\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00"
        # Use a simple non-zero pattern for payload
        return opus_header + bytes([0x33] * 50)
    elif format == "aac":
        # Minimal AAC header
        aac_header = bytes([0xFF, 0xF1])  # ADTS sync word
        # Non-zero pattern payload
        return aac_header + bytes([0x77] * 50)
    elif format == "flac":
        # Minimal FLAC header (fLaC)
        flac_header = b"fLaC"
        # Non-zero pattern payload
        return flac_header + bytes([0x99] * 50)
    elif format == "pcm":
        # Minimal PCM WAV header
        # WAV header structure
        wav_header = (
            b"RIFF" +  # ChunkID
            (36).to_bytes(4, byteorder="little") +  # ChunkSize
            b"WAVE" +  # Format
            b"fmt " +  # Subchunk1ID
            (16).to_bytes(4, byteorder="little") +  # Subchunk1Size
            (1).to_bytes(2, byteorder="little") +  # AudioFormat (PCM)
            (1).to_bytes(2, byteorder="little") +  # NumChannels
            (16000).to_bytes(4, byteorder="little") +  # SampleRate
            (32000).to_bytes(4, byteorder="little") +  # ByteRate
            (2).to_bytes(2, byteorder="little") +  # BlockAlign
            (16).to_bytes(2, byteorder="little") +  # BitsPerSample
            b"data" +  # Subchunk2ID
            (0).to_bytes(4, byteorder="little")  # Subchunk2Size
        )
        return wav_header
    else:
        # Default to MP3
        return generate_minimal_audio("mp3")


def generate_audio_by_size(format: str, target_size: int, speed: float = 1.0) -> bytes:
    """
    Generate audio data of approximately the target size.
    
    Args:
        format: Audio format (mp3, opus, aac, flac, pcm)
        target_size: Target size in bytes
        speed: Speech speed (affects duration, so faster = smaller for same text)
    
    Returns:
        bytes: Audio data approximately matching target_size
    """
    # Adjust target size based on speed (faster speed = shorter duration = smaller file)
    # Speed affects duration linearly, so we divide by speed
    adjusted_size = int(target_size / speed)
    
    # Get the minimal header/base for this format
    base = generate_minimal_audio(format)
    base_size = len(base)
    
    # If target is smaller than base, return base (minimum valid audio)
    if adjusted_size <= base_size:
        return base
    
    # Calculate how much payload we need
    payload_size = adjusted_size - base_size
    
    # Generate payload data with a pattern that looks like audio
    # Use a repeating pattern that varies to avoid compression artifacts
    pattern = [0x55, 0xAA, 0x33, 0xCC, 0x66, 0x99, 0x11, 0xEE]
    payload = bytes([pattern[i % len(pattern)] for i in range(payload_size)])
    
    return base + payload


def _load_preloaded_audio() -> None:
    """
    Preload three sizes (small, medium, large) of audio for each format.
    This is done once at startup to avoid per-request generation overhead.
    """
    global _PRELOADED_AUDIO
    
    # Formats we support for the speech endpoint
    formats = ["mp3", "opus", "aac", "flac", "pcm"]
    
    for fmt in formats:
        _PRELOADED_AUDIO[fmt] = {}
        for size_name, target_size in AUDIO_SIZES.items():
            # Generate audio of the target size
            audio_data = generate_audio_by_size(fmt, target_size, speed=1.0)
            _PRELOADED_AUDIO[fmt][size_name] = audio_data


# Initialize preloaded audio at import time
_load_preloaded_audio()


def get_histogram_sleep_time() -> float:
    """
    Returns a sleep time based on a histogram distribution:
    - Most requests (~70%): ~10 seconds (8-12s range)
    - Some requests (~25%): ~60 seconds (55-65s range)
    - Very few (~5%): 60+ seconds (60-300s range)
    
    This simulates realistic degraded provider behavior where most requests
    are slow but not terrible, some are very slow, and a few are extremely slow.
    """
    rand = random.random()
    
    if rand < 0.70:  # 70% of requests: ~10 seconds
        # Normal distribution around 10 seconds, std dev of 2
        sleep_time = max(1.0, random.gauss(10, 2))
        return sleep_time
    elif rand < 0.95:  # 25% of requests: ~60 seconds
        # Normal distribution around 60 seconds, std dev of 5
        sleep_time = max(30.0, random.gauss(60, 5))
        return sleep_time
    else:  # 5% of requests: 60+ seconds (up to 5 minutes)
        # Uniform distribution between 60 and 300 seconds
        sleep_time = random.uniform(60, 300)
        return sleep_time


def get_request_url(request: Request):
    return str(request.url)

limiter = Limiter(key_func=get_request_url)
load_dotenv()

# Suppress python-multipart's "Skipping data after last boundary" warning
# This warning appears even in patched versions (0.0.18+) where the DoS vulnerability is fixed.
# The warning is harmless but clutters logs. We suppress it via logging configuration.
# Note: Upgraded to python-multipart 0.0.20 which has better handling, but warning may still appear.
logging.getLogger("multipart").setLevel(logging.ERROR)  # Only show errors, not warnings

app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the batch and files router with /v1 prefix
app.include_router(batch_files_router, prefix="/v1")


def data_generator():
    response_id = uuid.uuid4().hex
    sentence = "Hello this is a test response from a fixed OpenAI endpoint."
    words = sentence.split(" ")
    for word in words:
        word = word + " "
        chunk = {
                    "id": f"chatcmpl-{response_id}",
                    "object": "chat.completion.chunk",
                    "created": 1677652288,
                    "model": "gpt-3.5-turbo-0125",
                    "choices": [{"index": 0, "delta": {"content": word}}],
                }
        try:
            yield f"data: {json.dumps(chunk.dict())}\n\n"
        except:
            yield f"data: {json.dumps(chunk)}\n\n"


# for completion
@app.post("/chat/completions")
@app.post("/v1/chat/completions")
@app.post("/openai/deployments/{model:path}/chat/completions")  # azure compatible endpoint
async def completion(request: Request):
    _time_to_sleep = os.getenv("TIME_TO_SLEEP", None)
    if _time_to_sleep is not None:
        print("sleeping for " + _time_to_sleep)
        await asyncio.sleep(float(_time_to_sleep))

    data = await request.json()

    if data.get("model") == "429":
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests")

    if data.get("model") == "random_sleep":
        # sleep for a random time between 1 and 10 seconds
        sleep_time = random.randint(1, 10)
        print("sleeping for " + str(sleep_time) + " seconds")
        await asyncio.sleep(sleep_time)
    
    # Degraded provider simulation: sleep with histogram distribution to simulate hanging requests
    # This causes event loop blocking, file descriptor accumulation, and tests LiteLLM's
    # behavior under degraded provider conditions
    if data.get("model") in ["degraded", "slow_provider", "blocked"]:
        # Histogram distribution: most ~10s, some ~60s, few 60s+
        sleep_time = get_histogram_sleep_time()
        print(f"[DEGRADED MODE] Sleeping for {sleep_time:.1f} seconds ({sleep_time/60:.1f} minutes) - histogram distribution")
        await asyncio.sleep(sleep_time)
    if data.get("stream") == True:
        return StreamingResponse(
            content=data_generator(),
            media_type="text/event-stream",
        )
    else:
        _model = data.get("model")
        if _model == "gpt-5":
            _model = "gpt-12"
        else:
            _model = "gpt-3.5-turbo-0301"
        response_id = uuid.uuid4().hex
        response = {
            "id": f"chatcmpl-{response_id}",
            "object": "chat.completion",
            "created": 1677652288,
            "model": _model,
            "system_fingerprint": "fp_44709d6fcb",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "\n\nHello there, how may I assist you today?",
                    },
                    "logprobs": None,
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 9, "completion_tokens": 12, "total_tokens": 21},
        }
        return response


# for completion
@app.post("/completions")
@app.post("/v1/completions")
async def text_completion(request: Request):
    data = await request.json()

    if data.get("stream") == True:
        return StreamingResponse(
            content=data_generator(),
            media_type="text/event-stream",
        )
    else:
        response_id = uuid.uuid4().hex
        response = {
            "id": "cmpl-9B2ycsf0odECdLmrVzm2y8Q12csjW",
            "choices": [
                {
                "finish_reason": "length",
                "index": 0,
                "logprobs": None,
                "text": "\n\nA test request, how intriguing\nAn invitation for knowledge bringing\nWith words"
                }
            ],
            "created": 1712420078,
            "model": "unknown",
            "object": "text_completion",
            "system_fingerprint": None,
            "usage": {
                "completion_tokens": 16,
                "prompt_tokens": 10,
                "total_tokens": 26
            }
        }

        return response




# for completion
@app.post("/invocations")
@app.post("/invocations/")
async def invocation(request: Request):
    _time_to_sleep = os.getenv("TIME_TO_SLEEP", None)
    if _time_to_sleep is not None:
        print("sleeping for " + _time_to_sleep)
        await asyncio.sleep(float(_time_to_sleep))
    data = await request.json()
    if data.get("model") == "429":
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests")
    else:
        response_id = uuid.uuid4().hex
        return {
            "generated_text": "This is a mock response from SageMaker.",
            "id": "cmpl-mockid",
            "object": "text_completion",
            "created": 1629800000,
            "model": "sagemaker/jumpstart-dft-hf-textgeneration1-mp-20240815-185614",
            "choices": [
                {
                    "text": "This is a mock response from SageMaker.",
                    "index": 0,
                    "logprobs": None,
                    "finish_reason": "length",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 8, "total_tokens": 9},
        }

@app.post("/embeddings")
@app.post("/v1/embeddings")
@app.post("/openai/deployments/{model:path}/embeddings")  # azure compatible endpoint
async def embeddings(request: Request):
    _small_embedding = [
        -0.006929283495992422,
        -0.005336422007530928,
        -4.547132266452536e-05,
        -0.024047505110502243,
    ]

    big_embedding = _small_embedding * 100
    return {
        "object": "list",
        "data": [
            {
            "object": "embedding",
            "index": 0,
            "embedding": big_embedding
            }
        ],
        "model": "text-embedding-3-small",
        "usage": {
            "prompt_tokens": 5,
            "total_tokens": 5
        }
    }


@app.post("/audio/speech")
@app.post("/v1/audio/speech")
async def audio_speech(request: Request):
    """OpenAI Audio Speech endpoint - Text to Speech"""
    _time_to_sleep = os.getenv("TIME_TO_SLEEP", None)
    if _time_to_sleep is not None:
        print("sleeping for " + _time_to_sleep)
        await asyncio.sleep(float(_time_to_sleep))

    data = await request.json()
    
    # Extract parameters
    model = data.get("model", "tts-1")
    input_text = data.get("input", "")
    voice = data.get("voice", "alloy")
    response_format = data.get("response_format", "mp3")
    speed = data.get("speed", 1.0)
    
    # Validate required parameters
    if not input_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required parameter: input"
        )
    
    # Validate voice
    valid_voices = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
    if voice not in valid_voices:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid voice. Must be one of: {', '.join(valid_voices)}"
        )
    
    # Validate response_format
    valid_formats = ["mp3", "opus", "aac", "flac", "pcm"]
    if response_format not in valid_formats:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid response_format. Must be one of: {', '.join(valid_formats)}"
        )
    
    # Validate speed
    if not (0.25 <= speed <= 4.0):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="speed must be between 0.25 and 4.0"
        )
    
    # Select audio size based on input text length
    # This allows testing different response sizes without dynamic generation overhead
    text_length = len(input_text)
    
    if text_length < 100:
        size_key = "small"
    elif text_length < 1000:
        size_key = "medium"
    else:
        size_key = "large"
    
    # Get preloaded audio data for the selected size
    audio_data = _PRELOADED_AUDIO.get(response_format, {}).get(size_key)
    if audio_data is None:
        # Fallback to on-demand minimal generation if something is missing
        audio_data = generate_minimal_audio(response_format)
    
    # Adjust for speed parameter (faster speed = smaller file)
    # For simplicity, we'll just use the preloaded data as-is
    # In a real implementation, speed would affect the audio duration
    # Optional: Log the size for testing/debugging (can be enabled via env var)
    if os.getenv("LOG_AUDIO_SIZES", "").lower() == "true":
        print(f"[Audio Speech] Input length: {text_length} chars, Format: {response_format}, "
              f"Size: {size_key}, Actual size: {len(audio_data)} bytes, Speed: {speed}")
    
    # Set appropriate content type
    content_types = {
        "mp3": "audio/mpeg",
        "opus": "audio/ogg",
        "aac": "audio/aac",
        "flac": "audio/flac",
        "pcm": "audio/wav"
    }
    content_type = content_types.get(response_format, "audio/mpeg")
    
    # Return binary audio response with preloaded size based on input text length
    return Response(
        content=audio_data,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="speech.{response_format}"'
        },
    )


# Pre-computed responses for maximum speed
_TRANSCRIPTION_TEXT = "This is a mock transcription of the audio file. The audio has been processed and transcribed to text."
_TRANSCRIPTION_JSON = {"text": _TRANSCRIPTION_TEXT}
_TRANSCRIPTION_VERBOSE_JSON = {
    "text": _TRANSCRIPTION_TEXT,
    "language": "en",
    "duration": 5.0,
    "segments": [{"id": 0, "start": 0.0, "end": 5.0, "text": _TRANSCRIPTION_TEXT}]
}
_TRANSCRIPTION_SRT = f"1\n00:00:00,000 --> 00:00:05,000\n{_TRANSCRIPTION_TEXT}\n\n"
_TRANSCRIPTION_VTT = f"WEBVTT\n\n00:00:00.000 --> 00:00:05.000\n{_TRANSCRIPTION_TEXT}\n"

@app.post("/audio/transcriptions")
@app.post("/v1/audio/transcriptions")
async def audio_transcriptions(
    file: UploadFile,
    model: str = Form(...),
    language: Optional[str] = Form(None),
    prompt: Optional[str] = Form(None),
    temperature: Optional[float] = Form(0.0),
    response_format: Optional[str] = Form("json")
):
    """OpenAI Audio Transcriptions endpoint - Speech to Text"""
    _time_to_sleep = os.getenv("TIME_TO_SLEEP", None)
    if _time_to_sleep is not None:
        print("sleeping for " + _time_to_sleep)
        await asyncio.sleep(float(_time_to_sleep))

    # Minimal validation - only check critical errors
    if model != "whisper-1":
        raise HTTPException(status_code=400, detail="Invalid model. Must be one of: whisper-1")
    
    # Fast path: return pre-computed responses based on format
    # Use simple dict returns (FastAPI auto-encodes to JSON) for maximum speed
    if response_format == "text":
        return PlainTextResponse(content=_TRANSCRIPTION_TEXT)
    elif response_format == "srt":
        return PlainTextResponse(content=_TRANSCRIPTION_SRT, media_type="text/plain")
    elif response_format == "vtt":
        return PlainTextResponse(content=_TRANSCRIPTION_VTT, media_type="text/vtt")
    elif response_format == "verbose_json":
        # Only modify language if different from default
        if language and language != "en":
            return {"text": _TRANSCRIPTION_TEXT, "language": language, "duration": 5.0, "segments": _TRANSCRIPTION_VERBOSE_JSON["segments"]}
        return _TRANSCRIPTION_VERBOSE_JSON
    else:  # json or default
        return _TRANSCRIPTION_JSON




@app.post("/triton/embeddings")
async def embeddings(request: Request):
    try:
        input_data = await request.json()
        assert "inputs" in input_data

        inputs = input_data["inputs"]
        element_one = inputs[0]

        assert "name" in element_one, "Missing name in inputs"
        assert "shape" in element_one, "Missing shape in inputs"
        assert "datatype" in element_one, "Missing datatype in inputs"
        assert "data" in element_one, "Missing data in inputs"


    except (ValueError, KeyError) as e:
        return HTTPException(status_code=400, detail=str(e))

    output_data = {
        "model_name": "triton-embeddings",
        "model_version": "1",
        "parameters": {
            "sequence_id": 0,
            "sequence_start": False,
            "sequence_end": False
        },
        "outputs": [
            {
                "name": "embedding_output",
                "datatype": "FP32",
                "shape": [2, 2],
                "data": [0.1, 0.2]  # Replace with actual output data
            }
        ]
    }

    return output_data


@app.post("/openai/fine_tuning/jobs")  # azure compatible endpoint
async def fine_tuning(request: Request):
    _time_to_sleep = os.getenv("TIME_TO_SLEEP", None)

    print("inside fine tuning /jobs endpoint")
    if _time_to_sleep is not None:
        print("sleeping for " + _time_to_sleep)
        await asyncio.sleep(float(_time_to_sleep))

    data = await request.json()

    if data.get("model") == "429":
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests")
    
    print("got request=" + json.dumps(data))

    return {
        "object": "fine_tuning.job",
        "id": "ftjob-abc123",
        "model": "davinci-002",
        "created_at": 1692661014,
        "finished_at": 1692661190,
        "fine_tuned_model": "ft:davinci-002:my-org:custom_suffix:7q8mpxmy",
        "organization_id": "org-123",
        "result_files": [
            "file-abc123"
        ],
        "status": "succeeded",
        "validation_file": None,
        "training_file": "file-abc123",
        "hyperparameters": {
            "n_epochs": 4,
            "batch_size": 1,
            "learning_rate_multiplier": 1.0
        },
        "trained_tokens": 5768,
        "integrations": [],
        "seed": 0,
        "estimated_finish": 0
    }


@app.get("/openai/fine_tuning/jobs")  # azure compatible endpoint
async def list_fine_tuning(request: Request):
    _time_to_sleep = os.getenv("TIME_TO_SLEEP", None)

    return {
        "object": "list",
        "data": [
            {
            "object": "fine_tuning.job.event",
            "id": "ft-event-TjX0lMfOniCZX64t9PUQT5hn",
            "created_at": 1689813489,
            "level": "warn",
            "message": "Fine tuning process stopping due to job cancellation",
            "data": None,
            "type": "message"
            },
        ], "has_more": True
    }



@app.post("/openai/fine_tuning/jobs/{fine_tuning_job_id:path}/cancel")  # azure compatible endpoint
async def cancel_fine_tuning(request: Request):
    _time_to_sleep = os.getenv("TIME_TO_SLEEP", None)

    return {
        "object": "fine_tuning.job",
        "id": "ftjob-abc123",
        "model": "gpt-4o-mini-2024-07-18",
        "created_at": 1721764800,
        "fine_tuned_model": None,
        "organization_id": "org-123",
        "result_files": [],
        "hyperparameters": {
            "n_epochs":  "auto"
        },
        "status": "cancelled",
        "validation_file": "file-abc123",
        "training_file": "file-abc123"
    }





@app.post("/openai/files")  # azure compatible endpoint
async def openai_files(request: Request):
    _time_to_sleep = os.getenv("TIME_TO_SLEEP", None)

    print("inside fine tuning /jobs endpoint")
    if _time_to_sleep is not None:
        print("sleeping for " + _time_to_sleep)
        await asyncio.sleep(float(_time_to_sleep))


    return {
        "id": "file-abc123",
        "object": "file",
        "bytes": 120000,
        "created_at": 1677610602,
        "filename": "mydata.jsonl",
        "purpose": "fine-tune",
    }


### FAKE BEDROCK ENDPOINT ### 

@app.post("/model/{modelId}/converse")
async def fake_bedrock_endpoint(request: Request):
    return {"metrics":{"latencyMs":393},"output":{"message":{"content":[{"text":"Good morning to you too! I am not Claude, however. Claude is a large language model trained by Google, while I am Gemini, a multi-modal AI model, developed by Google as well. Is there anything I can help you with today?"}],"role":"assistant"}},"stopReason":"end_turn","usage":{"inputTokens":37,"outputTokens":8,"totalTokens":45}}

### FAKE VERTEX ENDPOINT ### 


@app.post("/generateContent")
@app.post("/v1/projects/adroit-crow-413218/locations/us-central1/publishers/google/models/gemini-1.0-pro-vision-001:generateContent")
@app.post("/v1/projects/pathrise-convert-1606954137718/locations/us-central1/publishers/google/models/gemini-1.0-pro-vision-001:generateContent")
@app.post("/v1beta/models/gemini-1.5-flash:generateContent")
async def generate_content(request: Request, authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid or missing Authorization header")

    data = await request.json()
    
    # You can process the input data here if needed
    # For now, we'll just return the hardcoded response

    response = {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [
                        {
                            "text": "Good morning to you too! I am not Claude, however. Claude is a large language model trained by Google, while I am Gemini, a multi-modal AI model, developed by Google as well. Is there anything I can help you with today?"
                        }
                    ]
                },
                "finishReason": "STOP",
                "safetyRatings": [
                    {
                        "category": "HARM_CATEGORY_HATE_SPEECH",
                        "probability": "NEGLIGIBLE",
                        "probabilityScore": 0.037353516,
                        "severity": "HARM_SEVERITY_NEGLIGIBLE",
                        "severityScore": 0.03515625
                    },
                    {
                        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                        "probability": "NEGLIGIBLE",
                        "probabilityScore": 0.017944336,
                        "severity": "HARM_SEVERITY_NEGLIGIBLE",
                        "severityScore": 0.020019531
                    },
                    {
                        "category": "HARM_CATEGORY_HARASSMENT",
                        "probability": "NEGLIGIBLE",
                        "probabilityScore": 0.06738281,
                        "severity": "HARM_SEVERITY_NEGLIGIBLE",
                        "severityScore": 0.03173828
                    },
                    {
                        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        "probability": "NEGLIGIBLE",
                        "probabilityScore": 0.11279297,
                        "severity": "HARM_SEVERITY_NEGLIGIBLE",
                        "severityScore": 0.057373047
                    }
                ],
                "avgLogprobs": -0.30250951355578853
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 5,
            "candidatesTokenCount": 51,
            "totalTokenCount": 56
        }
    }

    return response


import random

request_counter = 0

@app.post("/generateContent")
@app.post("/v1/projects/bad-adroit-crow-413218/locations/us-central1/publishers/google/models/gemini-1.0-pro-vision-001:generateContent")
@limiter.limit("10000/minute")
async def generate_content_bad(request: Request, authorization: str = Header(None)):
    global request_counter
    request_counter += 1

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid or missing Authorization header")

    # Raise an error for every 200th request
    if request_counter % 200 == 0:
        raise HTTPException(status_code=500, detail="Internal Server Error: Simulated error for every 200th request")

    # Introduce a 0.5% chance of error for other requests
    if random.random() < 0.005:
        raise HTTPException(status_code=500, detail="Internal Server Error: Random error (0.5% chance)")

    data = await request.json()
    
    # You can process the input data here if needed
    # For now, we'll just return the hardcoded response

    response = {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [
                        {
                            "text": "Good morning to you too! I am not Claude, however. Claude is a large language model trained by Google, while I am Gemini, a multi-modal AI model, developed by Google as well. Is there anything I can help you with today?"
                        }
                    ]
                },
                "finishReason": "STOP",
                "safetyRatings": [
                    {
                        "category": "HARM_CATEGORY_HATE_SPEECH",
                        "probability": "NEGLIGIBLE",
                        "probabilityScore": 0.037353516,
                        "severity": "HARM_SEVERITY_NEGLIGIBLE",
                        "severityScore": 0.03515625
                    },
                    {
                        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                        "probability": "NEGLIGIBLE",
                        "probabilityScore": 0.017944336,
                        "severity": "HARM_SEVERITY_NEGLIGIBLE",
                        "severityScore": 0.020019531
                    },
                    {
                        "category": "HARM_CATEGORY_HARASSMENT",
                        "probability": "NEGLIGIBLE",
                        "probabilityScore": 0.06738281,
                        "severity": "HARM_SEVERITY_NEGLIGIBLE",
                        "severityScore": 0.03173828
                    },
                    {
                        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        "probability": "NEGLIGIBLE",
                        "probabilityScore": 0.11279297,
                        "severity": "HARM_SEVERITY_NEGLIGIBLE",
                        "severityScore": 0.057373047
                    }
                ],
                "avgLogprobs": -0.30250951355578853
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 5,
            "candidatesTokenCount": 51,
            "totalTokenCount": 56
        }
    }

    return response



@app.post("/predict")
@app.post("/v1/projects/adroit-crow-413218/locations/us-central1/publishers/google/models/textembedding-gecko@001:predict")
@app.post("/v1/projects/pathrise-convert-1606954137718/locations/us-central1/publishers/google/models/textembedding-gecko@001:predict")
async def predict(request: Request, authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid or missing Authorization header")

    data = await request.json()
    
    # Process the input data
    instances = data.get('instances', [])
    num_instances = len(instances)
    
    # Generate fake embeddings
    predictions = []
    for _ in range(num_instances):
        embedding = [random.uniform(-0.15, 0.15) for _ in range(768)]  # 768-dimensional embedding
        predictions.append({
            "embeddings": {
                "values": embedding,
                "statistics": {
                    "truncated": False,
                    "token_count": random.randint(4, 10)
                }
            }
        })

    # Calculate billable character count
    billable_character_count = sum(len(instance.get('content', '')) for instance in instances)

    response = {
        "predictions": predictions,
        "metadata": {
            "billableCharacterCount": billable_character_count
        }
    }

    return response


# Add catch-all routes for Vertex AI endpoints
# These must come AFTER the specific routes but handle any project/location/model combination

@app.post("/v1/projects/{project}/locations/{location}/publishers/google/models/{model}:generateContent")
async def vertex_generate_content_catchall(request: Request, project: str, location: str, model: str, authorization: str = Header(None)):
    """Catch-all endpoint for Vertex AI generateContent - accepts any project/location/model"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid or missing Authorization header")

    data = await request.json()
    
    # Return the same response format regardless of model name
    return {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [
                        {
                            "text": "Hello! This is a mock response from Vertex AI. Model: " + model
                        }
                    ]
                },
                "finishReason": "STOP",
                "safetyRatings": [
                    {
                        "category": "HARM_CATEGORY_HATE_SPEECH",
                        "probability": "NEGLIGIBLE",
                        "probabilityScore": 0.037353516,
                        "severity": "HARM_SEVERITY_NEGLIGIBLE",
                        "severityScore": 0.03515625
                    },
                    {
                        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                        "probability": "NEGLIGIBLE",
                        "probabilityScore": 0.017944336,
                        "severity": "HARM_SEVERITY_NEGLIGIBLE",
                        "severityScore": 0.020019531
                    },
                    {
                        "category": "HARM_CATEGORY_HARASSMENT",
                        "probability": "NEGLIGIBLE",
                        "probabilityScore": 0.06738281,
                        "severity": "HARM_SEVERITY_NEGLIGIBLE",
                        "severityScore": 0.03173828
                    },
                    {
                        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        "probability": "NEGLIGIBLE",
                        "probabilityScore": 0.11279297,
                        "severity": "HARM_SEVERITY_NEGLIGIBLE",
                        "severityScore": 0.057373047
                    }
                ],
                "avgLogprobs": -0.30250951355578853
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 5,
            "candidatesTokenCount": 51,
            "totalTokenCount": 56
        }
    }


@app.post("/v1/projects/{project}/locations/{location}/publishers/google/models/{model}:predict")
async def vertex_predict_catchall(request: Request, project: str, location: str, model: str, authorization: str = Header(None)):
    """Catch-all endpoint for Vertex AI predict (embeddings) - accepts any project/location/model"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid or missing Authorization header")

    data = await request.json()
    
    instances = data.get('instances', [])
    num_instances = len(instances)
    
    predictions = []
    for _ in range(num_instances):
        embedding = [random.uniform(-0.15, 0.15) for _ in range(768)]
        predictions.append({
            "embeddings": {
                "values": embedding,
                "statistics": {
                    "truncated": False,
                    "token_count": random.randint(4, 10)
                }
            }
        })

    billable_character_count = sum(len(instance.get('content', '')) for instance in instances)

    return {
        "predictions": predictions,
        "metadata": {
            "billableCharacterCount": billable_character_count
        }
    }


@app.post("/runs")
@app.post("/runs/batch")
async def runs(request: Request):
    start_time = time.perf_counter()
    
    # Simulate some minimal processing
    data = await request.json()
    
    # Create a simple response
    response = {
        "id": str(uuid.uuid4()),
        "status": "completed",
        "created_at": int(time.time()),
        "request": data
    }
    
    # Ensure the response takes at least 0.05 ms
    elapsed_time = (time.perf_counter() - start_time) * 1000  # Convert to milliseconds
    if elapsed_time < 0.05:
        time.sleep((0.05 - elapsed_time) / 1000)  # Convert back to seconds for sleep
    
    return response
    

@app.post("/traces")
async def traces(request: Request):
    try:
        start_time = time.perf_counter()
        
        # Attempt to parse the request body
        try:
            data = await request.json()
        except json.JSONDecodeError:
            # If JSON parsing fails, try to read the raw body
            body = await request.body()
            return HTTPException(status_code=400, detail=f"Invalid JSON: {body.decode('utf-8', errors='ignore')}")
        except UnicodeDecodeError:
            # If decoding fails, return an error about invalid encoding
            return HTTPException(status_code=400, detail="Request body is not valid UTF-8 encoded")
        
        # Rest of the function remains the same
        response = {
            "id": str(uuid.uuid4()),
            "status": "completed",
            "created_at": int(time.time()),
            "trace_data": {
                "events": [
                    {
                        "timestamp": int(time.time()),
                        "type": "start",
                        "details": "Trace started"
                    },
                    {
                        "timestamp": int(time.time()) + 1,
                        "type": "end",
                        "details": "Trace completed"
                    }
                ],
            }
        }
        
        # Ensure the response takes at least 0.05 ms
        elapsed_time = (time.perf_counter() - start_time) * 1000  # Convert to milliseconds
        if elapsed_time < 0.05:
            time.sleep((0.05 - elapsed_time) / 1000)  # Convert back to seconds for sleep
        
        return response
    except Exception as e:
        import traceback
        traceback.print_exc()
        return HTTPException(status_code=500, detail=str(e))

import gzip
import io

@app.post("/api/v2/logs")
async def logs(request: Request):
    await asyncio.sleep(60)  # Wait for 1 second
    return {"status": "done"}
    start_time = time.perf_counter()
    
    # Check if the content is gzipped
    content_encoding = request.headers.get("Content-Encoding", "").lower()
    
    # Read the raw body
    body = await request.body()
    
    # Decompress if gzipped
    if content_encoding == "gzip":
        try:
            body = gzip.decompress(body)
        except gzip.BadGzipFile:
            return HTTPException(status_code=400, detail="Invalid gzip data")
    
    # Attempt to parse the request body
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return HTTPException(status_code=400, detail=f"Invalid JSON: {body.decode('utf-8', errors='ignore')}")
    except UnicodeDecodeError:
        return HTTPException(status_code=400, detail="Request body is not valid UTF-8 encoded")
    
    # Create a log response
    response = {
        "id": str(uuid.uuid4()),
        "timestamp": int(time.time()),
        "level": "info",
        "message": "Log entry received",
        "data": data
    }
    
    # Ensure the response takes at least 0.05 ms
    elapsed_time = (time.perf_counter() - start_time) * 1000  # Convert to milliseconds
    if elapsed_time < 0.05:
        time.sleep((0.05 - elapsed_time) / 1000)  # Convert back to seconds for sleep
    
    return Response(
        content=json.dumps(response),
        status_code=202,
    )
slack_requests = deque(maxlen=10)
slack_requests = deque(maxlen=10)

class SlackRequest(BaseModel):
    timestamp: datetime
    data: Dict[str, Any]

@app.post("/slack")
async def slack_endpoint(request: Request):
    current_time = datetime.now()
    request_data = await request.json()

    # Add the current request to the deque
    slack_requests.append(SlackRequest(timestamp=current_time, data=request_data))

    # Remove requests older than 10 minutes
    slack_requests_list = list(slack_requests)
    slack_requests_list = [req for req in slack_requests_list if current_time - req.timestamp <= timedelta(minutes=10)]
    slack_requests.clear()
    slack_requests.extend(slack_requests_list)

    return {"message": "Request received and stored"}

@app.get("/slack/history", response_model=List[SlackRequest])
async def get_slack_history():
    return list(slack_requests)





def data_generator_anthropic():
    response_id = uuid.uuid4().hex
    sentence = "Hello this is a test response from a fixed OpenAI endpoint."
    words = sentence.split(" ")
    for word in words:
        word = word + " "
        chunk = {
                    "id": f"chatcmpl-{response_id}",
                    "object": "chat.completion.chunk",
                    "created": 1677652288,
                    "model": "gpt-3.5-turbo-0125",
                    "choices": [{"index": 0, "delta": {"content": word}}],
                }
        try:
            yield f"data: {json.dumps(chunk.dict())}\n\n"
        except:
            yield f"data: {json.dumps(chunk)}\n\n"



# for completion
@app.post("/v1/messages")
async def completion_anthropic(request: Request):
    data = await request.json()

    if data.get("stream") == True:
        return StreamingResponse(
            content=data_generator_anthropic(),
            media_type="text/event-stream",
        )
    else:
        response = {
            "id": "msg_01G7MsdWPT2JZMUuc1UXRavn",
            "type": "message",
            "role": "assistant",
            "content": [
                {
                "type": "text",
                "text": "I'm sorry, but the string of characters \"123450000s0 p kk\" doesn't appear to have any clear meaning or context. It seems to be a random combination of numbers and letters. If you could provide more information or clarify what you're trying to communicate, I'll do my best to assist you."
                }
            ],
            "model": "claude-3-opus-20240229",
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {
                "input_tokens": 17,
                "output_tokens": 71
            }
        }

        return response

@app.post("/load_test/api/public/ingestion")
async def mock_ingestion(request: Request):
    time.sleep(0.5)
    return {"status": "done"}


seen_langfuse_request_ids = set()

@app.post("/api/public/ingestion")
async def ingestion(request: Request):
    try:
        global seen_langfuse_request_ids
        data = await request.json()
        
        # Extract request IDs from the batch
        for item in data.get('batch', []):
            if item.get('type') == 'generation-create':
                full_request_id = item.get('body', {}).get('id')
                if full_request_id and '_' in full_request_id:
                    # Split on underscore and take the second part (the chatcmpl ID)
                    clean_request_id = full_request_id.split('_')[1]
                    seen_langfuse_request_ids.add(clean_request_id)
        
        print(f"Stored request IDs (total: {len(seen_langfuse_request_ids)}): {seen_langfuse_request_ids}")
        await asyncio.sleep(1)  # Original delay
        return {"status": "done", "stored_ids_count": len(seen_langfuse_request_ids)}
    
    except Exception as e:
        print(f"Error processing ingestion request: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")

@app.get("/langfuse/trace/{request_id}")
async def has_request_id(request_id: str):
    return {
        "exists": request_id in seen_langfuse_request_ids,
        "request_id": request_id
    }


# for responses
def responses_data_generator(input_text=""):
    """Generator for streaming Responses API chunks"""
    response_id = uuid.uuid4().hex
    item_id = f"msg_{uuid.uuid4().hex}"
    sentence = f"Hello! I received your input: '{input_text}'. This is a mock response from the Responses API."
    words = sentence.split(" ")
    current_time = int(time.time())
    
    # 1. Send response.created event
    response_created = {
        'type': 'response.created',
        'response': {
            'id': f'resp_{response_id}',
            'object': 'response',
            'created_at': current_time,
            'model': 'gpt-4.1',
            'status': 'in_progress',
            'output': []
        }
    }
    yield f"data: {json.dumps(response_created)}\n\n"
    
    # 2. Send output_item.added event
    output_item_added = {
        'type': 'response.output_item.added',
        'output_index': 0,
        'item': {
            'type': 'message',
            'id': item_id,
            'role': 'assistant',
            'status': 'in_progress',
            'content': []
        }
    }
    yield f"data: {json.dumps(output_item_added)}\n\n"
    
    # 3. Send text deltas
    for word in words:
        text_delta = {
            'type': 'response.output_text.delta',
            'item_id': item_id,
            'output_index': 0,
            'content_index': 0,
            'delta': word + ' '
        }
        yield f"data: {json.dumps(text_delta)}\n\n"
    
    # 4. Send output_text.done event
    output_text_done = {
        'type': 'response.output_text.done',
        'item_id': item_id,
        'output_index': 0,
        'content_index': 0,
        'text': sentence
    }
    yield f"data: {json.dumps(output_text_done)}\n\n"
    
    # 5. Send response.completed event
    response_completed = {
        'type': 'response.completed',
        'response': {
            'id': f'resp_{response_id}',
            'object': 'response',
            'created_at': current_time,
            'model': 'gpt-4.1',
            'status': 'completed',
            'output': [{
                'type': 'message',
                'id': item_id,
                'role': 'assistant',
                'status': 'completed',
                'content': [{'type': 'output_text', 'text': sentence}]
            }],
            'usage': {
                'input_tokens': len(input_text.split()) if input_text else 0,
                'output_tokens': len(sentence.split()),
                'total_tokens': (len(input_text.split()) if input_text else 0) + len(sentence.split())
            }
        }
    }
    yield f"data: {json.dumps(response_completed)}\n\n"
    
    # 6. Send [DONE]
    yield "data: [DONE]\n\n"


async def _send_realtime_text_response(
    websocket: WebSocket,
    text: str,
    model: str,
    next_event_id: Callable[[], str],
    conversation_id: str,
) -> None:
    """Emit realtime events that align with OpenAI's websocket schema."""

    current_time = int(time.time())
    response_id = f"resp_{uuid.uuid4().hex}"
    item_id = f"msg_{uuid.uuid4().hex}"

    await websocket.send_json(
        {
            "event_id": next_event_id(),
            "type": "response.created",
            "response": {
                "id": response_id,
                "object": "realtime.response",
                "created_at": current_time,
                "status": "in_progress",
                "model": model,
                "conversation_id": conversation_id,
                "output": [],
            },
        }
    )

    await websocket.send_json(
        {
            "event_id": next_event_id(),
            "type": "response.output_item.added",
            "response_id": response_id,
            "output_index": 0,
            "item": {
                "id": item_id,
                "object": "realtime.item",
                "type": "message",
                "role": "assistant",
                "status": "in_progress",
                "content": [],
            },
        }
    )

    await websocket.send_json(
        {
            "event_id": next_event_id(),
            "type": "response.content_part.added",
            "response_id": response_id,
            "output_index": 0,
            "item_id": item_id,
            "content_index": 0,
            "part": {
                "type": "text",
                "text": "",
            },
        }
    )

    await websocket.send_json(
        {
            "event_id": next_event_id(),
            "type": "response.text.delta",
            "response_id": response_id,
            "output_index": 0,
            "item_id": item_id,
            "content_index": 0,
            "delta": text,
        }
    )

    await websocket.send_json(
        {
            "event_id": next_event_id(),
            "type": "response.text.done",
            "response_id": response_id,
            "output_index": 0,
            "item_id": item_id,
            "content_index": 0,
            "text": text,
        }
    )

    await websocket.send_json(
        {
            "event_id": next_event_id(),
            "type": "response.content_part.done",
            "response_id": response_id,
            "output_index": 0,
            "item_id": item_id,
            "content_index": 0,
            "part": {
                "type": "text",
                "text": text,
            },
        }
    )

    await websocket.send_json(
        {
            "event_id": next_event_id(),
            "type": "response.output_item.done",
            "response_id": response_id,
            "output_index": 0,
            "item": {
                "id": item_id,
                "object": "realtime.item",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {
                        "type": "text",
                        "text": text,
                    }
                ],
            },
        }
    )

    await websocket.send_json(
        {
            "event_id": next_event_id(),
            "type": "response.done",
            "response": {
                "id": response_id,
                "object": "realtime.response",
                "status": "completed",
                "model": model,
                "conversation_id": conversation_id,
                "output": [
                    {
                        "object": "realtime.item",
                        "type": "message",
                        "id": item_id,
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "text",
                                "text": text,
                            }
                        ],
                    }
                ],
                "usage": {
                    "input_tokens": 0,
                    "output_tokens": len(text.split()),
                    "total_tokens": len(text.split()),
                },
            },
        }
    )


@app.post("/responses")
@app.post("/v1/responses")
async def create_response(request: Request):
    """OpenAI Responses API endpoint - Create a response"""
    _time_to_sleep = os.getenv("TIME_TO_SLEEP", None)
    if _time_to_sleep is not None:
        print("sleeping for " + _time_to_sleep)
        await asyncio.sleep(float(_time_to_sleep))

    data = await request.json()

    # Handle error cases
    if data.get("model") == "429":
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests")

    if data.get("model") == "random_sleep":
        sleep_time = random.randint(1, 10)
        print("sleeping for " + str(sleep_time) + " seconds")
        await asyncio.sleep(sleep_time)
    
    # Degraded provider simulation for responses endpoint
    if data.get("model") in ["degraded", "slow_provider", "blocked"]:
        sleep_time = get_histogram_sleep_time()
        print(f"[DEGRADED MODE] Sleeping for {sleep_time:.1f} seconds ({sleep_time/60:.1f} minutes) - histogram distribution")
        await asyncio.sleep(sleep_time)

    # Non-streaming response setup
    response_id = uuid.uuid4().hex
    model = data.get("model", "gpt-4.1")
    input_text = data.get("input", "")
    
    if data.get("stream") == True:
        return StreamingResponse(
            content=responses_data_generator(input_text=input_text),
            media_type="text/event-stream",
        )
    tools = data.get("tools", [])
    reasoning = data.get("reasoning", {})
    background = data.get("background", False)
    
    # Generate output text based on input
    output_text = f"Hello! I received your input: '{input_text}'. This is a mock response from the Responses API."
    
    # Handle background mode
    if background:
        # In background mode, return a job-like response
        return {
            "id": f"resp_{response_id}",
            "object": "response",
            "created_at": int(time.time()),
            "model": model,
            "status": "processing",
            "background": True,
            "output": [],  # Empty output for processing state
            "tools": tools,
            "reasoning": reasoning
        }
    
    # Regular response
    response = {
        "id": f"resp_{response_id}",
        "object": "response",
        "created_at": int(time.time()),
        "model": model,
        "output": [
            {
                "type": "message",
                "id": f"msg_{uuid.uuid4().hex}",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": output_text
                    }
                ]
            }
        ],
        "tools": tools if tools else [],
        "reasoning": reasoning if reasoning else {},
        "usage": {
            "input_tokens": len(input_text.split()) if input_text else 0,  
            "output_tokens": len(output_text.split()),
            "total_tokens": len(input_text.split()) + len(output_text.split()) if input_text else len(output_text.split())
        }
    }
    
    return response


@app.post("/openai/responses")
@app.post("/openai/v1/responses")
async def azure_responses_api(request: Request):
    """Azure Responses API endpoint - delegates to the same handler as /responses"""
    # Reuse the exact same logic as your existing /responses endpoint
    return await create_response(request)


@app.get("/v1/responses/{response_id}")
async def get_response(response_id: str):
    """OpenAI Responses API endpoint - Get a response by ID"""
    # Return a mock response with the given ID
    return {
        "id": response_id,
        "object": "response",
        "created_at": int(time.time()),
        "model": "gpt-4.1",
        "output": [
            {
                "type": "message",
                "id": f"msg_{uuid.uuid4().hex}",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "This is a mock response retrieved by ID."
                    }
                ]
            }
        ],
        "tools": [],
        "reasoning": {},
        "status": "completed",
        "usage": {
            "input_tokens": 5,       
            "output_tokens": 10,     
            "total_tokens": 15
        }
    }


@app.websocket("/v1/realtime")
async def realtime_endpoint(websocket: WebSocket):
    """Simplified realtime endpoint compatible with LiteLLM proxy tests."""

    model = websocket.query_params.get("model", "gpt-4o-realtime-preview-2024-10-01")
    session_id = f"sess_{uuid.uuid4().hex}"
    conversation_id = f"conv_{uuid.uuid4().hex}"

    event_counter = 0

    def next_event_id() -> str:
        nonlocal event_counter
        event_counter += 1
        return f"evt_{session_id}_{event_counter}"

    await websocket.accept()

    await websocket.send_json(
        {
            "event_id": next_event_id(),
            "type": "session.created",
            "session": {
                "id": session_id,
                "model": model,
                "created_at": int(time.time()),
                "modalities": ["text"],
            },
        }
    )

    try:
        while True:
            try:
                incoming = await websocket.receive()
            except RuntimeError as e:
                # Connection was closed by client
                if "already completed" in str(e) or "websocket.close" in str(e):
                    break
                raise

            if incoming.get("type") == "websocket.close":
                break

            message_text = incoming.get("text")
            if message_text is None:
                # Skip non-text messages (binary, ping/pong, etc.)
                continue

            try:
                payload = json.loads(message_text)
            except json.JSONDecodeError:
                await websocket.send_json(
                    {
                        "type": "error",
                        "error": {
                            "type": "invalid_request_error",
                            "message": "Payload must be valid JSON",
                        },
                    }
                )
                continue

            event_type = payload.get("type")

            if event_type == "session.update":
                await websocket.send_json(
                    {
                        "event_id": next_event_id(),
                        "type": "session.updated",
                        "session": {
                            "id": session_id,
                            "model": model,
                            "modalities": payload.get("session", {}).get("modalities", ["text"]),
                        },
                    }
                )
            elif event_type == "response.create":
                response_payload = payload.get("response", {})
                instructions = response_payload.get("instructions", "")
                prefix = "[fake-realtime] "
                output_text = (
                    f"{prefix}{instructions}"
                    if instructions
                    else f"{prefix}Hello! This is a realtime response from the fake endpoint."
                )
                await _send_realtime_text_response(
                    websocket,
                    output_text,
                    model,
                    next_event_id,
                    conversation_id,
                )
            else:
                await websocket.send_json(
                    {
                        "type": "error",
                        "error": {
                            "type": "unsupported_event",
                            "message": f"Unsupported realtime event: {event_type}",
                        },
                    }
                )

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await websocket.close(code=1011, reason=str(exc))
        except RuntimeError:
            pass
    finally:
        try:
            await websocket.close()
        except RuntimeError:
            pass


if __name__ == "__main__":
    import os
    import uvicorn

    port = int(os.getenv("PORT", "8090"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")