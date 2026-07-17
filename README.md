# NEUDC 2025 C - K230

本仓库是 `NEUDC_2025_C` 的 K230 部署子项目。它面向 01Studio CanMV K230 AI
开发板，不在代码中兼容树莓派的 V4L2、OpenCV GUI 或 Tkinter 运行时。

## 已冻结的目标平台

- 开发板：01Studio CanMV K230 AI 开发板；
- 固件：`CanMV_K230_01Studio_Emmc_micropython_v1.8-0-gc2d1f5c_nncase_v2.11.0.img.gz`；
- 摄像头：GC2093；
- 显示与输入：01Studio 3.5 寸 800×480 电容触摸屏；
- 目标：静态目标，准确率优先，单次完整测量尽量不超过 5 秒；
- 功能范围：普通几何、分离/重叠正方形、数字识别、距离、倾斜物面、静默预识别、相机调试与正式触摸界面；
- 扩展边界：允许升级或定制固件，并允许增加 C/C++ 扩展。

固件升级后必须新建或更新设备配置，并重新运行硬件能力探针和回归测试，不能默认
不同固件版本的 Media、`image`、`cv_lite`、LVGL 接口完全兼容。

## 目录

```text
main.py                     CanMV `/sdcard/main.py` 入口
nuedc_k230/
├── app/                    测量编排、状态机和结果契约
├── platform/               Sensor、Display、TOUCH、存储和内存管理
├── vision/                 K230/OpenMV/cv_lite/C++ 视觉实现
└── ui/                     800×480 触摸界面
config/                     固件、设备和相机 profile
assets/models/              K230 专用 kmodel 或轻量分类器参数
deploy/                     SD 卡部署清单和脚本
docs/                       架构、移植阶段和验收规则
tests/                      K230 单元测试及跨平台黄金样本清单
tools/                      主机端或板端诊断工具
runtime/                    板上日志、采集图和临时结果，不入库
```

详细设计见 [架构说明](docs/architecture.md) 和
[移植与验收计划](docs/migration_plan.md)。

## 当前状态

当前已进入 Phase 0。`main.py` 会运行能力探针，并逐步写入：

```text
runtime/phase0/runtime_probe.json
```

探针会验证固件与模块、扫描 CSI 0～2、采集 1920×1080 RGB888 样帧、显示与触摸、
显示/算法双通道、图像原语和可选稳定性测试。某一步失败不会阻止后续步骤，报告状态会是
`complete_with_errors`。

运行前确认没有其他程序占用 Sensor/Display。将仓库根目录内容复制到 `/sdcard`，在
CanMV IDE 中运行 `main.py`；显示触摸测试期间按屏幕提示触摸三次。首次短测保持
`config/probe.json` 的 `stability_seconds` 为 `0`。短测通过后改为 `1800`，执行30分钟
稳定性测试。
