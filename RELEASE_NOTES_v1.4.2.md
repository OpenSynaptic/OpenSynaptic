# OpenSynaptic v1.4.2 发布说明

**发布日期**：2026-07-18

## 修复内容

### 修复 sdist 打包时缺失 Rust 源码的问题

修复了 `pyproject.toml` 中 `exclude` 规则错误地排除了 Rust 源码目录的问题。

**问题表现**：用户通过 `pip install opensynaptic` 从 PyPI 安装时，报错 `manifest path src/opensynaptic/core/rscore/rust/Cargo.toml does not exist`。

**根本原因**：`pyproject.toml` 中的 `exclude` 规则将 Rust 源码从 sdist（源码包）中排除了，导致 `maturin` 构建时找不到 `Cargo.toml`。

**修复方式**：为 `exclude` 中关于 Rust 源码的规则添加 `format = "wheel"` 限定，使其仅对 wheel 包生效，而保留 sdist 中的 Rust 源码。

**涉及文件**：`pyproject.toml`

## 升级说明

无 API 变更，直接升级即可：

```bash
pip install --upgrade opensynaptic
