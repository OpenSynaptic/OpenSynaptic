---
layout: default
title: 文档组织
language: zh
---

# 文档组织（2026-04-01）

本文件定义了本地工作空间的当前文档布局。

## 目录结构

```text
docs/
├── README.md
├── INDEX.md
├── QUICK_START.md
├── DOCUMENT_ORGANIZATION.md
├── DOCUMENTATION_ORGANIZATION_FINAL.md
│
├── architecture/   # 架构和 FFI 分析
├── api/            # API 实现说明
├── features/       # 功能指南
├── guides/         # 用户/运营商/开发人员指南
├── plugins/        # 插件开发文档
├── reports/        # 报告、进度说明、变更日志
├── internal/       # 内部维护文档
├── releases/       # 发布说明和公告
└── assets/         # 图像和媒体资源
```

## 类别目的

1. `architecture/`：架构内部和 FFI 相关设计分析。
2. `api/`：API 实现报告和 API 特定技术说明。
3. `features/`：功能重点指南（例如端口转发变体）。
4. `plugins/`：插件开发规范、快速开始套件和快速参考。
5. `guides/`：操作方法文档和运营快速参考。
6. `reports/`：历史报告、修复说明、变更日志和完成摘要。
7. `internal/`：维护人员面向的过程和故障排除说明。
8. `releases/`：公开发布说明和公告记录。

## 如何使用此布局

1. 从 `docs/README.md` 开始获取概览导航。
2. 使用 `docs/INDEX.md` 进行完整文件发现。
3. 使用 `docs/QUICK_START.md` 进行基于角色的导航。
4. 在匹配的类别下添加新文档；避免根级 markdown 增长。

## 维护说明

- 保持主动维护的文档使用英文。
- 优先使用指向规范文档的链接，而非重复内容。
- 添加、移动或删除文件时更新索引。
