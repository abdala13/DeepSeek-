import io
import os
import re
import uuid
import zipfile
import tempfile
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Response, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agent import HusamAgent
from . import db
from .utils import env_bool, now_iso, run_command

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Husam Prime AI Final", version="7.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db.init_db()
agent = HusamAgent()


class CreateChatRequest(BaseModel):
    title: str = "محادثة جديدة"
    mode: str = "assistant"
    language: str = "auto"


class ChatUpdateRequest(BaseModel):
    title: str | None = None
    mode: str | None = None
    language: str | None = None


class MessageRequest(BaseModel):
    chat_id: str
    content: str = Field(min_length=1)
    mode: str = "assistant"
    language: str = "auto"


class ZipFileItem(BaseModel):
    path: str
    content: str


class ZipRequest(BaseModel):
    files: List[ZipFileItem]
    archive_name: str = "husam_generated_code.zip"


class RunPythonRequest(BaseModel):
    code: str


@app.get("/api/health")
def health() -> Dict[str, Any]:
    cached = agent.load_cached_model()
    return {"ok": True, "app": "Husam Prime AI", "version": "7.0.0", "cached_model": cached}


@app.post("/api/models/check")
def check_models() -> Dict[str, Any]:
    return agent.health_check()


@app.get("/api/chats")
def api_list_chats() -> Dict[str, Any]:
    return {"ok": True, "chats": db.list_chats()}


@app.post("/api/chats")
def api_create_chat(req: CreateChatRequest) -> Dict[str, Any]:
    chat_id = str(uuid.uuid4())
    now = now_iso()
    chat = db.create_chat(chat_id, req.title.strip() or "محادثة جديدة", req.mode, req.language, now)
    return {"ok": True, "chat": chat}


@app.patch("/api/chats/{chat_id}")
def api_update_chat(chat_id: str, req: ChatUpdateRequest) -> Dict[str, Any]:
    if not db.get_chat(chat_id):
        raise HTTPException(status_code=404, detail="Chat not found")
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    fields["updated_at"] = now_iso()
    chat = db.update_chat(chat_id, **fields)
    return {"ok": True, "chat": chat}


@app.delete("/api/chats/{chat_id}")
def api_delete_chat(chat_id: str) -> Dict[str, Any]:
    db.delete_chat(chat_id)
    return {"ok": True}


@app.get("/api/chats/{chat_id}/messages")
def api_messages(chat_id: str) -> Dict[str, Any]:
    if not db.get_chat(chat_id):
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"ok": True, "messages": db.list_messages(chat_id)}


@app.post("/api/chat")
def api_chat(req: MessageRequest) -> Dict[str, Any]:
    chat = db.get_chat(req.chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    now = now_iso()
    user_msg = db.add_message(str(uuid.uuid4()), req.chat_id, "user", req.content, {}, now)
    history = db.list_messages(req.chat_id, limit=60)
    llm_messages = [{"role": m["role"], "content": m["content"]} for m in history if m["role"] in {"user", "assistant"}]
    result = agent.call(llm_messages, mode=req.mode, language=req.language)
    if result["ok"]:
        assistant_msg = db.add_message(
            str(uuid.uuid4()),
            req.chat_id,
            "assistant",
            result["answer"],
            {"provider": result["provider"], "model": result["model"], "latency": result["latency"], "usage": result.get("usage", {})},
            now_iso(),
        )
        title = chat.get("title", "")
        if title in {"محادثة جديدة", "New Chat", "New chat"}:
            db.update_chat(req.chat_id, title=req.content[:42] + ("..." if len(req.content) > 42 else ""), updated_at=now_iso())
        return {"ok": True, "user_message": user_msg, "assistant_message": assistant_msg, "model": {"provider": result["provider"], "name": result["model"]}}
    error_text = "تعذر الحصول على رد من النماذج المتاحة. راجع المفاتيح أو اضغط فحص النماذج.\n\n" + str(result.get("errors", []))
    assistant_msg = db.add_message(str(uuid.uuid4()), req.chat_id, "assistant", error_text, {"error": True, "errors": result.get("errors", [])}, now_iso())
    return {"ok": False, "user_message": user_msg, "assistant_message": assistant_msg, "errors": result.get("errors", [])}


@app.post("/api/zip")
def api_zip(req: ZipRequest) -> StreamingResponse:
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if not req.files:
            zf.writestr("README.txt", "No files were provided.")
        for item in req.files:
            safe_path = item.path.strip().replace("\\", "/")
            safe_path = re.sub(r"(^/+|\.\./)", "", safe_path) or "file.txt"
            zf.writestr(safe_path, item.content)
    memory.seek(0)
    filename = re.sub(r"[^A-Za-z0-9_.-]", "_", req.archive_name or "husam_generated_code.zip")
    if not filename.endswith(".zip"):
        filename += ".zip"
    return StreamingResponse(memory, media_type="application/zip", headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.post("/api/run-python")
def api_run_python(req: RunPythonRequest) -> Dict[str, Any]:
    if not env_bool("ENABLE_SCRIPT_RUNNER", False):
        return {"ok": False, "stdout": "", "stderr": "Python runner is disabled. Set ENABLE_SCRIPT_RUNNER=true only for private deployments.", "returncode": 403}
    timeout = int(os.getenv("SCRIPT_TIMEOUT_SECONDS", "8"))
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "script.py"
        path.write_text(req.code, encoding="utf-8")
        try:
            proc = subprocess.run(["python", str(path)], cwd=tmp, capture_output=True, text=True, timeout=timeout)
            return {"ok": proc.returncode == 0, "stdout": proc.stdout[-10000:], "stderr": proc.stderr[-10000:], "returncode": proc.returncode}
        except subprocess.TimeoutExpired:
            return {"ok": False, "stdout": "", "stderr": f"Execution timed out after {timeout}s", "returncode": 124}


@app.post("/api/github/sync")
def api_github_sync() -> Dict[str, Any]:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    repo_url = os.getenv("GITHUB_REPO_URL", "").strip()
    branch = os.getenv("GITHUB_BRANCH", "main").strip()
    if not token or not repo_url:
        return {"ok": False, "message": "GITHUB_TOKEN and GITHUB_REPO_URL are required."}
    safe_url = repo_url.replace("https://", "")
    auth_url = f"https://x-access-token:{token}@{safe_url}"
    steps = []
    if not (BASE_DIR / ".git").exists():
        steps.append({"step": "git init", **run_command(["git", "init"], cwd=BASE_DIR)})
    steps.append({"step": "git config name", **run_command(["git", "config", "user.name", os.getenv("GIT_USER_NAME", "Husam Prime AI")], cwd=BASE_DIR)})
    steps.append({"step": "git config email", **run_command(["git", "config", "user.email", os.getenv("GIT_USER_EMAIL", "husam@example.com")], cwd=BASE_DIR)})
    remote = run_command(["git", "remote", "get-url", "origin"], cwd=BASE_DIR)
    if remote["ok"]:
        steps.append({"step": "git remote set", **run_command(["git", "remote", "set-url", "origin", auth_url], cwd=BASE_DIR)})
    else:
        steps.append({"step": "git remote add", **run_command(["git", "remote", "add", "origin", auth_url], cwd=BASE_DIR)})
    steps.append({"step": "git add", **run_command(["git", "add", "data", "logs"], cwd=BASE_DIR)})
    status = run_command(["git", "status", "--porcelain"], cwd=BASE_DIR)
    if not status.get("stdout"):
        return {"ok": True, "message": "No changes to sync.", "steps": steps}
    steps.append({"step": "git commit", **run_command(["git", "commit", "-m", f"Husam Prime AI sync {now_iso()}"], cwd=BASE_DIR)})
    push = run_command(["git", "push", "-u", "origin", f"HEAD:{branch}"], cwd=BASE_DIR, timeout=120)
    push["stdout"] = push.get("stdout", "").replace(token, "***")
    push["stderr"] = push.get("stderr", "").replace(token, "***")
    steps.append({"step": "git push", **push})
    return {"ok": push["ok"], "message": "Synced." if push["ok"] else "Git push failed.", "steps": steps}


# Serve React app last
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def serve_app(full_path: str):
        file_path = FRONTEND_DIST / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIST / "index.html", media_type="text/html; charset=utf-8")
else:
    @app.get("/")
    def no_frontend():
        return {"ok": True, "message": "Frontend not built yet. Run: cd frontend && npm ci && npm run build"}
