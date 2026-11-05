"""ACL-first BM25 retrieval with optional genuine multilingual semantic reranking."""
import hashlib
import math
import re
from collections import Counter
from functools import lru_cache
from io import BytesIO

from pypdf import PdfReader
from sqlalchemy import or_, select
from .db import Chunk, Document


STOP = set("a an the is are was were to of for in on and or do does how what my our your can i we me tell about please policy".split())


def terms(text):
    return [t for t in re.findall(r"[^\W_]+", text.lower(), re.UNICODE) if len(t) > 1 and t not in STOP]


def visible(user):
    # Administrators manage document metadata, but do not bypass department content ACLs.
    clauses = [Document.visibility == "organization",
               (Document.visibility == "department") & (Document.department == user.department)]
    if user.role == "admin":
        clauses.append(Document.visibility == "admin")
    return or_(*clauses)


def extract(filename, content):
    if filename.lower().endswith(".pdf"):
        reader = PdfReader(BytesIO(content), strict=True)
        if reader.is_encrypted or len(reader.pages) > 150:
            raise ValueError("Use an unencrypted PDF with at most 150 pages")
        pages = [(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]
    elif filename.lower().endswith((".md", ".txt")):
        pages = [(1, content.decode("utf-8-sig"))]
    else:
        raise ValueError("Supported files: PDF, Markdown and UTF-8 text")
    if sum(len(text) for _, text in pages) > 500_000:
        raise ValueError("Extracted text exceeds 500,000 characters")
    chunks = []
    for page, text in pages:
        text = text.replace("\x00", "").strip()
        for start in range(0, len(text), 1050):
            part = text[start:start + 1250].strip()
            if part:
                chunks.append((page, part))
    if not chunks:
        raise ValueError("No searchable text found. OCR is not included; use a text-based PDF")
    return chunks


@lru_cache(maxsize=1)
def encoder(model):
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model)


def retrieve(db, user, question, semantic_model="", limit=5):
    rows = db.execute(select(Chunk, Document).join(Document).where(
        Document.org_id == user.org_id, visible(user))).all()
    if not rows:
        return []
    query = Counter(terms(question))
    bags = [Counter(terms(chunk.text + " " + doc.title)) for chunk, doc in rows]
    avg = sum(sum(b.values()) for b in bags) / max(len(bags), 1) or 1
    frequencies = Counter(term for bag in bags for term in bag)
    scores = []
    for bag in bags:
        length = sum(bag.values())
        score = 0
        for term in query:
            tf = bag[term]
            idf = math.log(1 + (len(bags) - frequencies[term] + .5) / (frequencies[term] + .5))
            score += idf * (tf * 2.2) / (tf + 1.2 * (.25 + .75 * length / avg))
        scores.append(score)
    if semantic_model:
        # Optional local model only sees rows already filtered by ACLs.
        model = encoder(semantic_model)
        vectors = model.encode([question] + [chunk.text for chunk, _ in rows], normalize_embeddings=True)
        semantic = vectors[1:] @ vectors[0]
        lexical_order = sorted(range(len(rows)), key=lambda i: scores[i], reverse=True)
        semantic_order = sorted(range(len(rows)), key=lambda i: float(semantic[i]), reverse=True)
        ranks = {i: rank for rank, i in enumerate(lexical_order)}
        sem_ranks = {i: rank for rank, i in enumerate(semantic_order)}
        ranked = sorted(range(len(rows)), key=lambda i: 1 / (60 + ranks[i]) + 1 / (60 + sem_ranks[i]), reverse=True)
        ranked = [i for i in ranked if scores[i] > 0 or float(semantic[i]) > .45]
    else:
        ranked = sorted((i for i, score in enumerate(scores) if score > 0), key=lambda i: scores[i], reverse=True)
    return [{"chunk_id": rows[i][0].id, "document_id": rows[i][1].id,
             "title": rows[i][1].title, "page": rows[i][0].page,
             "version": rows[i][1].version, "text": rows[i][0].text,
             "score": round(scores[i], 4)} for i in ranked[:limit]]
