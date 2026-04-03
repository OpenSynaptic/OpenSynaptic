---
title: Web 命令参考
language: zh
---

# Web 命令参考

## 范围

本文档作为基于当前本地代码库的英文维护版本重建。

- 文件：`docs/guides/WEB_COMMANDS_REFERENCE.md`
- 更新日期：2026-04-01
- 重点：操作员/开发人员工作流和当前 CLI 和服务代码中的命令级用法。

## 代码定位点

- `src/opensynaptic/main.py`
- `src/opensynaptic/CLI/build_parser.py`
- `src/opensynaptic/CLI/parsers/`
- `src/opensynaptic/services/tui/`
- `src/opensynaptic/services/web_user/`

## Web 界面命令

### API 端点

```
GET  /api/status              # 获取应用状态
GET  /api/config              # 获取配置信息
POST /api/restart             # 重启应用
GET  /api/metrics             # 获取性能指标
POST /api/device/{id}/action  # 执行设备操作
```

### Web 服务调试

```powershell
# 启动 Web 服务
os-node web --port 8080

# 验证 Web 接口
curl http://localhost:8080/api/status

# 查看日志
os-node logs --service web
```

## 实践验证

使用以下命令验证当前工作区中的相关行为：

```powershell
pip install -e .
python -u src/main.py plugin-test --suite component
python -u src/main.py plugin-test --suite stress --workers 8 --total 200
```

## 相关文档

- `docs/README.md`
- `docs/INDEX.md`
- `docs/QUICK_START.md`
- `AGENTS.md`
- `README.md`

## 备注

- 本页面已规范化为英文并与当前本地路径对齐。
- 对于规范化的运行时行为，建议参考 `src/opensynaptic/` 中的源模块。
