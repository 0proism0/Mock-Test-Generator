# classifier/ — 题库自动分类与难度评级

用本地推理服务器上的大模型，给题库里每道题打上 **考点（`classification`）** 和 **难度（`difficulty`）**，产物直接是 paper format v1.1 的合法 JSON。

- 难度方案与算法细节：**[SCHEMES.md](SCHEMES.md)**
- 难度标尺在真实题目上长什么样：**[SCALE.md](SCALE.md)**
- 字段规范：`docs/paper-format.md` §4.5（分类）/ §4.6（难度）
- 考点词表：`taxonomy/amc-v1.json`（8 板块 / 86 考点 / 339 题型标签）

## 1. 模型服务器

| 项 | 值 |
| --- | --- |
| endpoint | `http://192.168.2.103:20300/v1` |
| model | `qwen3.8-27b`（`max_model_len` 240000） |
| 思考档位 | `reasoning_effort: "low"`（保留短思考；`"none"` 或 `chat_template_kwargs.enable_thinking=false` 可完全关掉） |

先探活（不改任何数据）：

```powershell
python -m classifier.probe_server            # 模型名 / 延迟 / 思考档位 / JSON 输出能力
```

`probe_server.py` 的作用是把"这台服务器能干什么"钉下来，**服务端升级后先重跑它**。

## 2. 跑分类

```powershell
python -m classifier.classify --bank amc10 --v2 --dry-run        # 只看 prompt 长什么样，不调模型
python -m classifier.classify --bank amc10 --v2 --sample 10      # 抽样跑 10 题
python -m classifier.classify --bank amc10 --v2                  # 全量（可断点续跑）
python -m classifier.classify --bank amc8 --sample 5             # 不指定 --v2 就走 bank/*.json
python -m classifier.classify --stats                            # 看每个 jsonl 的进度和等级分布
```

| 开关 | 作用 |
| --- | --- |
| `--bank <slug>` | 题库名，匹配 `bank/<slug>_*.json` 或 `bank/v2/<slug>*.json` |
| `--file <path>` | 直接指定一个题库文件 |
| `--v2` | 走 `bank/v2/`（含图题库） |
| `--sample N` | 均匀抽 N 题（跨题号跨度，用于试跑/验收） |
| `--limit N` | 只处理前 N 道未分类的 |
| `--positions 1,10,25` | 只取原卷这些题号（定向抽样，常与 `--sample` 连用） |
| `--redo-pending` | 只重试 jsonl 里记成 pending 的题（失败题不会永久卡住） |
| `--force` | 重分类已做过的题（覆盖已有结果） |
| `--dry-run` | 只拼 prompt 打印，不发请求 |

产物：

```
classifier/out/<bank>.jsonl        每行一题：classification + difficulty + llm 原始回复 + usage
classifier/out/<bank>_smoke.json   可直接给校验器的 paper v1.1（抽样时生成）
```

`.jsonl` 是**增量写、可断点续跑**的：中断后重跑会跳过已完成的题，记成 pending 的题下次会重试。
题目的身份用 `qid`（题库自带，或 `sha1(source + 题目)` 算出来），**不能用题号**——题号是它在原卷里的位置，各年份的"第 1 题"会撞成同一个 id。
删掉 jsonl 就是从头再来。

## 2.5 看哪些题有误（HTML 页）

分类的每一次调用都会顺带做**表面检查**（缺图/LaTeX 坏/题干截断/选项重复/答案缺失…），结果写在每行的 `issue` 里。
把这些行渲染成一页可以筛、可以勾“已处理”的 HTML：

```powershell
python -m classifier.report              # 生成 classifier/out/report.html，双击就能看
python -m classifier.report --serve      # http://127.0.0.1:8021/ ，每次刷新都重读 jsonl（跑批时实时跟踪）
python -m classifier.report --all-scales # 连旧 1-5 标尺的结果一起看（默认只看 amc20）
python -m classifier.report --all-rows   # 没有问题的题也一起渲染（默认只渲染有 issue 的）
```

页面按 severity 排序（blocker 在前），可按 code / 题库 / 分类状态筛，支持搜题干；
展开一行能看到完整题干、选项、答案、解析、分类标签和模型的 `why`。
“已处理”勾选存在浏览器 localStorage 里，刷新不丢。

## 3. 产物校验

```powershell
python scripts/validate_paper.py classifier/out/amc10_smoke.json --coverage
```

必须 `OK (0 error, ...)`。`--coverage` 会顺便打印分类覆盖率、词表形状和板块分布。

## 3.5 写回题库（bank/v2）

分类只写在 `out/*_v2.jsonl`，题库不会自己变。回写用仓库根的脚本：

```powershell
python scripts/apply_classification.py --stats     # 先看每条库会标多少、有没有没标到的
python scripts/apply_classification.py --dry-run   # 同上，不落盘
python scripts/apply_classification.py             # 写 bank/v2/*.json
python scripts/apply_classification.py --check     # 题库落后于 jsonl 时 exit 1
```

- 它只搬 `classification` 与 `difficulty` 两个字段，题干/选项/答案/解析/配图/分值一个字节都不动；
  顶层补 `taxonomy` 与 `classified_at`。
- 只吃 `difficulty.scale == "amc20"` 且 `classification.state == "done"` 的行 —— 旧 1–5 标尺的结果不会被写进去。
- 写完会用 `scripts/validate_paper.py` 的规则逐题复验（词表 id、tag 权重、难度自洽），有 error 就 exit 1。
- `--with-issues` 额外把模型上报的缺陷写进 `x-issue`（默认不写，缺陷清单看 HTML 页就够了）。

## 4. 结构

```
classifier/
  config.json          端点/模型/采样参数/并发/重试
  probe_server.py      服务器能力探针（模型名、思考档位、JSON 输出可靠性）
  report.py            把 out/*.jsonl 渲染成问题检查页（--serve 实时看）
  llm.py               OpenAI 兼容客户端（stdlib urllib）+ JSON 修复 + 截断重试
  taxonomy.py          词表加载、紧凑目录生成、id 解析（别名/末段/near 消歧）
  classify.py          CLI 主流程：读题库 → 拼 prompt → 并发跑 → 写 jsonl / paper
  prompts/classify.md  系统提示（含难度量表；{CATALOG} 处插入 433 节点目录）
  difficulty/
    prior.py           方案 A：竞赛 × 题号先验
    combine.py         融合：cold / early / mid / mature 四阶段权重
  review.py            人工抽检：逐题打印分类结果，重点看 why
  out/                 产物（已 gitignore）
```

## 5. 已知的服务器怪癖（别"优化"掉）

1. **不要用结构化输出。** `response_format: json_schema` / `json_object` 在这台服务器上会把内容打坏（实测返回 `{"primary":": "`），只能"提示里要 JSON + 本地修复"。
2. **长几何题会把 max_tokens 用在思考上。** 表现为 `content` 空、`reasoning_tokens == completion_tokens == max_tokens`。`llm.py` 的 `_starved()` 自动加倍预算重试一次，不算失败。
3. **前缀缓存有效但要"暖机"。** system prompt 约 20.7k 字符（≈5.2k tokens），第一次跑 `cached_tokens=0`，之后命中率 99%+。所以别频繁改 `prompts/classify.md`，改一次全库重跑就多付一遍冷缓存。
4. **单题 3–5 秒**（concurrency 4）。9266 题的 v1 全库约 3–5 小时，`--sample` 验收再全量。

## 6. 验收（跑全量前先做）

```powershell
python -m classifier.classify --bank amc10 --v2 --sample 30
python -m classifier.review --limit 20          # 逐题打印：题干摘要 / primary / tags / level / why
```

人眼过一遍 `why`：如果出现"因为题干很长所以算难"这类理由，说明量表 prompt 被绕过了，先改 `prompts/classify.md` 再跑全量。
