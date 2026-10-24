"""``pdf2zh.app_paths`` 与配置 / 缓存目录迁移的单元测试。

覆盖点：
- ``app_root`` 的源码模式推导、``PDF2ZH_HOME`` 覆盖、便携版 site-packages 布局；
- ``cache_dir`` 的路径拼接与目录创建（含进程内缓存）；
- ``ensure_hidden`` 不抛异常，并在 Windows 上真正设置隐藏属性位；
- 配置读写落盘到 ``<app_root>/config/pdf-cache/config.json``；
- 旧配置 ``~/.config/PDFMathTranslate/config.json`` 的自动迁移。
"""

import ctypes
import json
import os
from pathlib import Path

import pytest

import pdf2zh
from pdf2zh import app_paths
from pdf2zh.app_paths import app_root, cache_dir, ensure_hidden
from pdf2zh.config import ConfigManager

FILE_ATTRIBUTE_HIDDEN = 0x02
INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF


@pytest.fixture(autouse=True)
def _reset_state():
    """每个测试前后清理进程内缓存与 ConfigManager 单例，避免相互污染。"""
    ConfigManager._instance = None
    app_paths._cache_dir_cache.clear()
    yield
    ConfigManager._instance = None
    app_paths._cache_dir_cache.clear()


# --------------------------------------------------------------------------- #
# app_root
# --------------------------------------------------------------------------- #
def test_app_root_source_mode(monkeypatch):
    """源码 / 开发模式下 app_root 等于仓库根（pdf2zh 包的父目录）。"""
    monkeypatch.delenv(app_paths.ENV_APP_HOME, raising=False)
    expected = Path(pdf2zh.__file__).resolve().parent.parent
    assert app_root() == expected


def test_app_root_env_override(tmp_path, monkeypatch):
    """PDF2ZH_HOME 存在时优先返回其解析后的绝对路径。"""
    monkeypatch.setenv(app_paths.ENV_APP_HOME, str(tmp_path))
    assert app_root() == tmp_path.resolve()


def test_app_root_portable_layout(tmp_path, monkeypatch):
    """当包位于 <root>/site-packages/pdf2zh 时，返回 site-packages 的父目录。"""
    monkeypatch.delenv(app_paths.ENV_APP_HOME, raising=False)
    fake_root = tmp_path / "build"
    fake_file = fake_root / "site-packages" / "pdf2zh" / "app_paths.py"
    fake_file.parent.mkdir(parents=True, exist_ok=True)
    fake_file.touch()
    monkeypatch.setattr(app_paths, "__file__", str(fake_file))
    assert app_root() == fake_root.resolve()


# --------------------------------------------------------------------------- #
# cache_dir
# --------------------------------------------------------------------------- #
def test_cache_dir_path_and_creation(tmp_path, monkeypatch):
    """cache_dir 返回 <app_root>/config/pdf-cache 并确保目录已创建。"""
    monkeypatch.setenv(app_paths.ENV_APP_HOME, str(tmp_path))
    result = cache_dir()
    assert result == app_root() / "config" / "pdf-cache"
    assert result.is_dir()
    # 二级父目录 config 也应存在
    assert result.parent.is_dir()
    # 进程内缓存：再次调用返回同一路径，不重复创建
    assert cache_dir() == result


@pytest.mark.skipif(os.name != "nt", reason="Windows 隐藏属性仅 Windows 可用")
def test_cache_dir_hidden_on_windows(tmp_path, monkeypatch):
    """cache_dir 创建的目录在 Windows 上带隐藏属性位。"""
    monkeypatch.setenv(app_paths.ENV_APP_HOME, str(tmp_path))
    target = cache_dir()
    kernel32 = ctypes.windll.kernel32
    for candidate in (target, target.parent):
        attrs = kernel32.GetFileAttributesW(str(candidate))
        assert attrs != INVALID_FILE_ATTRIBUTES
        assert attrs & FILE_ATTRIBUTE_HIDDEN, f"{candidate} 未设置隐藏属性"


# --------------------------------------------------------------------------- #
# ensure_hidden
# --------------------------------------------------------------------------- #
def test_ensure_hidden_never_raises(tmp_path):
    """ensure_hidden 对各种入参均不抛异常（best-effort）。"""
    directory = tmp_path / "some_dir"
    directory.mkdir()
    ensure_hidden(directory)  # Path 入参
    ensure_hidden(str(directory))  # 字符串入参
    ensure_hidden(tmp_path / "does_not_exist")  # 不存在的路径

    file_path = tmp_path / "some_file.txt"
    file_path.write_text("x", encoding="utf-8")
    ensure_hidden(file_path)


@pytest.mark.skipif(os.name != "nt", reason="Windows 隐藏属性仅 Windows 可用")
def test_ensure_hidden_sets_attribute_on_windows(tmp_path):
    """Windows 上调用后应读取到 FILE_ATTRIBUTE_HIDDEN 位。"""
    target = tmp_path / "hidden_dir"
    target.mkdir()
    ensure_hidden(target)

    kernel32 = ctypes.windll.kernel32
    attrs = kernel32.GetFileAttributesW(str(target))
    assert attrs != INVALID_FILE_ATTRIBUTES
    assert attrs & FILE_ATTRIBUTE_HIDDEN

    # 保留原有属性位（目录位不应被清除，且重复调用幂等）
    ensure_hidden(target)
    assert kernel32.GetFileAttributesW(str(target)) & FILE_ATTRIBUTE_HIDDEN


# --------------------------------------------------------------------------- #
# 配置读写与迁移
# --------------------------------------------------------------------------- #
def test_config_read_write_lands_in_app_root(tmp_path, monkeypatch):
    """配置读写应落盘到 <PDF2ZH_HOME>/config/pdf-cache/config.json。"""
    app_home = tmp_path / "app"
    fake_home = tmp_path / "home"
    monkeypatch.setenv(app_paths.ENV_APP_HOME, str(app_home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    ConfigManager._instance = None

    ConfigManager.set("hello", "world")
    assert ConfigManager.get("hello") == "world"

    config_file = app_home / "config" / "pdf-cache" / "config.json"
    assert config_file.is_file()
    data = json.loads(config_file.read_text(encoding="utf-8"))
    assert data["hello"] == "world"


def test_config_migrates_legacy_file(tmp_path, monkeypatch):
    """新位置不存在而旧位置存在时，旧配置被复制到新位置并加载。"""
    app_home = tmp_path / "app"
    fake_home = tmp_path / "home"
    legacy = fake_home / ".config" / "PDFMathTranslate" / "config.json"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(json.dumps({"legacy_key": "legacy_value"}), encoding="utf-8")

    monkeypatch.setenv(app_paths.ENV_APP_HOME, str(app_home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    ConfigManager._instance = None

    assert ConfigManager.get("legacy_key") == "legacy_value"

    config_file = app_home / "config" / "pdf-cache" / "config.json"
    assert config_file.is_file()
    assert legacy.is_file()  # 复制而非移动，旧文件保留


def test_config_does_not_overwrite_existing_new_file(tmp_path, monkeypatch):
    """新位置已存在时不应被旧配置覆盖。"""
    app_home = tmp_path / "app"
    fake_home = tmp_path / "home"
    new_config = app_home / "config" / "pdf-cache" / "config.json"
    new_config.parent.mkdir(parents=True, exist_ok=True)
    new_config.write_text(json.dumps({"key": "new"}), encoding="utf-8")

    legacy = fake_home / ".config" / "PDFMathTranslate" / "config.json"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(json.dumps({"key": "legacy"}), encoding="utf-8")

    monkeypatch.setenv(app_paths.ENV_APP_HOME, str(app_home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    ConfigManager._instance = None

    assert ConfigManager.get("key") == "new"
