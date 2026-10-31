# 本次实际验证（2026-10-31）

- tests/test_tools.py通过：缺失文件/损坏XML、IP缺失、器件不符及数值相等/不同/容差/形状/NaN/Inf/大整数。
- 本项目真实HWH只读检查：必需axi_dma_0、alarm_mailbox、alarm_score_0均存在；--device 7z020通过。
- --device xc7z020clg400-1按预期失败：HWH中只有7z020，不能证明完整封装和速度等级。完整器件应另核对构建工程。
- 主机检查不加载FPGA，无MMIO，不测试物理通信；跨第二种板卡尚未验证。
- 提示词为此次提炼，未做稳定性统计；不以测试脚本通过冒充提示词已稳定验证。

复现：从包目录运行python tests/test_tools.py；从仓库根运行python skill/pynq_validation/scripts/check_overlay.py board/safenest_audio.bit --require-ip axi_dma_0 --require-ip alarm_mailbox --require-ip alarm_score_0 --device 7z020。
