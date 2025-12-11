# HAR 最小负载最小化工具

这是一个可配置的 HAR 请求最小化实验框架。它会批量读取 HAR 中的请求，按配置筛选目标接口，自动尝试删减请求头与请求体参数，并通过可配置的对比策略判定是否与基线响应一致，最终输出最小负载报告，并可选写回新的 HAR 文件。

## 功能概览
- **配置驱动**：所有行为（代理、筛选范围、对比策略、最小化顺序等）均由 JSON/YAML 配置控制，命令行可以临时覆盖关键路径。
- **灵活筛选**：支持按方法、Host、URL 正则、条目索引等规则筛选请求，并可进一步指定实际执行范围。
- **可选去重**：可开启“完全一致请求”去重，按方法 + URL + 请求参数合并重复条目（导出 HAR 也会去重），避免浪费请求次数。
- **多策略对比**：内置状态码、长度浮动、固定字符串、正则表达式等多种子策略，且支持 AND/OR 组合判断。
- **ddmin 最小化**：对 header 与 body 参数分别执行分治删减，可设置保护字段、候选正则等，自动缓存成功组合作为回退。
- **额外置空尝试**：可在最小化后逐个尝试将剩余参数值置空并验证，进一步缩小负载。
- **报告与导出**：输出 JSON 报告（含原始/最小化统计、响应信息、匹配结果），也能在原 HAR 上写入最小化版本及 `_minimized` 元数据。

## 快速开始
1. 安装依赖（建议使用虚拟环境）：
   ```bash
   pip install -e .
   ```
2. 复制 `example_config.yaml`，根据需求调整：
   - `input_har`：原始 HAR 路径。
   - `filters` / `scope`：筛选规则。
   - `comparator`：对比策略与逻辑。
   - `minimization`：是否最小化头/体、保护字段等。
   - `client`：超时、代理、限速。
   - `output_har`（可选）：写回最小化 HAR。
3. 运行命令行：
   ```bash
   python -m har_minimizer.cli --config your_config.yaml --log-level INFO
   ```
   如需临时覆盖输入/输出路径，可传入 `--input-har`、`--output-har`、`--report`。
4. 查看结果：
   - `report_path` 指定的 JSON 报告记录每个请求的最小化明细。
   - 若配置了 `output_har`，即可在新 HAR 中看到最小化后的请求及 `_minimized` 元数据。

## 配置提示
- `minimization.headers` 中的 `protected`/`ignore` 适合放必需头部（如 Cookie），`candidate_regex` 可缩小测试范围。
- `minimization.body` 支持 `auto` 检测 Content-Type，也可以强制 `json`/`form`/`raw`。当 `treat_empty_as_absent=false` 时，删除的字段会以空字符串保留。
- 需要进一步压缩请求体时，可开启 `minimization.body.try_blank_values`，最小化结束后会逐个尝试将保留字段的值置空再校验，只保留必须保留原值的字段。
- `client.rate_limit.requests_per_second` 可防止压测目标接口；当前实现串行执行（`max_concurrent=1`）。
- `max_rounds_per_request` 用于限制 ddmin 触发的请求次数，避免极端 HAR 引发爆炸式测试。
- 如需跳过重复请求，可在 `filters.deduplicate_identical` 设为 `true`，会按方法 + URL + 查询参数 + 请求体 去重，仅保留首个出现的条目，导出的 HAR 也会同步去重。

## 报告字段
每个数组元素表示一个请求：
- `index`/`method`/`url`/`path`/`query`：请求基本信息。
- `baseline`、`final`：对应响应的 `status` 与 `length`。
- `matched_baseline`：最终请求是否与基线一致。
- `headers`、`body`：原始数量、参与候选数量、最终数量。
- `minimized_headers` / `minimized_body`：最终保留下来的头部与请求体文本。
- `error`：基线或最小化过程中出现的异常描述。

## 目录结构
```
har_minimizer/
├── cli.py              # CLI 入口
├── config.py           # 配置解析/合并
├── har_loader.py       # HAR 读取与结构化
├── filtering.py        # 请求筛选
├── http_client.py      # HTTP 会话与限速
├── comparator.py       # 响应对比策略
├── minimizer.py        # ddmin 逻辑与回退
├── orchestrator.py     # 调度、报告、导出
├── reporting.py        # 报告与 HAR 写回
├── models.py           # 数据结构
└── __init__.py
```

## 注意事项
- 请在测试/预发环境使用，避免对生产接口造成高频访问。
- HAR 的敏感头部（如 Cookie）应放入 `protected` 列表，防止被误删。
- 如果基线请求本身失败，该条目会被跳过并在报告中记录错误。

欢迎根据自身场景扩展新的对比策略或输入输出格式。
