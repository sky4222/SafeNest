# 可复用PYNQ技能包

入口：[使用说明](pynq_validation/README.md) · [智能体指令](pynq_validation/SKILL.md)

| 技能内容 | 复用方式 |
|---|---|
| Overlay元数据检查 | 传入自己的bit/HWH、器件和必需IP，生成只读检查JSON |
| 黄金参考数组比对 | 传入对齐后的参考与实际.npy，以及误差容限 |
| 接口契约模板 | 填写本工程数据格式、DMA、时钟复位与验证标准 |
| 集成与排错流程 | 按常驻Overlay、同输入对照、时钟来源流程定位 |
| 大模型协作模板 | 提供实际代码和报告，记录判断、人工修正及复测 |

[经验流程与来源](pynq_validation/workflows.md)、[排错清单](pynq_validation/pitfalls.md)、[验证记录](pynq_validation/validation.md)说明适用范围和效果。整个目录可独立复制，脚本不依赖SafeNest业务代码或固定板卡地址。跨板实体复用需在目标平台另行验证。
