#!/usr/bin/env python3
"""把 Kokoro Studio 打成 Windows 64 位离线发行目录。

在 macOS 或 Linux 上运行。脚本会下载 Windows 嵌入式 Python、
win_amd64 依赖轮子、Kokoro 模型、全部内置音色、spaCy 英语分词模型和 ffmpeg，
组装成解压后双击即可启动的目录。

用法:
    python packaging/build_windows_bundle.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist" / "KokoroStudio-Windows"
PYTHON_DIR = DIST / "runtime" / "python"
SITE_PACKAGES = PYTHON_DIR / "Lib" / "site-packages"
APP_DIR = DIST / "app"
HF_SNAPSHOT = (
    DIST
    / "runtime"
    / "hf-home"
    / "hub"
    / "models--hexgrad--Kokoro-82M"
    / "snapshots"
    / "f3ff3571791e39611d31c381e3a41a3af07b4987"
)
COMMIT = "f3ff3571791e39611d31c381e3a41a3af07b4987"
LOCAL_MODEL_CACHE = Path.home() / ".cache" / "huggingface" / "hub" / "models--hexgrad--Kokoro-82M"
SPACY_WHEEL = Path("/tmp/en_core_web_sm-3.8.0-py3-none-any.whl")
# 本机代理。Clash 等工具的混合端口，慢的时候优先走这里。
PROXY = os.environ.get("KOKORO_PROXY", "http://127.0.0.1:7897")

VOICES = [
    "af_bella", "af_sarah", "af_nicole", "af_sky", "af_heart",
    "af_alloy", "af_aoede", "af_kore",
    "am_adam", "am_michael", "am_onyx", "am_puck", "am_fenrir",
    "bf_emma", "bf_isabella", "bf_alice", "bf_lily",
    "bm_george", "bm_lewis", "bm_daniel", "bm_fable",
]

APP_FILES = [
    "main.py",
    "ui_main.py",
    "tts_wrapper.py",
    "models.py",
    "persistence.py",
    "error_handler.py",
    "logging_setup.py",
    "config.yaml",
    "LICENSE",
]

# 与当前已验证环境对齐。不装 WebEngine，界面用不到。
# torch 走 CPU 轮子，这样没有 NVIDIA 显卡的电脑也能直接运行。
RUNTIME_PACKAGES = [
    "kokoro==0.9.4",
    "misaki==0.9.4",
    "soundfile==0.14.0",
    "huggingface-hub==2.2.0",
    "pydub==0.25.1",
    "espeakng-loader==0.2.4",
    "phonemizer-fork==3.3.2",
    "PySide6==6.12.0",
    "PyYAML==6.0.3",
    "munch==4.0.0",
    "librosa==0.11.0",
    "EbookLib==0.20",
    "beautifulsoup4==4.15.0",
    "spacy==3.7.5",
    "numpy==1.26.4",
]


def log(message: str) -> None:
    """打印打包阶段信息。"""
    print(message, flush=True)


def download(urls: list[str], dest: Path) -> None:
    """按顺序尝试多个地址，把文件下载到 dest。

    Args:
        urls: 候选下载地址，前面的优先。
        dest: 本地保存路径。已存在且非空时跳过。
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 0:
        log(f"已存在，跳过下载: {dest.name} ({dest.stat().st_size} 字节)")
        return
    partial = dest.with_suffix(dest.suffix + ".part")
    last_error = None
    attempts = []
    if PROXY:
        attempts.append(PROXY)
    attempts.append("")
    for url in urls:
        for proxy in attempts:
            via = f" 经由 {proxy}" if proxy else " 直连"
            log(f"下载 {url}{via}")
            try:
                if partial.exists():
                    partial.unlink()
                command = [
                    "curl", "-fL", "--retry", "2", "--connect-timeout", "15",
                    "--max-time", "600", "-o", str(partial), url,
                ]
                if proxy:
                    command[1:1] = ["-x", proxy]
                subprocess.run(command, check=True)
                if partial.stat().st_size < 1024:
                    raise RuntimeError(f"文件过小: {partial.stat().st_size}")
                partial.replace(dest)
                log(f"完成 {dest.name} ({dest.stat().st_size} 字节)")
                return
            except Exception as exc:  # noqa: BLE001 - 换下一个镜像继续
                last_error = exc
                log(f"失败，尝试下一个地址: {exc}")
                if partial.exists():
                    partial.unlink()
    raise RuntimeError(f"全部地址都下载失败: {dest.name}: {last_error}")


def prepare_embed_python() -> None:
    """下载 Windows 嵌入式 Python 3.11，并打开 site-packages。"""
    archive = ROOT / "dist" / "cache" / "python-3.11.9-embed-amd64.zip"
    download(
        [
            "https://npmmirror.com/mirrors/python/3.11.9/python-3.11.9-embed-amd64.zip",
            "https://mirrors.huaweicloud.com/python/3.11.9/python-3.11.9-embed-amd64.zip",
            "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip",
        ],
        archive,
    )
    if not (PYTHON_DIR / "python.exe").exists():
        if PYTHON_DIR.exists():
            shutil.rmtree(PYTHON_DIR)
        PYTHON_DIR.mkdir(parents=True)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(PYTHON_DIR)
    pth_files = list(PYTHON_DIR.glob("python*._pth"))
    if not pth_files:
        raise RuntimeError("嵌入式 Python 里没有 ._pth 文件")
    # 默认关闭了 site，第三方库不会被加载。这里显式打开。
    pth_files[0].write_text(
        "python311.zip\n.\nLib\\site-packages\nimport site\n",
        encoding="utf-8",
    )
    log(f"嵌入式 Python 就绪: {pth_files[0].name}")


def install_windows_packages() -> None:
    """把 Windows 64 位依赖安装进嵌入式 Python 的 site-packages。"""
    marker = SITE_PACKAGES / ".kokoro_bundle_ok"
    if marker.exists() and (SITE_PACKAGES / "torch").exists() and (SITE_PACKAGES / "PySide6").exists():
        log("Windows 依赖已安装，跳过")
        return
    SITE_PACKAGES.mkdir(parents=True, exist_ok=True)
    pip = [sys.executable, "-m", "pip", "install", "--upgrade", "--target", str(SITE_PACKAGES)]
    platform_flags = [
        "--platform", "win_amd64",
        "--python-version", "3.11",
        "--implementation", "cp",
        "--only-binary", ":all:",
    ]
    log("安装 CPU 版 PyTorch（Windows amd64）")
    subprocess.run(
        pip + platform_flags + [
            "torch==2.14.1",
            "numpy==1.26.4",
            "--index-url", "https://download.pytorch.org/whl/cpu",
            "--extra-index-url", "https://pypi.tuna.tsinghua.edu.cn/simple",
        ],
        check=True,
    )
    log("安装界面、分词和音频依赖")
    subprocess.run(
        pip + platform_flags + RUNTIME_PACKAGES + [
            "--index-url", "https://pypi.tuna.tsinghua.edu.cn/simple",
        ],
        check=True,
    )
    if not SPACY_WHEEL.is_file():
        download(
            [
                "https://ghproxy.net/https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl",
                "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl",
            ],
            SPACY_WHEEL,
        )
    log("安装英语分词模型 en_core_web_sm")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--target", str(SITE_PACKAGES), "--no-deps", str(SPACY_WHEEL)],
        check=True,
    )
    marker.write_text("ok\n", encoding="utf-8")


def copy_app() -> None:
    """复制界面程序本身，不带开发环境和历史输出。"""
    APP_DIR.mkdir(parents=True, exist_ok=True)
    for name in APP_FILES:
        src = ROOT / name
        if src.is_file():
            shutil.copy2(src, APP_DIR / name)
    (APP_DIR / "outputs").mkdir(exist_ok=True)
    (APP_DIR / "voices").mkdir(exist_ok=True)
    log("程序文件已复制")


def _copy_real(src: Path, dest: Path) -> None:
    """复制文件内容。源文件是符号链接时也复制真实数据。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size == src.stat().st_size and dest.stat().st_size > 0:
        return
    shutil.copyfile(src, dest)


def bundle_models() -> None:
    """放入 Kokoro 权重、配置和全部内置音色，并写成 Hugging Face 离线缓存结构。"""
    snapshot_src = LOCAL_MODEL_CACHE / "snapshots" / COMMIT
    config_src = snapshot_src / "config.json"
    weight_src = snapshot_src / "kokoro-v1_0.pth"
    if not config_src.exists() or not weight_src.exists():
        raise RuntimeError(f"本地没有 Kokoro 模型缓存: {snapshot_src}")
    _copy_real(config_src, HF_SNAPSHOT / "config.json")
    _copy_real(weight_src, HF_SNAPSHOT / "kokoro-v1_0.pth")

    refs = HF_SNAPSHOT.parents[1] / "refs"
    refs.mkdir(parents=True, exist_ok=True)
    (refs / "main").write_text(COMMIT, encoding="utf-8")

    voice_dir = HF_SNAPSHOT / "voices"
    voice_dir.mkdir(parents=True, exist_ok=True)
    for name in VOICES:
        dest = voice_dir / f"{name}.pt"
        local = snapshot_src / "voices" / f"{name}.pt"
        if local.exists():
            _copy_real(local, dest)
            continue
        download(
            [
                f"https://huggingface.co/hexgrad/Kokoro-82M/resolve/main/voices/{name}.pt",
                f"https://hf-mirror.com/hexgrad/Kokoro-82M/resolve/main/voices/{name}.pt",
            ],
            dest,
        )
    log(f"模型与 {len(VOICES)} 个音色已放入离线缓存")


def bundle_ffmpeg() -> None:
    """放入 Windows 版 ffmpeg，供 MP3 导出使用。"""
    ffmpeg_dir = DIST / "runtime" / "ffmpeg"
    exe = ffmpeg_dir / "ffmpeg.exe"
    if exe.exists() and exe.stat().st_size > 1_000_000:
        log("ffmpeg.exe 已存在，跳过")
        return
    archive = ROOT / "dist" / "cache" / "ffmpeg-win64.zip"
    download(
        [
            "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
            "https://ghproxy.net/https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
        ],
        archive,
    )
    ffmpeg_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        names = [n for n in zf.namelist() if n.endswith("/bin/ffmpeg.exe") or n.endswith("bin/ffmpeg.exe")]
        if not names:
            raise RuntimeError("压缩包里没有 ffmpeg.exe")
        target_name = names[0]
        with zf.open(target_name) as src, exe.open("wb") as out:
            shutil.copyfileobj(src, out)
    log(f"ffmpeg.exe 已放入 ({exe.stat().st_size} 字节)")


def write_launchers() -> None:
    """写启动脚本和使用说明。"""
    (DIST / "启动.bat").write_text(
        """@echo off
chcp 65001 >nul
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%app"
set "HF_HOME=%ROOT%runtime\\hf-home"
set "HF_HUB_CACHE=%ROOT%runtime\\hf-home\\hub"
set "HF_HUB_OFFLINE=1"
set "HF_HUB_DISABLE_TELEMETRY=1"
set "TRANSFORMERS_OFFLINE=1"
set "HF_DATASETS_OFFLINE=1"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONDONTWRITEBYTECODE=1"
set "PATH=%ROOT%runtime\\ffmpeg;%ROOT%runtime\\python;%PATH%"
"%ROOT%runtime\\python\\python.exe" main.py
if errorlevel 1 (
    echo.
    echo 程序异常退出。请把上面的文字保存下来排查。
    pause
)
""",
        encoding="utf-8",
        newline="\r\n",
    )
    (DIST / "检查环境.bat").write_text(
        """@echo off
chcp 65001 >nul
setlocal
set "ROOT=%~dp0"
set "HF_HOME=%ROOT%runtime\\hf-home"
set "HF_HUB_CACHE=%ROOT%runtime\\hf-home\\hub"
set "HF_HUB_OFFLINE=1"
set "TRANSFORMERS_OFFLINE=1"
set "PYTHONUTF8=1"
set "PATH=%ROOT%runtime\\ffmpeg;%ROOT%runtime\\python;%PATH%"
"%ROOT%runtime\\python\\python.exe" -c "import torch,PySide6,spacy,kokoro,soundfile,espeakng_loader; nlp=spacy.load('en_core_web_sm'); print('环境正常'); print('torch', torch.__version__); print('spacy', spacy.__version__); print('分词', [t.text for t in nlp('Hello world')])"
echo.
pause
""",
        encoding="utf-8",
        newline="\r\n",
    )
    (DIST / "使用说明.txt").write_text(
        """Kokoro Studio Windows 离线包
============================

这是 64 位 Windows 10/11 的离线发行目录，已经带上：

- Python 3.11 运行时
- 界面、音频和语音合成依赖（CPU 版 PyTorch）
- Kokoro-82M 模型权重
- 21 个内置英语音色
- 英语分词模型 en_core_web_sm
- espeak-ng 兜底发音库
- ffmpeg（用于导出和播放 MP3）

使用方法
--------
1. 把整个文件夹拷到 Windows 电脑，路径不要有特殊限制。
2. 双击「启动.bat」。
3. 第一次打开会在 CPU 上加载模型，大约需要几秒到十几秒。
4. 生成的音频在 app\\outputs 目录。

检查
----
如果打不开，先双击「检查环境.bat」。
它会打印 torch、spaCy 和分词结果。窗口里出现「环境正常」就说明运行库齐全。

说明
----
- 这个包使用 CPU 推理，没有 NVIDIA 显卡也能用。
- 不需要再联网下载模型或分词库。
- 若提示缺少 VCRUNTIME140.dll，请安装微软「Visual C++ 2015-2022 可再发行组件 (x64)」。
  Windows 10/11 多数已经自带。
""",
        encoding="utf-8",
        newline="\r\n",
    )


def verify_layout() -> None:
    """检查发行目录里的关键文件是否齐全。"""
    required = [
        PYTHON_DIR / "python.exe",
        PYTHON_DIR / "python311.zip",
        SITE_PACKAGES / "torch" / "__init__.py",
        SITE_PACKAGES / "PySide6" / "__init__.py",
        SITE_PACKAGES / "en_core_web_sm" / "__init__.py",
        SITE_PACKAGES / "kokoro" / "__init__.py",
        SITE_PACKAGES / "espeakng_loader" / "espeak-ng.dll",
        HF_SNAPSHOT / "kokoro-v1_0.pth",
        HF_SNAPSHOT / "config.json",
        DIST / "runtime" / "ffmpeg" / "ffmpeg.exe",
        APP_DIR / "main.py",
        DIST / "启动.bat",
    ]
    missing = [str(path.relative_to(DIST)) for path in required if not path.exists()]
    voices = list((HF_SNAPSHOT / "voices").glob("*.pt"))
    if len(voices) != len(VOICES):
        missing.append(f"voices ({len(voices)}/{len(VOICES)})")
    weight = (HF_SNAPSHOT / "kokoro-v1_0.pth").stat().st_size if (HF_SNAPSHOT / "kokoro-v1_0.pth").exists() else 0
    if weight < 100_000_000:
        missing.append(f"kokoro-v1_0.pth 过小 ({weight})")
    if missing:
        raise RuntimeError("发行包不完整: " + ", ".join(missing))
    log(f"目录检查通过，音色 {len(voices)} 个，模型 {weight / 1024 / 1024:.0f} MB")


def main() -> None:
    """按顺序组装 Windows 离线发行目录。"""
    os.chdir(ROOT)
    (ROOT / "dist" / "cache").mkdir(parents=True, exist_ok=True)
    prepare_embed_python()
    install_windows_packages()
    copy_app()
    bundle_models()
    bundle_ffmpeg()
    write_launchers()
    verify_layout()
    log(f"发行目录: {DIST}")


if __name__ == "__main__":
    main()
