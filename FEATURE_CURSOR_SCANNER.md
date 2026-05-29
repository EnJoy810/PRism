# Feature Spec: AI Cursor Scanner Panel

**状态**: 待实现  
**优先级**: P1（Demo 视觉核心）  
**预计工时**: 3 小时  
**替代文档**: 本文档替代 `FEATURE_DIFF_SCANNER.md`，实现更真实的"光标阅读"效果

---

## 一、目标效果

用户提交 PR URL 后，等待 AI 分析期间，页面出现一个仿 VSCode 编辑器面板，显示该 PR 的真实 diff 内容。一个白色箭头光标（操作系统原生形状的 SVG）在代码行间自然移动，模拟真人用鼠标逐行阅读代码的感觉。

**与固定高亮扫描条的核心区别**：光标会在 x 轴上变化（落点跟随行内容长度），会偶尔往回跳一行，会在关键行停留更久，制造"真人在读"而不是"机器在扫"的感觉。

---

## 二、现有代码状态（实现者必读）

### 后端已完成

`backend/app/routers/review.py` 的 `event_stream()` 已经在流式分析开始前发送一条 `diff` 事件：

```python
diff_lines = pr_context["diff"].split("\n")[:80]
yield f"data: {json.dumps({'type': 'diff', 'lines': diff_lines, 'title': pr_context['title']})}\n\n"
```

**后端不需要任何修改。**

### 前端 hook 已完成

`frontend/src/hooks/useReviewStream.ts` 已处理 `diff` 事件，返回 `diffLines: string[]` 和 `diffTitle: string`。

### ReviewPage 已集成

`frontend/src/pages/review/ReviewPage.tsx` 已经 import 了 `DiffScannerPanel` 并在 `isPending && diffLines.length > 0` 时渲染它：

```tsx
{isPending && !isStreaming && diffLines.length > 0 && (
  <DiffScannerPanel lines={diffLines} title={diffTitle} active />
)}
```

**唯一需要新建的文件**：`frontend/src/components/common/DiffScannerPanel.tsx`

---

## 三、组件规格：`DiffScannerPanel`

### 3.1 Props

```typescript
interface DiffScannerPanelProps {
  lines: string[]    // diff 原始行数组，来自 useReviewStream
  title: string      // PR 标题，显示在 tab 栏
  active: boolean    // true = 动画运行；false = 面板淡出
}
```

### 3.2 行类型解析

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

### 3.3 面板外壳结构

```
┌─────────────────────────────────────────────────────────┐
│  ● ● ●   CHANGES   pr-title-truncated...                 │  ← tab 栏，32px，#252526
├─────────────────────────────────────────────────────────┤
│  ▌ AI Agent · Reading diff...                            │  ← 状态栏，24px，#007acc
├─────────────────────────────────────────────────────────┤
│   1 │  @@ -1,5 +1,7 @@                                   │
│   2 │   import React                           ↖光标     │  ← 代码区 280px overflow:hidden
│   3 │  +import { useState }                              │
└─────────────────────────────────────────────────────────┘
```

### 3.4 颜色规格（VSCode Dark+）

```
面板背景:         #1e1e1e
tab 栏背景:       #252526
状态栏背景:       #007acc
行号文字:         #858585（当前行变为 #cccccc）
行号右边框:       #333333

add 行背景:       rgba(40, 120, 40, 0.25)
add 行文字:       #b5cea8
del 行背景:       rgba(120, 40, 40, 0.25)
del 行文字:       #f44747
meta 行背景:      rgba(0, 100, 200, 0.15)
meta 行文字:      #569cd6
ctx 行文字:       #d4d4d4
```

### 3.5 尺寸

```
面板宽度:         100%，max-width 继承父容器（660px）
代码区高度:       280px，overflow: hidden
行高:             20px
字体:             'JetBrains Mono', 'Fira Code', Consolas, monospace，12.5px
行号区宽度:       44px，右 padding 8px，文字右对齐
border-radius:    8px（整个面板），overflow: hidden
```

---

## 四、光标动画规格（核心）

### 4.1 光标元素

光标是一个绝对定位的 SVG，形状为操作系统默认箭头指针（左上角朝向），白色填充 + 黑色描边，带投影：

```tsx
<svg
  width="20" height="20" viewBox="0 0 20 20"
  style={{
    position: 'absolute',
    pointerEvents: 'none',
    zIndex: 10,
    filter: 'drop-shadow(1px 2px 3px rgba(0,0,0,0.6))',
    transition: 'top 180ms cubic-bezier(0.22, 1, 0.36, 1), left 120ms cubic-bezier(0.22, 1, 0.36, 1)',
  }}
>
  <path
    d="M4 2 L4 16 L7.5 12.5 L10.5 18 L12.5 17 L9.5 11 L14 11 Z"
    fill="white"
    stroke="black"
    strokeWidth="1"
  />
</svg>
```

光标用 `top` / `left` 定位，父容器为 `position: relative`（代码区容器）。

### 4.2 位置计算

**top（行位置）**：
```
cursorTop = currentLine * LINE_HEIGHT + LINE_HEIGHT / 2 - 4
```
`-4` 是光标热点补偿（箭头顶点在 SVG 左上角，不是中心）。

**left（列位置）**：
```typescript
function getCursorX(line: string): number {
  const LINE_NUM_WIDTH = 44    // 行号区宽度
  const CHAR_WIDTH = 7.5       // 12.5px monospace 字符平均宽度
  const content = line.slice(1) // 去掉 +/-/ 前缀
  const targetChar = Math.min(content.trimEnd().length, 60) // 最多到第60字符
  return LINE_NUM_WIDTH + 8 + targetChar * CHAR_WIDTH
}
```

这使光标落在每行文字末尾附近，而不是固定在同一列，制造"读到这行末尾"的感觉。

### 4.3 推进逻辑

```typescript
const SCAN_INTERVAL_MS = 110
const PAUSE_MULTIPLIER_INTERESTING = 2.5  // add/del 行停留 2.5 倍时长
const BACKTRACK_PROBABILITY = 0.05        // 5% 概率往回跳一行

const linesRef = useRef(lines)
useEffect(() => { linesRef.current = lines }, [lines])

const [currentLine, setCurrentLine] = useState(0)
const skipRef = useRef(false)  // 用于 add/del 行的额外停留

useEffect(() => {
  if (!active || lines.length === 0) return

  const interval = setInterval(() => {
    setCurrentLine(prev => {
      const line = linesRef.current[prev] ?? ''
      const kind = classifyLine(line)

      // add/del 行：第一次触发时跳过推进（相当于停留两个 interval）
      if ((kind === 'add' || kind === 'del') && !skipRef.current) {
        skipRef.current = true
        return prev
      }
      skipRef.current = false

      // 5% 概率往回跳一行（不能跳到 0 以下）
      if (Math.random() < BACKTRACK_PROBABILITY && prev > 0) {
        return prev - 1
      }

      return (prev + 1) % linesRef.current.length
    })
  }, SCAN_INTERVAL_MS)

  return () => clearInterval(interval)
}, [active, lines.length])
```

**为什么用 `linesRef`**：`setInterval` 闭包会捕获 `lines` 的初始值，后续更新不可见。通过 ref 同步最新值，避免闭包陷阱。

### 4.4 自动滚动

代码区设置 `overflow: hidden` 对用户隐藏 scrollbar，但 `scrollIntoView` 仍然有效（DOM 规范行为，不是 hack）：

```typescript
const lineRefs = useRef<(HTMLDivElement | null)[]>([])

useEffect(() => {
  const el = lineRefs.current[currentLine]
  if (!el) return
  el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
}, [currentLine])
```

给每个行 div 绑定 ref：
```tsx
ref={el => { lineRefs.current[index] = el }}
```

### 4.5 当前行高亮

当前行行号变色，行背景轻微提亮：

```tsx
const isCurrentLine = index === currentLine

// 行号颜色
color: isCurrentLine ? '#cccccc' : '#858585'

// 行背景额外叠加（在原有 add/del/meta 背景之上）
...(isCurrentLine && { backgroundColor: 'rgba(255,255,255,0.04)' })
```

---

## 五、进入 / 退出动画

**进入**（组件挂载时）：
```css
@keyframes panel-enter {
  from { opacity: 0; transform: translateY(12px); }
  to   { opacity: 1; transform: translateY(0); }
}
animation: panel-enter 200ms ease-out forwards;
```

**退出**（`active` 变为 false 时）：用 CSS class 切换 + `onTransitionEnd`，不用 `setTimeout`：

```tsx
const [visible, setVisible] = useState(true)

useEffect(() => {
  if (!active) {
    // 触发淡出 transition
    setVisible(false)
  }
}, [active])

// 样式
style={{
  opacity: visible ? 1 : 0,
  transform: visible ? 'translateY(0)' : 'translateY(-8px)',
  transition: 'opacity 150ms ease-in, transform 150ms ease-in',
}}
```

---

## 六、完整组件结构

```tsx
export default function DiffScannerPanel({ lines, title, active }: DiffScannerPanelProps) {
  // 1. state: currentLine, visible
  // 2. refs: linesRef, lineRefs, skipRef
  // 3. effect: 推进 currentLine（setInterval）
  // 4. effect: 同步 linesRef
  // 5. effect: scrollIntoView
  // 6. effect: active → visible 退出动画

  const cursorTop = currentLine * 20 + 6
  const cursorLeft = getCursorX(lines[currentLine] ?? '')

  return (
    <div style={{ /* 面板外壳，border-radius:8, overflow:hidden, animation */ }}>
      {/* Tab 栏 */}
      <div style={{ background: '#252526', height: 32, /* traffic lights + title */ }}>
        <span style={{ /* ● 红 #ff5f57 */ }} />
        <span style={{ /* ● 黄 #febc2e */ }} />
        <span style={{ /* ● 绿 #28c840 */ }} />
        <span>CHANGES</span>
        <span>{title.slice(0, 40)}{title.length > 40 ? '...' : ''}</span>
      </div>

      {/* 状态栏 */}
      <div style={{ background: '#007acc', height: 24, fontSize: 11 }}>
        <span className="animate-pulse">▌</span>
        <span>AI Agent · Reading diff...</span>
      </div>

      {/* 代码区 */}
      <div style={{ position: 'relative', height: 280, overflow: 'hidden', background: '#1e1e1e' }}>
        {/* 光标 SVG */}
        <svg style={{ position: 'absolute', top: cursorTop, left: cursorLeft, transition: '...' }}>
          <path d="M4 2 L4 16 L7.5 12.5 L10.5 18 L12.5 17 L9.5 11 L14 11 Z"
            fill="white" stroke="black" strokeWidth="1" />
        </svg>

        {/* 行列表 */}
        {lines.map((line, index) => {
          const kind = classifyLine(line)
          const isCurrent = index === currentLine
          return (
            <div key={index} ref={el => { lineRefs.current[index] = el }}
              style={{ display: 'flex', height: 20, /* kind 对应背景色 */ }}>
              {/* 行号 */}
              <span style={{ width: 44, textAlign: 'right', paddingRight: 8,
                color: isCurrent ? '#cccccc' : '#858585',
                borderRight: '1px solid #333333', flexShrink: 0 }}>
                {index + 1}
              </span>
              {/* 行内容 */}
              <span style={{ paddingLeft: 8, color: /* kind 对应文字色 */ }}>
                {line}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
```

---

## 七、macOS 交通灯颜色（不可替换）

```
红: #ff5f57
黄: #febc2e
绿: #28c840
```

圆点尺寸 12px，间距 8px，距左边缘 12px，垂直居中于 tab 栏。

---

## 八、验收标准

1. 提交 PR URL 后约 1-2 秒，面板出现（含进入动画）
2. 光标每行 x 坐标不同，落在行内容末尾附近
3. `+`/`-` 行光标停留约 275ms（普通行 110ms）
4. 偶尔可观察到光标往上跳一行再继续
5. 代码区随光标位置自动滚动，用户看不到 scrollbar
6. AI 结果返回后（`active=false`），面板在 150ms 内淡出
7. 调用 `reset()` 后面板消失，再次提交从第一行开始

---

## 九、不需要的东西

- ❌ 第三方 diff 渲染库（react-diff-view 等）
- ❌ 语法高亮（Prism/hljs）—— diff 颜色已足够
- ❌ 用户可手动滚动
- ❌ split view / side-by-side
- ❌ 任何后端改动（已完成）
- ❌ `useReviewStream.ts` 改动（已完成）
- ❌ `ReviewPage.tsx` 改动（已完成）

---

## 十、文件改动清单

```
新建（唯一改动）:
  frontend/src/components/common/DiffScannerPanel.tsx
```
