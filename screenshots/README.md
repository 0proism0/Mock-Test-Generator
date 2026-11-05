# screenshots/

Agent 截图专用目录 —— 浏览器验证、UI 回归、调样式时的对比图都放这里。

**目录内容被 git 忽略**（`.gitignore` 里写了 `screenshots/*` + `!screenshots/README.md`），
只有这个 README 会进仓库，所以克隆下来目录结构还在。

## 命名

```
<场景>-<简述>.png          例：dark-mode-home.png
<场景>-<简述>-<YYYYMMDD>.png   需要区分时间时
```

场景建议沿用页面名：`newtest` / `testrunner` / `practice` / `worksheet` / `pk` / `whiteboard` / `mobile`。
要对比改前改后，用 `-before` / `-after` 后缀成对存。

## 注意

- `.gitignore` 里还有一条全局 `*.png`，意味着**任何** png 都进不了 git。
  真需要入库的图片资产请用 SVG（题库配图就是 `bank/v2/figures/*.svg`）。
- 别把截图塞到 `app/`、`tests/` 或仓库根，保持这里一个出口。
- 目录不存在时：`New-Item -ItemType Directory screenshots`。
