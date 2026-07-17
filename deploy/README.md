# Deployment

`phase0_manifest.txt` 列出首次板端能力探针需要复制到 `/sdcard` 的文件。正式部署脚本
将在 Phase 0 确认 CanMV v1.8 的文件系统和工具链后加入。最终部署包应只包含
`main.py`、`nuedc_k230/`、选定设备配置、K230 模型及运行所需字体，不复制测试数据和
主机工具。
