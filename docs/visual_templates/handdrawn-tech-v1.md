# handdrawn-tech-v1

中文手绘技术解释页模板，用于把 AI / Agent / 工具实践类内容做成统一风格的文章配图、PPT 页面、抖音封面和口播视频素材。

## 适用场景

- 抖音 / 视频号 / 小红书的技术科普封面。
- 微信公众号技术文章的头图、分节图和总结图。
- 5-8 页短视频口播配图。
- HyperFrames 视频中的无文字底图，配合 HTML 叠加标题、标签、字幕。

## 视觉 DNA

- 纸张背景：接近白色的温暖纸感，轻微颗粒，不做强纹理。
- 构图：内容居中，四周留白充分，不画完整外边框。
- 线条：黑色细线，带一点铅笔 / 钢笔手绘抖动感。
- 色块：浅蓝、浅绿、浅桃、浅紫作为低饱和标签或模块底色。
- 信息气质：像技术老师在白纸上边讲边画，清楚、温和、有结构。
- 标题处理：中文大标题居中或上方偏中，下面可用浅蓝手绘横线强调。
- 装饰：允许少量星号、箭头、虚线、角标、手绘注释线，但不能喧宾夺主。

## 色彩

- 纸色：`#FBFAF5`
- 主墨色：`#111111`
- 次级文字：`#5F5A50`
- 浅蓝：`#D9E8F6`
- 浅绿：`#DCEAD6`
- 浅桃：`#F5DEB8`
- 浅紫：`#E4DCF4`
- 强调橙红：`#D66F4D`

## 页面角色

| 角色 | 推荐尺寸 | 用途 |
| --- | --- | --- |
| `douyin-cover-9x16` | 1080x1920 | 抖音竖版封面 |
| `article-cover-21x9` | 2520x1080 | 公众号头图 / 横版封面 |
| `explainer-page-16x9` | 1920x1080 | 口播视频正文页 / PPT 页 |
| `hybrid-bg-16x9` | 1920x1080 | 无文字底图，给 HyperFrames 叠字 |
| `contact-sheet` | 自适应 | 多页预览检查 |

## 语义版式

- 封面隐喻：一个核心隐喻承载主题，例如“AI 大脑 + 工具箱 + 任务清单”。
- 单概念解释：中央一个大图标，四周 3-5 个短标签。
- 左右对比：左边旧方式，右边新方式，中间用箭头或分割线。
- 横向流程：从输入到执行再到结果，适合步骤类内容。
- 循环机制：观察、计划、行动、反馈，适合 Agent / 工作流。
- 分支地图：一个中心主题发散出多个能力或模块。
- 分类地图：把概念拆成几类，适合入门解释。
- 批注提醒：主图旁边加 warning / tip / note 小标记。
- 总结页：一句核心判断 + 3 个记忆点。

## 文字规则

- 封面最多 3 行大字，每行尽量 2-6 个汉字。
- 正文页最多 5 个短标签，每个标签尽量 2-8 个汉字。
- 如果要生成最终图片，文字可以直接烘焙进图里，但必须少而大。
- 如果要后续复用为视频模板，优先使用 `hybrid-bg-16x9`：图片里不放任何可读文字，所有标题、标签、字幕都由 HTML 叠加。
- 字幕永远交给 HyperFrames / HTML 渲染，不要烘焙进图片。

## 避免事项

- 不要深色背景。
- 不要赛博朋克、玻璃拟态、强渐变、3D 卡通、商务海报风。
- 不要密密麻麻的小字。
- 不要把中文画得像乱码。
- 不要在 hybrid 底图里画空白标签框，HTML 很难精准对齐生成图里的框。
- 不要用完整边框包住整张页面。
- 不要让文字贴边、压线、挤进角落。

## Prompt 模板

### 通用风格锁

```text
Chinese hand-drawn technical explainer illustration, warm off-white paper background (#FBFAF5), clean black ink linework, subtle pencil hatching, pastel annotation colors (pale blue, pale green, peach, lavender), spacious layout, educational whiteboard/PPT feeling, precise composition, no photorealism, no 3D, no cyberpunk, no dark background, no full-page border.
```

### 竖版抖音封面

```text
Create a 9:16 vertical Chinese hand-drawn technical cover image.

Required visible Chinese text:
「<第一行>」
「<第二行>」
「<第三行>」

Theme:
<主题说明>

Composition:
- Large centered headline, three stacked lines.
- A clear metaphor illustration below or around the headline: <核心隐喻>.
- Warm off-white paper background, black hand-drawn lines, pastel highlights.
- Keep margins safe for mobile cover cropping.

Style:
<粘贴通用风格锁>
```

### 16:9 正文解释页

```text
Create a 16:9 Chinese hand-drawn technical explainer page.

Page title:
「<页面标题>」

Visible short labels:
- 「<标签1>」
- 「<标签2>」
- 「<标签3>」
- 「<标签4>」

Content idea:
<这一页要解释的概念>

Composition:
Use a <语义版式> layout. Make the concept visually understandable at a glance. Keep all Chinese text large, clean, and inside its intended area.

Style:
<粘贴通用风格锁>
```

### 16:9 Hybrid 无文字底图

```text
Create a 16:9 Chinese hand-drawn technical explainer background image for HTML text overlay.

Important:
No readable text anywhere. Do not draw Chinese, English, numbers, letters, pseudo-text, icons containing letters, or blank label boxes. Draw only objects, connector lines, empty spaces, simple arrows, and visual metaphors. Leave clean open areas where HTML labels can later be placed.

Theme:
<主题说明>

Composition:
Use a <语义版式> layout. Put the main objects clearly in the scene. Leave large clean spaces near each object for future HTML labels. Do not make boxes or cards for labels.

Style:
<粘贴通用风格锁>
```

## HyperFrames 叠字规则

- HTML 负责所有可读文本：标题、标签、页码、字幕、强调词。
- 底图只负责情绪、隐喻、线条和对象。
- 标签不要追着生成图里的空框对齐；应该靠近对象，用短 pin-line 指过去。
- 每页固定一个 `.scene`，页面图或底图铺满容器。
- 所有字幕放在统一的底部字幕层，避免遮挡页面主体。
- 使用 `npm run check` 检查资源、clip class、动画和可见性。
- 渲染前抽一帧预览，确认文字没有越界、重叠或压住关键图形。

## QA 清单

- 封面在手机上第一眼能读清主题。
- 每页 3 秒内能看懂主关系。
- 中文没有错字、乱码、出框。
- 图中文字不超过页面承载能力。
- 同一系列的纸色、线条、色块和标题位置一致。
- Hybrid 页没有任何图片内文字，也没有空白标签框。
- 视频字幕不挡标题、不挡核心图。
- 导出前检查 16:9 视频和 9:16 封面分别是否符合平台裁切。
