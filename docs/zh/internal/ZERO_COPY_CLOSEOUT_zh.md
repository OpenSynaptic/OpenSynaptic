---
title: 零复制收工
language: zh
---

# 零复制收工

## 范围

本收工记录了 OpenSynaptic 传输和融合路径收敛后的当前零复制状态。

本阶段涉及的主要文件：
- `src/opensynaptic/core/pycore/unified_parser.py`
- `src/opensynaptic/core/pycore/core.py`
- `src/opensynaptic/core/layered_protocol_manager.py`
- `src/opensynaptic/services/transporters/main.py`
- `src/opensynaptic/core/physical_layer/protocols/{rs485,can,lora}.py`
- `src/opensynaptic/utils/security/security_core.py`

## 运行时策略

- `engine_settings.zero_copy_transport = true`（默认行为）使用类字节透传和只读视图。
- `engine_settings.zero_copy_transport = false` 为兼容性回滚保留旧版字节物化后备方案。

## 被认为已完成的内容

- 传输管理器和分层协议管理器发送路径是零复制优先的。
- 融合帧构建/解码热路径是 memoryview/bytearray 优先的。
- 安全 XOR 路径支持原位写入。
- 组件测试包括融合的类字节回归覆盖。

## 收工验证

```powershell
py -3 -u scripts/zero_copy_closeout.py --runs 3 --total 100000 --config Config.json
```

或通过标准测试：

```powershell
py -3 -u src/main.py plugin-test --suite component
py -3 -u src/main.py plugin-test --suite stress --total 100000 --workers 1 --no-progress
```

## 备注

- 详见英文原始文档了解完整的技术细节和性能指标。
