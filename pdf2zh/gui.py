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
        vertical-align: middle;
    }
    /* Icon inline with section labels */
    .section-icon {
        width: 15px !important;
        height: 15px !important;
        vertical-align: -2px;
        margin-right: 5px;
        opacity: 0.85;
    }
    .icon-heading {
        margin: 2px 0 0 0 !important;
        padding: 0 !important;
        line-height: 1.6;
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
            service = gr.Dropdown(
                label="翻译服务",
                choices=enabled_services,
                value=enabled_services[0],
            )
            envs = []
            for i in range(3):
                envs.append(
                    gr.Textbox(
                        visible=False,
                        interactive=True,
                    )
                )
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
                for i, env in enumerate(translator.envs.items()):
                    label = env[0]
                    value = ConfigManager.get_env_by_translatername(
                        translator, env[0], env[1]
                    )
                    visible = True
                    if hidden_gradio_details:
                        if (
                            "MODEL" not in str(label).upper()
                            and value
                            and hidden_gradio_details
                        ):
                            visible = False
                        # Hidden Keys From Gradio
                        if "API_KEY" in label.upper():
                            value = "***"  # We use "***" Present Real API_KEY
                    _envs[i] = gr.update(
                        visible=visible,
                        label=label,
                        value=value,
                    )
                _envs[-1] = gr.update(visible=translator.CustomPrompt)
                return _envs

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
                service,
                envs,
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
                "This may be caused by global mode of proxy software."
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
