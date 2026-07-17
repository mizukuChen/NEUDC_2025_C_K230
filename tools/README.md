# Tools

本目录存放 K230 专用能力探针、板端诊断工具和部署辅助程序。能够继续使用主仓库现有
标定、靶图生成和批量评估脚本的功能，不在这里复制一份。

`phase0_probe.py` 与当前 `main.py` 执行相同的 Phase 0 探针，适合在 CanMV IDE 中手动
打开运行。探针参数位于 `config/probe.json`。把板端生成的报告复制回主机后，可运行：

```bash
python tools/validate_phase0_report.py runtime_probe.json
```
