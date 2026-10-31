# MQTT 配置

原始调试 Notebook 使用 safenest/alarm 和 true/false；之前文档使用 safenest/alert 和 ALARM，两者不同。手机订阅主题与负载必须和实际发布一致。

电脑运行 Mosquitto，手机用电脑 WLAN 地址，板卡用电脑以太网地址访问同一1883端口。认证配置通过本地用户名和密码提供，不上传密码。先测试电脑到手机，再使用 monitor 的 alarm_callback 接入真实 PL 新触发事件。不能把 hw_alarm.arm() 当成已触发报警。原调试代码发布成功返回不等于手机已接收，需保留接收证据。
