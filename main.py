from fastapi import FastAPI, Request, status, HTTPException, Depends
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import uuid
import asyncio
import os
from dotenv import load_dotenv
load_dotenv()

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

    if data.get("model") == "429":
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests")

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



    

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8090)