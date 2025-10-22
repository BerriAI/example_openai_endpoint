from fastapi import APIRouter, File, Form, HTTPException, UploadFile
# In-memory storage (replace with your actual storage)
from pydantic import BaseModel
from typing import Dict, Literal, Optional
import uuid
from datetime import datetime

router = APIRouter()

files_store = {}
batches_store = {}


# ============= Models =============

class FileObject(BaseModel):
    id: str
    object: Literal["file"] = "file"
    bytes: int
    created_at: int
    filename: str
    purpose: str


class BatchRequestCounts(BaseModel):
    total: int
    completed: int
    failed: int


class BatchObject(BaseModel):
    id: str
    object: Literal["batch"] = "batch"
    endpoint: str
    errors: Optional[Dict] = None
    input_file_id: str
    completion_window: str
    status: Literal["validating", "failed", "in_progress", "finalizing", "completed", "expired", "cancelling", "cancelled"]
    output_file_id: Optional[str] = None
    error_file_id: Optional[str] = None
    created_at: int
    in_progress_at: Optional[int] = None
    expires_at: Optional[int] = None
    finalizing_at: Optional[int] = None
    completed_at: Optional[int] = None
    failed_at: Optional[int] = None
    expired_at: Optional[int] = None
    cancelling_at: Optional[int] = None
    cancelled_at: Optional[int] = None
    request_counts: Optional[BatchRequestCounts] = None
    metadata: Optional[Dict[str, str]] = None


class CreateBatchRequest(BaseModel):
    input_file_id: str
    endpoint: Literal["/v1/chat/completions", "/v1/embeddings", "/v1/completions"]
    completion_window: Literal["24h"]
    metadata: Optional[Dict[str, str]] = None


# ============= Files Endpoints =============

@router.post("/files", response_model=FileObject)
async def create_file(
    file: UploadFile = File(...),
    purpose: str = Form(...)
):
    """
    Upload a file that can be used for batch processing.
    
    Compatible with: https://platform.openai.com/docs/api-reference/files/create
    """
    file_id = f"file-{uuid.uuid4().hex}"
    content = await file.read()
    
    file_obj = {
        "id": file_id,
        "object": "file",
        "bytes": len(content),
        "created_at": int(datetime.now().timestamp()),
        "filename": file.filename,
        "purpose": purpose,
        "content": content
    }
    
    files_store[file_id] = file_obj
    
    return FileObject(
        id=file_id,
        bytes=len(content),
        created_at=file_obj["created_at"],
        filename=file.filename,
        purpose=purpose
    )


@router.get("/files/{file_id}", response_model=FileObject)
async def retrieve_file(file_id: str):
    """
    Returns information about a specific file.
    
    Compatible with: https://platform.openai.com/docs/api-reference/files/retrieve
    """
    if file_id not in files_store:
        raise HTTPException(status_code=404, detail="File not found")
    
    file_obj = files_store[file_id]
    return FileObject(
        id=file_obj["id"],
        bytes=file_obj["bytes"],
        created_at=file_obj["created_at"],
        filename=file_obj["filename"],
        purpose=file_obj["purpose"]
    )


@router.get("/files/{file_id}/content")
async def retrieve_file_content(file_id: str):
    """
    Returns the contents of the specified file.
    
    Compatible with: https://platform.openai.com/docs/api-reference/files/retrieve-contents
    """
    if file_id not in files_store:
        raise HTTPException(status_code=404, detail="File not found")
    
    file_obj = files_store[file_id]
    return file_obj["content"].decode("utf-8")


@router.delete("/files/{file_id}")
async def delete_file(file_id: str):
    """
    Delete a file.
    
    Compatible with: https://platform.openai.com/docs/api-reference/files/delete
    """
    if file_id not in files_store:
        raise HTTPException(status_code=404, detail="File not found")
    
    del files_store[file_id]
    return {"id": file_id, "object": "file", "deleted": True}


# ============= Batches Endpoints =============

@router.post("/batches", response_model=BatchObject)
async def create_batch(request: CreateBatchRequest):
    """
    Creates and executes a batch from an uploaded file of requests.
    
    Compatible with: https://platform.openai.com/docs/api-reference/batch/create
    """
    if request.input_file_id not in files_store:
        raise HTTPException(status_code=400, detail="Input file not found")
    
    batch_id = f"batch_{uuid.uuid4().hex}"
    created_at = int(datetime.now().timestamp())
    
    # Simulate batch processing (replace with actual vLLM batch processing)
    batch_obj = {
        "id": batch_id,
        "object": "batch",
        "endpoint": request.endpoint,
        "errors": None,
        "input_file_id": request.input_file_id,
        "completion_window": request.completion_window,
        "status": "validating",
        "output_file_id": None,
        "error_file_id": None,
        "created_at": created_at,
        "in_progress_at": None,
        "expires_at": created_at + 86400,  # 24 hours
        "finalizing_at": None,
        "completed_at": None,
        "failed_at": None,
        "expired_at": None,
        "cancelling_at": None,
        "cancelled_at": None,
        "request_counts": None,
        "metadata": request.metadata or {}
    }
    
    batches_store[batch_id] = batch_obj
    
    # TODO: Trigger actual batch processing with vLLM here
    # For now, immediately move to in_progress
    batch_obj["status"] = "in_progress"
    batch_obj["in_progress_at"] = int(datetime.now().timestamp())
    
    return BatchObject(**batch_obj)


@router.get("/batches/{batch_id}", response_model=BatchObject)
async def retrieve_batch(batch_id: str):
    """
    Retrieves a batch.
    
    Compatible with: https://platform.openai.com/docs/api-reference/batch/retrieve
    """
    if batch_id not in batches_store:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    batch_obj = batches_store[batch_id]
    
    # TODO: Check actual batch status from vLLM
    # Simulate completion for demo
    if batch_obj["status"] == "in_progress":
        # You would check your actual batch processing status here
        pass
    
    return BatchObject(**batch_obj)


@router.post("/batches/{batch_id}/cancel", response_model=BatchObject)
async def cancel_batch(batch_id: str):
    """
    Cancels an in-progress batch.
    
    Compatible with: https://platform.openai.com/docs/api-reference/batch/cancel
    """
    if batch_id not in batches_store:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    batch_obj = batches_store[batch_id]
    
    if batch_obj["status"] not in ["validating", "in_progress"]:
        raise HTTPException(status_code=400, detail="Batch cannot be cancelled")
    
    batch_obj["status"] = "cancelling"
    batch_obj["cancelling_at"] = int(datetime.now().timestamp())
    
    # TODO: Actually cancel the batch processing
    
    # Simulate immediate cancellation
    batch_obj["status"] = "cancelled"
    batch_obj["cancelled_at"] = int(datetime.now().timestamp())
    
    return BatchObject(**batch_obj)


@router.get("/batches")
async def list_batches(limit: int = 20, after: Optional[str] = None):
    """
    List your organization's batches.
    
    Compatible with: https://platform.openai.com/docs/api-reference/batch/list
    """
    batches_list = list(batches_store.values())
    
    # Sort by created_at descending
    batches_list.sort(key=lambda x: x["created_at"], reverse=True)
    
    # Handle pagination
    if after:
        try:
            start_idx = next(i for i, b in enumerate(batches_list) if b["id"] == after) + 1
            batches_list = batches_list[start_idx:]
        except StopIteration:
            pass
    
    batches_list = batches_list[:limit]
    
    return {
        "object": "list",
        "data": [BatchObject(**b) for b in batches_list],
        "has_more": len(batches_store) > len(batches_list)
    }
