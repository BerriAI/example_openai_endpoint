from fastapi import FastAPI, Request, status, HTTPException, Depends, Header
from fastapi.responses import StreamingResponse, Response
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import uuid
import asyncio
import os
import time
import random
from dotenv import load_dotenv
from slowapi import Limiter
from collections import deque
from datetime import datetime, timedelta
from typing import List, Dict, Any
from pydantic import BaseModel

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
load_dotenv()

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
            "model": "gpt-3.5-turbo-instruct-0914",
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
    return {
        "object": "list",
        "data": [
            {
            "object": "embedding",
            "index": 0,
            "embedding": [
                -0.006929283495992422,
                -0.005336422007530928,
                -4.547132266452536e-05,
                -0.024047505110502243,
                -0.005336422007530928,
                -4.547132266452536e-05,
                -0.024047505110502243,
                -0.005336422007530928,
                -4.547132266452536e-05,
                -0.024047505110502243,
                -0.005336422007530928,
                -4.547132266452536e-05,
                -0.024047505110502243,
                -0.005336422007530928,
                -4.547132266452536e-05,
                -0.024047505110502243,
                -0.005336422007530928,
                -4.547132266452536e-05,
                -0.024047505110502243
            ],
            }
        ],
        "model": "text-embedding-3-small",
        "usage": {
            "prompt_tokens": 5,
            "total_tokens": 5
        }
    }




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
@limiter.limit("9000/minute")
async def generate_content(request: Request, authorization: str = Header(None)):
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




if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8090)