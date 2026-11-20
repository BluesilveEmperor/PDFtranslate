"""v2 bridge — convert v1 TranslateRequest to v2 CLI args + env vars.

This is the only translation layer between the v1 protocol and the v2
(pdf2zh_next) CLI.  v2 handles all its own config parsing, so we just
need to produce CLI args and environment variables.
"""

from __future__ import annotations

import dataclasses
import os
from typing import Any

# v1 service name → v2 CLI engine flag (lowercase)
SERVICE_NAME_MAP: dict[str, str] = {
    "google": "google",
    "bing": "bing",
    "deepl": "deepl",
    "deeplx": "deeplx",
    "ollama": "ollama",
    "openai": "openai",
    "azure": "azure",
    "azureopenai": "azure",
    "zhipu": "zhipu",
    "silicon": "siliconflow",
    "siliconflow": "siliconflow",
    "gemini": "gemini",
    "tencent": "tencent",
    "dify": "dify",
    "anythingllm": "anythingllm",
    "argos": "argos",
    "grok": "grok",
    "groq": "groq",
    "deepseek": "deepseek",
    "doubao": "doubao",
    "openai-compatible": "openaicompatible",
    "aliyun-dashscope": "aliyun_dashscope",
    "modelscope": "modelscope",
}

# Known engine-related env var names (without PDF2ZH_ prefix).
# Used to forward relevant vars from os.environ into the subprocess.
_ENGINE_ENV_NAMES: set[str] = {
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_MODEL",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_BASE_URL",
    "AZURE_OPENAI_MODEL",
    "AZURE_OPENAI_API_VERSION",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "ZHIPU_API_KEY",
    "ZHIPU_MODEL",
    "OLLAMA_HOST",
    "OLLAMA_MODEL",
    "DEEPL_AUTH_KEY",
    "DEEPLX_ENDPOINT",
    "DEEPLX_AUTH_KEY",
    "TENCENT_SECRET_ID",
    "TENCENT_SECRET_KEY",
    "DIFY_API_URL",
    "DIFY_API_KEY",
    "ANYTHINGLLM_API_URL",
    "ANYTHINGLLM_API_KEY",
    "GROK_API_KEY",
    "GROK_MODEL",
    "GROQ_API_KEY",
    "GROQ_MODEL",
    "DOUBAO_API_KEY",
    "DOUBAO_MODEL",
    "SILICONFLOW_API_KEY",
    "SILICONFLOW_MODEL",
    "OPENAI_COMPATIBLE_API_KEY",
    "OPENAI_COMPATIBLE_BASE_URL",
    "OPENAI_COMPATIBLE_MODEL",
    "ALIYUN_DASHSCOPE_API_KEY",
    "ALIYUN_DASHSCOPE_MODEL",
    "MODELSCOPE_API_KEY",
    "MODELSCOPE_MODEL",
}


# v1 服务无同名 v2 引擎时，走 v2 的 OpenAICompatible 引擎的映射表。
# v1 服务名 → (v2 base URL, v1 API key 环境名, v1 默认模型)
OPENAI_COMPAT_SERVICES: dict[str, tuple[str, str, str]] = {
    "longcat": (
        "https://api.longcat.chat/openai/v1",
        "LONGCAT_API_KEY",
        "LongCat-2.5",
    ),
}


def _split_service_model(service_raw: str) -> tuple[str, str]:
    """Split 'openai:gpt-4o' into ('openai', 'gpt-4o')."""
    if ":" in service_raw:
        svc, model = service_raw.split(":", 1)
        return svc.strip(), model.strip()
    return service_raw.strip(), ""


def _pages_to_v2(pages: Any) -> str:
    """Convert v1 pages to v2 format string.

    v1 (GUI/TranslateRequest) 页码为 0-based list[int]；v1 CLI 字符串
    （用户手填）已按文档使用 1-based，直接透传。v2/babeldoc 一律
    1-based，因此 list[int] 需整体 +1。
    """
    if pages is None:
        return ""
    if isinstance(pages, str):
        return pages
    if isinstance(pages, list):
        return ",".join(str(int(p) + 1) for p in pages)
    return str(pages)


def request_to_cli_args(request: Any) -> list[str]:
    """Convert a TranslateRequest to pdf2zh_next CLI arguments."""
    data = dataclasses.asdict(request)
    args: list[str] = []

    service_raw = data.get("service", "google")
    service, _model = _split_service_model(service_raw)
    pages_v2 = _pages_to_v2(data.get("pages"))

    # Positional: files
    for f in data.get("files", []):
        args.append(f)

    if data.get("lang_in"):
        args.extend(["--lang-in", data["lang_in"]])
    if data.get("lang_out"):
        args.extend(["--lang-out", data["lang_out"]])

    # Engine flag: --google, --openai, etc.
    engine_type = SERVICE_NAME_MAP.get(service.lower())
    if not engine_type and service.lower() in OPENAI_COMPAT_SERVICES:
        # v1 独有服务（如 longcat）→ v2 的 OpenAICompatible 引擎。
        # 注意 v2 布尔引擎旗标是 --openaicompatible（无连字符），
        # 其细节参数才是 --openai-compatible-*；环境变量在
        # request_to_env 中注入
        engine_type = "openaicompatible"
    if engine_type:
        args.append(f"--{engine_type.replace('_', '-')}")
    else:
        raise ValueError(
            f"Service '{service}' is not supported by the precise kernel "
            "(pdf2zh_next). Switch to 'fast' mode or pick a supported service."
        )

    if pages_v2:
        args.extend(["--pages", pages_v2])

    # Always resolve output to an absolute path to avoid cwd confusion
    # in the subprocess.  Default to input file's parent dir (v1 behavior).
    from pathlib import Path

    output = data.get("output", "")
    if not output and data.get("files"):
        output = str(Path(data["files"][0]).resolve().parent)
    elif output:
        output = str(Path(output).resolve())
    if output:
        args.extend(["--output", output])

    if data.get("thread"):
        args.extend(["--qps", str(data["thread"])])
    if data.get("debug"):
        args.append("--debug")
    if data.get("compatible"):
        args.append("--enhance-compatibility")
    if data.get("vfont"):
        args.extend(["--formular-font-pattern", data["vfont"]])
    if data.get("vchar"):
        args.extend(["--formular-char-pattern", data["vchar"]])
    if data.get("prompt"):
        args.extend(["--custom-system-prompt", data["prompt"]])
    if data.get("ignore_cache"):
        args.append("--ignore-cache")

    return args


def request_to_env(request: Any) -> dict[str, str]:
    """Build env dict with PDF2ZH_ prefixed vars for the v2 subprocess.

    v2's ConfigManager reads env vars with a ``PDF2ZH_`` prefix.  This
    function maps v1 env vars (from request.envs and os.environ) to the
    prefixed form, and also handles the ``service:model`` syntax by
    setting ``PDF2ZH_{ENGINE}_MODEL``.
    """
    env: dict[str, str] = {}
    data = dataclasses.asdict(request)
    envs = data.get("envs") or {}

    # Map v1 env vars from request.envs → PDF2ZH_ prefix
    for key, value in envs.items():
        env[f"PDF2ZH_{key.upper()}"] = str(value)

    # Forward relevant vars from os.environ (if not already set)
    for key in _ENGINE_ENV_NAMES:
        v2_key = f"PDF2ZH_{key}"
        if v2_key not in env and key in os.environ:
            env[v2_key] = os.environ[key]

    # Handle service:model → PDF2ZH_{ENGINE}_MODEL
    service_raw = data.get("service", "google")
    service, model = _split_service_model(service_raw)
    engine_type = SERVICE_NAME_MAP.get(service.lower())

    # v1 独有服务 → OpenAICompatible：注入 base URL / key / model。
    # v1 envs 优先，os.environ 兜底，最后用内置默认。
    compat = OPENAI_COMPAT_SERVICES.get(service.lower())
    if compat:
        compat_base, compat_key_name, compat_default_model = compat
        api_key = envs.get(compat_key_name) or os.environ.get(compat_key_name)
        v1_model_name = compat_key_name.replace("_API_KEY", "_MODEL")
        model_name = (
            model
            or envs.get(v1_model_name)
            or os.environ.get(v1_model_name)
            or compat_default_model
        )
        if not api_key:
            raise ValueError(
                f"Service '{service}' requires {compat_key_name} to be set."
            )
        env["PDF2ZH_OPENAI_COMPATIBLE_BASE_URL"] = compat_base
        env["PDF2ZH_OPENAI_COMPATIBLE_API_KEY"] = api_key
        env["PDF2ZH_OPENAI_COMPATIBLE_MODEL"] = model_name
    elif model:
        if engine_type:
            model_env = f"PDF2ZH_{engine_type.upper()}_MODEL"
            env[model_env] = model

    return env
