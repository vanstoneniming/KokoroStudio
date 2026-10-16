# Kokoro Studio v2.0.2（本地语音合成）

[English](README.md)

**Kokoro Studio** 是一个在本机运行的文本转语音程序，使用 **Kokoro-82M** 模型。合成过程不依赖在线语音服务。有 NVIDIA 显卡时走 CUDA，否则自动改用 CPU。

## 这个版本主要是英语

是的，**当前这个界面只接了英语模型**。

内置音色全部来自 [hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M)，一共 21 个，都是美式英语或英式英语，例如 Alice、Heart、George。程序启动时按美式英语加载语音管线，不会按普通话处理中文。

把中文句子贴进去，不会得到正常的中文发音。Kokoro 官方另有中文权重 [Kokoro-82M-v1.1-zh](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh)，这个图形界面目前没有接入它。

英文短句、英文有声书可以用。中文有声书不要用这个包来做。

## 以后再接中文（尚未实现）

2026-10-16 查过，先记在这里，当前版本不改代码。

中文不能靠把现有英语音色换成中文来完成。界面启动时固定调用 `build_pipeline()`，语言代码默认是 `a`（美式英语），仓库是 `hexgrad/Kokoro-82M`。中文要单独建一条管线：

```python
KPipeline(lang_code="z", repo_id="hexgrad/Kokoro-82M-v1.1-zh", device=device)
```

对应权重文件是 `kokoro-v1_1-zh.pth`。库在 `kokoro/model.py` 的 `MODEL_NAMES` 里已经登记了这个文件名。语言代码 `z` 会走 `misaki.zh.ZHG2P`。仓库名不是以 `/Kokoro-82M` 结尾，所以会使用 1.1 前端。

接入时要补的内容：

1. 安装 `misaki[zh]`。它依赖结巴分词、`pypinyin`、`cn2an`。2026-10-16 检查时这三项都还没装。`misaki/zh.py` 已经在包里。
2. 侧栏增加语言切换。切到中文时重建管线，并换成中文音色列表。`tts_wrapper.py` 里现在只建一条管线。
3. 音色只用 `zf_`（女声）和 `zm_`（男声）。官方仓库 `voices/` 下大约有 100 个，名字类似 `zf_001.pt`、`zm_009.pt`。同一仓库里还有 `af_maple`、`af_sol`、`bf_vale`，那是英语音色，不要放进中文管线。英语音色和中文音色不能在同一次合成里混合。
4. 离线包要另放中文权重和这些音色。体积与英语模型同一量级，第一次运行也会从 Hugging Face 下载。打包脚本 `packaging/build_windows_bundle.py` 目前只收英语的 21 个音色。
5. 中文句子里夹的英文，1.1 前端在没有 `en_callable` 时可能会丢掉。第一版按纯中文文本来做。

## 已包含的功能

* 有 NVIDIA 显卡时用 CUDA 加速，没有就用 CPU。
* 有声书模式：导入 TXT 或 EPUB，按段管理。
* 两个音色可以混合。
* 工程可保存为 `.kproj`，音色和文本分段都能留下。
* 可调语速、音高和采样率。
* 可以把文本或工程文件拖进窗口。
* 能试听单句、播放结果、保存音频，并看简易波形。

## Windows 使用

### 从源码安装

1. 下载本仓库。
2. 双击 `run.bat`。

脚本会创建 Python 环境。检测到可用的 NVIDIA 驱动时，会安装对应的 CUDA 版 PyTorch，然后启动程序。PyTorch 已经装好时不会重复安装。

环境坏了可以关掉程序后执行：

```bat
run.bat reinstall
```

### 本机打好的离线包

如果拿到的是已经打好的 `KokoroStudio-Windows` 目录或同名 zip：

1. 解压到 64 位 Windows 10/11。
2. 双击 `启动.bat`。
3. 打不开时先双击 `检查环境.bat`。

这个离线包自带 Python 3.11、CPU 版 PyTorch、Kokoro-82M 权重、21 个英语音色、英语分词模型 `en_core_web_sm`、espeak-ng 和 ffmpeg。解压后不用再下载模型。它用 CPU 推理，没有 NVIDIA 显卡也能跑。若提示缺少 `VCRUNTIME140.dll`，安装微软 Visual C++ 2015–2022 可再发行组件（x64）。

离线包大约 1 GB，超过 GitHub 普通文件限制，所以仓库里只保留打包脚本 `packaging/build_windows_bundle.py`，不把压缩包放进 Git。

## macOS 使用

已有虚拟环境时，在项目目录执行：

```bash
HF_ENDPOINT=https://hf-mirror.com .venv/bin/python main.py
```

第一次运行会从 Hugging Face 下载约 300 MB 的模型权重。国内网络可以设置 `HF_ENDPOINT=https://hf-mirror.com`。英语分词还需要 spaCy 模型 `en_core_web_sm`，缺失时界面能打开，但合成会失败。

这台 Mac 没有 NVIDIA GPU，实际会走 CPU。

## 怎么用

界面有两个主区域：

### 速写板

适合试音色或读短句。输入英文，在侧栏选音色，点合成。

### 有声书

* 拖入 `.txt` 或 `.epub`。
* 文本会拆成多行。
* 每一行可以指定不同音色。
* 点某一行的播放按钮只听这一句。
* 点渲染有声书，把各行合成一个 WAV 或 MP3。

侧栏还可以调主音色、混合音色、语速、音高、采样率，以及查看当前是 GPU 还是 CPU。

## 常见问题

* 界面显示 **Device: CPU (Slow)**：当前没有可用的 CUDA，合成会慢一些，但可以继续用。
* 首次启动下载模型失败：检查网络，或使用 Hugging Face 镜像。
* MP3 导出或播放失败：确认系统里有 `ffmpeg`，并且在 `PATH` 中。离线包已经自带。
* 很长的 MP3 会占较多内存。长篇有声书更适合导出 WAV。

## 许可证

Apache License 2.0，见 `LICENSE`。

模型同样基于 Apache License 2.0 的 [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M)。
