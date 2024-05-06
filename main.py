from fastapi import FastAPI, Request, status, HTTPException, Depends
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from loguru import logger
import asyncio
import json
import uuid
import asyncio
import os
import time
import tiktoken
# from langchain.text_splitter import TokenTextSplitter

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

time_to_sleep = 1
time_to_sleep_stream = 0.3

logger.add('error.log', level=40)

@app.exception_handler(Exception)
async def custom_exception_handler(request: Request, exc: Exception):
    # 记录异常信息
    logger.error("Uncaught exception: {0}".format(str(exc)))
    # 返回通用异常响应
    return JSONResponse(
        status_code=500,
        content={"message": "An unexpected error occurred"},
    )

def fix_incomplete_utf8(words):
    combined = bytearray()
    fixed_words = []
    for word in words:
        try:
            combined.extend(word)
            # 尝试解码来检查是否是完整的UTF-8字符
            combined.decode('utf-8')
            fixed_words.append(bytes(combined))
            combined.clear()
        except UnicodeDecodeError:
            continue  # 如果抛出解码错误，继续添加字节直到可以解码为止
    if combined:
        fixed_words.append(bytes(combined))  # 添加最后的字节序列
    return fixed_words
    

async def data_generator():
    response_id = uuid.uuid4().hex
    sentence = "花香蕉的钱，只能请到猴子. " * 5
    # a = TokenTextSplitter(model_name="gpt-3.5-turbo", chunk_size=1, chunk_overlap=0)
    # words = a.split_text(sentence)
    encoding = tiktoken.get_encoding("cl100k_base")
    token_integers = encoding.encode(sentence)
    words = [encoding.decode_single_token_bytes(token) for token in token_integers]
    fixed_words = fix_incomplete_utf8(words)
    for word in fixed_words:
        chunk = {
            "id": f"chatcmpl-{response_id}",
            "object": "chat.completion.chunk",
            "created": 1677652288,
            "model": "gpt-3.5-turbo-0125",
            "choices": [{"index": 0, "delta": {"content": word.decode('utf-8')}}],
        }
        yield f"data: {json.dumps(chunk)}\n\n"
        if time_to_sleep_stream:
            await asyncio.sleep(time_to_sleep_stream)

# for completion
@app.post("/chat/completions")
@app.post("/v1/chat/completions")
@app.post("/openai/deployments/{model:path}/chat/completions")  # azure compatible endpoint
async def completion(request: Request):
    if time_to_sleep:
        # print(f"sleeping for {time_to_sleep}")
        await asyncio.sleep(float(time_to_sleep))

    data = await request.json()
    #print(data)
    print(time.time())

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
    uvicorn.run(app, host="0.0.0.0", port=8000)
