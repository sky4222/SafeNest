# SafeNest-PYNQ

基于PYNQ-Z2的声音事件识别与硬件计分报警原型。

PS执行音频解码、48 kHz至16 kHz转换、最高能量2秒选窗、log-Mel及四类NumPy CNN；PL包含音频接口、AXI DMA、257抽头定点FIR和三轮计分报警。类别为正常对话、碰撞/物体跌落、尖叫/喊叫、脚步。声学类别不等同于真实危险。

## 环境

- PYNQ-Z2，xc7z020clg400-1；Vivado 2023.1。
- 原型板端环境：PYNQ 3.1.1、Python 3.10.4；依赖见board/requirements.txt，精确依赖版本尚未冻结。
- 使用镜像中的audio-codec-ctrl UIO映射及/dev/i2c-1；本工程bit不能直接用于其他板卡。

## 接线与运行

耳机麦克风接HP+MIC。兼容3.3V的低电平蜂鸣器VCC接3.3V，GND接GND，控制接Arduino A0/Y11。网线连接电脑。

将整个board目录上传到PYNQ Jupyter的新目录，从该目录打开run_monitor.ipynb。先运行初始化与FIR/计分自检，再执行三轮真实录音测试。默认不连接MQTT、不保存原始WAV；结果写入runtime/。同时只运行一个占用PL的内核，初始化后不要加载base.bit。

板端.py、配置、权重、bit/hwh沿用原型版本；新Notebook入口仍待实体板验收。运行步骤及验收条件见report/board_acceptance.md。

## 从源码构建

在新Vivado 2023.1会话中，设置实际仓库绝对路径后执行：

```tcl
set repo_root [file normalize {/absolute/path/to/safenest}]
source [file join $repo_root build scripts create_project.tcl]
source [file join $repo_root build scripts build_bitstream.tcl]
```

项目生成于build/，配套bit/hwh导出到board/。已有项目可打开build/safenest_audio.xpr。源码路径重排已静态检查，干净重建仍待验证；历史实现的时钟/接口约束警告见build/reports/README.md。

## 测试

主机端安装NumPy/SciPy后执行：

```text
python sim/tests/test_alarm_host.py
python sim/tests/verify_host.py
python skill/pynq_validation/tests/test_tools.py
```

主机测试使用模拟MMIO/DMA，不操作实体板。FIR和报警RTL仿真分别在新Vivado会话中source build/scripts/run_sim.tcl和run_alarm_sim.tcl（使用绝对路径）。测试平台PASS才代表该项通过。

## 目录

| 路径 | 内容 |
|---|---|
| src/ | RTL、XDC、音频IP、板卡定义 |
| board/ | 唯一版本PS源码、权重、bit/hwh和运行入口 |
| sim/ | 仿真平台、输入/参考和主机测试 |
| build/ | 可重建脚本与历史工具报告 |
| data/ | 历史事件日志及证据说明 |
| skill/ | 可独立复制的校验脚本、提示词与排错案例 |
| report/ | 验收、MQTT、授权和验证范围说明 |
| third_party/ | 第三方来源与许可 |

PS源码与板端资源保持同目录，以保留原运行时相对路径。build/不包含Vivado缓存。alarm_policy.py和apply_priority25.py属于历史辅助接口，标准入口不需要调用。

## 当前边界

顺序处理存在采集空档；CNN运行于PS，FFT/Mel未硬件化。25%为人为设定的优先规则，未证明最优。日志不是独立标注测试集，不据此宣称准确率、宏F1或加速比。MQTT标准入口尚未接入，配置与事件语义见report/mqtt_setup.md。训练源码、数据划分及模型上游许可尚未收录。

## 许可

原创软件及文档采用MIT（LICENSE）；第三方IP与引用文件保留各自许可。模型权重与训练数据的上游来源、再分发条件仍需核实，详见report/license_status.md。
