# 试卷 JSON 格式 v1.0

MockTest Maker 的试卷（mock paper）交换格式。一个 `.json` 文件 = 一份可作答、可判分、可导出 PDF 的完整试卷。

配套文件：

| 文件 | 作用 |
| --- | --- |
| `schema/paper-1.0.schema.json` | JSON Schema（draft 2020-12），机器可校验的字段/类型/枚举 |
| `examples/demo_rand_01.json` | 完整示例：无图 / 内联 SVG / 占位待补 三种状态各一题 |
| `scripts/validate_paper.py` | 校验器 + 旧卷升级器（纯标准库，无依赖） |

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
  "format_version": "1.0",        // 必填。格式版本号（结构版本）
  "paper_version": 2,             // 必填。试卷版本号（内容版本），从 1 开始
  "id": "aime_rand_01",           // 必填。稳定标识，同时是文件名主干
  "title": "AIME — Random Mock #1 · 2026-11-02 20:10",
  "competition": "AIME",
  "category": "Math",
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
  "content_hash": "sha256:73ad4b32…",   // 可选，见第 6 节
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
  "subject": "geometry",
  "difficulty": "medium"         // easy | medium | hard
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

```bash
python scripts/validate_paper.py users/test/tests/aime_rand_01.json --hash
```

---

## 7. 与现有代码的对应关系

| 现在 | v1.0 | 备注 |
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

# 旧卷（无版本号）→ v1.0，输出 <name>.v1.json，不动原文件
python scripts/validate_paper.py users/test/tests/amc8_rand_01.json --upgrade

# 重算 content_hash
python scripts/validate_paper.py examples/demo_rand_01.json --hash
```

`--upgrade` 会做三件事：补 `format_version` / `paper_version: 1` / `version_history`；按 `n` 生成 `qid`；**按题干里的 `diagram`/`figure`/`shown`/`如图` 关键词**给题目预留 `figure` 占位框（和题库 `has_diagram` 用同一套启发式），并逐条打印哪几题被占了位。不想要就加 `--no-guess-figures`。

退出码：`0` 通过（含 warning）、`1` 有 error、`2` 文件读不了。

校验器覆盖 schema 表达不了的部分：`answer` 是否在 `choices` 里、`section` 是否已声明、`qid`/题号是否重复、图文件是否存在且 `sha256` 匹配、内联 SVG 是否是合法 XML、`total_points` 是否等于各题之和、`version_history` 与 `paper_version` 是否一致、`content_hash` 是否过期。

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

1. `generate_test` 输出 v1.0 字段（`format_version` / `paper_version` / `qid` / `generator.seed` / `has_diagram → figure 占位`）。
2. `TestRunner.tsx` / 成绩页渲染 `figure`（三种状态），加 `.fig` 样式（含深色模式 token）。
3. 图库落盘约定 + 一个 `scripts/attach_figure.py <paper> <n> <svg|png>` 把图塞进 `figures/` 并回填 `src`/`sha256`/`width`/`height`、递增 `paper_version`。
4. 导出：网页 → 打印样式（`@media print`）→ PDF；导出时把 `src` 内联成 `inline` 得到单文件。

## 10. 留给 2.0 的候选

- 题干/解析改成 locale 映射 `{"en": "...", "zh": "..."}`，取代 `question_zh` 这种并列字段。
- `sections[].questions[]` 嵌套（现在用扁平 `questions[]` + `section` 标签，是为了兼容现有前端）。
- 顶层 `assets[]` 资源表，支持一图多题复用与打包导出。
- `rubric`（分步给分）与 `solution_steps[]`（可折叠的步骤级解析）。
