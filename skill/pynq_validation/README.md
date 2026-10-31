# 通用PYNQ校验与排错包

整个目录可复制到其他题目。脚本不绑定SafeNest、音频采样率、寄存器地址或板卡型号。

## 1. Overlay文件只读检查

- 场景：更换/上传Overlay后，在访问PL前检查元数据；Python标准库，Windows/Linux。
- 用法：`python scripts/check_overlay.py design.bit --require-ip your_dma --device your_part`。多个IP重复传入--require-ip。输出JSON，成功退出0，失败退出1。
- 来源：本项目旧Tcl混入、新版bit/HWH版本核对，以及多次重配后掉线的观察。先检查文件身份和IP清单可缩小排查范围。
- 已验证：缺失文件、损坏XML、必需IP缺失、器件不符的小样例；本项目HWH另做只读实测。详见validation.md。
- 失效：HWH格式改变、器件字段缺失。SHA256只记录文件身份，不能证明bit/HWH同次构建；不检查时序、管脚、复位逻辑或物理功能。

## 2. 黄金参考数组校验

- 场景：CPU参考与加速器输出已保存为.npy，依赖NumPy。
- 用法：`python scripts/compare_arrays.py reference.npy actual.npy --atol 0 --rtol 0`。定点默认逐值相同，浮点容差应由算法误差预算确定。
- 来源：FIR定点参考、PCM解码及WAV/内存推理一致性检查；不能只看分类标签是否相同。
- 已验证：相等、单点差异、给定容差、形状不符、NaN/Inf及超大整数拒绝。
- 失效：参考本身错误；窗口、延迟或形状未对齐；复数、对象数组及超过2**53的值。脚本不自动选窗或补偿延迟。

## 3. 提示词模板与踩坑清单

prompts.md有软硬件划分和证据审查模板；pitfalls.md包含触发条件、排查步骤、验收和边界。来源和验证范围分别写在文件内。模板是本次根据协作观察提炼，尚未验证跨题目稳定性，不宣称“经过多次稳定验证”。

## 复用步骤与验证边界

复制目录后先运行`python tests/test_tools.py`。再传入自己的器件/IP和参考输出，保存输入、JSON结果、构建hash、人工修正和板端复测记录。当前验证仅覆盖工具逻辑及本项目元数据；尚未在第二种实体板上实测，不能据此保证跨板兼容或比赛额外加分。
