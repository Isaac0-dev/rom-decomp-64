from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
import extract
import threading
import queue
import sys
import io

app = FastAPI()

# A simple log queue to store output
log_queue = queue.Queue()


class ExtractionRequest(BaseModel):
    path: str


def run_extraction(rom_path):
    # Redirect stdout to a string buffer or custom stream if needed
    # For now, print to server console for testing
    print(f"Starting extraction for: {rom_path}")
    try:
        extract.main(
            filename_override=rom_path,
            output_status_override=True,
            called_by_main_override=False,
        )
    except Exception as e:
        print(f"Extraction failed: {e}")


@app.post("/api/start")
async def start_extraction(request: ExtractionRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(run_extraction, request.path)
    return {"message": "Extraction started"}


@app.post("/api/stop")
async def stop_extraction():
    # Placeholder: stopping in-process extraction is tricky without signal support
    return {"message": "Stop requested"}
