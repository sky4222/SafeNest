"""Run in the ORIGINAL MindSpore 1.5 training environment.
Usage: python verify_mindspore.py original.ckpt parity_case.npz
Checks official CKPT loading against repacked weights, then logits parity.
"""
import sys
import numpy as np
import mindspore as ms
from mindspore import nn, ops, Tensor, context
from mindspore.train.serialization import load_checkpoint, load_param_into_net
from pathlib import Path
context.set_context(mode=context.GRAPH_MODE, device_target="CPU")
class ConvBlock(nn.Cell):
    def __init__(self, in_channels, out_channels, kernel_size):
        super(ConvBlock, self).__init__()
        self.conv = nn.Conv2d(
            in_channels, out_channels, kernel_size=kernel_size,
            stride=1, pad_mode="same", has_bias=False,
        )
        self.bn = nn.BatchNorm2d(out_channels)
        self.relu = nn.ReLU()
        self.pool = nn.MaxPool2d(kernel_size=2, stride=2, pad_mode="valid")

    def construct(self, x):
        x = self.conv(x)
        x = self.bn(x)
        x = self.relu(x)
        return self.pool(x)

class Identification_Net(nn.Cell):
    def __init__(self, num_class=5, channel=1, keep_prob=0.5):
        super(Identification_Net, self).__init__()
        self.block1 = ConvBlock(channel, 32, 5)
        self.block2 = ConvBlock(32, 64, 5)
        self.block3 = ConvBlock(64, 128, 3)
        self.block4 = ConvBlock(128, 128, 3)

        self.global_mean = ops.ReduceMean(keep_dims=False)
        # 【改进】全连接层从 128->64->num_class 瘦身为 128->32->num_class
        self.fc1 = nn.Dense(128, 32)
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(keep_prob=keep_prob)
        self.fc2 = nn.Dense(32, num_class)

    def construct(self, x):
        x = self.block1(x)
        x = self.block2(x)
        x = self.block3(x)
        x = self.block4(x)

        # [B,128,H,W] -> [B,128]
        x = self.global_mean(x, (2, 3))

        x = self.relu(self.fc1(x))
        x = self.dropout(x)

        # 返回 logits，不添加 Softmax。
        return self.fc2(x)
parameters = load_checkpoint(sys.argv[1])
with np.load(str(Path(__file__).with_name("safenest_weights.npz")), allow_pickle=False) as weights:
    if set(weights.files) != set(parameters):
        raise ValueError("Parameter names differ")
    for key in weights.files:
        np.testing.assert_array_equal(weights[key], parameters[key].asnumpy())
net = Identification_Net(num_class=4, channel=1, keep_prob=0.5)
missing = load_param_into_net(net, parameters, strict_load=True)
if missing:
    raise RuntimeError("Unloaded parameters: " + str(missing))
net.set_train(False)
with np.load(sys.argv[2], allow_pickle=False) as case:
    expected = case["logits"]
    actual = net(Tensor(case["features"][None], ms.float32)).asnumpy()[0]
print("MindSpore logits:", actual)
print("NumPy logits:", expected)
print("Max absolute error:", float(np.max(np.abs(actual-expected))))
np.testing.assert_allclose(actual, expected, rtol=1e-4, atol=1e-4)
print("PASS: checkpoint values and inference logits match.")
