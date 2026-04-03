---
layout: default
title: 根目录文档清理报告
language: zh
---

# 根目录文档清理报告

**报告日期**：2026-04-01  
**范围**：仅本地工作空间

---

## 当前结果

- 根目录 markdown 文件：**2** 个（`README.md`、`AGENTS.md`）
- `docs/` 下的 markdown 文件：**98** 个
- 存储库中的 markdown 文件（不包括 `.venv`）：**111** 个

这确认了 markdown 文档集中在 `docs/` 下，根目录级别的 markdown 保持最少。

---

## 根目录 vs Docs 布局

### 存储库根目录（markdown）

- `README.md`
- `AGENTS.md`

### `docs/` 分类

- `architecture/`（4 个）
- `api/`（2 个）
- `features/`（5 个）
- `guides/`（10 个）
- `plugins/`（10 个）
- `reports/`（31 个）
- `internal/`（12 个）
- `releases/`（8 个）

---

## 为什么这种结构有帮助

- 保持根目录清洁，用于项目级入口点。
- 使文档易于按主题分类发现。
- 简化维护和索引。

---

## 维护者指南

1. 仅在 `docs/` 下添加新文档。
2. 保持根目录 markdown 限于 `README.md` 和 `AGENTS.md`。
3. 结构变更时更新 `docs/INDEX.md` 和 `docs/README.md`。
4. 保持维护的文档为英文。
