# Terrane Parse —— 自研文档解析引擎(设计)

> 用户要求(2026-06-20):纯自研、高质量、资源少、又快又准、可不用 GPU 的高保真复杂版面/表格/公式解析引擎。
> 经深度 Web 调研定稿。

## 核心理念
**数字文档本身带结构,智能在于「重建」而非「识别」。** 数字 PDF/Office 已含文字坐标、字体、字号、矢量框线、嵌入表格——
用几何/启发式算法重建结构,纯 CPU、毫秒级、IP 自有。ML/GPU 只在扫描件兜底,且可降级。

## 调研结论(支撑可行性)
- **EdgeParse**「Zero ML, Best Benchmark Score」——纯启发式可达 SOTA。
- **PyMuPDF-Layout**:特征(CPU 便宜)+ 极小 GNN(CPU 便宜),启发式扛重活,10× 快、纯 CPU 无 GPU。
- **XY-Cut / XY-Cut++**(OpenDataLoader):递归投影切分定阅读序;先抽全宽元素(页眉/标题)再做分栏,正确处理多栏。
- **表格**:有框线→矢量线网格;无框线→文字坐标聚类成行列(+合并单元格)。

## 引擎流水线(自研算法,底层取原语用成熟库=等同字体光栅化层)
1. **原语提取**(PyMuPDF):每页文字 span(bbox/font/size/flags)+ 矢量 drawings(line/rect)。Office 用 python-docx/openpyxl/pptx。
2. **版面分析 + 阅读序(XY-Cut)**:递归找横/纵"空白山谷"切块;先剥离全宽元素(标题/页眉脚),再左→右、上→下排栏。
3. **标题分级**:span 字号/字重相对正文 → H1/H2/H3;正文聚成段。
4. **表格重建**:
   - 有框线:收集水平/垂直矢量线→求交成网格→cell→文字按 bbox 归位(支持跨行列合并)。
   - 无框线:文字 span 按 y 聚类成行、按 x 聚类成列→网格。
5. **公式**:数学字体(Cambria Math/STIX/CMMI…)或 Unicode 数学区高密度 → 标记 formula;图片公式 → CPU OCR(RapidOCR,可选/降级)。
6. **输出**:结构化 Markdown(标题/段落/Markdown 表格/公式)+ 元素树(供 wiki/图谱)。

## 分层降级(出厂纯 CPU 可跑全功能)
- 数字文档:纯启发式(无模型无 GPU)。
- 扫描件/图片 PDF:+ CPU OCR(RapidOCR ONNX)。
- 复杂版面高保真增强:可选小模型/GPU 加速,无则降级 CPU。

## 模块落位
`terrane-server/app/services/parse/`:`primitives.py`(取原语)、`layout.py`(XY-Cut/阅读序/标题)、`tables.py`(框线+无框线重建)、`formula.py`(检测)、`engine.py`(编排→Markdown)。
接入摄入:文件上传 → `engine.parse(path, mime)` → parsed_text(Markdown)→ 既有切片/嵌入/图谱链路。
依赖:PyMuPDF(原语)、python-docx/openpyxl/python-pptx(Office)、RapidOCR(可选 OCR)。**均纯 CPU、无 GPU。** 加入 requirements。
