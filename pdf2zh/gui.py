import sys
import os
import base64
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio
import cgi
import shutil
import socket
import threading
import time
import uuid
import webbrowser
from asyncio import CancelledError
from pathlib import Path
import typing as T

import gradio as gr
import requests
import tqdm
from gradio_pdf import PDF
from string import Template
import logging

from pdf2zh import __version__
from pdf2zh.high_level import translate
from pdf2zh.doclayout import ModelInstance
from pdf2zh.config import ConfigManager
from pdf2zh.translator import (
    AnythingLLMTranslator,
    AzureOpenAITranslator,
    AzureTranslator,
    BaseTranslator,
    BingTranslator,
    DeepLTranslator,
    DeepLXTranslator,
    DifyTranslator,
    ArgosTranslator,
    GeminiTranslator,
    GoogleTranslator,
    MiniMaxTranslator,
    ModelScopeTranslator,
    OllamaTranslator,
    OpenAITranslator,
    SiliconTranslator,
    TencentTranslator,
    XinferenceTranslator,
    ZhipuTranslator,
    LongCatTranslator,
    GrokTranslator,
    GroqTranslator,
    DeepseekTranslator,
    OpenAIlikedTranslator,
    QwenMtTranslator,
    X302AITranslator,
)
from babeldoc.docvision.doclayout import OnnxModel


logger = logging.getLogger(__name__)

# Avoid Gradio startup telemetry requests to overseas endpoints
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

# ---------------------------------------------------------------------------
# HarmonyOS icon set (inline base64, single-color SVG)
# ---------------------------------------------------------------------------
_ICON_DIR = Path(__file__).parent / "gui_assets"


def load_icon(name: str, color: str = "#165DFF") -> str:
    """Read an SVG icon from gui_assets and return a base64 <img> tag.

    Icons are monochrome (#000000); the fill color is replaced so the icon
    can follow the theme. Base64 <img> avoids element-id collisions between
    multiple inlined SVGs on the same page.
    """
    try:
        svg = (_ICON_DIR / f"{name}.svg").read_text(encoding="utf-8")
        svg = svg.replace('fill="#000000"', f'fill="{color}"')
        b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
        return (
            f'<img class="section-icon" '
            f'src="data:image/svg+xml;base64,{b64}" alt=""/>'
        )
    except OSError:
        return ""


def _favicon_head() -> str:
    """Return a <link rel=icon> tag with an SVG data URI, themed blue."""
    try:
        svg = (_ICON_DIR / "ic_normal_white_grid_pdf.svg").read_text(
            encoding="utf-8"
        )
        svg = svg.replace('fill="#000000"', 'fill="#165DFF"')
        b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
        return f'<link rel="icon" href="data:image/svg+xml;base64,{b64}">'
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# 模型/服务商图标（参照 cc-switch 的图标索引方案：名称→内联 SVG→关键词匹配）
# 单色图标用 currentColor 填充，渲染时替换为主题蓝；品牌色图标保持原色
# ---------------------------------------------------------------------------
_MODEL_ICON_DIR = _ICON_DIR / "model_icons"

# 服务名 → 图标文件名（不含扩展名）
SERVICE_ICON_MAP = {
    "Google": "google",
    "Bing": "bing",
    "OpenAI": "openai",
    "AzureOpenAI": "azure",
    "Zhipu": "zhipu",
    "LongCat": "longcat-color",
    "ModelScope": "modelscope-color",
    "Silicon": "siliconflow",
    "Gemini": "gemini",
    "Grok": "grok",
    "DeepSeek": "deepseek",
    "MiniMax": "minimax",
    "Ollama": "ollama",
    "OpenAI-liked": "openai",
    "Ali Qwen-Translation": "qwencloud",
    "302.AI": "openai",
}

# 模型名片段 → 图标文件名（大小写不敏感的子串匹配，按顺序首个命中生效）
MODEL_ICON_KEYWORDS = [
    ("longcat", "longcat-color"),
    ("deepseek", "deepseek"),
    ("chatglm", "chatglm"),
    ("glm-", "zhipu"),
    ("glm", "zhipu"),
    ("zhipu", "zhipu"),
    ("gemini", "gemini"),
    ("gemma", "gemini"),
    ("gpt", "openai"),
    ("chatgpt", "openai"),
    ("o1", "openai"),
    ("o3", "openai"),
    ("o4", "openai"),
    ("claude", "claude"),
    ("grok", "grok"),
    ("qwen", "qwen"),
    ("qwq", "qwen"),
    ("kimi", "kimi"),
    ("moonshot", "kimi"),
    ("doubao", "doubao"),
    ("minimax", "minimax"),
    ("abab", "minimax"),
    ("mistral", "mistral"),
    ("mixtral", "mistral"),

    ("ollama", "ollama"),
]

ICON_TINT = "#165DFF"


def load_vendor_icon(icon_name: str) -> str:
    """渲染厂商 SVG 图标为 base64 <img>；currentColor 替换为主题色。

    尺寸由 CSS 的 .vendor-icon 类控制（对抗 Gradio preflight 的
    img display:block，保证与文字同行）。品牌色（如 longcat 的
    #29E154、Bing 渐变）保持原样。图标缺失时返回空串。
    """
    if not icon_name:
        return ""
    try:
        svg = (_MODEL_ICON_DIR / f"{icon_name}.svg").read_text(
            encoding="utf-8"
        )
        # cc-switch 图标用 currentColor，单色图标用 #000000，统一着主题色
        svg = svg.replace("currentColor", ICON_TINT)
        svg = svg.replace('fill="#000000"', f'fill="{ICON_TINT}"')
        b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
        return (
            f'<img class="vendor-icon" '
            f'src="data:image/svg+xml;base64,{b64}" alt=""/>'
        )
    except OSError:
        return ""


def service_icon_html(service_name: str) -> str:
    """服务的厂商图标 HTML。"""
    return load_vendor_icon(SERVICE_ICON_MAP.get(service_name, ""))


def model_icon_html(model_id: str) -> str:
    """按模型名子串匹配厂商图标 HTML。"""
    mid = str(model_id or "").lower()
    for kw, icon in MODEL_ICON_KEYWORDS:
        if kw in mid:
            return load_vendor_icon(icon)
    return ""


# ---------------------------------------------------------------------------
# OpenAI 兼容服务的模型列表获取（参照 cc-switch：GET /v1/models）
# 服务名 → (默认 base_url, BASE_URL 覆盖用的 env 键或 None, API_KEY env 键或 None)
# ---------------------------------------------------------------------------
OPENAI_COMPAT: dict = {
    "OpenAI": ("https://api.openai.com/v1", "OPENAI_BASE_URL", "OPENAI_API_KEY"),
    "Zhipu": ("https://open.bigmodel.cn/api/paas/v4", None, "ZHIPU_API_KEY"),
    "LongCat": (
        "https://api.longcat.chat/openai/v1",
        None,
        "LONGCAT_API_KEY",
    ),
    "ModelScope": (
        "https://api-inference.modelscope.cn/v1",
        "MODELSCOPE_BASE_URL",
        "MODELSCOPE_API_KEY",
    ),
    "Silicon": ("https://api.siliconflow.cn/v1", None, "SILICON_API_KEY"),
    "Gemini": (
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        None,
        "GEMINI_API_KEY",
    ),
    "Grok": ("https://api.x.ai/v1", "GROK_BASE_URL", "GROK_API_KEY"),
    "Groq": ("https://api.groq.com/openai/v1", None, "GROQ_API_KEY"),
    "DeepSeek": ("https://api.deepseek.com/v1", None, "DEEPSEEK_API_KEY"),
    "MiniMax": ("https://api.minimax.io/v1", None, "MINIMAX_API_KEY"),
    "302.AI": ("https://api.302.ai/v1", None, "X302AI_API_KEY"),
    "OpenAI-liked": ("", "OPENAILIKED_BASE_URL", "OPENAILIKED_API_KEY"),
    "Ollama": ("http://127.0.0.1:11434/v1", "OLLAMA_HOST", None),
}


def fetch_model_list(service: str, api_key: str, base_url_value: str) -> list:
    """从 OpenAI 兼容端点拉取模型列表，返回排序后的模型 id。

    base_url_value 为界面 BASE_URL 输入框的当前值（优先于默认值）。
    """
    entry = OPENAI_COMPAT.get(service)
    if not entry:
        raise gr.Error("当前服务不支持自动获取模型列表")
    default_url, base_url_env, _key_env = entry

    base_url = (base_url_value or "").strip()
    if not base_url:
        base_url = default_url
    if not base_url:
        raise gr.Error("请先填写 Base URL（接口地址）")
    if base_url_env == "OLLAMA_HOST" and "/v1" not in base_url:
        base_url = base_url.rstrip("/") + "/v1"

    headers = {}
    if api_key and str(api_key).strip() not in ("", "***"):
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        resp = requests.get(
            f"{base_url.rstrip('/')}/models", headers=headers, timeout=15
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        ids = sorted(
            str(m.get("id")) for m in data if m.get("id")
        )
    except requests.exceptions.Timeout:
        raise gr.Error("获取模型列表超时，请检查网络或接口地址")
    except requests.exceptions.ConnectionError:
        raise gr.Error("无法连接到接口地址，请检查 Base URL")
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        if code in (401, 403):
            raise gr.Error("鉴权失败（HTTP {0}），请检查 API 密钥".format(code))
        if code in (404, 405):
            raise gr.Error("接口不支持模型列表（HTTP {0}）".format(code))
        raise gr.Error("获取模型列表失败（HTTP {0}）".format(code))
    except ValueError:
        raise gr.Error("接口返回内容无法解析")
    if not ids:
        raise gr.Error("接口未返回任何模型")
    return ids


class _LazyModel:
    """Defers model loading until first access so the GUI starts instantly."""

    def __init__(self):
        self._model = None

    def _ensure_loaded(self):
        if self._model is None:
            self._model = OnnxModel.load_available()

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        self._ensure_loaded()
        return getattr(self._model, name)


BABELDOC_MODEL = _LazyModel()
# The following variables associate strings with translators
service_map: dict[str, BaseTranslator] = {
    "Google": GoogleTranslator,
    "Bing": BingTranslator,
    "DeepL": DeepLTranslator,
    "DeepLX": DeepLXTranslator,
    "Ollama": OllamaTranslator,
    "Xinference": XinferenceTranslator,
    "AzureOpenAI": AzureOpenAITranslator,
    "OpenAI": OpenAITranslator,
    "Zhipu": ZhipuTranslator,
    "LongCat": LongCatTranslator,
    "ModelScope": ModelScopeTranslator,
    "Silicon": SiliconTranslator,
    "Gemini": GeminiTranslator,
    "Azure": AzureTranslator,
    "Tencent": TencentTranslator,
    "Dify": DifyTranslator,
    "AnythingLLM": AnythingLLMTranslator,
    "Argos Translate": ArgosTranslator,
    "Grok": GrokTranslator,
    "Groq": GroqTranslator,
    "DeepSeek": DeepseekTranslator,
    "MiniMax": MiniMaxTranslator,
    "OpenAI-liked": OpenAIlikedTranslator,
    "Ali Qwen-Translation": QwenMtTranslator,
    "302.AI": X302AITranslator,
}

# The following variables associate strings with specific languages
# 键为界面显示名（中文），值为传给翻译服务的语言代码
lang_map = {
    "简体中文": "zh",
    "繁體中文": "zh-TW",
    "英语": "en",
    "法语": "fr",
    "德语": "de",
    "日语": "ja",
    "韩语": "ko",
    "俄语": "ru",
    "西班牙语": "es",
    "意大利语": "it",
}

# 兼容旧配置：历史版本以英文语言名存储
_LANG_EN2ZH = {
    "Simplified Chinese": "简体中文",
    "Traditional Chinese": "繁體中文",
    "English": "英语",
    "French": "法语",
    "German": "德语",
    "Japanese": "日语",
    "Korean": "韩语",
    "Russian": "俄语",
    "Spanish": "西班牙语",
    "Italian": "意大利语",
}


def _norm_lang(name: str) -> str:
    """把旧英文语言名归一化为中文显示名。"""
    return _LANG_EN2ZH.get(name, name)


# The following variable associate strings with page ranges
page_map = {
    "全部": None,
    "首页": [0],
    "前 5 页": list(range(0, 5)),
    "指定页": None,
}

# Check if this is a public demo, which has resource limits
flag_demo = False

# Limit resources
if ConfigManager.get("PDF2ZH_DEMO"):
    flag_demo = True
    service_map = {
        "Google": GoogleTranslator,
    }
    page_map = {
        "首页": [0],
        "前 20 页": list(range(0, 20)),
    }
    client_key = ConfigManager.get("PDF2ZH_CLIENT_KEY")
    server_key = ConfigManager.get("PDF2ZH_SERVER_KEY")


# Limit Enabled Services
enabled_services: T.Optional[T.List[str]] = ConfigManager.get("ENABLED_SERVICES")
if isinstance(enabled_services, list):
    default_services = ["Google", "Bing"]
    lookup = {str(k).lower().strip(): k for k in service_map.keys()}
    enabled_services = list(
        dict.fromkeys(
            lookup[str(name).lower().strip()]
            for name in enabled_services
            if str(name).lower().strip() in lookup
        )
    )
    if len(enabled_services) == 0:
        raise RuntimeError("No services available.")
    # Keep user-configured order first; append defaults only if missing
    enabled_services = enabled_services + [
        k for k in default_services if k not in enabled_services
    ]
else:
    enabled_services = list(service_map.keys())


# Configure about Gradio show keys
hidden_gradio_details: bool = bool(ConfigManager.get("HIDDEN_GRADIO_DETAILS"))


# Public demo control
def verify_recaptcha(response):
    """
    This function verifies the reCAPTCHA response.
    """
    recaptcha_url = "https://www.google.com/recaptcha/api/siteverify"
    data = {"secret": server_key, "response": response}
    result = requests.post(recaptcha_url, data=data).json()
    return result.get("success")


def download_with_limit(url: str, save_path: str, size_limit: int) -> str:
    """
    This function downloads a file from a URL and saves it to a specified path.

    Inputs:
        - url: The URL to download the file from
        - save_path: The path to save the file to
        - size_limit: The maximum size of the file to download

    Returns:
        - The path of the downloaded file
    """
    chunk_size = 1024
    total_size = 0
    with requests.get(url, stream=True, timeout=10) as response:
        response.raise_for_status()
        content = response.headers.get("Content-Disposition")
        try:  # filename from header
            _, params = cgi.parse_header(content)
            filename = params["filename"]
        except Exception:  # filename from url
            filename = os.path.basename(url)
        filename = os.path.splitext(os.path.basename(filename))[0] + ".pdf"
        with open(save_path / filename, "wb") as file:
            for chunk in response.iter_content(chunk_size=chunk_size):
                total_size += len(chunk)
                if size_limit and total_size > size_limit:
                    raise gr.Error("文件超出大小限制")
                file.write(chunk)
    return save_path / filename


def stop_translate_file(state: dict) -> None:
    """
    This function stops the translation process.

    Inputs:
        - state: The state of the translation process

    Returns:- None
    """
    session_id = state["session_id"]
    if session_id is None:
        return
    if session_id in cancellation_event_map:
        logger.info(f"Stopping translation for session {session_id}")
        cancellation_event_map[session_id].set()


def translate_file(
    file_type,
    file_input,
    link_input,
    service,
    lang_from,
    lang_to,
    page_range,
    page_input,
    prompt,
    threads,
    skip_subset_fonts,
    ignore_cache,
    vfont,
    mode_choice,
    recaptcha_response,
    state,
    progress=gr.Progress(),
    *envs,
):
    """
    This function translates a PDF file from one language to another.

    Inputs:
        - file_type: The type of file to translate
        - file_input: The file to translate
        - link_input: The link to the file to translate
        - service: The translation service to use
        - lang_from: The language to translate from
        - lang_to: The language to translate to
        - page_range: The range of pages to translate
        - page_input: The input for the page range
        - prompt: The custom prompt for the llm
        - threads: The number of threads to use
        - recaptcha_response: The reCAPTCHA response
        - state: The state of the translation process
        - progress: The progress bar
        - envs: The environment variables

    Returns:
        - The translated file
        - The translated file
        - The translated file
        - The progress bar
        - The progress bar
        - The progress bar
    """
    session_id = uuid.uuid4()
    state["session_id"] = session_id
    cancellation_event_map[session_id] = asyncio.Event()
    # Translate PDF content using selected service.
    if flag_demo and not verify_recaptcha(recaptcha_response):
        raise gr.Error("reCAPTCHA fail")

    progress(0, desc="正在开始翻译…")

    output = Path("pdf2zh_files")
    output.mkdir(parents=True, exist_ok=True)

    if file_type == "本地文件":
        if not file_input:
            raise gr.Error("请先选择或输入文件")
        file_path = shutil.copy(file_input, output)
    else:
        if not link_input:
            raise gr.Error("请先输入文件链接")
        file_path = download_with_limit(
            link_input,
            output,
            5 * 1024 * 1024 if flag_demo else None,
        )

    filename = os.path.splitext(os.path.basename(file_path))[0]
    file_raw = output / f"{filename}.pdf"
    file_mono = output / f"{filename}-mono.pdf"
    file_dual = output / f"{filename}-dual.pdf"

    translator = service_map[service]
    if page_range != "指定页":
        selected_page = page_map[page_range]
    else:
        selected_page = []
        for p in page_input.split(","):
            if "-" in p:
                start, end = p.split("-")
                selected_page.extend(range(int(start) - 1, int(end)))
            else:
                selected_page.append(int(p) - 1)
    lang_from = lang_map[lang_from]
    lang_to = lang_map[lang_to]

    _envs = {}
    for i, env in enumerate(translator.envs.items()):
        _envs[env[0]] = envs[i]
    for k, v in _envs.items():
        if str(k).upper().endswith("API_KEY") and str(v) == "***":
            # Load Real API_KEYs from local configure file
            real_keys: str = ConfigManager.get_env_by_translatername(
                translator, k, None
            )
            _envs[k] = real_keys

    logger.debug("Files before translation: %s", os.listdir(output))

    def progress_bar(t: tqdm.tqdm):
        desc = getattr(t, "desc", "翻译中…")
        if desc == "":
            desc = "翻译中…"
        progress(t.n / t.total, desc=desc)

    try:
        threads = int(threads)
    except ValueError:
        threads = 1

    param = {
        "files": [str(file_raw)],
        "pages": selected_page,
        "lang_in": lang_from,
        "lang_out": lang_to,
        "service": f"{translator.name}",
        "output": output,
        "thread": int(threads),
        "callback": progress_bar,
        "cancellation_event": cancellation_event_map[session_id],
        "envs": _envs,
        "prompt": Template(prompt) if prompt else None,
        "skip_subset_fonts": skip_subset_fonts,
        "ignore_cache": ignore_cache,
        "vfont": vfont,  # 添加自定义公式字体正则表达式
        "model": ModelInstance.value,
    }

    try:
        from pdf2zh.kernel import KernelRegistry
        from pdf2zh.kernel.protocol import TranslateRequest

        KernelRegistry.switch(mode_choice)
        kernel = KernelRegistry.get()
        request = TranslateRequest(
            files=[str(file_raw)],
            output=str(output),
            pages=selected_page,
            lang_in=lang_from,
            lang_out=lang_to,
            service=f"{translator.name}",
            thread=int(threads),
            envs=_envs,
            prompt=str(prompt) if prompt else None,
            skip_subset_fonts=skip_subset_fonts,
            ignore_cache=ignore_cache,
            vfont=vfont,
        )
        kernel.translate(
            request,
            callback=progress_bar,
            cancellation_event=cancellation_event_map[session_id],
        )
    except CancelledError:
        del cancellation_event_map[session_id]
        raise gr.Error("翻译已取消")
    logger.debug("Files after translation: %s", os.listdir(output))

    if not file_mono.exists() or not file_dual.exists():
        raise gr.Error("翻译失败：未生成输出文件")

    progress(1.0, desc="翻译完成！")

    return (
        str(file_mono),
        str(file_mono),
        str(file_dual),
        gr.update(visible=True),
        gr.update(visible=True),
        gr.update(visible=True),
    )


def babeldoc_translate_file(**kwargs):
    from babeldoc.high_level import init as babeldoc_init

    babeldoc_init()
    from babeldoc.high_level import async_translate as babeldoc_translate
    from babeldoc.translation_config import TranslationConfig as YadtConfig

    for translator in [
        GoogleTranslator,
        BingTranslator,
        DeepLTranslator,
        DeepLXTranslator,
        OllamaTranslator,
        XinferenceTranslator,
        AzureOpenAITranslator,
        OpenAITranslator,
        ZhipuTranslator,
        LongCatTranslator,
        ModelScopeTranslator,
        SiliconTranslator,
        GeminiTranslator,
        AzureTranslator,
        TencentTranslator,
        DifyTranslator,
        AnythingLLMTranslator,
        ArgosTranslator,
        GrokTranslator,
        GroqTranslator,
        DeepseekTranslator,
        OpenAIlikedTranslator,
        QwenMtTranslator,
        X302AITranslator,
    ]:
        if kwargs["service"] == translator.name:
            translator = translator(
                kwargs["lang_in"],
                kwargs["lang_out"],
                "",
                envs=kwargs["envs"],
                prompt=kwargs["prompt"],
                ignore_cache=kwargs["ignore_cache"],
            )
            break
    else:
        raise ValueError("Unsupported translation service")
    import asyncio
    from babeldoc.main import create_progress_handler

    for file in kwargs["files"]:
        file = file.strip("\"'")
        yadt_config = YadtConfig(
            input_file=file,
            font=None,
            pages=",".join((str(x) for x in getattr(kwargs, "raw_pages", []))),
            output_dir=kwargs["output"],
            doc_layout_model=BABELDOC_MODEL,
            translator=translator,
            debug=False,
            lang_in=kwargs["lang_in"],
            lang_out=kwargs["lang_out"],
            no_dual=False,
            no_mono=False,
            qps=kwargs["thread"],
            use_rich_pbar=False,
            disable_rich_text_translate=not isinstance(translator, OpenAITranslator),
            skip_clean=kwargs["skip_subset_fonts"],
            report_interval=0.5,
        )

        async def yadt_translate_coro(yadt_config):
            progress_context, progress_handler = create_progress_handler(yadt_config)

            # 开始翻译
            with progress_context:
                async for event in babeldoc_translate(yadt_config):
                    progress_handler(event)
                    if yadt_config.debug:
                        logger.debug(event)
                    kwargs["callback"](progress_context)
                    if kwargs["cancellation_event"].is_set():
                        yadt_config.cancel_translation()
                        raise CancelledError
                    if event["type"] == "finish":
                        result = event["translate_result"]
                        logger.info("Translation Result:")
                        logger.info(f"  Original PDF: {result.original_pdf_path}")
                        logger.info(f"  Time Cost: {result.total_seconds:.2f}s")
                        logger.info(f"  Mono PDF: {result.mono_pdf_path or 'None'}")
                        logger.info(f"  Dual PDF: {result.dual_pdf_path or 'None'}")
                        file_mono = result.mono_pdf_path
                        file_dual = result.dual_pdf_path
                        break
            import gc

            gc.collect()
            return (
                str(file_mono),
                str(file_mono),
                str(file_dual),
                gr.update(visible=True),
                gr.update(visible=True),
                gr.update(visible=True),
            )

        return asyncio.run(yadt_translate_coro(yadt_config))


# Global setup
custom_blue = gr.themes.Color(
    c50="#E8F3FF",
    c100="#BEDAFF",
    c200="#94BFFF",
    c300="#6AA1FF",
    c400="#4080FF",
    c500="#165DFF",  # Primary color
    c600="#0E42D2",
    c700="#0A2BA6",
    c800="#061D79",
    c900="#03114D",
    c950="#020B33",
)

custom_css = """
    .secondary-text {color: #999 !important;}
    footer {visibility: hidden}
    .env-warning {color: #dd5500 !important;}
    .env-success {color: #559900 !important;}

    /* Add dashed border to input-file class */
    .input-file {
        border: 1.2px dashed #165DFF !important;
        border-radius: 6px !important;
    }

    .progress-bar-wrap {
        border-radius: 8px !important;
    }

    .progress-bar {
        border-radius: 8px !important;
    }

    .pdf-canvas canvas {
        width: 100%;
    }

    /* ===== Compact layout: higher space efficiency ===== */
    /* Shrink section paddings */
    .block {
        padding-top: var(--spacing-sm) !important;
        padding-bottom: var(--spacing-sm) !important;
    }
    .form {
        padding: var(--spacing-sm) !important;
        gap: var(--spacing-sm) !important;
    }
    .gap {
        gap: var(--spacing-sm) !important;
    }
    /* Compact section labels (replace big H2 headings) */
    .section-label {
        font-size: 13px !important;
        font-weight: 700 !important;
        letter-spacing: 0.5px;
        color: #555 !important;
        margin: 2px 0 0 0 !important;
        padding: 0 !important;
        display: inline-block !important;
        text-transform: uppercase;

    }
    /* Icon inline with section labels */
    /* NOTE: Gradio's Tailwind preflight sets .gradio-container img
       { display: block }, which puts icons on their own line. The
       inline-block here is required to keep icon + label on one row.
       vertical-align:middle measured best (within 1px of text center). */
    .section-icon {
        width: 20px !important;
        height: 20px !important;
        display: inline-block !important;
        vertical-align: middle;
        margin-right: 6px;
        opacity: 0.9;
    }
    .vendor-icon {
        width: 24px !important;
        height: 24px !important;
        display: inline-block !important;
        vertical-align: middle;
        margin-right: 6px;
    }
    .icon-heading {
        margin: 2px 0 0 0 !important;
        padding: 0 !important;
        line-height: 1.6;
    }
    .icon-heading img {
        border-radius: 4px;
    }
    /* Compact top title */
    .top-title {
        font-size: 18px !important;
        font-weight: 700 !important;
    }
    /* Slimmer inputs */
    .input-file {
        min-height: 90px !important;
    }
    /* Footer tech details centered */
    .tech-details {
        font-size: 12px !important;
    }
    """

demo_recaptcha = """
    <script src="https://www.google.com/recaptcha/api.js?render=explicit" async defer></script>
    <script type="text/javascript">
        var onVerify = function(token) {
            el=document.getElementById('verify').getElementsByTagName('textarea')[0];
            el.value=token;
            el.dispatchEvent(new Event('input'));
        };
    </script>
    """


cancellation_event_map = {}


# The following code creates the GUI
with gr.Blocks(
    title="PDFMathTranslate — PDF 翻译",
    theme=gr.themes.Default(
        primary_hue=custom_blue, spacing_size="sm", radius_size="md"
    ),
    css=custom_css,
    head=(
        (_favicon_head() + demo_recaptcha) if flag_demo else _favicon_head()
    ),
) as demo:
    gr.Markdown(
        f"{load_icon('ic_public_translate_e2c')} "
        "<span class='top-title'>[PDFMathTranslate](https://github.com/BluesilveEmperor/PDFtranslate)</span>"
        " <span class='secondary-text'>— 保留公式与排版的 PDF 翻译</span>",
        elem_classes=["icon-heading"],
    )

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown(
                f"{load_icon('ic_public_file')} "
                '<span class="section-label">文件</span>'
                + (" | < 5 MB" if flag_demo else ""),
                elem_classes=["icon-heading"],
            )
            file_type = gr.Radio(
                choices=["本地文件", "链接"],
                label="输入方式",
                value="本地文件",
            )
            file_input = gr.File(
                label="文件",
                file_count="single",
                file_types=[".pdf", ".doc", ".docx"],
                type="filepath",
                elem_classes=["input-file"],
            )
            link_input = gr.Textbox(
                label="链接",
                visible=False,
                interactive=True,
            )
            gr.Markdown(
                f"{load_icon('ic_public_settings')} "
                '<span class="section-label">选项</span>',
                elem_classes=["icon-heading"],
            )
            service_label_md = gr.Markdown(
                f"{service_icon_html(enabled_services[0])} "
                '<span class="section-label">翻译服务</span>',
                elem_classes=["icon-heading"],
            )
            service = gr.Dropdown(
                choices=enabled_services,
                value=enabled_services[0],
                show_label=False,
                interactive=True,
            )
            # 模型选择行：图标标签 + 可搜索下拉 + 在线获取按钮
            model_label_md = gr.Markdown(
                '<span class="section-label">模型</span>',
                visible=False,
                elem_classes=["icon-heading"],
            )
            with gr.Row() as model_row:
                model_dd = gr.Dropdown(
                    choices=[],
                    value=None,
                    allow_custom_value=True,
                    scale=4,
                    interactive=True,
                    visible=False,
                    filterable=True,
                    show_label=False,
                )
                fetch_models_btn = gr.Button(
                    "获取模型列表",

                    scale=2,
                    visible=False,
                )
            envs = []
            for i in range(3):
                envs.append(
                    gr.Textbox(
                        visible=False,
                        interactive=True,
                    )
                )
            # 记录当前服务的 env 槽位布局（MODEL/API_KEY/BASE_URL 各在第几槽）
            env_layout = gr.State({"model_slot": -1, "base_slot": -1})
            with gr.Row():
                lang_from = gr.Dropdown(
                    label="源语言",
                    choices=lang_map.keys(),
                    value=_norm_lang(
                        ConfigManager.get("PDF2ZH_LANG_FROM", "英语")
                    ),
                )
                lang_to = gr.Dropdown(
                    label="目标语言",
                    choices=lang_map.keys(),
                    value=_norm_lang(
                        ConfigManager.get("PDF2ZH_LANG_TO", "简体中文")
                    ),
                )
            page_range = gr.Radio(
                choices=page_map.keys(),
                label="页面范围",
                value=list(page_map.keys())[0],
            )

            page_input = gr.Textbox(
                label="页码范围",
                visible=False,
                interactive=True,
            )

            with gr.Accordion("更多实验选项", open=False):
                gr.Markdown("#### 实验性功能")
                threads = gr.Textbox(
                    label="线程数", interactive=True, value="4"
                )
                skip_subset_fonts = gr.Checkbox(
                    label="跳过字体子集化", interactive=True, value=False
                )
                ignore_cache = gr.Checkbox(
                    label="忽略缓存", interactive=True, value=False
                )
                vfont = gr.Textbox(
                    label="自定义公式字体正则（vfont）",
                    interactive=True,
                    value=ConfigManager.get("PDF2ZH_VFONT", ""),
                )
                prompt = gr.Textbox(
                    label="自定义 Prompt（LLM）", interactive=True, visible=False
                )
                mode_choice = gr.Dropdown(
                    label="翻译模式",
                    choices=["fast", "precise"],
                    value="fast",
                    interactive=True,
                )
                envs.append(prompt)

            def on_select_service(service, evt: gr.EventData):
                translator = service_map[service]
                _envs = []
                for i in range(4):
                    _envs.append(gr.update(visible=False, value=""))
                # 语义槽位：MODEL/BASE_URL 用独立行展示与交互
                layout = {
                    "model_slot": -1,
                    "key_slot": -1,
                    "base_slot": -1,
                    "key_env": "",
                    "base_env": "",
                }
                model_value = ""
                for i, env in enumerate(translator.envs.items()):
                    if i >= 3:  # 仅 3 个动态槽位，其余（stream 等）不展示
                        break
                    label = env[0]
                    upper = str(label).upper()
                    value = ConfigManager.get_env_by_translatername(
                        translator, env[0], env[1]
                    )
                    is_model = "MODEL" in upper
                    is_key = "API_KEY" in upper or "AUTH" in upper
                    is_base = "BASE_URL" in upper or "HOST" in upper
                    if is_model:
                        layout["model_slot"] = i
                        model_value = value
                    if is_key:
                        layout["key_slot"] = i
                        layout["key_env"] = str(label)
                    if is_base:
                        layout["base_slot"] = i
                        layout["base_env"] = str(label)
                    visible = True
                    if is_model:
                        visible = False  # 由独立的模型下拉行替代
                    elif hidden_gradio_details and value:
                        visible = False
                    if is_key and value:
                        value = "***"  # 用 *** 代替真实密钥
                    _envs[i] = gr.update(
                        visible=visible,
                        label=label,
                        value=value,
                    )
                _envs[-1] = gr.update(visible=translator.CustomPrompt)

                has_model = layout["model_slot"] >= 0
                can_fetch = service in OPENAI_COMPAT and has_model
                _model_dd = gr.update(
                    visible=has_model,
                    value=model_value or None,
                    choices=[],
                )
                _fetch_btn = gr.update(visible=can_fetch)
                # 图标嵌入 Markdown 标签（与"文件/选项"标题同一渲染路径）
                if has_model:
                    _model_label_md = (
                        f"{model_icon_html(model_value)} "
                        '<span class="section-label">模型</span>'
                    )
                else:
                    _model_label_md = gr.update(visible=False)
                _service_label_md = (
                    f"{service_icon_html(service)} "
                    '<span class="section-label">翻译服务</span>'
                )
                return (
                    _envs[0],
                    _envs[1],
                    _envs[2],
                    _envs[3],
                    _model_dd,
                    _fetch_btn,
                    _model_label_md,
                    _service_label_md,
                    layout,
                )

            def on_model_dd_change(
                value, e0, e1, e2, layout
            ):
                """把模型下拉的值同步回对应的 MODEL env 槽位，保持
                translate_file 按 index 对齐的兼容性。"""
                vals = [e0, e1, e2]
                slot = layout.get("model_slot", -1)
                if 0 <= slot <= 2:
                    vals[slot] = value
                return vals[0], vals[1], vals[2]

            def on_fetch_models(service, e0, e1, e2, layout):
                """从 OpenAI 兼容端点在线获取模型列表。"""
                vals = [e0, e1, e2]
                key = ""
                if 0 <= layout.get("key_slot", -1) <= 2:
                    key = str(vals[layout["key_slot"]] or "")
                if key == "***" and layout.get("key_env"):
                    # 界面密钥打码时回读本地配置的真实值
                    key = ConfigManager.get_env_by_translatername(
                        service_map[service], layout["key_env"], None
                    ) or ""
                base = ""
                if 0 <= layout.get("base_slot", -1) <= 2:
                    base = str(vals[layout["base_slot"]] or "")
                    if base == "***":
                        base = ""
                ids = fetch_model_list(service, key, base)
                return gr.update(choices=ids)

            def on_select_filetype(file_type):
                return (
                    gr.update(visible=file_type == "本地文件"),
                    gr.update(visible=file_type == "链接"),
                )

            def on_select_page(choice):
                if choice == "指定页":
                    return gr.update(visible=True)
                else:
                    return gr.update(visible=False)

            def on_vfont_change(value):
                ConfigManager.set("PDF2ZH_VFONT", value)
                return value

            output_title = gr.Markdown(
                f"{load_icon('ic_public_download')} "
                '<span class="section-label">翻译结果</span>',
                visible=False,
                elem_classes=["icon-heading"],
            )
            output_file_mono = gr.File(
                label="下载译文（单语）", visible=False
            )
            output_file_dual = gr.File(
                label="下载译文（双语对照）", visible=False
            )
            recaptcha_response = gr.Textbox(
                label="reCAPTCHA Response", elem_id="verify", visible=False
            )
            recaptcha_box = gr.HTML('<div id="recaptcha-box"></div>')
            with gr.Row():
                translate_btn = gr.Button(
                    "开始翻译", variant="primary", scale=4
                )
                cancellation_btn = gr.Button(
                    "取消", variant="secondary", scale=1
                )
            page_range.select(on_select_page, page_range, page_input)
            service.select(
                on_select_service,
                [service],
                [
                    envs[0],
                    envs[1],
                    envs[2],
                    envs[3],
                    model_dd,
                    fetch_models_btn,
                    model_label_md,
                    service_label_md,
                    env_layout,
                ],
            )
            model_dd.change(
                on_model_dd_change,
                inputs=[model_dd, envs[0], envs[1], envs[2], env_layout],
                outputs=[envs[0], envs[1], envs[2]],
            )
            model_dd.change(
                lambda v: (
                    f"{model_icon_html(v)} "
                    '<span class="section-label">模型</span>'
                ),
                inputs=model_dd,
                outputs=model_label_md,
            )
            fetch_models_btn.click(
                on_fetch_models,
                inputs=[service, envs[0], envs[1], envs[2], env_layout],
                outputs=model_dd,
            )
            vfont.change(on_vfont_change, inputs=vfont, outputs=None)
            file_type.select(
                on_select_filetype,
                file_type,
                [file_input, link_input],
                js=(
                    f"""
                    (a,b)=>{{
                        try{{
                            grecaptcha.render('recaptcha-box',{{
                                'sitekey':'{client_key}',
                                'callback':'onVerify'
                            }});
                        }}catch(error){{}}
                        return [a];
                    }}
                    """
                    if flag_demo
                    else ""
                ),
            )

        with gr.Column(scale=2):
            gr.Markdown(
                f"{load_icon('ic_public_detail')} "
                '<span class="section-label">预览</span>',
                elem_classes=["icon-heading"],
            )
            preview = PDF(label="文档预览", visible=True, height=760)

    # Event handlers
    file_input.upload(
        lambda x: x,
        inputs=file_input,
        outputs=preview,
        js=(
            f"""
            (a,b)=>{{
                try{{
                    grecaptcha.render('recaptcha-box',{{
                        'sitekey':'{client_key}',
                        'callback':'onVerify'
                    }});
                }}catch(error){{}}
                return [a];
            }}
            """
            if flag_demo
            else ""
        ),
    )

    state = gr.State({"session_id": None})

    translate_btn.click(
        translate_file,
        inputs=[
            file_type,
            file_input,
            link_input,
            service,
            lang_from,
            lang_to,
            page_range,
            page_input,
            prompt,
            threads,
            skip_subset_fonts,
            ignore_cache,
            vfont,
            mode_choice,
            recaptcha_response,
            state,
            *envs,
        ],
        outputs=[
            output_file_mono,
            preview,
            output_file_dual,
            output_file_mono,
            output_file_dual,
            output_title,
        ],
    ).then(lambda: None, js="()=>{grecaptcha.reset()}" if flag_demo else "")

    cancellation_btn.click(
        stop_translate_file,
        inputs=[state],
    )


def parse_user_passwd(file_path: str) -> tuple:
    """
    Parse the user name and password from the file.

    Inputs:
        - file_path: The file path to read.
    Outputs:
        - tuple_list: The list of tuples of user name and password.
        - content: The content of the file
    """
    tuple_list = []
    content = ""
    if not file_path:
        return tuple_list, content
    if len(file_path) == 2 and file_path[1]:
        try:
            with open(file_path[1], "r", encoding="utf-8") as file:
                content = file.read()
        except FileNotFoundError:
            logger.warning("Auth content file not found: %s", file_path[1])
    if file_path[0]:
        try:
            with open(file_path[0], "r", encoding="utf-8") as file:
                tuple_list = [
                    tuple(line.strip().split(",")) for line in file if line.strip()
                ]
        except FileNotFoundError:
            logger.warning("Auth file not found: %s", file_path[0])
    return tuple_list, content


def _has_ipv6() -> bool:
    """Check whether the system can bind an IPv6 socket."""
    try:
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.close()
        return True
    except OSError:
        return False


def open_browser_when_ready(port: int, timeout: float = 15.0) -> None:
    """Open the browser at a reachable local URL once the server is listening.

    Gradio's ``inbrowser=True`` opens the literal bind address
    (e.g. ``http://[::]:7860``), which browsers cannot reach on Windows.
    ``localhost`` resolves to whichever loopback address is listening.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("localhost", port), timeout=1):
                webbrowser.open(f"http://localhost:{port}")
                return
        except OSError:
            time.sleep(0.2)


def setup_gui(
    share: bool = False, auth_file: list = None, server_port=7860
) -> None:
    """
    Setup the GUI with the given parameters.

    Inputs:
        - share: Whether to share the GUI.
        - auth_file: The file path to read the user name and password.

    Outputs:
        - None
    """
    if auth_file is None:
        auth_file = ["", ""]
    user_list, html = parse_user_passwd(auth_file)

    auth_kwargs = {}
    if len(user_list) > 0:
        auth_kwargs = {"auth": user_list, "auth_message": html}

    # Compact startup banner for the console window
    print(
        f"\n  PDFMathTranslate v{__version__}"
        f"\n  界面地址: http://localhost:{server_port}"
        "\n  浏览器未自动打开时请手动访问；按 Ctrl+C 停止服务\n"
    )

    if flag_demo:
        threading.Thread(
            target=open_browser_when_ready, args=(server_port,), daemon=True
        ).start()
        demo.launch(server_name="0.0.0.0", max_file_size="5mb", inbrowser=False)
        return

    # Try binding addresses in order: "::" accepts both IPv4+IPv6 on most
    # dual-stack systems, "0.0.0.0" is IPv4-only, "127.0.0.1" is loopback,
    # and finally fall back to Gradio's share mode.
    bind_addresses = ["0.0.0.0", "127.0.0.1"]
    if _has_ipv6():
        bind_addresses.append("[::]")

    threading.Thread(
        target=open_browser_when_ready, args=(server_port,), daemon=True
    ).start()
    for addr in bind_addresses:
        try:
            demo.launch(
                server_name=addr,
                debug=True,
                inbrowser=False,
                share=share,
                server_port=server_port,
                **auth_kwargs,
            )
            return
        except Exception:
            print(
                f"Error launching GUI using {addr}.\n"
                "可能原因：端口被其他 pdf2zh 实例占用（请在任务管理器中结束残留的\n"
                "pdf2zh.exe 进程后重试），或代理软件的全局模式干扰了端口绑定。"
            )
            try:
                demo.close()  # release the port so the next attempt can bind
            except Exception:
                pass

    # Last resort: let Gradio create a share link
    demo.launch(
        debug=True,
        inbrowser=True,
        share=True,
        server_port=server_port,
        **auth_kwargs,
    )


# For auto-reloading while developing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    setup_gui()
