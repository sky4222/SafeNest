---
name: pynq-validation
description: Audit PYNQ overlay files before loading hardware, compare accelerator output with a golden reference, and diagnose PS/PL integration failures using explicit evidence.
---

先读README.md。用scripts/check_overlay.py只读核对配套文件、器件和必需IP；用scripts/compare_arrays.py比较已对齐的参考/硬件.npy。参数由实际工程提供，不复制SafeNest的硬件地址或算法参数。元数据PASS不代表bit/HWH配对正确或硬件验收通过。按pitfalls.md定位故障，按prompts.md组织与大模型协作，记录人工修正和复测证据。
