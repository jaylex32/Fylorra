from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class AiModelSpec:
    """
    Minimal model metadata used by Fylorra.

    Notes:
    - Vision models require an mmproj (CLIP projector) file and a vision chat handler.
    - Text models use `chat_format` (or None to let llama-cpp choose).
    """

    id: str
    name: str
    repo: str
    model_file: str
    mmproj_file: Optional[str] = None
    kind: str = "vision"  # "vision" | "text"
    chat_format: Optional[str] = None
    max_context_tokens: int = 65536


MODEL_CATALOG: Dict[str, AiModelSpec] = {
    # Recommended (Vision)
    "qwen3vl-4b-q4km": AiModelSpec(
        id="qwen3vl-4b-q4km",
        name="Qwen3-VL 4B Instruct (Q4_K_M) - Recommended",
        repo="Qwen/Qwen3-VL-4B-Instruct-GGUF",
        model_file="Qwen3VL-4B-Instruct-Q4_K_M.gguf",
        mmproj_file="mmproj-Qwen3VL-4B-Instruct-F16.gguf",
        kind="vision",
        chat_format=None,
        max_context_tokens=256000,
    ),
    "qwen3vl-8b-q4km": AiModelSpec(
        id="qwen3vl-8b-q4km",
        name="Qwen3-VL 8B Instruct (Q4_K_M) — Recommended",
        repo="Qwen/Qwen3-VL-8B-Instruct-GGUF",
        model_file="Qwen3VL-8B-Instruct-Q4_K_M.gguf",
        # The upstream repo typically provides a matching mmproj; keep the expected name.
        mmproj_file="mmproj-Qwen3VL-8B-Instruct-F16.gguf",
        kind="vision",
        chat_format=None,
    ),
    # Google Gemma 3 (Vision+Text via mmproj)
    "gemma-3-4b-it-q8": AiModelSpec(
        id="gemma-3-4b-it-q8",
        name="Gemma 3 4B IT (Q8_0) - Vision",
        repo="unsloth/gemma-3-4b-it-GGUF",
        model_file="gemma-3-4b-it-Q8_0.gguf",
        mmproj_file="mmproj-F16.gguf",
        kind="vision",
        chat_format="gemma",
        max_context_tokens=128000,
    ),
    "gemma-3-12b-it-q4km": AiModelSpec(
        id="gemma-3-12b-it-q4km",
        name="Gemma 3 12B IT (Q4_K_M) - Vision",
        repo="unsloth/gemma-3-12b-it-GGUF",
        model_file="gemma-3-12b-it-Q4_K_M.gguf",
        mmproj_file="mmproj-F16.gguf",
        kind="vision",
        chat_format="gemma",
        max_context_tokens=128000,
    ),
    # GLM 4.6V Flash (Vision+Text via mmproj)
    "glm-4.6v-flash-q4km": AiModelSpec(
        id="glm-4.6v-flash-q4km",
        name="GLM-4.6V Flash (Q4_K_M) - Vision",
        repo="unsloth/GLM-4.6V-Flash-GGUF",
        model_file="GLM-4.6V-Flash-Q4_K_M.gguf",
        mmproj_file="mmproj-F16.gguf",
        kind="vision",
        chat_format="chatml",
        max_context_tokens=128000,
    ),
    # Qwen3 Text (Workflow Automation / Writing)
    "qwen3-4b-instruct-2507-q8": AiModelSpec(
        id="qwen3-4b-instruct-2507-q8",
        name="Qwen3 4B Instruct 2507 (Q8_0) - Text",
        repo="unsloth/Qwen3-4B-Instruct-2507-GGUF",
        model_file="Qwen3-4B-Instruct-2507-Q8_0.gguf",
        mmproj_file=None,
        kind="text",
        # llama-cpp supports a dedicated qwen chat format; fall back to auto if unavailable.
        chat_format="qwen",
        max_context_tokens=256000,
    ),
    "qwen3-8b-instruct-q4km": AiModelSpec(
        id="qwen3-8b-instruct-q4km",
        name="Qwen3 8B Instruct (Q4_K_M) - Text",
        repo="lm-kit/qwen-3-8b-instruct-gguf",
        model_file="Qwen3-8B-Q4_K_M.gguf",
        mmproj_file=None,
        kind="text",
        chat_format="qwen",
        max_context_tokens=256000,
    ),
}


DEFAULT_MODEL_ID = "qwen3vl-4b-q4km"
DEFAULT_TEXT_MODEL_ID = "qwen3-4b-instruct-2507-q8"


def get_model_spec(model_id: str | None) -> AiModelSpec:
    if model_id and model_id in MODEL_CATALOG:
        return MODEL_CATALOG[model_id]
    return MODEL_CATALOG[DEFAULT_MODEL_ID]


def get_model_max_context(model_id: str | None) -> int:
    try:
        return int(get_model_spec(model_id).max_context_tokens or 65536)
    except Exception:
        return 65536


def get_models_by_kind(kind: str) -> Dict[str, AiModelSpec]:
    k = (kind or "").strip().lower()
    if not k:
        return dict(MODEL_CATALOG)
    return {mid: spec for mid, spec in MODEL_CATALOG.items() if (spec.kind or "text").strip().lower() == k}
