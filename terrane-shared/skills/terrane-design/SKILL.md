---
name: terrane-design
description: Terrane 前端设计规范（taste-skill v2 + minimalist-skill 落地版）。任何出码 Agent 在写 terrane-web/terrane-admin-web/terrane-clipper 的 UI 代码前必须遵守本规范；Pre-Flight 清单 = PR 验收红线。
---

# Terrane 设计规范（设计规范即 Agent 指令文件）

> 来源：taste-skill v2（决策门/三旋钮/禁令）+ minimalist-skill（Notion/Linear 编辑器风主基调）+ soft-skill（仅营销/欢迎页）。原仓库 https://github.com/leonxlnx/taste-skill（2026-06-13 全文调研落地）。本文件为 Terrane 定制版，与原 skill 冲突处以本文件为准。

## 0. 决策门

写任何页面前先输出一行设计判读："Reading this as: [页面类型] for [受众], with a [气质] language, leaning toward minimalist editor-style."
**旋钮锁定（应用界面，不许悄改）**：DESIGN_VARIANCE = **3-4**（工具要稳）｜ MOTION_INTENSITY = **3-4**（克制）｜ VISUAL_DENSITY = **5-7**（知识密集型偏高密度）。营销/欢迎页可临时升 VARIANCE 至 6 并显式声明。

## 1. 绝对禁令（出现即 Pre-Flight 失败）

- **全局零 em-dash（—）**（头号 AI 痕迹；中文破折号——在中文文案中允许，英文 UI 文案禁）
- 禁纯 `#000000` / `#ffffff`（用 off-black `#111111` / 骨白 `#FBFBFA`）
- 禁 Inter/Roboto/Open Sans 默认字体；禁 Lucide/Feather 图标（图标统一 **Phosphor**）
- 禁 `shadow-md` 以上投影（卡片 = 1px `#EAEAEA` 边框无阴影；hover 至多 `0 2px 8px rgba(0,0,0,0.04)`）
- 禁大面积彩色渐变铺底、霓虹色、AI 紫/蓝辉光（LILA 规则）、重玻璃拟态
- 禁三等宽功能卡、禁 div 矩形伪造截图、禁 placeholder 当 label、禁 emoji 当图标
- 禁 `window.addEventListener('scroll')`；禁把滚动进度放 React state；**只许动画 transform 和 opacity**
- >5 项列表禁裸 `<ul>`+divide-y（改卡片/分组/虚拟列表）
- 禁无来源伪精确数字文案（除真实数据）

## 2. 色彩 Token（minimalist 基调）

- 画布：浅色 `#FBFBFA`（骨白）/ 暗色 `#191919`；文字 off-black `#111111` / 暗色 `#D4D4D4`
- 边框：`#EAEAEA` 或 `rgba(0,0,0,0.06)`；暗色 `rgba(255,255,255,0.08)`
- **单强调色一致性锁**：全应用唯一强调色（OKLCH 定义，Branding 可配，默认哑光蓝 `#1F6C9F` 系），第 N 个页面的 CTA 不许突变
- **哑光粉彩四色对**（Notion 标签系）专用于实体类型/状态标签：淡红 `#FDEBEC/#9F2F2D`、淡蓝 `#E1F3FE/#1F6C9F`、淡绿 `#EDF3EC/#346538`、淡黄 `#FBF3DB/#956400`
- 浅/暗双主题必做且双测；`html.dark` class 驱动；尊重 `prefers-color-scheme`

## 3. 排版

- 字体：UI/正文 = **Geist Sans**，中文 = **思源黑体**（自托管 `font-display:swap`，禁 Google Fonts `<link>`）；代码/数字 = Geist Mono；**token/计量/日期一律 `tabular-nums`**
- 正文行高 ≥1.6；标题 letter-spacing `-0.02em`；圆角体系 ≤8px（卡片）/12px（弹窗），全局一致锁
- 知识页渲染：Markdown 阅读态最大宽 `max-w-3xl`，`[[wikilink]]` 用强调色下划线虚线，悬浮预览卡 1px 边框无阴影；"推断"标注 = 淡黄标签前缀

## 4. 布局

- 应用框架：左侧导航（可折叠 64px/240px）+ 内容区；库工作台 = 双栏（左对话 55% / 右知识 45%，可拖分界，1024px 下右栏可收起为抽屉）
- section 间距 `py-6`（应用密度，非营销页的 py-24）；卡片内距 16-24px
- 空状态必须有插画位 + 单主 CTA（≤3 词）+ 一句说明；骨架屏形状必须匹配最终布局
- 表格：TanStack Table，行高 40px，等宽数字列右对齐

## 5. 动效

- 入场：`translateY(8px)+opacity 0 → 400ms cubic-bezier(0.16,1,0.3,1)`（应用档收短）；列表交错 `index*60ms`，上限 6 项
- 图谱"知识长出来"：新节点 `scale 0.6→1 + opacity`，300ms，同帧批量不超过 20 节点（多于则直接渲染终态）
- 每个动画必须回答"传达了什么"（层级/反馈/状态切换）；`prefers-reduced-motion` 全包裹给静态降级
- 按压触感：`active:scale-[0.98]`；SSE 更新高亮 = 背景色 1.2s 渐隐（强调色 8% 透明度起）

## 6. 组件规则

- 按钮：主 = off-black 底白字（暗色反转），радиус 6px；CTA 文案 ≤3 词且禁换行；同一意图全站同文案
- 表单：label 在上、错误内联在下、永禁 placeholder 当 label；对比度 WCAG AA 4.5:1 强检
- 弹窗：固定高度内容不抖动（License 激活弹窗教训）；焦点陷阱 + Esc 关闭
- 语言切换 = 自定义下拉（母语名标签）；所有原生控件（select/date）必须包装
- 通知 Bell：未读小红点（数字 >9 显示 9+）；toast 右上 3.5s

## 7. 页面专项

- **图谱宇宙视图**：暗色画布优先（浅色模式给纸感米白）；节点色 = 实体类型四色对；LOD：缩放 <0.3 隐标签；选中节点邻域高亮其余降透明 0.15
- **记忆面板**：三类分栏 tab；每条记忆卡带置信度细条 + 来源对话链接；删除二次确认文案"删除后不可恢复"
- **onboarding 四幕剧**：每幕全屏引导层（spotlight 镂空高亮目标区域），可跳过按钮恒在右上；进度点 4 枚
- **锁定页（/locked）**：标题逐字 `需要激活许可证.` / `License activation required.`，副描述按 verdict 区分，整页极简居中

## 8. Pre-Flight 终检（PR 验收红线，逐项勾选）

[ ] 设计判读已声明，旋钮值在锁定范围 ｜ [ ] 零 em-dash（英文文案） ｜ [ ] 单强调色锁 ｜ [ ] 禁纯黑白 ｜ [ ] 圆角体系一致 ｜ [ ] 浅暗双主题双测 ｜ [ ] 按钮 AA 对比 ｜ [ ] CTA ≤3 词不换行 ｜ [ ] >5 项列表非裸 ul ｜ [ ] 骨架屏匹配布局 ｜ [ ] 每个动画有动机 + reduced-motion 包裹 ｜ [ ] 只动 transform/opacity ｜ [ ] tabular-nums 用于一切计量 ｜ [ ] 1024px + 5 档缩放无破版 ｜ [ ] 空状态完整 ｜ [ ] i18n 无硬编码文案
