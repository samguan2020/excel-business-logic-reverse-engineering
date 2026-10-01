---
title: Finance Excel Reverse Engineering
description: An experimental Excel documentation pipeline using open-source substitutes for selected Microsoft IQ roles, with a Microsoft Teams SDK bot.
---

## Overview

Finance Excel Reverse Engineering turns spreadsheet formulas and dependencies
into business-readable documentation and draft migration assets. It combines a
Python analysis pipeline with an optional TypeScript bot built using the
Microsoft Teams SDK.

The project explores how to implement an IQ-inspired workflow without calling
Microsoft IQ services. Local retrieval, web search, collaboration metadata, and
orchestration are implemented with open-source libraries. The backend can run
with local model inference through Ollama or an optional hosted model.

This is an independent experimental prototype, not an official Microsoft
implementation, a financial calculation engine, or a production migration tool.
Generated explanations, requirements, and code require human review.

## Showcase

Read the case study: **[samguan2020.github.io/finance-excel-reverse-engineering](https://samguan2020.github.io/finance-excel-reverse-engineering/)**

The page source is [`docs/index.html`](docs/index.html), served by GitHub Pages.

## Microsoft IQ and the replacement architecture

[Microsoft IQ](https://learn.microsoft.com/en-us/microsoft-iq/) describes an
enterprise intelligence layer with four interconnected capabilities:

* Work IQ provides context about people, collaboration, and workflows.
* Fabric IQ provides context about business entities, data, relationships, and rules.
* Foundry IQ provides institutional knowledge from authoritative documents and
  reusable knowledge bases.
* Web IQ provides fresh information from across the web.

Those are broader managed capabilities, not a single SDK installed by this
project. The table below distinguishes their roles from the smaller replacements
actually implemented here.

| Microsoft capability or application layer | Implementation in this project | Boundary of the replacement |
|------------------------------------------|--------------------------------|-----------------------------|
| Foundry IQ: knowledge retrieval | ChromaDB with Sentence Transformers embeddings; a seeded finance glossary and workbook comments | Local similarity search, not managed enterprise retrieval, source permissions, Purview enforcement, or guaranteed citations |
| Web IQ: web grounding | `ddgs` search when local retrieval appears weak | External search snippets, not Microsoft's Web IQ service, search infrastructure, reliability commitments, or full citation handling |
| Work IQ: collaboration context | OOXML author metadata, cell comments, and optional local `git log` | File-local signals only; no Microsoft 365 mail, meeting, chat, organization, or permission-aware retrieval |
| Fabric IQ: business data and semantics | `openpyxl` extraction, `formulas` reference parsing, and a NetworkX cell dependency graph | Workbook-scoped structure, not a Fabric IQ implementation, OneLake integration, ontology, or semantic model |
| Agent orchestration | LangGraph state graph | A fixed, inspectable sequence rather than a general enterprise agent platform |
| Model inference | Ollama by default; optional OpenAI-compatible or Microsoft Foundry endpoint | Model choice and model licensing are separate from the open-source application libraries |
| API and Teams channel | FastAPI plus the Microsoft Teams SDK for JavaScript/TypeScript | An optional Teams front end, not a replacement for the Teams service |

The application-level workflow is implemented without an IQ service dependency.
That does not mean feature, security, governance, or performance parity with
Microsoft IQ. The pipeline does not call Work IQ, Foundry IQ, Fabric IQ, or Web IQ
APIs. Choosing a hosted Foundry model for inference does not change that distinction.

## What the pipeline produces

Given an `.xlsx` workbook, the pipeline produces one Markdown report containing:

* Workbook structure and formula/input/output counts
* Available author, comment, and local history context
* Cell dependency analysis
* Per-sheet explanations of formulas and inferred business rules
* Draft functional requirements and migration recommendations
* Reusable prompt templates and starter Python scaffolding

The sample generator creates fictional finance data across `Inputs`, `Forecast`,
and `Summary` worksheets. No customer workbook or historical report is required.
The API also accepts `.xlsm` files; the pipeline does not execute VBA macros.

## Processing flow

```text
Workbook from CLI or Teams
          |
          v
Extract cells, formulas, references, and dependency graph
          |
          v
Gather local glossary, workbook comments, and collaboration metadata
          |
          v
For each formula-bearing sheet:
  retrieve local context -> weak retrieval? -> query the web
          |
          v
Generate sheet documentation with the configured model
          |
          v
Build dependency narrative and draft migration assets
          |
          v
Compile Markdown report
          |
          +--> CLI output file
          +--> Teams Adaptive Card and consent-based report upload
```

The implementation lives in [the LangGraph pipeline](src/agent.py).
Reference extraction uses the `formulas` parser and expands supported ranges;
it is not the older regex-only approach. The graph records dependencies, not
evaluated financial results.

## Open-source components and remaining service dependencies

The core application uses `openpyxl`, `formulas`, NetworkX, ChromaDB,
Sentence Transformers, LangGraph, FastAPI, Uvicorn, and `ddgs`.
Their individual licenses and transitive dependencies still apply.

Ollama provides local inference, but the selected model has its own license.
The default `llama3.1` model is distributed under a custom model license; using
an open-source runtime does not make every model OSI-licensed open source.
Choose and review model weights appropriate to your intended use.

Local inference is not the same as an offline end-to-end pipeline:

* Web grounding can send formula fragments to external search providers.
* The embedding model and local language model must be downloaded before use.
* Hosted inference sends prompts and retrieved context to the configured endpoint.
* The optional bot uses the Microsoft Teams service.

There is currently no configuration switch that disables web grounding.
Use synthetic, non-sensitive workbooks unless you have reviewed and adapted the
data flow for your requirements.

## Local setup

Use Python 3.11 and an existing Python package-management environment.
The dependency list is in [requirements.txt](requirements.txt).
The following PowerShell commands use a project-local virtual environment:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

For local inference, install [Ollama](https://ollama.com/) and download the
configured model:

```powershell
ollama pull llama3.1
```

Ensure the Ollama service is running at `http://localhost:11434`.
The default settings in [.env.example](.env.example) are:

```dotenv
LLM_BACKEND=ollama
LLM_MODEL=llama3.1
```

Keep real credentials in your local `.env`, never in committed examples or reports.

### Model backend options

| Backend | Configuration | Behavior |
|---------|---------------|----------|
| `ollama` | `LLM_MODEL` | Calls the local OpenAI-compatible API at `http://localhost:11434/v1` |
| `openai` | `LLM_MODEL`, `OPENAI_API_KEY`, optional `OPENAI_BASE_URL` | Calls an OpenAI-compatible endpoint; without a base URL it uses the OpenAI endpoint |
| `azure_ai_foundry` | `AZURE_AI_FOUNDRY_ENDPOINT`, `AZURE_AI_FOUNDRY_DEPLOYMENT` | Uses `AnthropicFoundry` and `DefaultAzureCredential` for an Anthropic Messages-compatible Foundry deployment |

The Foundry adapter is not a universal adapter for every Foundry model family.
It requires an existing deployment, suitable identity permissions, and the correct
endpoint. Hosted services can incur charges. No cloud resources are provisioned
by this project.

### Generate and analyze a sample

Run from the project root:

```powershell
.\.venv\Scripts\python.exe sample\make_sample.py
.\.venv\Scripts\python.exe main.py sample\finance_sample.xlsx --out report.md
```

The generator overwrites the synthetic sample workbook. Analysis invokes the
configured model, can perform web searches, and can take several minutes.
The report is written to the `--out` path; the persistent local knowledge store
is created under `.chroma_kb`.

### Run the existing offline tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The tests cover formula-reference extraction and dependency graph construction.
They do not validate live model output, external web search, or Teams delivery.

## FastAPI analysis service

Start the API locally:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.server:app --host 127.0.0.1 --port 8000
```

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Process health check |
| `POST /analyze` | Upload multipart field `file`; returns HTTP 202 with a job ID |
| `GET /analyze/{job_id}` | Poll for `running`, `done`, or `error`; successful results contain the report and summary |

The API runs analysis in a background executor so a long sequence of model calls
does not require a single long-lived HTTP request. Jobs are held in process
memory, with age-based pruning triggered by new submissions. Restarting the
process loses job state; this is not a durable queue.

The service has no built-in API authentication. Keep it local or behind a trusted,
authenticated boundary. The [Dockerfile](Dockerfile) packages the backend, but
does not make it production-ready or provide deployment credentials.

## Teams bot and SDK licensing

The optional [Teams bot](teams-bot/README.md) is an implemented TypeScript front
end, not a bot generated dynamically by the model. It uses
`@microsoft/teams.apps` and `@microsoft/teams.cards`, pinned to version `2.0.5`.
It is the server-side Teams SDK, not the browser-oriented TeamsJS client library.

The [Microsoft Teams SDK for JavaScript repository](https://github.com/microsoft/teams.ts)
is open source under the [MIT license for SDK v2.0.5](https://github.com/microsoft/teams.ts/blob/v2.0.5/LICENSE).
The SDK license does not make the Microsoft Teams service open source or remove
tenant, account, application registration, or deployment requirements.

The bot handles the interaction around the analysis pipeline:

1. Receive a workbook attachment in a personal Teams chat.
2. Download it and submit it to the analysis API.
3. Poll the asynchronous job until completion or failure.
4. Send an Adaptive Card with the workbook summary.
5. Request file-upload consent before delivering the full Markdown report.

Use the [bot setup guide](teams-bot/README.md) for local development, configuration,
and real Teams registration. The [app manifest](teams-bot/appPackage/manifest.json)
is a template: replace placeholder registration IDs and public URLs with your own
before packaging or sideloading. No deployed app identity or ready-to-install app
archive is included.

The Python CLI remains usable without the Teams bot or a Microsoft 365 tenant.

## Limitations and data handling

* Formula parsing is not complete Excel execution. Complex formulas, external
  references, named ranges, dynamic behavior, macros, and unsupported constructs
  need additional validation. A dependency graph is not proof of computational
  equivalence.
* Documentation uses at most 80 formulas per sheet. Web queries use fragments
  from at most the first three formulas when retrieval is weak. Large workbooks
  can be only partially represented in generated explanations.
* The default Chroma collection is shared across runs. Workbook comments can
  persist and be reused or overwritten by later workbooks. There is no per-user
  isolation, tenant boundary, or enterprise document-permission enforcement.
* `allowed_sources` is a metadata filter, not an authorization mechanism.
  The current pipeline does not pass a permission-specific allow-list.
* Search can fail or return unsuitable material. Although the search helper
  returns URLs, the current generation prompt uses titles and snippets, so
  source-linked report citations are not guaranteed.
* Workbook metadata and comments can identify people; reports and caches can
  retain that information. This project does not anonymize arbitrary uploads.
* The API job store and bot report cache are in memory. Durable storage, upload
  controls, concurrency management, authentication, and operational monitoring
  need further work before production use.
* Model-generated requirements and starter code are drafts. Review and test
  calculations before relying on them for financial decisions or executing
  generated code.

## Repository guide

| Location | Purpose |
|----------|---------|
| [main.py](main.py) | Command-line entry point |
| [src/excel_parser.py](src/excel_parser.py) | Workbook extraction and dependency graph |
| [src/knowledge_base.py](src/knowledge_base.py) | ChromaDB retrieval and finance glossary |
| [src/web_grounding.py](src/web_grounding.py) | External search and retrieval-strength heuristic |
| [src/work_context.py](src/work_context.py) | Workbook and local Git collaboration signals |
| [src/llm_client.py](src/llm_client.py) | Local and hosted model adapters |
| [src/agent.py](src/agent.py) | LangGraph workflow and report assembly |
| [api/server.py](api/server.py) | Asynchronous HTTP interface |
| [sample/make_sample.py](sample/make_sample.py) | Fictional workbook generator |
| [tests/test_excel_parser.py](tests/test_excel_parser.py) | Offline parser regression tests |
| [teams-bot](teams-bot/) | Teams SDK application, manifest template, and bot guide |

Credentials, caches, environments, generated reports, logs, and application
archives are not part of the source distribution. The included sample is
synthetically generated. Dependency licenses do not establish a license for this
project; no repository-wide license has been selected.

## References

* [Microsoft IQ overview](https://learn.microsoft.com/en-us/microsoft-iq/)
* [Foundry IQ concepts](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/what-is-foundry-iq)
* [Work IQ overview](https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/work-iq/)
* [Fabric IQ overview](https://learn.microsoft.com/en-us/fabric/iq/overview)
* [Web IQ documentation](https://aka.ms/WebIQLearn)
* [Microsoft Teams SDK source](https://github.com/microsoft/teams.ts)

Documentation prepared with AI assistance and checked against the implementation.
Public release and licensing decisions remain subject to the applicable review.
