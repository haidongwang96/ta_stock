# Mootdx 实时行情服务

该服务只为 `stock_web` 的登录用户自选云图提供实时快照，不写入
`stock_data.db`，也不参与打分、选股或买卖信号计算。

## 启动

使用与 ta_stock 相同的 Python 环境，确认已安装 `mootdx`、`fastapi`、
`uvicorn` 和 `pandas`：

```bash
export MOOTDX_QUOTE_SECRET='replace-with-a-long-random-secret'
python services/intraday_quote_service.py
```

服务默认只监听 `127.0.0.1:8765`。`POST /quotes` 最多接受 300 个
Tushare 格式的沪深股票代码；结果仅在进程内缓存 8 秒。服务启动后的
第一次查询会探测可用的通达信节点，后续复用长连接，断线后自动重选。

## stock_web 配置

stock_web 使用相同密钥，并通过服务端 API 代理请求：

```bash
MOOTDX_QUOTE_SERVICE_URL=http://127.0.0.1:8765
MOOTDX_QUOTE_SECRET=replace-with-a-long-random-secret
```

行情服务不可用时，浏览器保留本次会话最后一次成功快照并显示“行情延迟”；
首次请求失败则显示灰色 `--`。
