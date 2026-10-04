"""HealthLens 边缘网关（edge gateway）

一台常开的 Linux 小盒子（树莓派 Zero 2 W / 3B+ / 4 / 5 都够）：
连上 Muse 头环这类带蓝牙的低速生理设备，在盒子本地做频谱聚合，
只把「日粒度健康指标」推给 HealthLens 云端，原始波形不出户。

设计取舍（参照 Meta Muse Gadget SDK 的架构，但把它的方向掉个头）：
- 抄它的「设备侧常驻服务 + 命令白名单 + 可观测性 + webhook 上报」骨架；
- 不抄它的 `system.run`：那等于把 shell / sudo 交给一个远端 AI 助手，
  官方自己都写着 "Muse gets the same access to the machine as the account
  you install it for"，且自承 community device 无厂商验证、挡不住中间人。
  我们这边所有命令只读，且受白名单 + 路径受限约束。
"""
