---
layout: default
title: 驱动程序快速参考
language: zh
---

# 驱动程序快速参考

驱动程序用法指南和双向通信说明的规范路径。

---

## 驱动程序契约

所有驱动程序应该公开：

- `send(payload: bytes, config: dict) -> bool`
- 可选 `listen(config: dict, callback)` 用于连续接收工作流

---

## 层映射

- 应用层（L7）：`mqtt`
- 传输层（L4）：`udp`、`tcp`、`quic`、`iwip`、`uip`
- 物理层（PHY）：`uart`、`rs485`、`can`、`lora`

---

## 监听器指南

- 在后台线程/任务中运行监听器循环。
- 保持驱动程序之间的回调签名一致。
- 在所有配置映射中将适配器密钥规范化为小写。
- 使用能力审计和集成测试进行验证。

---

## 验证命令

```powershell
python -u scripts/audit_driver_capabilities.py
python -u scripts/integration_test.py
```
