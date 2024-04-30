from fastapi import FastAPI, Request, status, HTTPException, Depends
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import uuid
import asyncio
import os

app = FastAPI()

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

    if data.get("stream") == True:
        return StreamingResponse(
            content=data_generator(),
            media_type="text/event-stream",
        )
    else:
        response_id = uuid.uuid4().hex
        response = {
            "id": f"chatcmpl-{response_id}",
            "object": "chat.completion",
            "created": 1677652288,
            "model": "gpt-3.5-turbo-0125",
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
    

    

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8090)
