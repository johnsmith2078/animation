# LeetCode 题解动画流水线

这是一个分阶段、可落盘的题解视频生成骨架：

`题目 -> 题解 -> 时间轴脚本 -> Manim 代码 / edge-tts 配音 -> 合成视频`

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
- `Problem -> Solution` 提示词/自动生成骨架
- `Solution -> Timeline` 提示词/自动生成骨架
- 时间轴驱动的：
  - 配音脚本
  - 动画脚本
  - Manim 场景代码
  - edge-tts 渲染脚本
  - ffmpeg 合成脚本
- 音频生成后，按真实音频时长回写时间轴并重新生成 Manim 代码

暂未实现：

- 直接通过题号自动抓取 LeetCode 原题内容
  - 现在支持 `题目文件 / 内联题目文本 / 占位题号+标题`
  - 后续可以在 `ProblemProvider` 层接入 LeetCode 抓题
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
│   ├── manim_scene.py
│   ├── render_manim.sh
│   ├── render_tts.sh
│   └── tts_config.json
├── 05_outputs/
│   ├── audio/
│   │   ├── text/
│   │   ├── s01.mp3
│   │   └── s01.srt
│   └── video/
└── 06_final/
    └── compose.sh
```

## 快速开始

### 1) 准备题目输入

建议先准备一个 markdown 文件，比如：

```md
# 1. 两数之和

给定一个整数数组 nums 和一个整数 target，请你在数组中找出和为目标值 target 的那两个整数，并返回它们的下标。

- 可以假设每种输入只会对应一个答案
- 同一个元素不能重复使用
```

### 2) 可选：配置自动生成用的 LLM

如果你希望 `题目 -> 题解` 与 `题解 -> 时间轴` 自动完成，可设置一个 OpenAI-compatible 接口：

```bash
export LEETANIM_LLM_API_KEY="your-key"
export LEETANIM_LLM_MODEL="gpt-4.1-mini"
export LEETANIM_LLM_BASE_URL="https://api.openai.com/v1"
```

未配置时，项目也会继续生成完整骨架，但 `solution.md` 和 `timeline.json` 会退化为可人工编辑的模板/启发式结果。

### 3) 生成完整流水线骨架

```bash
python3 main.py all \
  --problem-file /path/to/problem.md \
  --problem-id 1 \
  --title "两数之和"
```

### 4) 生成配音

```bash
bash runs/<run_id>/04_codegen/render_tts.sh
```

可通过环境变量控制 voice：

```bash
export LEETANIM_VOICE="zh-CN-XiaoxiaoNeural"
export LEETANIM_RATE="+0%"
export LEETANIM_PITCH="+0Hz"
export LEETANIM_VOLUME="+0%"
```

### 5) 用真实音频时长回写时间轴

```bash
python3 main.py sync --run-dir runs/<run_id>
```

这一步会：

- 检查 `05_outputs/audio/*.mp3`
- 尝试用 `ffprobe` 读取真实时长
- 更新 `03_timeline/timeline.json`
- 重写 `voiceover_script.md`
- 重写 `animation_script.md`
- 重写 `04_codegen/manim_scene.py`

### 6) 渲染动画

```bash
bash runs/<run_id>/04_codegen/render_manim.sh
```

> `manimgl`/`manim-render` 的输出目录取决于你的 manim 配置。渲染后请将视觉视频放到：
>
> `runs/<run_id>/05_outputs/video/raw_visual.mp4`

### 7) 合成最终视频

```bash
bash runs/<run_id>/06_final/compose.sh runs/<run_id>/05_outputs/video/raw_visual.mp4
```

## CLI

```bash
python3 main.py ingest    # 仅创建 run 并保存题目
python3 main.py solution  # 生成题解
python3 main.py timeline  # 生成时间轴/配音脚本/动画脚本
python3 main.py manim     # 生成 manim_scene.py
python3 main.py tts       # 生成 edge-tts 文本资产与脚本
python3 main.py sync      # 按真实音频回写时间轴
python3 main.py compose   # 生成 compose.sh
python3 main.py all       # 一次完成以上阶段
```

## 关键设计

### 1. 时间轴是单一事实源

核心文件是 `03_timeline/timeline.json`。

它同时驱动：

- `voiceover_script.md`
- `animation_script.md`
- `manim_scene.py`
- `render_tts.sh`

这样可以保证动画与配音都围绕同一组 segment 时间轴生成。

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

1. 接入 `LeetCodeProvider`：支持 `题号 -> slug -> 题面`
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
