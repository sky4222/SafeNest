# 本次实际验证（2026-10-31）

- tests/test_tools.py通过：缺失文件/损坏XML、IP缺失、器件不符及数值相等/不同/容差/形状/NaN/Inf/大整数。
- 本项目真实HWH只读检查：必需axi_dma_0、alarm_mailbox、alarm_score_0均存在；--device 7z020通过。
- --device xc7z020clg400-1按预期失败：HWH中只有7z020，不能证明完整封装和速度等级。完整器件应另核对构建工程。
- 主机检查不加载FPGA，无MMIO，不测试物理通信；跨第二种板卡尚未验证。
- 提示词为此次提炼，未做稳定性统计；不以测试脚本通过冒充提示词已稳定验证。

复现：从包目录运行python tests/test_tools.py；从仓库根运行python skill/pynq_validation/scripts/check_overlay.py board/safenest_audio.bit --require-ip axi_dma_0 --require-ip alarm_mailbox --require-ip alarm_score_0 --device 7z020。

## 2026-11-01 技能整理复核

- 更新智能体入口，新增接口契约模板及常驻Overlay、同输入对照、时钟来源三个流程。
- skill-creator格式检查通过；元数据与数组比较测试通过。
- 当前board/safenest_audio.bit和同名HWH只读检查通过，确认axi_dma_0、alarm_mailbox、alarm_score_0及7z020字段。
- 本机默认临时目录写入受限，工具测试改用仓库之外的D:/FPGA/tmp/skill_validation；格式校验以Python UTF-8模式运行。未改变测试断言。
- 此次未下载Overlay、运行Vivado或操作实体板；新增流程的工程效果引用原有观察，不计为新增上板验证。
