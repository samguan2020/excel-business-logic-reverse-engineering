"""
agent.py
---------
LangGraph-orchestrated finance workbook documentation pipeline using
open-source components for selected Microsoft IQ-inspired roles.
These are scoped substitutes, not implementations of Microsoft IQ:

    excel_parser   -> raw extraction + dependency graph
    knowledge_base -> local RAG over a finance glossary and workbook comments
    work_context   -> local author/annotation/git signal
    web_grounding  -> web lookup when local retrieval is weak
    llm_client     -> pluggable LLM (Ollama by default, OpenAI-compatible optional)

Flow:
  extract -> gather_context -> [retrieve KB -> weak? -> web_ground] -> per-sheet
  documentation -> dependency narrative -> migration assets -> compile report
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, TypedDict

from langgraph.graph import END, StateGraph

from . import llm_client, web_grounding
from .excel_parser import WorkbookModel, parse_workbook, summarize as summarize_workbook
from .knowledge_base import KnowledgeBase, seed_glossary
from .work_context import build_work_context, summarize as summarize_context


class AgentState(TypedDict, total=False):
    path: str
    model: WorkbookModel
    kb: KnowledgeBase
    work_ctx: Any
    sheet_docs: Dict[str, str]
    dependency_narrative: str
    functional_requirements: str
    migration_recommendations: str
    prompt_templates: str
    starter_code: str
    final_report: str


SYSTEM_DOC_WRITER = (
    "You are a senior financial-systems analyst reverse-engineering an Excel "
    "workbook for migration to an agentic AI system. Be precise, cite cell "
    "references, and flag anything ambiguous rather than guessing."
)


def node_extract(state: AgentState) -> AgentState:
    model = parse_workbook(state["path"])
    return {"model": model}


def node_gather_context(state: AgentState) -> AgentState:
    kb = KnowledgeBase(persist_dir=".chroma_kb")
    seed_glossary(kb)
    model = state["model"]

    # Ingest this workbook's own comments as first-class knowledge
    # (Foundry-IQ "knowledge source": excel-workbook-comments).
    for node_id, cell in model.cells.items():
        if cell.comment:
            kb.ingest(f"comment-{node_id}", f"{node_id}: {cell.comment}", source="excel-workbook-comments")

    work_ctx = build_work_context(model)
    return {"kb": kb, "work_ctx": work_ctx}


def _formulas_for_sheet(model: WorkbookModel, sheet: str) -> List[str]:
    return [
        f"{cell.coord}: {cell.formula}"
        for node_id, cell in model.cells.items()
        if cell.sheet == sheet and cell.formula
    ]


def node_document_sheets(state: AgentState) -> AgentState:
    model = state["model"]
    kb: KnowledgeBase = state["kb"]
    sheet_docs: Dict[str, str] = {}

    for sheet in model.sheets:
        formulas = _formulas_for_sheet(model, sheet)
        if not formulas:
            continue

        # Foundry-IQ-style retrieval before generation.
        kb_hits = kb.retrieve(f"business meaning of formulas in {sheet}", top_k=3)

        # Web-IQ-style grounding only when local retrieval is weak.
        grounding_notes = []
        if web_grounding.should_ground(sheet, kb_hits):
            for hit_query in {f.split(":", 1)[1].strip()[:60] for f in formulas[:3]}:
                grounding_notes.extend(web_grounding.web_ground(f"Excel formula meaning {hit_query}", max_results=1))

        context_block = "\n".join(f"- {h['text']}" for h in kb_hits)
        grounding_block = "\n".join(f"- {g.get('title')}: {g.get('snippet')}" for g in grounding_notes)

        user_prompt = (
            f"Sheet: {sheet}\n\nFormulas:\n" + "\n".join(formulas[:80]) +
            f"\n\nRelevant internal knowledge (Foundry-IQ equivalent):\n{context_block or 'none'}"
            f"\n\nWeb grounding notes (Web-IQ equivalent, use only if helpful):\n{grounding_block or 'none'}"
            "\n\nWrite a business-readable summary of what this sheet computes: "
            "inputs, outputs, calculation logic, and any business rules you can infer."
        )
        sheet_docs[sheet] = llm_client.chat(SYSTEM_DOC_WRITER, user_prompt)

    return {"sheet_docs": sheet_docs}


def node_dependency_narrative(state: AgentState) -> AgentState:
    model = state["model"]
    graph = model.graph
    outputs = [n for n in graph.nodes if graph.out_degree(n) == 0 and model.cells.get(n) and model.cells[n].formula]
    lines = [f"Dependency graph: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges."]
    for out in outputs[:15]:
        try:
            ancestors = list(nx_ancestors_safe(graph, out))
        except Exception:
            ancestors = []
        lines.append(f"- {out} depends on {len(ancestors)} upstream cell(s).")
    return {"dependency_narrative": "\n".join(lines)}


def nx_ancestors_safe(graph, node):
    import networkx as nx

    return nx.ancestors(graph, node)


def node_migration_assets(state: AgentState) -> AgentState:
    model = state["model"]
    sheet_docs = state.get("sheet_docs", {})
    combined_docs = "\n\n".join(f"## {s}\n{d}" for s, d in sheet_docs.items())

    functional_requirements = llm_client.chat(
        SYSTEM_DOC_WRITER,
        f"Based on this reconstructed business logic:\n{combined_docs}\n\n"
        "Write a numbered list of functional requirements suitable for a migration backlog.",
    )
    migration_recommendations = llm_client.chat(
        SYSTEM_DOC_WRITER,
        f"Based on this business logic:\n{combined_docs}\n\n"
        "Recommend a target architecture and migration approach to move this to a "
        "cloud-native agentic workflow (call out risk areas and phased steps).",
    )
    prompt_templates = llm_client.chat(
        SYSTEM_DOC_WRITER,
        f"Based on this business logic:\n{combined_docs}\n\n"
        "Draft 2-3 reusable LLM prompt templates an agent could use at runtime to "
        "replicate this workbook's calculations, with clear input/output placeholders.",
    )
    starter_code = llm_client.chat(
        "You are a senior Python engineer.",
        f"Based on this business logic:\n{combined_docs}\n\n"
        "Generate starter Python scaffolding (functions + docstrings, no execution) "
        "that implements the described calculations as testable, pure functions.",
    )
    return {
        "functional_requirements": functional_requirements,
        "migration_recommendations": migration_recommendations,
        "prompt_templates": prompt_templates,
        "starter_code": starter_code,
    }


def node_compile_report(state: AgentState) -> AgentState:
    model = state["model"]
    parts = [
        "# Finance Excel Reverse Engineering - Generated Report",
        "## Workbook Summary",
        summarize_workbook(model),
        "## Collaboration Context (Work-IQ equivalent)",
        summarize_context(state["work_ctx"]),
        "## Dependency Analysis",
        state.get("dependency_narrative", ""),
        "## Per-Sheet Business Logic Documentation",
        "\n\n".join(f"### {s}\n{d}" for s, d in state.get("sheet_docs", {}).items()),
        "## Functional Requirements",
        state.get("functional_requirements", ""),
        "## Migration Recommendations",
        state.get("migration_recommendations", ""),
        "## Prompt Templates",
        state.get("prompt_templates", ""),
        "## Starter Implementation Scaffolding",
        "```python\n" + state.get("starter_code", "") + "\n```",
    ]
    return {"final_report": "\n\n".join(parts)}


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("extract", node_extract)
    graph.add_node("gather_context", node_gather_context)
    graph.add_node("document_sheets", node_document_sheets)
    graph.add_node("dependency_narrative", node_dependency_narrative)
    graph.add_node("migration_assets", node_migration_assets)
    graph.add_node("compile_report", node_compile_report)

    graph.set_entry_point("extract")
    graph.add_edge("extract", "gather_context")
    graph.add_edge("gather_context", "document_sheets")
    graph.add_edge("document_sheets", "dependency_narrative")
    graph.add_edge("dependency_narrative", "migration_assets")
    graph.add_edge("migration_assets", "compile_report")
    graph.add_edge("compile_report", END)
    return graph.compile()


def run(path: str) -> str:
    app = build_graph()
    result = app.invoke({"path": path})
    return result["final_report"]
