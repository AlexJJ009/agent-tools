---
name: read-paper
description: |
  Read, add, track, and discuss papers or articles using the user's global Zotero library as the
  source of PDFs, indexed full text, LaTeX source, metadata, and annotations, with the Obsidian
  read_papers vault as the default note destination. Use this skill even when the current working
  directory is another repository. Trigger on requests such as "读这篇", "和我一起读", "解释这篇论文",
  "从 Zotero 读取", "读取 PDF/LaTeX/source", "分析第几页/某个公式", "add/download/track this paper",
  a Zotero item key or link, an arXiv/DOI/title, a literature-note path, or any indication of starting
  or continuing an interactive paper-reading session.
---

# Read Paper — 论文阅读管理

使用 Zotero 与 Obsidian 管理论文阅读。Zotero library 是跨仓库的全局资料源；Obsidian
`read_papers/` 只是默认笔记和知识产出的落点，不能把 skill 的读取能力限制在当前仓库。

## 路径与作用域

每次执行时分别解析两个位置，不要假设当前工作目录就是 vault：

1. **Zotero**：先调用 Zotero skill 的 `status --json`，再通过本地 API 按 item key、arXiv ID、
   DOI 或标题查找论文。Zotero 数据目录的本机默认值是
   `/mnt/c/AppsExternal/Zotero/dataStorage`，但优先使用 Zotero helper 探测到的实际配置。
2. **Obsidian 笔记目录**：若当前目录的祖先包含 `ZOTERO_WORKFLOW.md`、`notes/` 和 `templates/`，
   使用该 `read_papers`；否则使用默认路径
   `/mnt/c/appsexternal/obsidian/vault-repo/personal_knowledge_base/read_papers`。
3. 若默认 vault 当前不可访问，仍可从 Zotero 读取并在对话中回答；只有确实需要写入笔记时才
   请求用户提供新的 vault 路径。

不要在调用 skill 的其他代码仓库中创建 `read_papers/`、`notes/`、PDF 或 metadata 副本。

## 目录结构

```
read_papers/
├── notes/            # 单篇笔记（每篇一个 .md，含 frontmatter）
├── insights/         # 跨论文感悟（按主题）
├── blogs/            # legacy 网页原文，只读，迁移到 Zotero 后清退
├── sources/          # legacy 原文，只读、禁止新增，迁移完成后清退
├── templates/        # 笔记模板
├── reader_profile/   # 读者画像（动态维护）
│   ├── index.md      # 基本信息 + 领域概览 + 更新日志
│   └── knowledge_map.md  # 按领域的详细知识图谱
└── index.md          # 主索引
```

论文和网页的外部资料统一由 Zotero 管理。网页 parent 下保存 canonical HTML snapshot，并可附 clean Markdown 供 Agent 检索；Obsidian 只管理自己的 notes、insights、索引和阅读状态。协议见 `read_papers/ZOTERO_WORKFLOW.md`。

## 工作流

### 0. 定位一篇已有论文

用户开始或继续讨论一篇论文时，按以下优先级解析，不要求用户提供文件路径：

1. 当前/显式指定的 literature note frontmatter 中的 `zotero-key` 和 `zotero_pdf_key`；
2. 显式 Zotero item/attachment key 或 `zotero://` URI；
3. arXiv ID、DOI；
4. 标题和作者搜索。

从 skill 目录运行确定性 resolver；它会遍历 Zotero top-level items，并精确匹配 Zotero 的
URL、volume、Extra、DOI 和 title，因此不依赖 Zotero `q=` 是否索引 arXiv ID：

```bash
python3 <skill-dir>/scripts/resolve_zotero_paper.py "<item-key|arxiv|doi|title>"
```

命中 parent item 后调用 Zotero skill 的 `children <PARENT_KEY> --json` 查找 PDF、LaTeX source、
补充材料和 child notes。多个候选无法可靠消歧时，列出标题、作者、年份和 item key，再让用户选择。
不要因为 Obsidian 尚无笔记就判定论文不存在。

### 1. 添加新论文（arXiv）

当用户给出 arXiv ID 或链接时：

```
Step 1: 检查 Zotero
  → 使用 Zotero skill 按 arXiv ID、DOI、标题搜索本地库
  → 命中时复用现有 parent item，避免重复导入

Step 2: 写入 Zotero（未命中时）
  → 有 arxiv-downloader 产出的 metadata.json / PDF / source archive 时，调用：
    python3 read_papers/scripts/import_arxiv_to_zotero.py \
      --metadata <metadata.json> --pdf <paper.pdf> --source <source.tar.gz> \
      --zotero-data-dir /mnt/c/AppsExternal/Zotero/dataStorage \
      --expected-collection "<当前选中的 Zotero collection>" --yes
  → 脚本先按 arXiv ID 查重，再通过 Zotero Connector import/saveAttachment routes 写入；SQLite 只读、不直写
  → 没有本地下载产物时，通过等价的 Connector 流程直接添加 metadata 和 PDF
  → Zotero 写操作需符合 Zotero skill 的确认规则
  → 不在 read_papers/sources/ 或 papers/ 保存副本

Step 3: 取得稳定映射
  → parent item key → zotero-key（ZotLit 识别字段）
  → 主要 PDF attachment key → zotero_pdf_key（如有）
  → 生成 zotero_item_uri 和 zotero_pdf_uri
  → 校验 PDF/source 实际位于 Zotero dataStorage/storage/<ATTACHMENT_KEY>/

Step 4: 创建笔记
  → 优先通过 ZotLit quick switcher 或 companion 创建/打开 literature note
  → 同一 zotero-key 只能对应一份笔记；命中已有笔记时不得重复创建
  → 根据阅读模式应用项目结构：
    - 启发式精读 → templates/heuristic-reading.md（讨论为主体，不预设结构化 section）
    - 普通添加/略读 → templates/paper-note.md（结构化摘要 section）
  → 填写 frontmatter：title, arxiv, status, date_added, Zotero keys/URI
  → title、authors、year 等 metadata 从 Zotero parent item 读取
  → ZotLit 生成内容放在 %%zt-managed%% ... %%/zt-managed%%；个人与 Agent 内容放在区域外

Step 5: 更新索引
  → 在 index.md 的 Papers 表格末尾追加一行
  → Source 列写 Zotero item URI，不写 sources/ 路径
```

### 2. 添加新文章/博客（URL）

当用户给出普通网页 URL 时：

```
Step 1: 抓取内容
  → 调用 markdown-proxy skill 将 URL 转为临时 clean Markdown
  → 用 SingleFile 捕获渲染后的自包含 HTML snapshot

Step 2: 保存到 Zotero
  → 按规范化 URL 查重并创建或复用 Web Page parent
  → HTML snapshot 作为 canonical source child
  → clean Markdown 作为 derived child，供全文检索和 Agent 处理
  → 必须 readback 验证两个 stored attachments 都存在并可读取

Step 3: 更新 Obsidian 导航
  → 只在 index/notes/insights 中保存 zotero:// parent/attachment URI 与自己的分析
  → 不把网页正文复制到 blogs/；blogs/ 只处理尚未迁移的 legacy 原文
```

### 3. 添加本地论文（用户已有 PDF）

当用户提供本地 PDF 路径时：

```
Step 1: 导入 Zotero
  → 搜索现有库并去重
  → 未命中时，将本地 PDF 作为 Zotero stored attachment 导入，并补齐 parent item metadata
  → 不把 PDF 复制到 read_papers/sources/

Step 2: 取得 parent item key 与 PDF attachment key

Step 3: 创建笔记（同上 Step 4）

Step 4: 更新索引（同上 Step 5）
```

### 4. 从 Zotero 读取并与用户互动

当用户要求解释、讨论、精读、读取 PDF/源码、分析某页/公式/实验时：

```
Step 1: 解析论文
  → 按“定位一篇已有论文”的顺序取得 parent item key
  → 读取 metadata、children 和已有 Obsidian note（如有）

Step 2: 选择读取层级
  → 一般内容理解：优先调用 Zotero full-text API 读取 PDF attachment 的 indexed full text
  → 页码、图表、公式或版面敏感问题：取得 PDF attachment 的 file URL/path，直接检查 Zotero
    保存的 PDF；只生成临时解析产物，不复制到 vault
  → 实现细节、伪代码与宏定义：优先读取 Zotero 中已有的 LaTeX/source attachment

Step 3: LaTeX source 缺失时
  → 只有用户明确要求源码级分析且论文有 arXiv ID 时，调用 arxiv-downloader 下载到 mktemp 临时目录
  → 不写入 read_papers/sources/；阅读完成后清理临时目录
  → 只有用户明确要求长期保存/补齐 Zotero 附件时，才把 source archive 写入 Zotero

Step 4: 互动与记录
  → 简短问题可直接在对话中回答
  → 公式、表格、长分析或持续讨论写入对应 literature note 的 managed region 外
  → 引用证据时加入 page/annotation zotero:// backlink
  → 若 Zotero annotation 刚改变，先让 ZotLit refresh，再编辑 managed region 外内容
```

读取 attachment/full text 是只读操作，不需要额外确认。创建条目、导入 PDF/source 或修改
Zotero library 才属于写操作；用户已经明确要求添加、下载、迁移或保存时视为已授权该项写入。

### 5. 启发式阅读（精读模式）

当用户指定"启发式阅读"/"启发式"/"精读"时，在完成 Zotero 入库、keys 映射、创建笔记和更新索引之后，进入以下流程：

```
Step A: 调查论文内容
  → 按“从 Zotero 读取并与用户互动”选择 full text、原始 PDF 或 LaTeX source
  → 临时取得的 source 不写入 sources/；只有用户要求长期保存时才导入 Zotero
  → 提取：motivation、related work、方法概要、实验设计、核心发现
  → 目的：让 Claude 对论文有完整理解，为后续引导做准备

Step B: 探测用户层级（关键步骤！）
  → 首先读取 reader_profile/knowledge_map.md 获取用户已有的背景画像
  → 识别论文涉及的领域，与 knowledge_map 中已有记录做匹配
  → 对于已有记录的领域：
    - 直接使用已有信息，不重复提问
    - 仅在画像较旧（>30天）或论文涉及该领域的深层子方向时，简短确认是否有更新
  → 对于未覆盖的新领域：
    - 向用户提出 1-2 个针对性问题
  → 始终确认阅读目的（可能因论文而异）
  → 使用 AskUserQuestion 工具收集回答
  → 将新获取的用户信息写入 knowledge_map.md（新增领域或更新已有领域）
  → 同时在论文笔记中添加简要的"读者当时背景"记录（可选，便于回溯）
  → 根据综合画像，调整后续内容的深度和表达方式
    - 如果用户对前置知识陌生 → 补充必要的背景解释，避免知识诅咒
    - 如果用户已经很熟悉 → 跳过基础概念，直接进入核心问题

Step C: 呈现问题设定
  → 根据用户层级，将 problem setup + 约束条件 + 必要的背景知识写入笔记的"问题设定"section
  → 只写问题本身：问题是什么、为什么难、已有方法为什么不够用、有哪些可用的"原料"
  → 不写论文的 insight、方法、解法 — 这些在 Step D-E 的讨论中由用户自己发现
  → 命令行给出简短摘要（2-5 句）
  → 内容深度适配用户水平：
    - 初学者：从直觉入手，用类比解释核心概念，补充前置知识
    - 有基础：聚焦 gap，强调约束条件，提供足够的"原料"让用户思考
    - 专家：直接切入问题本身，点明关键张力

Step D: 启发式引导 — 让用户先想
  → 给出明确的问题框架：这篇论文要解决什么问题、约束条件是什么
  → 提供适当的提示（不剧透方法），引导用户构想自己的解决方案
  → 提示的粒度也应适配用户层级：
    - 初学者：给更多 hint，缩小搜索空间
    - 专家：只给问题，让用户自由发挥
  → 等待用户回答

Step E: 对比与启发
  → 用户给出方案后，将作者的方法与用户的方案进行对比
  → 写入笔记文件，覆盖：
    - 用户方案与作者方案的异同
    - 作者方案的优势 / 用户方案的独到之处
    - 关键的技术细节和实验结果
  → 重复 Step D-E 可以覆盖论文的多个核心贡献

Step F: 总结与感悟
  → 引导用户总结学到了什么
  → 将讨论记录、感悟写入笔记的"感悟与启发"和"讨论记录" section

Step G: 更新读者画像
  → 根据本次阅读中用户展现的认知变化，更新 reader_profile/knowledge_map.md
  → 具体更新内容：
    - 新增领域（如果论文涉及之前未记录的领域）
    - 调整已有领域的水平（如果用户在讨论中展现了比画像更深/浅的理解）
    - 将本次学到的新概念加入"已掌握"
    - 将讨论中暴露的新缺口加入"待深入"
    - 记录来源（哪篇论文触发的更新）
  → 更新 reader_profile/index.md 的领域概览表格和更新日志
```

**核心原则（认知负荷理论 + 最近发展区）：**

启发式阅读的本质是**先把论文内容拉入用户自己的分布内**。先在用户的知识空间中建立锚点（"我会怎么做"），然后论文中更成熟的方法作为增量修正，而不是全新的外部灌入。因此：
- **必须先探测用户层级**，否则无法判断什么是"分布内"
- 背景介绍要考虑用户现有知识，不要陷入知识诅咒
- 引导式提问比直接告知更重要
- 可以使用 subagents 查询论文细节，节省主上下文窗口
- **严格不剧透**：笔记中只写问题设定，论文的 insight/方法/解法只在讨论中逐步揭示

**两种模板的关系：**

| 模板 | 用途 | 何时使用 |
|------|------|----------|
| `heuristic-reading.md` | 精读讨论 | 启发式阅读时创建，结构为：问题设定 → 讨论记录 → 感悟 |
| `paper-note.md` | 结构化笔记 | 精读完成后可选择整理，或略读/普通添加时使用 |

精读完成后，如果用户想要一份结构化的总结笔记，可以另外从讨论记录中整理到 `paper-note.md` 模板。两者可以共存：
- `notes/{paper_id}.md` — 精读讨论笔记
- `notes/{paper_id}_summary.md` — 整理后的结构化笔记（可选）

### 6. 讨论论文（核心交互模式）

命令行无法渲染数学公式，因此讨论论文时采用**文件优先**的交互方式：

```
输出规则：
  1. 包含公式、表格、长段分析的内容 → 写入 Markdown 文件（Obsidian 可渲染）
  2. 命令行中只给出简短摘要（2-5 句），告知用户"详细内容已写入 XXX 文件"
  3. 摘要应包含关键结论，使上下文足够让后续对话无缝衔接

写入位置（按情况选择）：
  a. 与某篇论文直接相关的讨论 → 追加到 notes/{paper_id}.md 的对应 section
  b. 跨论文的思考 → 写入 insights/ 下的主题文件
  c. 临时性的探讨、问答 → 创建 notes/{paper_id}_discussion.md
     → 在 notes/{paper_id}.md 的 frontmatter 下方添加链接：
       `相关讨论：[[notes/{paper_id}_discussion]]`

用户反馈：
  - 用户会直接在文件中（通常在末尾）追加自己的见解、问题、反馈
  - Claude 应先读取文件末尾的用户追加内容，再继续讨论
  - 回复同样写入文件 + 命令行给摘要

恢复上下文：
  - 当新对话介入时，读取 notes/{paper_id}.md（和关联的 _discussion 文件）
    即可恢复到最新讨论状态
  - 命令行摘要也作为对话历史的锚点，帮助快速定位
```

### 7. 更新阅读状态

当用户说"读完了"或更新状态时：
  → 修改 notes/{paper_id}.md 的 frontmatter：status 和 date_finished

## Frontmatter 格式

```yaml
---
title: "论文标题"
arxiv: "2602.12222"          # arXiv ID（如有）
status: to-read              # to-read / reading / finished
tags: [tag1, tag2]
date_added: 2026-03-29
date_finished:               # 完成日期
zotero-key: "XHWF5XUK"
zotero_pdf_key: "ABCD1234"
zotero_item_uri: "zotero://select/library/items/XHWF5XUK"
zotero_pdf_uri: "zotero://open-pdf/library/items/ABCD1234"
citekey: ""                 # 可选，不作为映射主键
modified: 2026-03-29
related: []
---
```

证据链接直接写在相关段落：

```markdown
[查看原文标注](zotero://open-pdf/library/items/ABCD1234?page=17&annotation=EFGH5678)
```

PDF 不使用“行号”作为稳定定位；精确位置使用 annotation key，只知道页码时使用 `?page=`。

## ZotLit managed region 规则

- `%%zt-managed%%` 与 `%%/zt-managed%%` 之间由 ZotLit 重建，Agent 不得编辑、格式化或移动其中内容。
- 用户与 Agent 的总结、讨论和 insights 只写在 managed region 外。
- Zotero annotations 改变后，先运行 `ZotLit: Update literature note`，再让 Agent 修改区域外内容。
- Agent 可修复 `zotero-key`、attachment/annotation keys、`zotero://` links、frontmatter、index 和 wikilinks。
- 更新前检查同一个 `zotero-key` 在 vault 中只有一份 literature note。

## 关键路径

- 默认根目录：`/mnt/c/appsexternal/obsidian/vault-repo/personal_knowledge_base/read_papers`
- 模板：`<read_papers>/templates/paper-note.md`
- 主索引：`<read_papers>/index.md`
- 博客索引：`<read_papers>/blogs/index.md`
- 读论文方法论：`<read_papers>/关注点prompt/`
- 读者画像：`<read_papers>/reader_profile/`（启发式阅读 Step B 必读）

## 可协同的 Skills

- **Zotero**：论文入库、去重、metadata、attachments、full text、keys 与 URI；是论文事实来源
- **ZotLit v2 + companion**：创建/刷新 literature note、managed region、annotation backlinks 与 Zotero → Obsidian 导航
- **arxiv-downloader**：只在明确需要 arXiv source 且 Zotero 尚无附件时临时使用；结果不得长期落在 `sources/`
- **markdown-proxy**：将任意 URL 转为 Markdown（支持微信公众号、飞书等）
