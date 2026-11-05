import asyncio
import hashlib
import json
import re
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .automation import run_due
from .config import Settings
from .db import (Action, Audit, Automation, AutomationRun, Chunk, Conversation, Credential,
                 DailyQuota, Document, Invite, Message, Organization, Run, Task, Ticket,
                 User, Workflow, database)
from .providers import PROMPT_VERSION, ProviderUnavailable, generate
from .retrieval import extract, retrieve, visible
from .security import (Principal, audit, authenticate, browser_only, digest, issue_session,
                       password_hash, password_matches, require_role, require_scope)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class IdentityInput(Input):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def email_valid(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address")
        return value


class Signup(IdentityInput):
    name: str = Field(min_length=2, max_length=80)
    organization: str = Field(min_length=2, max_length=100)
    industry: str = Field(default="General", max_length=80)


class AcceptInvite(IdentityInput):
    name: str = Field(min_length=2, max_length=80)
    token: str = Field(min_length=20, max_length=100)


class Invitation(Input):
    email: str = Field(min_length=3, max_length=254)
    role: Literal["employee", "reviewer", "admin"] = "employee"
    department: str = Field(default="General", min_length=1, max_length=60)

    @field_validator("email")
    @classmethod
    def email_valid(cls, value):
        return IdentityInput.email_valid(value)


class OrgSettings(Input):
    name: str = Field(min_length=2, max_length=100)
    industry: str = Field(min_length=1, max_length=80)
    assistant_name: str = Field(min_length=2, max_length=60)
    guidance: str = Field(min_length=1, max_length=1000)


class UserUpdate(Input):
    role: Literal["employee", "reviewer", "admin"]
    department: str = Field(min_length=1, max_length=60)
    active: bool


class Question(Input):
    question: str = Field(min_length=2, max_length=2000)
    conversation_id: str | None = None


class WorkflowInput(Input):
    name: str = Field(min_length=2, max_length=100)
    description: str = Field(min_length=5, max_length=1000)
    department: str = Field(default="General", min_length=1, max_length=60)


class Proposal(Input):
    workflow_id: str
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=5, max_length=4000)
    priority: Literal["low", "normal", "high"] = "normal"
    idempotency_key: str = Field(min_length=8, max_length=100)


class Decision(Input):
    decision: Literal["approve", "reject"]
    reason: str = Field(default="", max_length=500)


class TokenInput(Input):
    label: str = Field(min_length=2, max_length=80)
    scopes: list[Literal["knowledge:read", "chat:write", "actions:read", "actions:write", "workflows:read"]] = Field(min_length=1, max_length=5)
    days: int = Field(default=30, ge=1, le=90)


class AutomationInput(Input):
    name: str = Field(min_length=2, max_length=100)
    kind: Literal["document_review", "approval_reminder"]
    interval_hours: int = Field(default=24, ge=1, le=720)


def create_app(settings=None):
    settings = settings or Settings.from_env()
    engine, factory = database(settings.database_url)

    @asynccontextmanager
    async def lifespan(app):
        yield
        engine.dispose()

    app = FastAPI(title="AIVORA Workspace API", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.factory, app.state.settings = factory, settings
    auth_attempts = defaultdict(deque)
    static = Path(__file__).parent / "static"

    @app.middleware("http")
    async def security_headers(request, call_next):
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin and origin != settings.origin:
            return Response("Cross-origin writes are not allowed", status_code=403)
        length = request.headers.get("content-length", "0")
        if not length.isdigit() or int(length) > 6 * 1024 * 1024:
            return Response("Request exceeds the 6 MB limit", status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def db_session():
        with factory() as db:
            yield db

    def principal(request: Request, db: Session = Depends(db_session)):
        return authenticate(request, db, settings)

    def auth_limit(request):
        # Single-process local-pilot limiter; deployment must use shared Redis limits.
        key = digest(request.client.host if request.client else "unknown")
        now = time.monotonic()
        queue = auth_attempts[key]
        while queue and queue[0] < now - 300:
            queue.popleft()
        if len(queue) >= 15:
            raise HTTPException(429, "Too many authentication attempts. Retry in five minutes")
        queue.append(now)

    def profile(db, p):
        user = p.user
        org = db.get(Organization, user.org_id)
        return {"user": {"id": user.id, "name": user.name, "email": user.email,
                         "role": user.role, "department": user.department},
                "organization": {"id": org.id, "name": org.name, "industry": org.industry,
                                 "assistant_name": org.assistant_name, "guidance": org.guidance},
                "csrf": p.credential.csrf if p.credential.kind == "session" else "",
                "provider": settings.provider, "model": settings.model,
                "retrieval": "hybrid-local" if settings.semantic_model else "bm25",
                "daily_limit": settings.daily_limit}

    def owned(db, model, object_id, user):
        value = db.scalar(select(model).where(model.id == object_id, model.org_id == user.org_id))
        if not value:
            raise HTTPException(404, "Resource not found")
        return value

    def doc_access(db, document_id, user):
        doc = db.scalar(select(Document).where(Document.id == document_id,
            Document.org_id == user.org_id, visible(user)))
        if not doc:
            raise HTTPException(404, "Document not found or no longer accessible")
        return doc

    def safe_citations(db, citations, user):
        safe = []
        for citation in citations:
            row = db.execute(select(Chunk, Document).join(Document).where(
                Chunk.id == citation["chunk_id"], Document.org_id == user.org_id, visible(user))).first()
            if row and row[1].version == citation["version"]:
                safe.append({**citation, "title": row[1].title})
        return safe

    def can_review(db, action, user):
        if user.role not in {"admin", "reviewer"} or action.user_id == user.id:
            return False
        workflow = db.get(Workflow, action.workflow_id)
        return user.role == "admin" or workflow.department in {"General", user.department}

    def action_view(db, action, user):
        workflow = db.get(Workflow, action.workflow_id)
        ticket = db.scalar(select(Ticket).where(Ticket.action_id == action.id))
        status = "expired" if action.status == "pending" and action.expires <= time.time() else action.status
        return {"id": action.id, "title": action.title, "description": action.description,
                "priority": action.priority, "status": status, "workflow": workflow.name,
                "department": workflow.department, "created": action.created, "expires": action.expires,
                "reason": action.reason, "ticket_id": ticket.id if ticket else None,
                "ticket_status": ticket.status if ticket else None,
                "can_review": status == "pending" and can_review(db, action, user),
                "mine": action.user_id == user.id}

    @app.get("/api/health")
    def health(db: Session = Depends(db_session)):
        db.execute(select(1))
        return {"status": "ok", "version": "0.1.0", "environment": settings.environment}

    @app.get("/api/config")
    def public_config():
        return {"allow_signup": settings.allow_signup, "version": "0.1.0"}

    @app.post("/api/auth/signup", status_code=201)
    def signup(body: Signup, request: Request, response: Response, db: Session = Depends(db_session)):
        auth_limit(request)
        if not settings.allow_signup:
            raise HTTPException(403, "Organization creation is disabled")
        if db.scalar(select(User.id).where(User.email == body.email)):
            raise HTTPException(409, "Unable to create account with this email")
        org = Organization(name=body.organization.strip(), industry=body.industry.strip())
        db.add(org)
        db.flush()
        user = User(org_id=org.id, email=body.email, name=body.name.strip(),
                    password=password_hash(body.password), role="admin")
        db.add(user)
        db.flush()
        db.add_all([
            Workflow(org_id=org.id, name="IT support", description="Request help with access, devices or software.", department="IT"),
            Workflow(org_id=org.id, name="Operations request", description="Request an operational change or assistance.", department="General")])
        csrf = issue_session(db, user, response, settings)
        audit(db, user, "organization.created", org.id)
        db.commit()
        return {"csrf": csrf}

    @app.post("/api/auth/login")
    def login(body: IdentityInput, request: Request, response: Response, db: Session = Depends(db_session)):
        auth_limit(request)
        user = db.scalar(select(User).where(User.email == body.email))
        # Constant password work also runs for unknown users.
        encoded = user.password if user else "0" * 32 + ":" + "0" * 64
        valid = password_matches(body.password, encoded)
        if not valid or not user or not user.active:
            raise HTTPException(401, "Email or password is incorrect")
        csrf = issue_session(db, user, response, settings)
        audit(db, user, "session.created")
        db.commit()
        return {"csrf": csrf}

    @app.post("/api/auth/logout")
    def logout(response: Response, p: Principal = Depends(principal), db: Session = Depends(db_session)):
        browser_only(p)
        db.delete(p.credential)
        response.delete_cookie("aivora_session", path="/")
        db.commit()
        return {"ok": True}

    @app.get("/api/me")
    def me(p: Principal = Depends(principal), db: Session = Depends(db_session)):
        return profile(db, p)

    @app.put("/api/organization")
    def change_organization(body: OrgSettings, p: Principal = Depends(principal), db: Session = Depends(db_session)):
        browser_only(p)
        require_role(p, "admin")
        org = db.get(Organization, p.user.org_id)
        for key, value in body.model_dump().items():
            setattr(org, key, value.strip())
        org.revision += 1
        audit(db, p.user, "organization.updated", org.id)
        db.commit()
        return profile(db, p)["organization"]

    @app.get("/api/users")
    def users(p: Principal = Depends(principal), db: Session = Depends(db_session)):
        browser_only(p)
        require_role(p, "admin")
        return [{"id": u.id, "name": u.name, "email": u.email, "role": u.role,
                 "department": u.department, "active": u.active} for u in db.scalars(
                     select(User).where(User.org_id == p.user.org_id).order_by(User.created))]

    @app.put("/api/users/{user_id}")
    def change_user(user_id: str, body: UserUpdate, p: Principal = Depends(principal), db: Session = Depends(db_session)):
        browser_only(p)
        require_role(p, "admin")
        user = owned(db, User, user_id, p.user)
        if user.id == p.user.id:
            raise HTTPException(409, "Ask another administrator to change your own access")
        for key, value in body.model_dump().items():
            setattr(user, key, value)
        db.execute(delete(Credential).where(Credential.user_id == user.id))
        audit(db, p.user, "membership.updated", user.id)
        db.commit()
        return {"ok": True}

    @app.post("/api/invites", status_code=201)
    def invite(body: Invitation, p: Principal = Depends(principal), db: Session = Depends(db_session)):
        browser_only(p)
        require_role(p, "admin")
        email = IdentityInput.email_valid(body.email)
        token = secrets.token_urlsafe(32)
        db.add(Invite(id=digest(token), org_id=p.user.org_id, email=email,
                      role=body.role, department=body.department, expires=time.time() + 86400))
        audit(db, p.user, "invitation.created")
        db.commit()
        return {"token": token, "url": settings.origin + "/?invite=" + token,
                "expires_in_hours": 24, "delivery": "manual"}

    @app.post("/api/auth/accept-invite", status_code=201)
    def accept(body: AcceptInvite, request: Request, response: Response, db: Session = Depends(db_session)):
        auth_limit(request)
        item = db.get(Invite, digest(body.token))
        if not item or item.used or item.expires < time.time() or item.email != body.email:
            raise HTTPException(400, "Invitation is invalid or expired")
        claimed = db.execute(update(Invite).where(Invite.id == item.id, Invite.used.is_(False)).values(used=True)).rowcount
        if not claimed:
            raise HTTPException(409, "Invitation was already accepted")
        user = User(org_id=item.org_id, name=body.name, email=body.email,
                    password=password_hash(body.password), role=item.role, department=item.department)
        db.add(user)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Unable to create account with this email") from None
        csrf = issue_session(db, user, response, settings)
        audit(db, user, "invitation.accepted")
        db.commit()
        return {"csrf": csrf}

    @app.get("/api/documents")
    def documents(p: Principal = Depends(principal), db: Session = Depends(db_session)):
        require_scope(p, "knowledge:read")
        return [{"id": d.id, "title": d.title, "visibility": d.visibility,
                 "department": d.department, "version": d.version, "created": d.created,
                 "chunks": db.scalar(select(func.count()).select_from(Chunk).where(Chunk.doc_id == d.id))}
                for d in db.scalars(select(Document).where(Document.org_id == p.user.org_id, visible(p.user)).order_by(Document.created.desc()))]

    @app.post("/api/documents", status_code=201)
    def upload(file: UploadFile = File(...), title: str = Form(..., min_length=2, max_length=200),
               visibility: Literal["organization", "department", "admin"] = Form("organization"),
               department: str = Form("General", min_length=1, max_length=60),
               replace_id: str = Form(""), p: Principal = Depends(principal), db: Session = Depends(db_session)):
        browser_only(p)
        require_role(p, "admin")
        content = file.file.read(5 * 1024 * 1024 + 1)
        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(413, "File exceeds 5 MB")
        try:
            parts = extract(file.filename or "", content)
        except Exception:
            raise HTTPException(422, "Could not read file. Use a UTF-8 text/Markdown file or an unencrypted text PDF (maximum 150 pages / 500,000 characters)") from None
        if visibility == "department" and department != p.user.department:
            raise HTTPException(403, "Switch to an administrator in that department to publish restricted content")
        if replace_id:
            doc = doc_access(db, replace_id, p.user)
            db.execute(delete(Chunk).where(Chunk.doc_id == doc.id))
            doc.version += 1
        else:
            doc = Document(org_id=p.user.org_id, title=title, content_hash="")
            db.add(doc)
            db.flush()
        doc.title, doc.visibility, doc.department = title, visibility, department
        doc.content_hash = hashlib.sha256(content).hexdigest()
        doc.created = time.time()
        db.add_all([Chunk(doc_id=doc.id, page=page, text=text) for page, text in parts])
        audit(db, p.user, "document.indexed", doc.id)
        db.commit()
        return {"id": doc.id, "chunks": len(parts), "version": doc.version, "status": "indexed"}

    @app.get("/api/documents/{document_id}")
    def document_detail(document_id: str, p: Principal = Depends(principal), db: Session = Depends(db_session)):
        require_scope(p, "knowledge:read")
        doc = doc_access(db, document_id, p.user)
        return {"id": doc.id, "title": doc.title, "version": doc.version,
                "chunks": [{"id": c.id, "page": c.page, "text": c.text} for c in db.scalars(
                    select(Chunk).where(Chunk.doc_id == doc.id).order_by(Chunk.page, Chunk.id))]}

    @app.delete("/api/documents/{document_id}")
    def delete_document(document_id: str, p: Principal = Depends(principal), db: Session = Depends(db_session)):
        browser_only(p)
        require_role(p, "admin")
        doc = doc_access(db, document_id, p.user)
        audit(db, p.user, "document.deleted", doc.id)
        db.execute(delete(Chunk).where(Chunk.doc_id == doc.id))
        db.delete(doc)
        db.commit()
        return {"ok": True}

    def chat_run(body, p, db):
        require_scope(p, "chat:write")
        require_scope(p, "knowledge:read")
        started = time.perf_counter()
        if body.conversation_id:
            conversation = owned(db, Conversation, body.conversation_id, p.user)
            if conversation.user_id != p.user.id:
                raise HTTPException(404, "Conversation not found")
        else:
            conversation = Conversation(org_id=p.user.org_id, user_id=p.user.id, title=body.question[:80])
            db.add(conversation)
            db.flush()
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        dialect = db.bind.dialect.name
        if dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert
        else:
            from sqlalchemy.dialects.postgresql import insert
        db.execute(insert(DailyQuota).values(user_id=p.user.id, day=day, count=0).on_conflict_do_nothing(index_elements=["user_id", "day"]))
        reserved = db.execute(update(DailyQuota).where(DailyQuota.user_id == p.user.id,
            DailyQuota.day == day, DailyQuota.count < settings.daily_limit).values(count=DailyQuota.count + 1)).rowcount
        if not reserved:
            db.rollback()
            raise HTTPException(429, "Daily request limit reached; resets at 00:00 UTC")
        run = Run(org_id=p.user.org_id, user_id=p.user.id, provider=settings.provider, model=settings.model)
        db.add(run)
        db.flush()
        db.commit()  # durable reservation before potentially slow external inference
        try:
            sources = retrieve(db, p.user, body.question, settings.semantic_model)
            retrieval_ms = round((time.perf_counter() - started) * 1000)
            answer = generate(settings, db.get(Organization, p.user.org_id), body.question, sources)
        except ProviderUnavailable as error:
            run.status = "provider_error"
            run.latency_ms = round((time.perf_counter() - started) * 1000)
            audit(db, p.user, "chat.provider_error", run.id)
            db.commit()
            raise HTTPException(503, str(error)) from None
        citations = [{k: s[k] for k in ("chunk_id", "document_id", "title", "page", "version")} for s in sources]
        # Recheck source authorization/version after inference; account policy can change while it runs.
        db.expire(p.user)
        if not p.user.active or len(safe_citations(db, citations, p.user)) != len(citations):
            run.status = "access_changed"
            db.commit()
            raise HTTPException(409, "Document access changed during this request. Ask again")
        db.add(Message(conversation_id=conversation.id, role="user", content=body.question))
        db.add(Message(conversation_id=conversation.id, role="assistant", content=answer.text, citations=json.dumps(citations)))
        run.status = "answered" if sources else "abstained"
        run.retrieved = len(sources)
        run.latency_ms = round((time.perf_counter() - started) * 1000)
        run.input_tokens, run.output_tokens = answer.input_tokens, answer.output_tokens
        run.stages = json.dumps([{"name": "authorize", "status": "ok"},
            {"name": "retrieve", "ms": retrieval_ms, "chunks": len(sources)},
            {"name": "generate", "provider": settings.provider, "prompt_version": PROMPT_VERSION},
            {"name": "persist", "status": "ok"}])
        audit(db, p.user, "chat." + run.status, run.id)
        db.commit()
        return {"answer": answer.text, "citations": citations, "conversation_id": conversation.id,
                "run_id": run.id, "provider": settings.provider, "latency_ms": run.latency_ms,
                "mode": "extractive" if settings.provider == "extractive" else "generated"}

    @app.post("/api/chat")
    def chat(body: Question, p: Principal = Depends(principal), db: Session = Depends(db_session)):
        return chat_run(body, p, db)

    @app.post("/api/chat/stream")
    def chat_stream(body: Question, p: Principal = Depends(principal), db: Session = Depends(db_session)):
        result = chat_run(body, p, db)
        def events():
            # Delivery streaming after validation; provider token streaming is not claimed.
            yield "event: sources\ndata: " + json.dumps(result["citations"]) + "\n\n"
            for start in range(0, len(result["answer"]), 90):
                yield "event: delta\ndata: " + json.dumps({"text": result["answer"][start:start+90]}) + "\n\n"
            yield "event: done\ndata: " + json.dumps({k: v for k, v in result.items() if k != "answer"}) + "\n\n"
        return StreamingResponse(events(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})

    @app.get("/api/conversations")
    def conversations(p: Principal = Depends(principal), db: Session = Depends(db_session)):
        browser_only(p)
        return [{"id": c.id, "title": c.title, "created": c.created} for c in db.scalars(select(Conversation).where(
            Conversation.org_id == p.user.org_id, Conversation.user_id == p.user.id).order_by(Conversation.created.desc()).limit(100))]

    @app.get("/api/conversations/{conversation_id}")
    def history(conversation_id: str, p: Principal = Depends(principal), db: Session = Depends(db_session)):
        browser_only(p)
        c = owned(db, Conversation, conversation_id, p.user)
        if c.user_id != p.user.id:
            raise HTTPException(404, "Conversation not found")
        messages = []
        for m in db.scalars(select(Message).where(Message.conversation_id == c.id).order_by(Message.created)):
            citations = json.loads(m.citations)
            safe = safe_citations(db, citations, p.user)
            changed = len(safe) != len(citations)
            messages.append({"id": m.id, "role": m.role,
                "content": "This answer is hidden because its sources changed or are no longer accessible. Ask again for current information." if changed else m.content,
                "citations": [] if changed else safe})
        return {"id": c.id, "title": c.title, "messages": messages}

    @app.get("/api/workflows")
    def workflows(p: Principal = Depends(principal), db: Session = Depends(db_session)):
        require_scope(p, "workflows:read")
        return [{"id": w.id, "name": w.name, "description": w.description, "department": w.department}
                for w in db.scalars(select(Workflow).where(Workflow.org_id == p.user.org_id, Workflow.active.is_(True)))]

    @app.post("/api/workflows", status_code=201)
    def add_workflow(body: WorkflowInput, p: Principal = Depends(principal), db: Session = Depends(db_session)):
        browser_only(p)
        require_role(p, "admin")
        w = Workflow(org_id=p.user.org_id, **body.model_dump())
        db.add(w)
        db.flush()
        audit(db, p.user, "workflow.created", w.id)
        db.commit()
        return {"id": w.id}

    @app.post("/api/actions", status_code=201)
    def propose(body: Proposal, p: Principal = Depends(principal), db: Session = Depends(db_session)):
        require_scope(p, "actions:write")
        w = owned(db, Workflow, body.workflow_id, p.user)
        if not w.active:
            raise HTTPException(409, "Workflow is inactive")
        previous = db.scalar(select(Action).where(Action.org_id == p.user.org_id,
            Action.user_id == p.user.id, Action.idempotency_key == body.idempotency_key))
        if previous:
            if any(getattr(previous, k) != getattr(body, k) for k in ("workflow_id", "title", "description", "priority")):
                raise HTTPException(409, "Idempotency key already used for different arguments")
            return action_view(db, previous, p.user)
        action = Action(org_id=p.user.org_id, user_id=p.user.id, expires=time.time() + 7 * 86400, **body.model_dump())
        db.add(action)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Request is already being created; retry with the same key") from None
        audit(db, p.user, "action.proposed", action.id)
        db.commit()
        return action_view(db, action, p.user)

    @app.get("/api/actions")
    def actions(p: Principal = Depends(principal), db: Session = Depends(db_session)):
        require_scope(p, "actions:read")
        rows = db.scalars(select(Action).where(Action.org_id == p.user.org_id).order_by(Action.created.desc()).limit(300))
        return [action_view(db, a, p.user) for a in rows if a.user_id == p.user.id or can_review(db, a, p.user)]

    @app.post("/api/actions/{action_id}/decision")
    def decision(action_id: str, body: Decision, p: Principal = Depends(principal), db: Session = Depends(db_session)):
        browser_only(p)
        action = owned(db, Action, action_id, p.user)
        if not can_review(db, action, p.user):
            raise HTTPException(403, "A separate authorized reviewer must decide this request")
        requester = db.get(User, action.user_id)
        workflow = db.get(Workflow, action.workflow_id)
        if not requester.active or not workflow.active:
            raise HTTPException(409, "Requester or workflow is inactive")
        if action.status != "pending":
            if action.status == ("executed" if body.decision == "approve" else "rejected"):
                return action_view(db, action, p.user)
            raise HTTPException(409, "This request already has a decision")
        if action.expires <= time.time():
            raise HTTPException(409, "Approval request has expired")
        claimed = db.execute(update(Action).where(Action.id == action.id, Action.status == "pending").values(
            status="executed" if body.decision == "approve" else "rejected", reviewer_id=p.user.id, reason=body.reason)).rowcount
        if not claimed:
            raise HTTPException(409, "Another reviewer has decided this request")
        if body.decision == "approve":
            # Local action and decision are one database transaction; no external side effects.
            db.add(Ticket(org_id=p.user.org_id, action_id=action.id))
        audit(db, p.user, "action." + body.decision, action.id)
        db.commit()
        db.refresh(action)
        return action_view(db, action, p.user)

    @app.post("/api/actions/{action_id}/resolve")
    def resolve(action_id: str, p: Principal = Depends(principal), db: Session = Depends(db_session)):
        browser_only(p)
        action = owned(db, Action, action_id, p.user)
        if not can_review(db, action, p.user):
            raise HTTPException(403, "Only the handling reviewer can resolve this ticket")
        ticket = db.scalar(select(Ticket).where(Ticket.action_id == action.id))
        if not ticket:
            raise HTTPException(409, "There is no executed ticket to resolve")
        ticket.status = "resolved"
        audit(db, p.user, "ticket.resolved", ticket.id)
        db.commit()
        return {"ok": True}

    @app.get("/api/tokens")
    def tokens(p: Principal = Depends(principal), db: Session = Depends(db_session)):
        browser_only(p)
        return [{"id": c.id, "label": c.label, "scopes": json.loads(c.scopes), "expires": c.expires}
            for c in db.scalars(select(Credential).where(Credential.user_id == p.user.id, Credential.kind == "api", Credential.expires > time.time()))]

    @app.post("/api/tokens", status_code=201)
    def create_token(body: TokenInput, p: Principal = Depends(principal), db: Session = Depends(db_session)):
        browser_only(p)
        token = "av_" + secrets.token_urlsafe(32)
        db.add(Credential(id=digest(token), user_id=p.user.id, kind="api", label=body.label,
            scopes=json.dumps(body.scopes), expires=time.time() + body.days * 86400))
        audit(db, p.user, "token.created")
        db.commit()
        return {"token": token, "display_once": True}

    @app.delete("/api/tokens/{token_id}")
    def revoke(token_id: str, p: Principal = Depends(principal), db: Session = Depends(db_session)):
        browser_only(p)
        c = db.get(Credential, token_id)
        if not c or c.user_id != p.user.id or c.kind != "api":
            raise HTTPException(404, "Token not found")
        db.delete(c)
        audit(db, p.user, "token.revoked")
        db.commit()
        return {"ok": True}

    @app.get("/api/automations")
    def automations(p: Principal = Depends(principal), db: Session = Depends(db_session)):
        browser_only(p)
        require_role(p, "admin")
        return {"schedules": [{"id": a.id, "name": a.name, "kind": a.kind,
                  "interval_hours": a.interval_hours, "next_run": a.next_run, "enabled": a.enabled}
                  for a in db.scalars(select(Automation).where(Automation.org_id == p.user.org_id))],
                "runs": [{"id": r.id, "summary": r.summary, "created": r.created}
                  for r in db.scalars(select(AutomationRun).where(AutomationRun.org_id == p.user.org_id).order_by(AutomationRun.created.desc()).limit(30))],
                "tasks": [{"id": t.id, "title": t.title, "source_type": t.source_type, "source_id": t.source_id,
                           "status": t.status, "created": t.created}
                  for t in db.scalars(select(Task).where(Task.org_id == p.user.org_id).order_by(Task.created.desc()).limit(100))]}

    @app.post("/api/automations", status_code=201)
    def schedule(body: AutomationInput, p: Principal = Depends(principal), db: Session = Depends(db_session)):
        browser_only(p)
        require_role(p, "admin")
        item = Automation(org_id=p.user.org_id, next_run=time.time(), **body.model_dump())
        db.add(item)
        db.flush()
        audit(db, p.user, "automation.created", item.id)
        db.commit()
        return {"id": item.id}

    @app.post("/api/automations/run")
    def execute_schedules(p: Principal = Depends(principal)):
        browser_only(p)
        require_role(p, "admin")
        return {"runs": run_due(factory, p.user.org_id)}

    @app.post("/api/automations/{automation_id}/toggle")
    def toggle(automation_id: str, p: Principal = Depends(principal), db: Session = Depends(db_session)):
        browser_only(p)
        require_role(p, "admin")
        item = owned(db, Automation, automation_id, p.user)
        item.enabled = not item.enabled
        audit(db, p.user, "automation.toggled", item.id)
        db.commit()
        return {"enabled": item.enabled}

    @app.post("/api/tasks/{task_id}/complete")
    def complete_task(task_id: str, p: Principal = Depends(principal), db: Session = Depends(db_session)):
        browser_only(p)
        require_role(p, "admin")
        item = owned(db, Task, task_id, p.user)
        item.status = "completed"
        audit(db, p.user, "task.completed", item.id)
        db.commit()
        return {"ok": True}

    @app.get("/api/overview")
    def overview(p: Principal = Depends(principal), db: Session = Depends(db_session)):
        browser_only(p)
        user = p.user
        runs = select(Run).where(Run.org_id == user.org_id)
        if user.role != "admin":
            runs = runs.where(Run.user_id == user.id)
        recent = list(db.scalars(runs.order_by(Run.created.desc()).limit(100)))
        count = db.scalar(select(func.count()).select_from(Document).where(Document.org_id == user.org_id, visible(user)))
        pending = [a for a in db.scalars(select(Action).where(Action.org_id == user.org_id, Action.status == "pending", Action.expires > time.time()))
                   if a.user_id == user.id or can_review(db, a, user)]
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        used = db.scalar(select(DailyQuota.count).where(DailyQuota.user_id == user.id, DailyQuota.day == day)) or 0
        return {"documents": count, "pending_actions": len(pending), "requests_today": used,
                "daily_limit": settings.daily_limit, "recent_runs": [{"id": r.id, "status": r.status,
                "provider": r.provider, "model": r.model, "latency_ms": r.latency_ms,
                "input_tokens": r.input_tokens, "output_tokens": r.output_tokens,
                "retrieved": r.retrieved, "created": r.created, "stages": json.loads(r.stages)} for r in recent]}

    @app.get("/api/audit")
    def audits(p: Principal = Depends(principal), db: Session = Depends(db_session)):
        browser_only(p)
        require_role(p, "admin")
        return [{"id": a.id, "event": a.event, "object_id": a.object_id, "actor_id": a.user_id, "created": a.created}
                for a in db.scalars(select(Audit).where(Audit.org_id == p.user.org_id).order_by(Audit.created.desc()).limit(200))]

    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(static / "index.html")

    @app.get("/docs", include_in_schema=False)
    def api_reference():
        return FileResponse(static / "docs.html")

    return app
