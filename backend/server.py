import sys
import os
import json
from pathlib import Path
from typing import Any, Dict, List

# Ensure we can import modules from the src/ directory
root_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(root_dir / "src"))

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import Settings
from app.graph import ShoppingAssistant
from app.utils import timestamp_utc

app = FastAPI(title="Multi-Agent Shopping Assistant API")

# Initialize the assistant (which loads embeddings, data index, etc.)
settings = Settings.load()
assistant = ShoppingAssistant(settings)

# Global in-memory batch test tracking state
batch_status = {
    "is_running": False,
    "current": 0,
    "total": 0,
    "results": [],
    "completed_at": None,
}

class ChatRequest(BaseModel):
    question: str

@app.post("/api/chat")
def chat(payload: ChatRequest):
    try:
        res = assistant.ask(payload.question)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def run_batch_task():
    global batch_status
    try:
        test_file = root_dir / "data" / "test.json"
        output_dir = root_dir / "src" / "artifacts"
        traces_dir = output_dir / "traces"
        
        output_dir.mkdir(parents=True, exist_ok=True)
        traces_dir.mkdir(parents=True, exist_ok=True)

        if not test_file.exists():
            batch_status["is_running"] = False
            return

        with open(test_file, "r", encoding="utf-8") as f:
            test_cases = json.load(f)

        batch_status["total"] = len(test_cases)
        batch_status["current"] = 0
        batch_status["results"] = []
        batch_status["completed_at"] = None

        results = []
        for case in test_cases:
            if not batch_status["is_running"]:
                break

            case_id = case.get("id", "unknown")
            question = case.get("question", "")
            expected_status = case.get("expected_status", "ok")
            expected_route = case.get("expected_route", [])

            trace_file_path = traces_dir / f"{case_id}_trace.json"
            res = assistant.ask(question, trace_file=trace_file_path)

            ans = res["final_answer"]
            status = "ok"
            if "status: clarification_needed" in ans.lower():
                status = "clarification_needed"
            elif "status: not_found" in ans.lower():
                status = "not_found"

            passed = (status == expected_status)

            case_result = {
                "id": case_id,
                "question": question,
                "expected_status": expected_status,
                "expected_route": expected_route,
                "route": res["route"],
                "status": status,
                "passed": passed,
                "final_answer": ans,
            }
            results.append(case_result)
            batch_status["results"].append(case_result)
            batch_status["current"] += 1

        # Write final summary results to summary.json
        summary = {
            "timestamp": timestamp_utc(),
            "total_cases": len(results),
            "results": [{
                "id": r["id"],
                "question": r["question"],
                "route": r["route"],
                "status": r["status"],
                "final_answer": r["final_answer"]
            } for r in results],
        }
        
        summary_file = output_dir / "summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        batch_status["completed_at"] = timestamp_utc()
    except Exception as e:
        print(f"Error in batch execution background task: {e}")
    finally:
        batch_status["is_running"] = False

@app.post("/api/batch/run")
def trigger_batch(background_tasks: BackgroundTasks):
    global batch_status
    if batch_status["is_running"]:
        return JSONResponse(status_code=400, content={"message": "Batch evaluation is already running."})
    
    batch_status["is_running"] = True
    background_tasks.add_task(run_batch_task)
    return {"message": "Batch evaluation started."}

@app.get("/api/batch/status")
def get_batch_status():
    return batch_status

@app.get("/api/batch/results")
def get_batch_results():
    summary_file = root_dir / "src" / "artifacts" / "summary.json"
    if not summary_file.exists():
        return JSONResponse(status_code=404, content={"message": "Summary results not found."})
    
    try:
        with open(summary_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Serve the static frontend assets from /frontend folder
frontend_dir = root_dir / "frontend"
app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    # Start uvicorn server directly on localhost port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)
