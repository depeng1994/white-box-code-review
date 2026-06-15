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
