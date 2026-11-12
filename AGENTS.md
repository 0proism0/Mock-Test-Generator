# AGENTS.md

给接手的 agent 看的落地说明。目标是：**读完这一页就能跑起来、知道东西在哪、不踩已经踩过的坑。**
人看的项目介绍在 `README.md`；试卷格式规范在 `docs/paper-format.md`（当前 v1.1）；
题目分类法词表在 `taxonomy/amc-v1.json`（3 层：板块 → 考点 → 题型标签）。

---

## 1. 这是什么

竞赛数学的**模拟卷生成器 + 在线做题站**。

- 后端：`app/server.py`，**单文件、纯 Python 标准库、零依赖**（Flask 没被用到，别被 `requirements.txt` 误导）。
- 前端：`app/web/`，React 19 + TypeScript 6 + Vite 8，构建产物 `app/web/dist` 由 `server.py` 在 `/` 直接托管。
- 老界面：`app/static/index.html`（vanilla JS），`dist` 不存在时兜底，也可直接访问 `/legacy`。
- 题库：`bank/` 下的 JSON，**不联网、不调用模型**，生成试卷时只是分层随机抽题，题干一字不改。

## 2. 60 秒跑起来

```powershell
python app/server.py                     # 后端，默认 http://localhost:8020
pwsh scripts/build.ps1                   # 或 scripts\build.bat / sh scripts/build.sh —— 构建 React（需要 Node 20+）
pwsh scripts/start.ps1 -Dev              # 或 scripts\start.bat dev —— API :8020 + Vite HMR :5173
pwsh scripts/watch.ps1                   # 改了前端不想开 dev server 时：持续重建 dist
```

端口：默认 **8020**，用环境变量 `MOCKTEST_PORT` 覆盖。改端口只改 `app/server.py:40` 的默认值即可——
`app/web/vite.config.ts`、三套 `scripts/start.*` 都从同一个环境变量读，别再各处硬编码。

常见一次性自检：

```powershell
cd app/web; npx tsc -b ; npm run build   # 类型 + 构建
curl http://127.0.0.1:8020/api/banks     # 后端活着吗（200 且返回 ~25 张卡）
```

## 3. 仓库地图

| 路径 | 是什么 |
|---|---|
| `app/server.py` | 全部后端：HTTP 路由、认证、题库加载、组卷、统计、PK、班级、学校文档、练习 |
| `app/web/src/` | React 前端（见 §6） |
| `app/web/dist/` | 构建产物，gitignore，由 server 托管 |
| `app/static/index.html` | 老 UI，兜底 |
| `app/latex_wrap.py` | 帮老 UI 包 LaTeX 的小工具 |
| `bank/<slug>_<set>.json` | **题库真源**：`{competition, set, variants[]}` |
| `bank/<slug>_<set>.v1.json` | 同一批题按试卷格式 v1.0 迁移的副本（加 `qid`、规范化 `type`、`has_diagram`→`figure` 占位） |
| `bank/v2/*.json` + `bank/v2/figures/*.svg` | **含图题库**（amc10 / amc12），导入源在仓库外，见 §4.3 |
| `tests/` | 已生成的试卷 JSON（**受控文件，146 个，别乱删**） |
| `schema/`, `examples/`, `docs/paper-format.md` | 试卷 JSON 格式 v1.1 的规范 / Schema / 示例 / 文档（`paper-1.0.schema.json` 冻结保留） |
| `taxonomy/amc-v1.json` | AMC 考点分类体系：8 板块 / 86 考点 / 339 题型标签（共 433 节点），`classification` 只引它的 id，不复制词表 |
| `classifier/` | 题库自动分类 + 难度评级（本地大模型），见 `classifier/README.md`、`classifier/SCHEMES.md` |
| `scripts/` | 构建、启动、校验、迁移、导入脚本（每个都有 `.ps1/.bat/.sh` 三套或单份 Python） |
| `scraper/` | 抓题流水线（AoPS wiki、官方 PDF），当前与实际 bank 之间有断链，见 §12。`shsid_crawler.py` 可用：从 OpenSHSID 移植的 SHSID LinkedClassroom(Moodle) 爬虫，抓取课程/章节/文件到 `raw/shsid/`（需学生账号，凭据走 `--username/--password` 或 `SHSID_USER`/`SHSID_PASS` 环境变量） |
| `competitions.yaml` | 竞赛注册表（分类、来源适配器、状态） |
| `screenshots/` | **放截图的地方**，见 §11 |

被 gitignore 的运行时数据（都在仓库根，**绝不提交**）：`users.json`、`sessions.json`、
`friends.json`、`messages.jsonl`、`classes.json`、`class_reports.jsonl`、`school_docs.json`、
`school_docs/`、`worksheets/`、`pk/`、`users/`、`results.jsonl`、`*.log`。

## 4. 数据模型

### 4.1 题库（bank v1，经典库）

```json
{ "competition": "amc10", "set": "A",
  "variants": [ { "position": 1, "source": "AMC 10 2003 Problem 4",
                  "question": "...", "choices": ["...", ...],
                  "answer": "B", "solution": "...",
                  "type": "multiple_choice", "points": 6 } ] }
```

- `position` = 原卷题号。组卷就靠它：**第 N 题只从各年原卷第 N 题里抽**，难度梯度天然保留。
- `type` 枚举：`multiple_choice` / `integer_answer` / `numeric` / `proof`。
- 缺 `solution` 或 `answer` 的题不参与常规抽题；某一位置凑不出候选就整卷 400（不出半套卷）。

### 4.2 试卷（paper format v1.1）

`docs/paper-format.md` 是完整规范，`schema/paper-1.1.schema.json` 是机器可校验版
（`paper-1.0.schema.json` 冻结保留，校验器同时接受 `1.0` / `1.1`）。两个版本号分工：

- `format_version`（结构版本，`1.x` 只增字段不破坏）——改结构时动它。
- `paper_version`（内容版本，整数，每次改卷 +1）——改内容时动它。
- `figure` 三态：缺省 = 无图；`state:"ready"` = 有图（`src` / `inline` 二选一）；
  `state:"placeholder"` = 留位待补（必须有 `width`/`height`/`alt`，不得带 `src`/`inline`）。
- `difficulty` 是**对象**（`level` 必填，**1–20 分制**：20 = 平均的 AMC 12 第 25 题，
  AIME/奥赛题在 20 以上，上限 60；可带 `scale/band/score/method/confidence/components`），
  旧的 `"easy"|"medium"|"hard"` 仍可读。算法见 `classifier/SCHEMES.md`。
- `content_hash` = 对 `questions` 做 `sha256(json.dumps(..., sort_keys=True, separators=(",",":")))`，前缀 `sha256:`；
  算之前剔除 `classification`、`difficulty` 和所有 `x-*`（都是标注/估计，不是内容）。
- `classification`（**v1.1 新增**，详见 `docs/paper-format.md` §4.5）：每题的分类槽位。
  三态：字段缺省/null = 还没考虑过；`{state:"pending"}` = 排队待分类；
  `{state:"done", primary, tags[]}` = 已分类。`primary` 必须 ∈ `tags`，`tags` 1–8 条带 `weight`。
  词表不在卷子里，顶层只用 `taxonomy: {id: "amc-v1"}` 引一下。
  层级 = id 段数：`combinatorics`(板块) → `combinatorics.lattice_paths`(考点) →
  `combinatorics.lattice_paths.forbidden_points`(题型标签)。`primary` 不可只写板块；
  `methods.*` 是跨板块方法轴，可与任意知识板块同挂。

```powershell
python scripts/validate_paper.py tests\amc8_rand_01.json --legacy-ok   # 校验
python scripts/validate_paper.py <paper> --upgrade                    # 旧卷 → 当前格式（另存 <name>.v1.json）
python scripts/migrate_banks.py --check                               # 校验所有 *.v1.json
python scripts/validate_paper.py <paper> --coverage                   # 分类覆盖率
python scripts/validate_paper.py <paper> --upgrade --mark-pending     # 升级时种待分类占位
```

### 4.3 含图题库（bank v2）

- 内容：`bank/v2/amc10.json`、`bank/v2/amc12.json` + `bank/v2/figures/*.svg`（250+ 张）。
- 来源：`C:\Users\xiang\Projects\AutoAOPS\papers`（仓库外，所以必须提交 `bank/v2/`，无法重跑复现）。
- 重新导入：`python scripts/import_papers.py --source <dir>`（`--dry-run` / `--check`）。
- 服务端：`BANK_V2`、`BANK_VERSIONS = (1, 2)`、`bank_files(slug, version)`、`load_bank(slug, round, version)`、
  `generate_test(..., version=)`；卡片上带 `versions / v2_variants / v2_figures`。
- 前端：`NewTest` 有版本选择框（localStorage `mt_bank_version`），v2 生成失败会**自动回退 v1** 并把
  `fallback: true` 传回，`TestRunner` 显示提示。
- 做题页（`routes/TestRunner.tsx`）的题头有两个徽章：**考点**（`classification.primary`，
  经 `/api/taxonomy` 查 `amc-v1` 的 en/zh 标签；`title` 里列出全部 `tags`）与
  **难度**（`difficulty.level`，显示 `L13 · 中等`，`title` 里有 `amc20` 刻度）。
  未标注的老卷子没有这两个字段，难度徽章回退到按题号猜的旧逻辑。
- **已标注**：每个 variant 都带 `classification`（`amc-v1` 词表 id）与 `difficulty`（1–20 分制对象），
  顶层有 `taxonomy` + `classified_at`。回写用 `python scripts/apply_classification.py`，
  它只搬运这两个字段、绝不改题干；`--check` 判断题库是否落后于 `classifier/out/*_v2.jsonl`。
  `generate_test` 会把这两个字段原样带进生成的试卷。

### 4.4 题库浏览（`/questions`）

- 后端 `GET /api/questions`：把 `bank/*.json`（v1）与 `bank/v2/*.json` 建成一个平铺索引
  （`build_qindex()`，按文件 mtime 缓存，11898 行约 0.3s），支持 `q`（全文，含题干/来源/选项/答案/解析）、
  `comp`、`v`（1/2）、`domain`、`topic`（含子节点前缀）、`level_min`/`level_max`、`type`、
  `figure`、`classified`、`sort`（default/level_asc/level_desc/position）、`limit`（≤200）/`offset`。
  返回 `{total, items, counts:{all, competition, domain, level, type}}`，facets 跟随当前搜索词。
- 前端 `routes/Bank.tsx`（侧栏 Bank）：搜索框 250ms 防抖 + 7 个筛选下拉 + 2 个复选 + 分页（25/页），
  卡片显示难度徽章、考点徽章（经 `/api/taxonomy` 翻译）、题型/库/配图/分值，展开看选项、答案、解析、其余标签。
- v1 题库没有 `classification`/`difficulty`，所以那些卡上只有题型与来源；`--classified` 勾选可只看已标注的 v2 题。
- 每张卡右下角有 **Report a problem**（`components/ReportIssue.tsx`，做题页也挂了同一个控件）：
  选原因（`wrong_statement` / `wrong_answer` / `wrong_solution` / `broken_latex` / `missing_figure` /
  `duplicate_choices` / `not_a_problem` / `other`）+ 可选备注，`POST /api/report` 追加一行到
  `reports.jsonl`（**gitignored**，含 qid/来源/题干前 400 字，方便离线核对）。
  登录用户可用 `GET /api/reports?mine=1` 回看自己的上报；原因码必须与 `server.py` 的
  `REPORT_REASONS` 和 `ReportIssue.tsx` 的 `REASONS` 三处同步。

## 5. 后端结构（`app/server.py`，约 1800 行）

顺序：常量（`COMP_META` 竞赛元数据、`ROUND_PATTERNS`、`DEFAULT_POINTS`）→ 认证 → 在线状态 →
friends/chat → PK → 班级 → 学校文档 → worksheet 解析 → 题目筛选（`is_eligible`、`round_allows_proofs`、
`points_for`）→ 题库加载（`bank_files`、`load_bank`、`list_banks`）→ `generate_test` → 统计 →
`class Handler(BaseHTTPRequestHandler)` 路由表。

主要路由：

```
GET  /api/me /api/tests /api/banks /api/taxonomy /api/questions /api/results /api/stats /api/announcements /api/friends
GET  /api/reports   (own problem reports)
GET  /api/generate/<slug>[/<round>]?v=<1|2>   GET /api/test/<id>   GET /figures/<file>
GET  /api/practice  /api/classes  /api/class/<code>/reports  /api/schools  /api/school/docs
GET  /api/pk  /api/pk/invites  /api/pk/<gid>  /api/chat/<user>  /api/worksheets
GET  /api/test/<id>/classify   (per-question teacher classification)
POST /api/register /api/login /api/logout /api/result /api/practice /api/report
POST /api/practice_similar   (wrong questions -> same-topic variant test)
POST /api/friends/(request|accept|decline|remove)  /api/chat/<user>
POST /api/class/create /api/class/join  /api/pk/(challenge|respond|start)
POST /api/school/join /api/school/leave /api/school/docs/upload  /api/worksheet/generate
```

一切非 `/api/`、非 `/figures/` 的 GET 交给 `_serve_web()`：先找 `app/web/dist`，找不到再回退 `app/static`。

## 6. 前端结构（`app/web/src/`）

```
main.tsx / App.tsx            路由与全局 provider（Auth → I18n → Theme）
routes/                       每个页面一个文件（Bank, MyTests, NewTest, TestRunner, Practice,
                              Worksheet, Classes, Friends, Pk, Stats, Whiteboard, Login,
                              Analysis 模考分析报告, Mistakes 错题+同类题练习…）
routes/whiteboard/            白板的纯逻辑（data.ts / keys.ts）
components/Layout.tsx         侧栏 + 顶栏；components/icons.ts 是全站图标唯一来源
lib/api.ts                    唯一的 API 客户端，视图不要自己 fetch()
lib/i18n.ts                   en + zh 全部文案（一个对象里两份）；lib/i18n-provider.tsx 提供 t()
lib/theme.ts + theme-provider.tsx  light / dark / system，localStorage `mt_theme`
index.css                     全部样式 + 设计 token
```

## 7. 铁律（改之前先读这一段）

1. **图标只从 `components/icons.ts` 引。** 它 re-export react-feather + lucide-react（缺的补 lucide），
   并导出 `IconComponent` 类型。**绝不手写 `<svg>`，绝不用 unicode emoji 当图标。**
2. **文案不塞符号。** 装饰性符号一律由图标承担；i18n 里只留真正的数学符号（`− ∛ √ ↔ ≤` 等）。
   `whiteboard/keys.ts` 里的 `→ ∞ ∑` 是 LaTeX 输入快捷键，**不是图标，禁止替换**。
3. **颜色用 token，不写死。** `index.css` 顶部 `:root` 定义亮色，`[data-theme="dark"]` 覆盖；
   新样式一律引用 `var(--ink-2)` / `var(--success-border)` 这类变量，否则深色模式下会瞎。
   （历史遗留：`index.css` 靠后的 `.ws-*` / `.dr-*` 少量仍是写死的亮色值，改到那片时顺手 token 化。）
4. **文案要中英双份。** 新增 key 时 `i18n.ts` 的 en 和 zh 都要加，缺一边就会出现英文兜底或空串。
5. **仓库行尾是 CRLF、无 BOM。** `write` 类工具默认写 LF，
   写完必须转 CRLF：`[IO.File]::WriteAllText($p,$t,(New-Object System.Text.UTF8Encoding($false)))` 且
   `$t = $t -replace "\r\n","\n" -replace "\n","\r\n"`。`.bat` 还要保持纯 ASCII（BOM 会让 `@echo off` 失效）。
6. **脚本/命令行输出用 ASCII 英文。** 控制台是 GBK，Python 打印中文或 emoji 会
   `UnicodeEncodeError: 'gbk' codec can't encode character`。
7. **不要重构传输格式。** 试卷 JSON 同时是磁盘格式和 API 载荷，字段名沿用 snake_case 扁平结构。
8. **分类只写 `classification`，不要写 `subject`。** `subject` 是历史字段（自由字符串，全库只有 48 处，
   值全是 `Physics`）。tag id 必须来自 `taxonomy/amc-v1.json`，写错 id 校验器直接报 error。

## 8. 地雷清单（都真踩过）

- **`generate_test()` 会自己落盘。** 哪怕只是做一次进程内抽样验证，也会在 `tests/` 里留下文件。
  验完必须 `git clean -n tests/` 预览 → `git clean -f tests/` 清理**未跟踪**文件。
  **绝不能用通配删已跟踪文件**（曾误删 30 个受控试卷，靠 `git checkout -- tests/` 才救回来）。
- **`bank/` 的 glob 会双载。** `BANK.glob(f"{slug}_*.json")` 同时匹配 `amc8_A.json` 和 `amc8_A.v1.json`，
  `bank_files()` 里有 `if name.endswith(".v1.json"): continue` 守卫，**别删**。
- **"功能没生效" 先怀疑旧进程。** 端口上可能挂着一个改动前启动的 `server.py`。
  判断代码新旧的唯一办法：`/api/banks` 里有没有 `versions` 字段。先 `Stop-Process` 再重启。
- **沙箱挡子进程。** `vite`（dev / build）、`git fetch`(ssh)、`Stop-Process`/`tasklist`/`Get-NetTCPConnection`
  在 workspace-write 下会 `spawn EPERM` 或 Access denied，需要提权到 `danger-full-access` 才能跑。
- **5173 只绑 `::1`。** 连 `127.0.0.1:5173` 被拒是正常现象，用 `localhost:5173`。
- **`cmimc` 抽不出题是数据问题**：458 题全部 `type=proof` 且无 `answer`，
  `round_allows_proofs()` 直接判不合格 → `load_bank('cmimc')` 返回 0 条。
- **`generate_test` 的 type 兜底是错的**：题库里既无 `type` 又无 `choices` 的题会被标成
  `multiple_choice` + `choices: null`（约 962 道）。读 v1 题库可绕过，但兜底逻辑本身没改。

## 9. 交付前验证清单

```powershell
cd app/web; npx tsc -b                              # 必须 exit 0
cd app/web; npm run build                           # 需 danger-full-access
python scripts/validate_paper.py <改过的卷> --quiet  # 动过试卷格式时
python scripts/validate_paper.py <改过的卷> --coverage  # 动过 classification 时
python scripts/migrate_banks.py --check             # 动过 bank/*.v1.json 时
python scripts/apply_classification.py --check      # 动过 bank/v2 的标注时
python -m classifier.classify --bank <slug> --v2 --sample 5   # 动过 classifier/ 时先抽样跑
```

再起服务做一次冒烟：`GET /` 200 且 HTML 引用的 `assets/index-*.js` 与本次构建产物同名；
`GET /api/banks` 200。用完把进程和端口收干净。

## 10. Git 与 PR

- `origin` = `zengyuxiang0921/Mock-Test-Generator`（本人的 fork）
- `upstream` = `0proism0/Mock-Test-Generator`（**主仓库，不能直接 push**）
- 本地 `main` 跟踪 `upstream/main`。**曾经因为这样裸 `git push` 把提交直接推上了主仓库**，
  已经加了防呆 `git config branch.main.pushRemote origin`，别删。
- 工作分支形如 `feat/xxx`，推 `origin`，PR 用：
  `https://github.com/0proism0/Mock-Test-Generator/compare/main...zengyuxiang0921:<branch>?expand=1`
- 提 PR 前顺手看一眼 `git status`：`bank/*.v1.json` 有 12 MB+，别不小心把二进制/数据文件塞进去。

## 11. 截图放这里

用浏览器或测试脚本截的图一律丢进仓库根的 **`screenshots/`**，不要散落在项目各处：

```
screenshots/
  dark-mode-home.png
  v2-figure-question.png
```

- 该目录已被 `.gitignore` 忽略（只保留 `screenshots/README.md`），**不会被提交**。
- 命名：`<场景>-<简述>.png`，日期敏感的加 `YYYYMMDD`。
- 目录不存在时直接 `New-Item -ItemType Directory screenshots`。
- 注意 `.gitignore` 里有一条全局 `*.png`：**任何需要入库的 png 都会被忽略**，
  真要有图片资产入库请用 SVG（题库配图就是 `bank/v2/figures/*.svg`）。

## 12. 已知未完成 / 待决定

- `bank/*.v1.json`（39 个、12 MB）是否长期留在 git 里没定；原始 `.json` 都在，
  `scripts/migrate_banks.py` 可重跑。
- v1 题库迁移时按 `has_diagram` 预留了 **144 个 `figure` 占位**，等真正的图补上。
- **v2 已回写，v1 没做**：`bank/v2/*.json` 的 2632 题已带 `classification` + `difficulty`
  （`scripts/apply_classification.py`，`--check` 可复验）；`bank/*.json`（v1，9272 题中的主体）
  仍未标注 —— 用户已决定 v1 弃用，不再跑。下一步：人工抽检 + 组卷时按考点/难度筛。
- **逐题作答已采集**（2026-11 起）：`/api/result` 接收 `details[]`（`{n, given, ok}`），
  前端 TestRunner 在交卷时上报。基于它的功能：`/analysis` 模考分析报告
  （成绩总览 / 分段得分 / 失分明细 / 能力画像 / 提分空间，见 `lib/analysis.ts`），
  `/mistakes` 错题本 + `POST /api/practice_similar`（按 classifier 考点找同主题变式组卷）。
  考点解析优先级：教师手标（`/api/test/<id>/classify`，存 `tests/<id>.cls.json`）
  > bank 内嵌 `classification.primary` 经 `/api/taxonomy` 翻译。Elo / IRT（方案 C/D）
  的数据前提已满足，算法本身还没写。
- `scraper/` 断链：`download_manager.py` / `ingest_server.py` 写 `raw/aops_wiki/<slug>.jsonl`，
  但所有 `build_*_banks.py` 只读 `raw/wikitext_problems.jsonl`，新抓的赛事进不了 bank。
- `requirements.txt` 与实际不符（列了未使用的 Flask，缺 curl_cffi / pdfplumber / pypdf / playwright / pyyaml）。
- 图题口径不一致：`scrape_aops.py` 保留 `[asy]`，`build_wiki_banks.py` 一律丢图题，所以 v1 库里有图题 0 道。
- `competitions.yaml` 状态漂移：amc8/10/12/aime 标 `done`，其余约 40 个仍 `pending`。
