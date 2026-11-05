# 试卷 JSON 格式 v1.1

MockTest Maker 的试卷（mock paper）交换格式。一个 `.json` 文件 = 一份可作答、可判分、可导出 PDF 的完整试卷。

配套文件：

| 文件 | 作用 |
| --- | --- |
| `schema/paper-1.1.schema.json` | JSON Schema（draft 2020-12），**当前版本** |
| `schema/paper-1.0.schema.json` | v1.0 的 Schema，冻结保留（读端仍兼容 1.0 文件） |
| `taxonomy/amc-v1.json` | AMC 考点分类体系（3 层：板块 → 考点 → 题型标签），`classification` 里的所有 id 都来自这里 |
| `examples/demo_rand_01.json` | 完整示例：三种 `figure` 状态 + 三种 `classification` 状态各一题 |
| `scripts/validate_paper.py` | 校验器 + 旧卷升级器（纯标准库，无依赖） |

> **v1.1 相对 v1.0 只加了两样东西**：顶层 `taxonomy` 和每题的 `classification`（见第 4.5 节）。
> 其余字段一个字没动，1.0 的文件不改也能读，校验器同时接受 `1.0` 和 `1.1`。

---

## 1. 为什么要重定这个格式

现在磁盘上的试卷（`users/<user>/tests/<id>.json`，由 `app/server.py:generate_test` 写出）长这样：

```json
{"id": "...", "competition": "...", "title": "...", "instructions": "...",
 "time_limit_min": 180, "total_points": 15,
 "questions": [{"n": 1, "source": "...", "question": "...", "choices": null,
                "answer": "028", "solution": "...", "type": "integer_answer", "points": 1}]}
```

四个问题：

1. **没有版本号**。文件结构一旦改，历史卷子就无法判断“这是哪一版格式”，只能靠猜。
2. **没有配图位**。几何题现在只能把图丢掉或者干脆排除；题库里已经有 `has_diagram` 标记（`bank/bmt_A.json` 27 题、`bank/pumac_A.json` 29 题…），但试卷格式里无处安放这张图。
3. **题目没有稳定 id**。作答记录、错题本、PK、版本 diff 都靠 `n`（卷面题号）定位，一旦换题、加题就全错位。
4. **来源不可复现**。不知道用了哪个题库文件、什么随机种子，同一份卷子没法重造。

v1.0 在**保持现有字段全部不变**的前提下补上这四件事——所以 `generate_test` 只需要加几个字段，前端渲染器可以逐条迁移，历史卷子用 `--upgrade` 一次性升级。

---

## 2. 顶层字段

```jsonc
{
  "format_version": "1.1",        // 必填。格式版本号（结构版本）
  "paper_version": 2,             // 必填。试卷版本号（内容版本），从 1 开始
  "id": "aime_rand_01",           // 必填。稳定标识，同时是文件名主干
  "title": "AIME — Random Mock #1 · 2026-11-02 20:10",
  "competition": "AIME",
  "category": "Math",
  "taxonomy": { "id": "amc-v1" },      // 分类法声明，见第 4.5 节
  "instructions": "15 questions · 180 minutes · No calculator. 15 points total.",
  "time_limit_min": 180,
  "total_points": 15,
  "calculator_allowed": false,
  "locale": "en",                 // en | zh，决定题干/解析优先用哪一栏
  "created_at": "2026-11-02T20:10:00+08:00",
  "updated_at": "2026-11-02T20:24:00+08:00",
  "generator": { "name": "mocktest-maker", "version": "0.9.0", "seed": 20261102, "banks": ["bank/aime_B.json"] },
  "version_history": [ { "version": 1, "at": "...", "by": "generator", "note": "initial generation" } ],
  "sections": [ { "id": "S1", "title": "Section 1", "instructions": null, "points": 15 } ],
  "questions": [ /* 见第 4 节 */ ],
  "content_hash": "sha256:3ce4c908…",   // 可选，见第 6 节
  "notes": null
}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `format_version` | ✅ | 结构版本。`1.x` 内只增不改（向后兼容）；破坏性改动升 `2.0`。校验器按 `^1\.\d+$` 接受 |
| `paper_version` | ✅ | **这一份卷子的内容版本**。生成时为 1，之后每改一次（换题、改图、改答案）+1 |
| `id` | ✅ | `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`，建议与文件名一致 |
| `title` / `instructions` | ✅ | 卷面文字，前端直接渲染 |
| `time_limit_min` / `total_points` | 建议 | 判分与计时用；`total_points` 应与题目 `points` 之和一致 |
| `locale` | 建议 | `en` / `zh` |
| `generator` | 建议 | `name` 必填；`seed` + `banks` 让同一份卷子可复现 |
| `version_history` | 建议 | 版本流水；最后一条的 `version` 应等于 `paper_version` |
| `sections` | 可选 | 分卷/分节（如 BPhO Section 1/2）；题目用 `section` 字段挂靠 |
| `taxonomy` | 可选 | `{id, version?, name?, uri?}`，声明本卷用哪套分类法。有题目带 `classification` 时必须给，否则 tag id 无从校验（只警告，不拦） |
| `questions` | ✅ | 非空数组 |
| `content_hash` | 可选 | 内容指纹，见第 6 节 |
| `x-*` | 可选 | 扩展字段保留前缀，任何实现都可以加而不破坏校验 |

---

## 3. 两个版本号的分工

| | `format_version` | `paper_version` |
| --- | --- | --- |
| 描述 | **格式**的结构版本 | **这一份卷子**的内容版本 |
| 谁改 | 改格式的人（改 schema） | 改卷子的人（换题/改图/改答案/重新组卷） |
| 取值范围 | `1.0` → `1.1` → `2.0` | `1` → `2` → `3` … |
| 兼容规则 | `1.x` 只增字段；读端遇到不认识的字段应忽略（扩展字段用 `x-`）；`2.0` 表示旧读端必须升级 | 只增不减；每次写盘前 +1 并追加一条 `version_history` |
| 典型消费者 | 校验器、导入导出、迁移脚本 | 缓存键、查重、作答记录归属、教师端“回滚到 v1” |

**迁移规则**：读端先看 `format_version`，主版本号大于自己支持的就拒绝（而不是猜）；等于或小于则按自己版本的规则读。写端永远写自己支持的最新 `1.x`。

---

## 4. 题目（`questions[]`）

```jsonc
{
  "n": 3,                        // 必填。卷面题号，1 起连续
  "qid": "q03",                  // 稳定 id，1–32 位 [A-Za-z0-9_-]
  "section": "S1",               // 可选，挂到顶层 sections
  "type": "integer_answer",      // multiple_choice | integer_answer | numeric | proof
  "source": "2019 AMC 8 Problem 12",
  "question": "题干，LaTeX 用 $...$ / $$...$$",
  "question_zh": null,           // 可选中文题干
  "choices": { "A": "6", "B": "7" },   // multiple_choice 必填，键限 A–H
  "answer": "028",               // 见下
  "solution": "解析",
  "solution_zh": null,
  "points": 3,
  "grading": { "mode": "exact", "tolerance": 0, "unit": "" },
  "figure": null,                // 见第 5 节
  "subject": "geometry",         // 历史字段，新代码请读 classification
  "difficulty": { "level": 10 }, // 1–20 分制，见第 4.6 节；旧写法 "medium" 仍可读
  "classification": { /* 见第 4.5 节 */ }
}
```

**`answer` 的写法按 `type` 区分：**

| type | answer | 校验规则 |
| --- | --- | --- |
| `multiple_choice` | `"D"` | 必须是 `choices` 的某个键 |
| `integer_answer` | `"028"` / `"-35"` / `"18888"` | 整数串 `^-?[0-9]{1,15}$`。AIME/MathCounts 约定零填充三位（`000`–`999`），前端按整数比较，`28` 与 `028` 等价；BMT/BMMT 这类答案可为多位数或负数 |
| `numeric` | `"3.14"` | 可解析为数；**单位放 `grading.unit`**（如 BPhO 的 `"ms^{-1}"`），带 `grading.tolerance` 时按相对误差判分（`0.02` = ±2%） |
| `proof` | `null` | 无标准答案，人工/自评 |

`n` 是卷面顺序，`qid` 是身份。**换题时保留 `qid`、只改内容**，作答记录和错题本才不会丢；重排顺序只动 `n`。

---

## 4.5 题目分类（`classification`）—— 给每道题贴知识点

v1.1 新增。目标不是现在就填满，而是**把管道先铺好**：以后不管是人工标、规则推、还是模型批量标，都往同一个槽位里写，下游（按知识点组卷、薄弱点分析、错题本归类、题目检索）只认这一个字段。

```jsonc
"classification": {
  "state": "done",                 // done | pending；字段整体缺省 = 还没考虑过
  "taxonomy": "amc-v1",            // 可选，覆盖顶层声明
  "primary": "plane_geometry.right_triangles",  // done 必填。2 级考点或 3 级标签，不能只写 1 级板块
  "tags": [                        // done 必填，1–8 条。多标签，按权重排序
    { "id": "plane_geometry.right_triangles", "weight": 1 },
    { "id": "plane_geometry.incircle_circumcircle.incircle_radius", "weight": 0.5, "note": "内切圆半径" },
    { "id": "methods.case_analysis", "weight": 0.3, "note": "方法轴：分类讨论" }
  ],
  "source": "human",               // human | rule | model | import，谁标的
  "confidence": 1,                 // 0–1。model 标注必须给，否则没法抽检
  "reviewed": true,                // 人有没有复核过
  "at": "2026-11-05T10:20:00+08:00",
  "note": null
}
```

### 三态，和 `figure` 同一套思路

| 写法 | 含义 | 谁会写 |
| --- | --- | --- |
| 字段缺省 / `null` | 还没考虑过（老卷子、新题默认都是这个） | 什么都不做 |
| `{"state": "pending"}` | 已排进待分类队列，但还没结论 | `--mark-pending`、导入器 |
| `{"state": "done", primary, tags}` | 已分类 | 人工 / 模型 / 规则 |

`pending` **不允许**带 `primary`/`tags`——没结论就是没结论，别写一半让人以为分好了。

### 为什么是「多标签 + primary」而不是单选

一道 AMC 题经常同时是「相似三角形」+「面积比」+「代数换元」。单选会丢掉后来要用的信息，而全多选又没法排序、没法做「薄弱点就一个主因」的统计。所以：`primary` 一个（用于聚合和排序），`tags` 一组带权重的多标签（用于检索和精细画像）。

### 分类法（taxonomy）长什么样

词表**不在试卷里**，单独放 `taxonomy/amc-v1.json`，试卷只引 `id`。理由：一份卷子 25 题都抄一遍词表，纯属重复；而且改词表要改几百个文件。

词表是**三层**的，对应「一级大板块 → 二级考点 → 三级具体题型」：

```jsonc
{
  "id": "amc-v1",
  "version": "1.0",
  "name": { "en": "AMC Topic Taxonomy (AMC 8/10/12)", "zh": "AMC 考点分类体系" },
  "levels": {
    "1": "domain - 互斥大板块，用于「各板块占比」这类统计",
    "2": "topic - 考点，一道题的主归类",
    "3": "tag - 题型标签，细粒度、可跨年份复用"
  },
  "conventions": {
    "primary": "填 2 级考点，必要时填 3 级标签；永远不要只填 1 级板块",
    "multi_label": true,
    "methods_axis": "根分支 methods 装跨板块技巧，是方法轴，不是知识板块",
    "synonyms": "一个概念只有一个 id，别名放 nodes[].aliases"
  },
  "counts": { "domains": 8, "topics": 86, "tags": 339 },
  "roots": [
    { "id": "combinatorics", "level": 1, "kind": "topic",
      "label": { "en": "Combinatorics & Counting", "zh": "组合数学与计数" },
      "children": [
        { "id": "combinatorics.lattice_paths", "level": 2,
          "aliases": ["grid path", "网格路径计数"],
          "label": { "en": "Lattice Paths", "zh": "格路计数" },
          "children": [
            { "id": "combinatorics.lattice_paths.forbidden_points", "level": 3,
              "label": { "en": "Paths Avoiding Points", "zh": "禁止经过点" } }
          ] }
      ] }
  ]
}
```

规则：

- **节点 id 就是点分路径** `^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$`，**层级 = 路径段数**：1 段是板块、2 段是考点、3 段是题型标签。父子关系由路径表达，不额外写 parent。
- **父节点自动汇总子节点**：挂了 `combinatorics.lattice_paths.forbidden_points` 的题，查 `combinatorics.lattice_paths` 和 `combinatorics` 时都算命中（下游按前缀匹配即可，不用展开）。
- **`methods` 是方法轴，不是知识板块**：它是根的一支（`kind: "method"`），装「分类讨论 / 极端原理 / 不变量与单调量 / 对称性 / 逆向思维 / 递推与 DP / 构造法 / 反证法 / 代数几何互化 / 枚举与模式识别 / 双计数 / 降维与转化」这些跨板块技巧，可以和任意知识板块同时挂。用递推做的概率题，`primary` 仍是 `probability.*`，方法再挂一条 `methods.recursion_dp`。
- **同义词只放 `aliases`，不新造 id**：`floor` = `下取整` = `gauss` 都指向 `number_theory.floor`；`格路计数` = `网格路径计数` 都指向 `combinatorics.lattice_paths`。
- **难度不进词表**：同一考点在 AMC 8/10/12 里难度不同，难度只写在题的 `difficulty` 字段（1–20 分制，见第 4.6 节）。
- 当前词表：**8 个板块 / 86 个考点 / 339 个题型标签，共 433 个节点**（数论 40、代数 44、平面几何 64、立体几何 31、组合 45、概率统计 39、应用题 37、跨板块方法 39 个标签）。

### 和「原始 10 个考点体系」的字段对应

早期方案给了五个平行字段（`primary_domain` / `primary_topic` / `subtopic_tags` / `secondary_topics` / `method_tags`）。本格式把它们压成 **`primary` + `tags`** 两个字段——层级由 id 的点分深度表达，同一信息只存一处，才不会互相矛盾：

| 原字段 | 在本格式里 |
| --- | --- |
| `primary_domain` | `primary` 的 id 前缀（`combinatorics.lattice_paths` → 板块 `combinatorics`），不用单独存 |
| `primary_topic` | `classification.primary`（2 级考点） |
| `subtopic_tags` | `classification.tags` 里深度为 3 的项 |
| `secondary_topics` | `classification.tags` 里**其他考点**的 id（权重通常 < 1） |
| `method_tags` | `classification.tags` 里 `methods.*` 的项 |
| `difficulty` | 题的 `difficulty` 字段（1–20 分制），不塞进词表 |
| `competition` / `year` / `problem_number` | 已在 `source`（如 `"2019 AMC 8 Problem 12"`）与顶层 `competition` 里 |

### 校验器会检查什么

| 检查 | 级别 | 说明 |
| --- | --- | --- |
| tag / primary 是否在词表里 | error | 词表文件找得到时才查；找不到降级成 `taxonomy-missing` + `classification-unverified` warning，不拦 |
| `primary` 是否 ∈ `tags` | error | 主标签必须在标签集里 |
| `primary` 是否只写到一级板块 | warning | `classification-branch`：`primary` 要落在 2 级考点或 3 级标签上，只写 `plane_geometry` 会丢信息 |
| `pending` 是否夹带 `primary`/`tags` | error | 见上 |
| `weight` 范围 | error | `(0, 1]`，0 会被当成「不相关」却没删掉，容易误读 |
| 重复 tag | error | 同一 id 列两次，权重到底听谁 |
| `source` / `confidence` | error / warning | 枚举外的 source 是 error；`model` 标注没给 `confidence` 是 warning（后面抽检靠它） |

### 分类不进 `content_hash`

`classification` 是**标注**，不是卷面内容。它和 `x-*` 一起被排除在 `content_hash` 之外（见第 6 节），所以：

- 重新打一遍标签，不会让所有下游缓存失效；
- 不需要为了加分类升 `paper_version`、也不用往 `version_history` 里塞一条。

---

## 4.6 难度（`difficulty`）—— 1–20 分制 + 怎么算出来的

v1.1 把 `difficulty` 从三个词（`easy | medium | hard`）扩成一个**对象**。旧写法继续可读（校验器当 legacy 简写接受），新代码请写对象：

```jsonc
"difficulty": {
  "level": 15,                   // 必填，整数；锚点：20 = 平均的 AMC 12 第 25 题
  "scale": "amc20",              // 可选，缺省即 amc20；legacy5 标记已退役的 1-5 级
  "band": "medium",              // 可选，粗映射：≤9 easy / 10-17 medium / ≥18 hard
  "score": 14.6,                 // 可选，1-60 连续分，排序和插值用
  "method": "hybrid",            // prior | llm_rubric | elo | irt | human | hybrid
  "confidence": 0.62,            // 0-1，低置信度进人工抽检队列
  "components": [                // 每路来源各占一行，可解释、可重算
    { "method": "prior",      "score": 13.9, "weight": 0.35, "reason": "amc12 7.0->20.0 at t=0.58" },
    { "method": "llm_rubric", "score": 15.0, "weight": 0.65, "reason": "needs one key construction" }
  ],
  "evidence": { "attempts": 0 }, // elo / irt 用到的作答次数
  "reviewed": false,             // 人工确认过则 true，自动值一律 false
  "at": "2026-11-05"
}
```

**为什么不用三档**：在题号密集的竞赛卷里，`easy/medium/hard` 几乎全落在 medium，排不出序。`band` 保留三档，给只看粗粒度的下游（选卷难度配比）用。

**为什么也不用 1–5**：1–5 只有五个整数，一份 25 题的卷子挤在五个点上，相邻题号分不开。1–20 才够把一卷内部的梯度拉开。

**为什么锚点是 20 而不是满分**：难度需要一个人人有直觉的参照物。这里把 **20 钉在「平均的 AMC 12 第 25 题」**——大家一眼能想象的难度上限，而不是抽象的"最难"。于是 AMC 8 落在 1–8、AMC 10 落在 5–15、AMC 12 落在 7–20，AIME 与奥林匹克题自然落在 20 上方（最高到 60，IMO 第 6 题级）。硬把 AIME 压到 20 以内，会让它和 AMC 12 压轴混成一个点。

**为什么留 `components`**：难度不是一个值，而是一次**估计**，不同来源会互相打架。留下每路来源的分数与权重，才能解释"为什么这题是 15"、才能在数据变多后重算而不丢历史。

**为什么 `difficulty` 不进 `content_hash`**：它是估计值，重新标定就会变；进哈希会让每次校准都要重发版本（见第 6 节）。

### 1–20 标尺（锚点）

| level | 锚点题 | 典型特征 |
| --- | --- | --- |
| 1 | AMC 8 #1 | 一步直取：代公式、读表、一次四则运算 |
| 3 | AMC 8 #8 | 两步常规，一个公式 |
| 5 | AMC 8 #15 | 标准课本方法 + 小分类 |
| 7 | AMC 8 #22 ≈ AMC 10 #4 | 两个想法组合 |
| 9 | AMC 10 #12 | 需要选对工具 |
| 11 | AMC 10 #19 | 三步 + 一个轻观察 |
| 13 | AMC 10 #25 ≈ AMC 12 #10 | 多步综合 |
| 15 | AMC 12 #15 | 真综合，需关键观察 |
| 17 | AMC 12 #20 | 构造或细致分类讨论 |
| 19 | AMC 12 #24 | |
| **20** | **AMC 12 #25** | **锚点：平均的 AMC 12 压轴** |
| 23 | AIME #1–#5 | 需要真想法，但路径短 |
| 27 | AIME #8–#11 | 中段 AIME |
| 30 | AIME #14–#15 | 难 AIME |
| 34 | 奥赛短名单 / USAMO #1–#2 | |
| 38 | USAMO #3–#6、IMO #1–#3 | |
| 42+ | IMO #6 级 | 仅在题目确实如此时使用 |

明确**不**作为依据：题干长度、数字好不好算、解析写得多长。

### 五种算法

| 方案 | 数据依赖 | 现在能用吗 | 说明 |
| --- | --- | --- | --- |
| `prior` | 无 | ✅ | 竞赛 (起点→终点) 线性内插，零成本、可复现（`classifier/difficulty/prior.py` 的 `BASE_TOP`） |
| `llm_rubric` | 无 | ✅ | 把上面那张标尺交给模型，产出 level + `why` |
| `elo` | 逐题对错 | ❌ 缺数据 | 题目初始分由 prior 折算，避免冷启动还债 |
| `irt` | ≥200 次/题 | ❌ 缺数据 | 多一个区分度参数，需离线拟合 |
| `human` | 人工时间 | ⚠️ 少量 | 锚题校准；`reviewed: true` 时覆盖自动值 |

融合规则：按作答次数分 `cold / early / mid / mature` 四阶段，`prior` 权重从 0.35 递减到 0.05，实测数据权重递增。完整公式、参数表与验收指标见 **`classifier/SCHEMES.md`**。

### 校验器查什么

| 检查 | 级别 |
| --- | --- |
| `level` 是 1-60 整数、`band` 与 `level` 推导一致（`scale: legacy5` 时跳过） | error / warning |
| `scale` 只允许 `amc20` / `legacy5` | error `difficulty-scale` |
| `score` 与 `level` 推导一致（`score_level()` 同标尺，四舍五入） | warning `difficulty-score` |
| `components[].method` 合法、`weight`/`confidence` ∈ [0,1] | error |
| `components` 的加权平均值 ≈ `score`（容差 0.15） | warning `difficulty-weights` |
| `evidence.attempts` 非负整数、`at` 形如 `YYYY-MM-DD` | error |

已实现工具：`classifier/`（分类 + 评级）、`scripts/validate_paper.py`（上面这些检查）。

---

## 5. 配图槽位（`figure`）—— 几何题的位置

这是 v1.0 的核心新增。`figure` 有 **三种状态**：

| 状态 | 写法 | 渲染 |
| --- | --- | --- |
| **明确无图** | `"figure": null` 或省略 | 不渲染任何东西 |
| **图就位** | `state: "ready"` + `src` **或** `inline` | 渲染图 |
| **占位待补** | `state: "placeholder"`，无 `src`/`inline`，但必须有 `width`/`height`/`alt` | 渲染一个虚线预留框 + 尺寸 + `alt` 文字（导出 PDF 时留白，不塌版） |

```jsonc
"figure": {
  "kind": "svg",              // 必填。svg（矢量，优先） | image（位图）
  "state": "ready",           // 必填。ready | placeholder
  "placement": "prompt",      // 必填。prompt（题干旁） | solution（解析里） | both

  "inline": "<svg xmlns=… viewBox=\"0 0 240 180\">…</svg>",  // 二选一：内联
  "src": "figures/q03.svg",   // 二选一：外链，相对本试卷文件所在目录
  "mime": "image/svg+xml",
  "sha256": "9f2c…",          // src 的文件指纹，防止图被改坏/换错

  "width": 240, "height": 180, // 必填。显示尺寸（px @96dpi）；placeholder 时即预留框尺寸
  "viewBox": "0 0 240 180",    // svg 可选，便于等比缩放
  "alt": "直角三角形 ABC，直角在 A，斜边 AB 上画有内切圆",  // 必填
  "caption": "图 1",           // 可选图注
  "credit": "AoPS",            // 可选来源/版权
  "source_code": { "lang": "asy", "text": "size(4cm); draw(unitsquare); …" }  // 可选：原始作图源码
}
```

### 为什么这么设计

- **`src` 与 `inline` 二选一**：`src` 适合仓库里存图（可 diff、可替换、文件小）；`inline` 适合导出单文件（发给别人一个 json 就能完整打开）。两者语义等价，由导出器决定用哪个。
- **`width`/`height` 必填**：网页上缺尺寸会闪跳（CLS），打印排版更需要知道占多高。占位状态尤其重要——**先把位置和尺寸留出来，图后补，版式不会塌**。
- **`alt` 必填**：一箭三雕——无障碍文本、图加载失败时的降级文案、占位期间“这张图该画什么”的说明。
- **`sha256`**：题库里的图会被人重画/替换，指纹能保证“这份卷子的第 3 题确实是当时那张图”，导出归档时不会张冠李戴。
- **`state: placeholder`**：直接对应题库里的 `has_diagram: true`。组卷时可以立刻把几何题排进去并留好位置，图晚点补——不用再把带图题整题排除。
- **`source_code`**：AoPS 的 `[asy]` 块、TikZ 源码值得留着，将来接 Asymptote/TikZ 渲染器可以直接重绘，不必依赖位图。

### 约定

- 图放在试卷同级目录：`users/<user>/tests/figures/<paper_id>/q03.svg`，`src` 写 `figures/<paper_id>/q03.svg`。
- SVG 里的描边/文字用 `stroke="currentColor"` / `fill="currentColor"`，这样深色模式下自动反色（校验器会给 warning 提醒）。
- 矢量优先：同一张图能画成 SVG 就别用 PNG；位图给 `mime` + `width`/`height`（按 2x 导出以免高分屏糊）。
- 一张图只描述一件事；解析里需要的辅助线图用第二个 `figure`（`placement: "solution"`）而不是塞进题干那张。

---

## 6. `content_hash`

```
sha256( json.dumps(questions, ensure_ascii=False, sort_keys=True, separators=(",", ":")) )
```

写成 `"sha256:<64 位小写 hex>"`。用途：缓存渲染结果、查重（同一份卷子被生成两次）、判断“这份卷子到底改没改”。

图通过 `inline` / `src`+`sha256` 参与哈希，所以换图会改变哈希。**改完题目记得重算**：

v1.1 起，算哈希前会先剔除每个 question 的 `classification` 与所有 `x-*` 字段——
标注变了不算内容变了。因此在同一批题目上，1.0 与 1.1 算出的 `content_hash` 完全相同。

```bash
python scripts/validate_paper.py users/test/tests/aime_rand_01.json --hash
```

剔除清单以 `scripts/validate_paper.py` 的 `HASH_EXCLUDED_KEYS` 为准：`classification`（标注）与
`difficulty`（估计值）都不算内容，再加上所有 `x-*` 扩展字段。理由同上：标注和标定会反复变，
不该让已发布试卷的哈希失效，也不该逼着升 `paper_version`。

---

## 7. 与现有代码的对应关系

| 现在 | v1.1 | 备注 |
| --- | --- | --- |
| `server.py:generate_test` 组装 `test` 字典 | 同一处，追加 `format_version` / `paper_version` / `qid` / `figure` / `generator` / `version_history` | 改动局限在一个函数 |
| `bank/*.json` 的 variant `{position, source, question, choices, answer, solution, points, type, question_zh, solution_zh, subject, has_diagram}` | 逐字段搬进 `questions[]` | 字段名保持不变，零映射成本 |
| `has_diagram: true` | `figure: {kind:"svg", state:"placeholder", placement:"prompt", width, height, alt}` | 组卷时自动占位 |
| `TestRunner.tsx` 读 `q.n / q.source / q.question(_zh) / q.choices / q.answer / q.solution(_zh) / q.points / q.type` | 全部保留 | 前端目前**不读** `figure`，需要新增渲染分支 |
| 试卷落盘 `users/<user>/tests/<id>.json` | 同一路径 | 无需迁移目录 |

**前端渲染 `figure` 的最小改动**（`TestRunner.tsx`）：

```tsx
{q.figure?.placement !== 'solution' && (
  q.figure.state === 'ready'
    ? q.figure.inline
      ? <div className="fig" style={{width: q.figure.width, height: q.figure.height}}
             dangerouslySetInnerHTML={{__html: q.figure.inline}} />
      : <img className="fig" src={q.figure.src} alt={q.figure.alt}
             width={q.figure.width} height={q.figure.height} />
    : <div className="fig placeholder" style={{width: q.figure.width, height: q.figure.height}}>
        <span>{q.figure.alt}</span>
      </div>
)}
```

（`inline` 是仓库自己产出的 SVG，走 `dangerouslySetInnerHTML` 可接受；若将来允许外部导入，改为 `src` + 白名单清洗。）

---

## 8. 工具

```bash
# 校验（0 error 即通过；warning 不阻塞）
python scripts/validate_paper.py examples/demo_rand_01.json
python scripts/validate_paper.py users/test/tests/*.json --legacy-ok

# 旧卷（无版本号）→ 当前格式，输出 <name>.v1.json，不动原文件
python scripts/validate_paper.py users/test/tests/amc8_rand_01.json --upgrade

# 重算 content_hash
python scripts/validate_paper.py examples/demo_rand_01.json --hash

# 分类覆盖率：已分类 / 待分类 / 还没考虑过 / 已复核
python scripts/validate_paper.py examples/demo_rand_01.json --coverage

# 旧卷升级时顺手给每题种一个待分类占位
python scripts/validate_paper.py old.json --upgrade --mark-pending
```

```bash
# 自动分类 + 难度评级（需要本地推理服务器，见 classifier/README.md）
python -m classifier.probe_server                                   # 探活：模型名/延迟/思考档位
python -m classifier.classify --bank amc10 --v2 --dry-run            # 只看 prompt
python -m classifier.classify --bank amc10 --v2 --sample 20          # 抽样试跑
python -m classifier.classify --bank amc10 --v2                      # 全量，可断点续跑
python -m classifier.classify --stats                                # 进度 + 等级分布
```

```bash
# 把分类/难度回写进题库（bank/v2），只搬标注字段，不动题干
python scripts/apply_classification.py --stats                        # 先看每条库会标多少
python scripts/apply_classification.py --dry-run                      # 同上看，不落盘
python scripts/apply_classification.py                                # 写 bank/v2/*.json
python scripts/apply_classification.py --check                        # 复检题库是否落后于 jsonl
```

`--upgrade` 会做三件事：补 `format_version` / `paper_version: 1` / `version_history`；按 `n` 生成 `qid`；**按题干里的 `diagram`/`figure`/`shown`/`如图` 关键词**给题目预留 `figure` 占位框（和题库 `has_diagram` 用同一套启发式），并逐条打印哪几题被占了位。不想要就加 `--no-guess-figures`。

退出码：`0` 通过（含 warning）、`1` 有 error、`2` 文件读不了。

校验器额外查 schema 表达不了的部分：`answer` 是否在 `choices` 里、`section` 是否已声明、`qid`/题号是否重复、图文件是否存在且 `sha256` 匹配、内联 SVG 是否合法 XML、`total_points` 是否等于各题之和、`version_history` 与 `paper_version` 是否一致、`content_hash` 是否过期、`classification` 的 tag 是否在词表里（见第 4.5 节）、`difficulty` 对象是否自洽（见第 4.6 节）。

词表查找顺序：试卷同目录的 `uri` → 试卷目录下 `taxonomy/<id>.json` → 仓库 `taxonomy/<id>.json`。所以把一个 `taxonomy/` 目录和卷子一起打包发送，也能离线校验。

---

## 8.5 题库（bank）v1.0 与迁移

试卷是「一次考试的产物」，题库是「可抽的题源」。两者共用同一套题目字段，所以题库 v1.0 的 `variants[]` 里每个元素就是一个「没有 `n`、多了 `position`」的 `question` 对象。

```jsonc
{
  "format_version": "1.0",     // 与试卷同一套结构版本
  "bank_version": 1,           // 题库内容版本，抽题规则变了就 +1
  "competition": "AMC 8",
  "set": "A",
  "source_file": "amc8_A.json",// 从哪个旧文件转来的，便于回溯
  "count": 589,
  "figure_slots": 27,          // 有 figure 占位的题数，一眼看出待补图量
  "variants": [
    {
      "position": 1,           // 原卷题号，组卷时按它分池
      "qid": "q1a2b3c4d5e6f",  // 内容指纹，见下
      "source": "2019 AMC 8 Problem 1",
      "type": "multiple_choice",
      "question": "...",
      "choices": { "A": "1", "B": "2" },
      "answer": "B",
      "solution": "...",
      "figure": null           // 见第 5 节；有图则 placeholder
    }
  ]
}
```

**`qid` 怎么来的**：`"q" + sha1(source + "\0" + question)[:12]`。取的是**内容**而不是位置，所以重排题号、换文件都不会变。题库里确实存在同一道题重复出现的情况（`cmimc_A` 有 51 组重复行，爬虫产物），第二份起加确定性后缀 `-2`、`-3`，保证作答记录不会撞。

**迁移工具**：

```bash
python scripts/migrate_banks.py --dry-run --stats   # 只看，不写
python scripts/migrate_banks.py                     # 写 bank/*.v1.json，原文件不动
python scripts/migrate_banks.py --check             # 复检已生成的 *.v1.json
python scripts/migrate_banks.py --dry-run --notes   # 打印每一条 type/answer 的改写理由
```

迁移做四件事：补 `qid`；把 `type` 归一到四值枚举（旧 `integer` → `integer_answer`；缺失的按「有选项且答案是字母 → `multiple_choice`，整数 → `integer_answer`，小数 → `numeric`，都没有 → `proof`」推断）；把 `has_diagram` 换成 `figure` 占位框（320×240，`alt` 写明待重绘），然后删掉 `has_diagram`；物理题答案里内嵌的单位（`"7.0 ms^{-1}"`）拆成 `answer: "7.0"` + `grading.unit: "ms^{-1}"`，原值留在 `x-legacy_answer`。脚本幂等，跑两遍哈希不变。

当前存量：**39 个题库 / 9266 道题 / 144 个图占位**。

---

## 9. 还没做的（下一步）

1. `generate_test` 输出 v1.1 字段（`format_version` / `paper_version` / `qid` / `generator.seed` / `has_diagram → figure 占位`）。
2. `TestRunner.tsx` / 成绩页渲染 `figure`（三种状态），加 `.fig` 样式（含深色模式 token）。
3. 图库落盘约定 + 一个 `scripts/attach_figure.py <paper> <n> <svg|png>` 把图塞进 `figures/` 并回填 `src`/`sha256`/`width`/`height`、递增 `paper_version`。
4. 导出：网页 → 打印样式（`@media print`）→ PDF；导出时把 `src` 内联成 `inline` 得到单文件。
5. **标注已进 v2 题库**：`bank/v2/*.json` 的 2632 题全部带 `classification` + `difficulty`，`generate_test` 会原样带进生成的试卷（`scripts/apply_classification.py` 负责回写与 `--check`）。仍缺：v1 库（用户已决定弃用，不再跑）、人工抽检（`reviewed` 目前全为 `false`）、按考点/难度筛题的接口。

## 10. 留给 2.0 的候选

- 题干/解析改成 locale 映射 `{"en": "...", "zh": "..."}`，取代 `question_zh` 这种并列字段。
- `sections[].questions[]` 嵌套（现在用扁平 `questions[]` + `section` 标签，是为了兼容现有前端）。
- 顶层 `assets[]` 资源表，支持一图多题复用与打包导出。
- `rubric`（分步给分）与 `solution_steps[]`（可折叠的步骤级解析）。
- `classification` 的权重改成可加性约束（现在只校验范围，不校验总和），以及「先修关系」`prereq: [...]`（判断某题是否超纲）。
