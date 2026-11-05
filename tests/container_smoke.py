"""Verify a separately launched local container with synthetic data only."""
import secrets

import httpx


def main():
    with httpx.Client(base_url="http://127.0.0.1:8090", timeout=60, trust_env=False) as c:
        assert c.get("/api/health").json()["status"] == "ok"
        assert c.get("/api/me").status_code == 401
        signup = c.post("/api/auth/signup", json={"name": "Container Tester", "organization": "Synthetic Container Test",
            "email": secrets.token_hex(8) + "@container.example", "password": secrets.token_urlsafe(20)})
        assert signup.status_code == 201, signup.text
        c.headers["x-csrf-token"] = signup.json()["csrf"]
        assert c.post("/api/documents", data={"title": "Container policy"}, files={
            "file": ("policy.md", b"Annual leave allowance is 21 days.", "text/markdown")}).status_code == 201
        answer = c.post("/api/chat", json={"question": "Annual leave allowance"}).json()
        assert "21 days" in answer["answer"] and answer["citations"]
        assert c.post("/api/automations", json={"name": "Container review", "kind": "document_review", "interval_hours": 24}).status_code == 201
        assert c.post("/api/automations/run").status_code == 200
        assert c.get("/api/audit").json()
    print("PASS: container HTTP health, authentication, document ingestion, LangGraph answer, citations, automation and audit persistence")


if __name__ == "__main__":
    main()
