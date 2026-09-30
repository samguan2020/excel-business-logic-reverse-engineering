"""
llm_client.py
--------------
Pluggable LLM backend for local inference (Ollama), against any
OpenAI-compatible endpoint (Azure OpenAI, OpenAI, vLLM, etc.), or against a
model deployed on Azure AI Foundry via Entra ID auth (no API key).
Local inference does not disable the pipeline's external web search.

Set via environment variables (see .env.example):
  LLM_BACKEND=ollama|openai|azure_ai_foundry
  LLM_MODEL=llama3.1|gpt-4o-mini|...
  OPENAI_API_KEY / OPENAI_BASE_URL          (only for LLM_BACKEND=openai)
  AZURE_AI_FOUNDRY_ENDPOINT / AZURE_AI_FOUNDRY_DEPLOYMENT
                                            (only for LLM_BACKEND=azure_ai_foundry)
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# Cached across calls: token acquisition (managed identity/az login) is slow,
# and get_bearer_token_provider() already handles caching/refresh internally.
_foundry_token_provider = None


def _get_foundry_token_provider():
    global _foundry_token_provider
    if _foundry_token_provider is None:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider

        _foundry_token_provider = get_bearer_token_provider(
            DefaultAzureCredential(), "https://ai.azure.com/.default"
        )
    return _foundry_token_provider


def get_client_and_model():
    backend = os.getenv("LLM_BACKEND", "ollama").lower()
    if backend == "ollama":
        # Ollama exposes an OpenAI-compatible API at :11434/v1 out of the box.
        client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
        model = os.getenv("LLM_MODEL", "llama3.1")
    else:
        # Anthropic's OpenAI-SDK-compatible endpoint requires an extra header
        # when the key is an "identity-linked" API key (workspace-scoped).
        default_headers = {}
        workspace_id = os.getenv("ANTHROPIC_WORKSPACE_ID")
        if workspace_id:
            default_headers["anthropic-workspace-id"] = workspace_id

        client = OpenAI(
            base_url=os.getenv("OPENAI_BASE_URL"),  # None -> default OpenAI endpoint
            api_key=os.getenv("OPENAI_API_KEY"),
            default_headers=default_headers or None,
        )
        model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    return client, model


def _chat_azure_ai_foundry(system: str, user: str, temperature: float) -> str:
    # Claude (or other Anthropic) models deployed on Azure AI Foundry, called
    # via the native Anthropic Messages API + Entra ID (no API key needed).
    import sys
    import time

    from anthropic import AnthropicFoundry

    endpoint = os.environ["AZURE_AI_FOUNDRY_ENDPOINT"]
    deployment = os.getenv("AZURE_AI_FOUNDRY_DEPLOYMENT", os.getenv("LLM_MODEL", "claude-opus-5"))

    t0 = time.time()
    print(f"[foundry] acquiring token... endpoint={endpoint} deployment={deployment}", flush=True, file=sys.stderr)
    client = AnthropicFoundry(
        azure_ad_token_provider=_get_foundry_token_provider(),
        base_url=endpoint,
        timeout=60.0,
    )
    print(f"[foundry] client created (+{time.time()-t0:.1f}s), calling messages.create...", flush=True, file=sys.stderr)
    message = client.messages.create(
        model=deployment,
        system=system,
        messages=[{"role": "user", "content": user}],
        max_tokens=4096,
    )
    print(f"[foundry] response received (+{time.time()-t0:.1f}s)", flush=True, file=sys.stderr)
    return "".join(block.text for block in message.content if block.type == "text")


def chat(system: str, user: str, temperature: float = 0.2) -> str:
    backend = os.getenv("LLM_BACKEND", "ollama").lower()
    if backend == "azure_ai_foundry":
        return _chat_azure_ai_foundry(system, user, temperature)

    client, model = get_client_and_model()
    resp = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content or ""
