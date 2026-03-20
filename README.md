# LeetCode 题解动画流水线

这是一个分阶段、可落盘的题解视频生成骨架：

`题目 -> 题解 -> 时间轴脚本 -> Manim 代码 / edge-tts 配音 -> 合成视频`

现在 `Manim` 阶段会优先调用 LLM，根据 `timeline.json` 和 `animation_script.md` 生成真正的动画代码；只有在未配置 LLM 或生成失败时，才会回退到兜底骨架场景。

## 目标

- 支持从 **题号 / 标题 / 题目内容** 启动一个视频制作 run
- 每个阶段都保存中间产物，方便人工校对和二次编辑
- 先统一生成 **时间轴**，再分别生成动画脚本与配音脚本，保证同步
- 最后生成：
  - `Manim` 动画代码
  - `edge-tts` 配音脚本
  - `ffmpeg` 合成脚本

## 当前实现范围

已实现：

- 分阶段目录结构
- 题目入库
- 仅提供题号时，自动从 LeetCode 中文站抓取标题和题目描述
- `Problem -> Solution` 提示词/自动生成骨架
- `Solution -> Timeline` 提示词/自动生成骨架
- 时间轴驱动的：
  - 配音脚本
  - 动画脚本
  - LLM 生成的 Manim 场景代码
  - edge-tts 渲染脚本
  - ffmpeg 合成脚本
- 音频生成后，按真实音频时长回写时间轴并重新生成 Manim 代码

暂未实现：

- 高度定制化的算法动画
  - 当前自动生成的是“题解讲解型”场景骨架
  - 后续可以为双指针、二叉树、DP、回溯等题型增加专用动画模板

## 目录结构

执行一次 `all` 后，会生成：

```text
runs/<run_id>/
├── manifest.json
├── 01_problem/
│   ├── problem.json
│   └── problem.md
├── 02_solution/
│   ├── problem_to_solution.prompt.md
│   └── solution.md
├── 03_timeline/
│   ├── solution_to_timeline.prompt.md
│   ├── timeline.json
│   ├── voiceover_script.md
│   └── animation_script.md
├── 04_codegen/
│   ├── timeline_to_manim.prompt.md
│   ├── timeline_to_manim.response.md
│   ├── manim_scene.py
│   ├── render_manim.py
│   ├── render_tts.py
│   └── tts_config.json
├── 05_outputs/
│   ├── audio/
│   │   ├── text/
│   │   ├── s01.mp3
│   │   └── s01.srt
│   └── video/
└── 06_final/
    └── compose.py
```

## 快速开始

### 1) 准备题目输入

可以直接只传题号自动抓题：

```bash
python main.py ingest --problem-id 1
```

也可以继续手工准备一个 markdown 文件，比如：

```md
# 1. 两数之和

给定一个整数数组 nums 和一个整数 target，请你在数组中找出和为目标值 target 的那两个整数，并返回它们的下标。

- 可以假设每种输入只会对应一个答案
- 同一个元素不能重复使用
```

### 2) 可选：通过 `.env` 配置自动生成用的 LLM

项目会在启动时自动加载根目录下的 `.env`。推荐做法是先复制一份示例配置：

```bash
cp .env.example .env
```

然后在 `.env` 里填写你的本地配置，例如：

```dotenv
LEETANIM_LLM_API_KEY=your-key
LEETANIM_LLM_MODEL=gpt-4.1-mini
LEETANIM_LLM_BASE_URL=https://api.openai.com/v1
```

`.env` 已加入 `.gitignore`，不会被提交；仓库中保留的是可共享的 `.env.example`。
如果某些 OpenAI-compatible 服务偶发断流，可额外配置 `LEETANIM_LLM_MAX_TOKENS`、`LEETANIM_LLM_MAX_RETRIES`、`LEETANIM_LLM_RETRY_BACKOFF_SEC` 和 `LEETANIM_LLM_MAX_CONTINUATIONS`。其中 `LEETANIM_LLM_MAX_TOKENS` 是单轮生成上限；如果模型因为 `finish_reason=length` 被截断，流水线会自动续写，直到自然收尾或达到 continuation 上限。如果 Manim 代码生成经常被截断，可单独调大 `LEETANIM_MANIM_MAX_TOKENS`。

未配置时，项目也会继续生成完整骨架，但 `solution.md` 和 `timeline.json` 会退化为可人工编辑的模板/启发式结果。

### 3) 一步生成到最终视频

```bash
uv run make_video.py \
  --problem-id 1
```

这个脚本会自动顺序执行：

- `main.py all`
- `runs/<run_id>/04_codegen/render_tts.py`
- `main.py sync --run-dir runs/<run_id>`
- `runs/<run_id>/04_codegen/render_manim.py`
- `runs/<run_id>/06_final/compose.py runs/<run_id>/05_outputs/video/raw_visual.mp4`

成功后，最终视频默认输出到：

`runs/<run_id>/06_final/final_video.mp4`

如果你已经有现成的视觉视频，也可以额外传：

```bash
uv run make_video.py \
  --problem-id 1 \
  --video-input /path/to/raw_visual.mp4
```

### 4) 仅生成完整流水线骨架

```bash
python main.py all \
  --problem-id 1
```

### 5) 生成配音

```bash
python runs/<run_id>/04_codegen/render_tts.py
```

可通过 `.env` 控制 voice：

```dotenv
LEETANIM_VOICE=zh-CN-XiaoxiaoNeural
LEETANIM_RATE=+0%
LEETANIM_PITCH=+0Hz
LEETANIM_VOLUME=+0%
```

### 6) 用真实音频时长回写时间轴

```bash
python main.py sync --run-dir runs/<run_id>
```

这一步会：

- 检查 `05_outputs/audio/*.mp3`
- 尝试用 `ffprobe` 读取真实时长
- 更新 `03_timeline/timeline.json`
- 重写 `voiceover_script.md`
- 重写 `animation_script.md`
- 重写 `04_codegen/manim_scene.py`

### 7) 渲染动画

```bash
python runs/<run_id>/04_codegen/render_manim.py
```

`manim` 阶段会先把 prompt 写到 `04_codegen/timeline_to_manim.prompt.md`，再把模型原始输出写到 `04_codegen/timeline_to_manim.response.md`，最后产出 `manim_scene.py`。如果 LLM 不可用或输出无效 Python，才会回退到兜底场景骨架。

如果中文文字显示成方块、乱码或十六进制码位，可在 `.env` 里显式指定：

```dotenv
LEETANIM_MANIM_FONT=Microsoft YaHei
```

> `manimgl`/`manim-render` 的输出目录取决于你的 manim 配置。渲染后请将视觉视频放到：
>
> `runs/<run_id>/05_outputs/video/raw_visual.mp4`

### 8) 合成最终视频

```bash
python runs/<run_id>/06_final/compose.py runs/<run_id>/05_outputs/video/raw_visual.mp4
```

compose 阶段会自动把 `05_outputs/audio/*.srt` 合并成 `06_final/final_subtitles.srt`，并烧录到 `06_final/final_video.mp4`。因此生成 Manim 动画时应默认给底部字幕留出安全区。

## CLI

```bash
python main.py ingest    # 仅创建 run 并保存题目
python main.py solution  # 生成题解
python main.py timeline  # 生成时间轴/配音脚本/动画脚本
python main.py manim     # 生成 manim_scene.py 与 render_manim.py
python main.py tts       # 生成 edge-tts 文本资产与 render_tts.py
python main.py sync      # 按真实音频回写时间轴
python main.py compose   # 生成 compose.py
python main.py all       # 一次完成以上阶段
```

## 关键设计

### 1. 时间轴是单一事实源

核心文件是 `03_timeline/timeline.json`。

它同时驱动：

- `voiceover_script.md`
- `animation_script.md`
- `manim_scene.py`
- `render_tts.py`

这样可以保证动画与配音都围绕同一组 segment 时间轴生成。需要注意的是，`animation_script.md` 现在是给 LLM 生成动画代码的“指导输入”，不应该再被直接当成屏幕文字渲染。

### 2. 先估时，再用真实音频校准

1. 初次生成 timeline 时，按文本长度估算时长
2. 生成 edge-tts 音频后，读取真实 mp3 时长
3. 回写到 timeline
4. 再重新生成 manim 代码

这能解决“脚本同步了，但真正配音时长和估计不一致”的问题。

### 3. 中间产物全部可编辑

你可以人工修改：

- `02_solution/solution.md`
- `03_timeline/timeline.json`
- `03_timeline/voiceover_script.md`
- `03_timeline/animation_script.md`
- `04_codegen/manim_scene.py`

再单独重跑后续阶段。

## 推荐的下一步扩展

1. 为常见题型增加更强的专用动画模板，而不是只依赖通用讲解骨架
2. 增加算法模板：
   - 数组/哈希
   - 双指针
   - 滑动窗口
   - 链表
   - 树/图
   - DP
   - 回溯
3. 增加代码高亮与指针移动动画
4. 增加字幕 burn-in / 封面 / BGM / 片头片尾
5. 接入更强的“解题结构化生成器”，把题解拆成：
   - intuition
   - invariant
   - walkthrough
   - complexity
   - pitfalls
   - code explanation
