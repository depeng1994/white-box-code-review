# white-box-code-review

代码白盒检视看板，用于展示 PR 合入质量、检视意见密度、评分分布和贡献者统计。

## 本地查看

```bash
.venv/bin/python backend/review_board.py --db data/review_board.sqlite3 serve --host 127.0.0.1 --port 8090
```

打开 `http://127.0.0.1:8090/`。

## 生成 GitHub Pages 静态数据

```bash
.venv/bin/python scripts/export_static_dashboard.py --db data/review_board.sqlite3 --output demo/dashboard-static.json
```

GitHub Pages 发布 `demo/` 目录，静态页面会读取 `dashboard-static.json`。

## 每日自动刷新并推送

常驻任务会在本地时区每天 0 点运行，默认同步“昨天当天”已合入 PR，刷新 SQLite 与 `demo/dashboard-static.json`，如果数据有变化则自动提交并推送到 `origin/main`。

先确认环境变量可用：

```bash
export GITCODE_API_TOKEN="your-token"
```

先手动跑一次验证链路：

```bash
.venv/bin/python scripts/daily_refresh_and_push.py --once --dry-run
```

放到 tmux 常驻：

```bash
tmux new -s review-board-daily -c /mnt/workspace/work/white-box-code-review \
  '.venv/bin/python scripts/daily_refresh_and_push.py 2>&1 | tee -a data/daily_refresh.log'
```
