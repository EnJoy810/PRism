# Feature Spec: AI Diff Scanner Panel

**状态**: 待实现  
**优先级**: P1（Demo 视觉核心）  
**预计工时**: 2.5 小时  
**负责模块**: `frontend/` + `backend/app/routers/review.py`

---

## 一、目标效果

用户提交 PR URL 并点击 Review 后，在等待 AI 分析结果期间，页面下方出现一个仿 VSCode 编辑器窗口。窗口内显示该 PR 的**真实 diff 内容**，一个高亮扫描条从第一行缓慢向下移动，像真人在逐行阅读代码一样。编辑器随扫描条自动滚动。AI 分析结果返回后，面板淡出消失，结构化 Review 结果取而代之。

**传达的感觉**：AI 正在认真审查你的每一行代码，而不是对着 spinner 等待黑盒。

---

## 二、参考与反参考

**参考感觉**：
- Cursor.sh 官网 Hero 动画（鼠标在代码间移动）
- GitHub Copilot 宣传视频中代码逐行高亮补全的效果
- 终端里 `grep` 搜索结果滚动出来的感觉

**反参考（不要做成这样）**：
- 不是 typewriter 打字效果（那是文字生成，不是代码阅读）
- 不是随机闪烁（要有方向感，从上到下）
- 不是全屏遮罩（只是页面下方的一个面板）

---

## 三、数据流

### 3.1 后端变更

文件：`backend/app/routers/review.py`，函数：`create_review_stream` 内的 `event_stream()`

在现有流程基础上，**获取 PR 数据成功后**、**开始 LLM 分析前**，插入一条新的 SSE 事件：

```python
# 在 "正在分析代码变更..." 的 status 事件之后，LLM stream 之前插入：
diff_lines = pr_context["diff"].split("\n")[:80]  # 最多取 80 行
yield f"data: {json.dumps({'type': 'diff', 'lines': diff_lines, 'title': pr_context['title']})}\n\n"
```

**事件结构**：
```json
{
  "type": "diff",
  "lines": ["@@ -1,5 +1,7 @@", " import React", "+import { useState }", " ", "-const x = 1", "+const x = 2"],
  "title": "feat: add SSE streaming hook"
}
```

### 3.2 前端 hook 变更

文件：`frontend/src/hooks/useReviewStream.ts`

新增 state：
```typescript
const [diffLines, setDiffLines] = useState<string[]>([])
const [diffTitle, setDiffTitle] = useState('')
```

在事件解析 switch 里加一个 case：
```typescript
} else if (parsed.type === 'diff') {
  setDiffLines(parsed.lines ?? [])
  setDiffTitle(parsed.title ?? '')
}
```

在 `reset()` 里清空：
```typescript
setDiffLines([])
setDiffTitle('')
```

hook 返回值新增：`diffLines`, `diffTitle`

### 3.3 ReviewPage 变更

文件：`frontend/src/pages/review/ReviewPage.tsx`

从 `useReviewStream` 解构新增的 `diffLines`, `diffTitle`，传给 `AnalyzingState`：

```tsx
<AnalyzingState
  statusMessage={statusMessage}
  diffLines={diffLines}
  diffTitle={diffTitle}
/>
```

---

## 四、组件规格：`DiffScannerPanel`

### 4.1 文件位置

新建：`frontend/src/components/common/DiffScannerPanel.tsx`

### 4.2 Props

```typescript
interface DiffScannerPanelProps {
  lines: string[]       // diff 原始行数组
  title: string         // PR 标题，显示在 tab 栏
  active: boolean       // true = 扫描动画运行中；false = 面板淡出
}
```

### 4.3 行类型解析

```typescript
type LineKind = 'add' | 'del' | 'meta' | 'ctx'

function classifyLine(line: string): LineKind {
  if (line.startsWith('+++') || line.startsWith('---')) return 'meta'
  if (line.startsWith('@@')) return 'meta'
  if (line.startsWith('+')) return 'add'
  if (line.startsWith('-')) return 'del'
  return 'ctx'
}
```

### 4.4 颜色规格（VSCode Dark+ 标准）

```
面板背景:        #1e1e1e
行号区背景:      #1e1e1e
行号文字:        #858585
行号区右边框:    #333333

add 行背景:      rgba(40, 120, 40, 0.25)
add 行文字:      #b5cea8
del 行背景:      rgba(120, 40, 40, 0.25)
del 行文字:      #f44747
meta 行背景:     rgba(0, 100, 200, 0.15)
meta 行文字:     #569cd6
ctx 行文字:      #d4d4d4

当前扫描行背景:  rgba(255, 255, 255, 0.07)
当前扫描行左竖线: 2px solid rgba(255, 255, 255, 0.5)
```

### 4.5 面板外壳结构

```
┌─────────────────────────────────────────────────────────┐
│  [•][•][•]   CHANGES   pr-title-truncated...   [×]      │  ← tab bar，高度 32px，背景 #252526
├─────────────────────────────────────────────────────────┤
│  [scanning dot] AI 正在审查代码...                        │  ← 状态栏，高度 24px，背景 #007acc，字号 11px
├─────────────────────────────────────────────────────────┤
│  1  │  @@ -1,5 +1,7 @@                                  │
│  2  │   import React                                     │  ← 代码区，高度 280px，overflow: hidden
│  3  │  +import { useState }         ← 扫描高亮行         │
│  4  │                                                    │
│  ...                                                     │
└─────────────────────────────────────────────────────────┘
```

**尺寸**：
- 面板总宽度：`100%`（随父容器，最大 660px）
- 代码区高度：`280px`，`overflow: hidden`（用户不可手动滚动）
- 行高：`20px`
- 字体：`'JetBrains Mono', 'Fira Code', 'Cascadia Code', Consolas, monospace`，字号 `12.5px`
- 行号区宽度：`44px`，右 padding `8px`，文字右对齐

### 4.6 扫描动画逻辑

```typescript
const SCAN_INTERVAL_MS = 110  // 每行停留时间，约 110ms
const VISIBLE_LINES = 14      // 面板可见行数（280px / 20px）
const PAUSE_AT_INTERESTING = 280  // add/del 行多停留一次

const lineRefs = useRef<(HTMLDivElement | null)[]>([])
const [currentLine, setCurrentLine] = useState(0)
const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

useEffect(() => {
  if (!active || lines.length === 0) return

  intervalRef.current = setInterval(() => {
    setCurrentLine(prev => {
      const next = (prev + 1) % lines.length
      return next
    })
  }, SCAN_INTERVAL_MS)

  return () => {
    if (intervalRef.current) clearInterval(intervalRef.current)
  }
}, [active, lines])
```

**add/del 行多停留**：在 `setInterval` 回调里判断当前行类型，如果是 `add` 或 `del`，跳过一次推进（即连续触发两次才前进一行）。

### 4.7 自动滚动

```typescript
useEffect(() => {
  const el = lineRefs.current[currentLine]
  if (!el) return
  el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
}, [currentLine])
```

`scrollIntoView` 目标容器需要设置 `overflow: hidden`（不暴露滚动条给用户），但 scrollIntoView 依然有效——DOM 内部会滚动，用户看不到 scrollbar。

### 4.8 进入/退出动画

**进入**：面板从 `opacity: 0, transform: translateY(12px)` 渐入到 `opacity: 1, translateY(0)`，持续 `200ms ease-out`。

**退出**（`active` 变为 false 时）：`opacity: 0, transform: translateY(-8px)`，持续 `150ms ease-in`，动画结束后 `display: none`。用 CSS transition + onTransitionEnd 处理，不要用 setTimeout。

---

## 五、AnalyzingState 集成

文件：`frontend/src/pages/review/ReviewPage.tsx`

### 修改前的 AnalyzingState：
只显示骨架屏（shimmer 占位卡片）。

### 修改后的 AnalyzingState：

```
状态 A：diffLines 为空（尚未收到 diff 事件）
  → 显示原有骨架屏（不变）

状态 B：diffLines 非空
  → 骨架屏淡出，DiffScannerPanel 淡入
  → 骨架屏和面板不共存，切换用 opacity transition
```

**布局**：
```tsx
{diffLines.length === 0 ? (
  <SkeletonCards />
) : (
  <DiffScannerPanel lines={diffLines} title={diffTitle} active={true} />
)}
```

---

## 六、边界条件

| 场景 | 处理方式 |
|------|---------|
| diff 为空（空 PR）| 不发 `diff` 事件，保持骨架屏 |
| diff 超过 80 行 | 后端截断到 80 行，前端不感知 |
| PR 只有 1-2 行变更 | `currentLine` 循环（`% lines.length`） |
| 结果在 5 秒内返回 | 面板可能刚出现就淡出，无问题 |
| 结果迟迟不来 | 动画持续循环，不超时 |
| 用户在分析中点击"重新分析" | `reset()` 调用时清空 `diffLines`，面板随之消失 |

---

## 七、不需要的东西（明确排除）

- ❌ 不需要 `react-diff-view` / `react-diff-viewer-continued` 等第三方库（自己解析更轻）
- ❌ 不需要语法高亮（Prism/hljs）——diff 颜色已经足够，不需要 token 级别着色
- ❌ 不需要用户可交互的滚动条
- ❌ 不需要 split view / side-by-side（只需要 unified inline view）
- ❌ 不需要鼠标光标 SVG 动画（行高亮已经传达了"阅读"感）

---

## 八、验收标准

1. 提交有效 PR URL 后，等待约 1-2 秒（GitHub fetch 时间），代码面板出现
2. 面板显示真实 diff 内容，`+` 行绿色、`-` 行红色
3. 高亮条平滑从上向下移动，`add`/`del` 行停留时间略长
4. 面板内容跟随高亮条自动滚动，用户看不到 scrollbar
5. AI 分析结果返回后，面板在 150ms 内淡出，Review 结果正常显示
6. 在 `reset()` 后面板消失，再次提交时从头开始

---

## 九、文件改动清单

```
新增:
  frontend/src/components/common/DiffScannerPanel.tsx

修改:
  backend/app/routers/review.py          （event_stream 中插入 diff 事件）
  frontend/src/hooks/useReviewStream.ts  （新增 diffLines/diffTitle state）
  frontend/src/pages/review/ReviewPage.tsx （AnalyzingState 集成面板）
```

---

## 十、给实现者的额外提示

1. `scrollIntoView` 在 `overflow: hidden` 容器内仍然有效——这是 DOM 规范行为，不是 hack。
2. `setInterval` 里不要直接引用 `lines` 状态，通过 `useRef` 同步最新值，避免闭包陷阱。
3. tab 栏的三个圆点颜色：`#ff5f57`（红）、`#febc2e`（黄）、`#28c840`（绿），这是 macOS Terminal 标准色，不要用其他颜色。
4. 当前行高亮时，行号区的数字颜色从 `#858585` 变为 `#cccccc`（轻微提亮）。
5. 整个面板加 `border-radius: 8px` 和 `overflow: hidden`，tab 栏圆角和代码区圆角一致。
