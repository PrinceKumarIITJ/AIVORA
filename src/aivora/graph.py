"""Bounded knowledge graph. Side-effecting workflows use the separate action ledger."""

import re
import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context

from .providers import Generation
from .retrieval import retrieve


class KnowledgeState(TypedDict, total=False):
    question: str
    sources: list[dict]
    generation: Generation
    retrieval_ms: int
    route: str


def answer_question(db, user, organization, settings, question, generator):
    started = time.perf_counter()

    def search(state):
        sources = retrieve(db, user, state["question"], settings.semantic_model)
        return {
            "sources": sources,
            "retrieval_ms": round((time.perf_counter() - started) * 1000),
        }

    def answer(state):
        return {
            "generation": generator(settings, organization, state["question"], state["sources"]),
            "route": "grounded",
        }

    def abstain(state):
        return {
            "generation": Generation(
                "I couldn't find enough evidence in the documents you can access. Try a more specific question or ask your administrator to add the relevant document."
            ),
            "route": "abstain",
        }

    def verify(state):
        generated = state["generation"]
        if state["sources"]:
            citations = {int(x) for x in re.findall(r"\[(\d+)\]", generated.text)}
            if not citations or not citations.issubset(set(range(1, len(state["sources"]) + 1))):
                return {
                    "generation": Generation(
                        "The answer did not pass citation validation. Please inspect the retrieved source passages and try rephrasing your question.",
                        generated.input_tokens,
                        generated.output_tokens,
                    ),
                    "route": "citation_rejected",
                }
        return {}

    builder = StateGraph(KnowledgeState)
    builder.add_node("retrieve", search)
    builder.add_node("answer", answer)
    builder.add_node("abstain", abstain)
    builder.add_node("verify", verify)
    builder.add_edge(START, "retrieve")
    builder.add_conditional_edges(
        "retrieve", lambda state: "answer" if state["sources"] else "abstain"
    )
    builder.add_edge("answer", "verify")
    builder.add_edge("abstain", "verify")
    builder.add_edge("verify", END)
    # No ambient LangSmith export: document contents must not leave via inherited trace settings.
    with tracing_context(enabled=False):
        return builder.compile().invoke({"question": question}, config={"recursion_limit": 6})
