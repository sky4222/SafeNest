---
name: pynq-validation
description: Validate PYNQ Overlay metadata and accelerator outputs, or diagnose Overlay switching, DMA stalls, inconsistent preprocessing and clock constraints. Use for PS/PL integration and reusable verification workflows; not for implementing a board-independent bitstream or certifying hardware from metadata alone.
---

# PYNQ软硬件协同校验

先阅读README.md确定工具用法与验证范围。对用户已有工程做检查时，先记录当前构建和失败位置，再决定是否修改；不能用重新加载Overlay代替故障定位。

## 文件与接口

使用interface_contract.md填写目标器件、IP、数据类型、长度、时钟复位和传输结束约定。未提供的参数从源码、HWH、构建脚本读取，不照搬其他工程的地址、采样率或寄存器位。

运行scripts/check_overlay.py只读检查bit及同名HWH。它不访问板卡。记录两文件哈希和构建来源；哈希仅标识文件，不证明同次构建。必须核对完整器件时，HWH只有器件系列不能视为完整匹配。

## 数值验证

先用相同输入完成旁路，再对齐黄金参考与硬件输出，最后测试应用结果。遵循workflows.md中的同输入对照流程，以scripts/compare_arrays.py比较.npy；不要仅凭最终分类相同判定计算正确。整数和浮点误差标准分别由接口契约确定。

## 故障定位

按pitfalls.md和workflows.md从最小失败步骤定位。区分Overlay下载、IP查找、MMIO读写、DMA启动和等待；更换Overlay后重建所有依赖该设计的驱动对象。时序摘要通过仍需检查时钟来源与未约束端口；不添加无依据的false_path来消除告警。

## 交付证据

输出实际执行的检查、输入/输出路径、构建身份、结果和下一项可验证动作。主机测试、RTL仿真、上板测试分别标注。validation.md记录本包已验证范围；prompts.md可用于组织协作，不能把模板预期效果写成实测效果。
