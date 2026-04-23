# OpenSynaptic v1.4.1 发布说明

> 发布日期：2026-04-23  
> 对应 tag：`v1.4.1`  
> 变更范围：`pyproject.toml`、`src/opensynaptic/core/rscore/rust/Cargo.toml`、`.gitignore`

---

## 概述

v1.4.1 为补丁版本，修复 wheel 构建流程中的三个问题，不包含任何功能变更或 API 改动。

---

## 修复内容

### 1. 取消追踪 `utils/c/bin/` 下的编译产物

`src/opensynaptic/utils/c/bin/` 目录下的 DLL / LIB / EXP 文件此前被错误地纳入 git 追踪。尽管 `.gitignore` 已有对应规则，但规则是在文件被追踪之后才添加的，导致规则失效。

本次通过 `git rm --cached` 将所有编译产物从索引中移除。现在本地构建时不再会有旧版本 Windows DLL 意外打包进其他平台的 wheel。

**涉及文件：**
- `src/opensynaptic/utils/c/bin/os_rscore.dll` / `.tmp.dll`
- `src/opensynaptic/utils/c/bin/os_base62.dll` / `.lib` / `.tmp.exp` / `.tmp.lib`
- `src/opensynaptic/utils/c/bin/os_security.dll` / `.lib` / `.tmp.exp` / `.tmp.lib`

### 2. 修正 Cargo.toml 版本号

`src/opensynaptic/core/rscore/rust/Cargo.toml` 中的版本号遗留为 `1.3.0`，与 `pyproject.toml` 的 `1.4.x` 不一致。`os_rscore_version()` C-ABI 函数会返回错误的版本字符串。

本次修正为 `1.4.1`，与项目版本保持同步。

### 3. 补全 `before-build` 中的 C 原生库构建步骤

`pyproject.toml` 的 `[tool.cibuildwheel] before-build` 仅安装了 `cffi`，缺少调用 `build_native.py` 编译 `os_base62` / `os_security` C 原生库的步骤。CI 通过 `CIBW_BEFORE_BUILD` 环境变量覆盖了该值，所以 CI 产出的 wheel 一直是正确的，但本地直接运行 `cibuildwheel` 时无法正确构建。

本次在 `before-build` 中补充了 `build_native.py` 的调用，使本地与 CI 行为一致。

---

## 升级说明

无 API 变更，直接升级即可。已安装的 wheel 的运行时行为与 v1.4.0 完全相同。
