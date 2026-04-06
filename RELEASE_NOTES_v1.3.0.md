# OpenSynaptic v1.3.0 Release Notes

> This release merges all v1.2.x improvements and new features directly into v1.3.0.
> No separate v1.2.x release was shipped.

---

## What's New in v1.3.0

### Bug Fixes — Critical

#### Wheel Installation Equivalence
`pip install opensynaptic` now produces a fully functional installation equivalent to running from source.

- **`standardization.py` wrote cache into `site-packages/`** — The `standardization_cache.json` path was resolved relative to `__file__`, which pointed inside the read-only site-packages directory after installation. This caused a `PermissionError` on every `OpenSynapticStandardizer` initialization. Fixed to resolve relative to `project_root` (the directory containing `Config.json`), which is always user-writable.
- **`libraries/__init__.py` wrong module import path** — Dynamic imports used `importlib.import_module("libraries.xxx")`, which fails after installation because the package is `opensynaptic.libraries`. Fixed to `"opensynaptic.libraries.xxx"`.

#### Runtime Data Not Shipped with Package
- `libraries/OS_Symbols.json`, `Prefixes.json`, and all `Units/*.json` UCUM data files are now bundled inside the wheel under `opensynaptic/libraries/`. Previously these were only present in the source tree and would be missing after `pip install`.
- All path resolution functions (`solidity.py`, `standardization.py`, `paths.get_lib_path()`) now check the package-internal path first, then fall back to `ctx.root/libraries` for source-tree compatibility.

---

### Bug Fixes — Build & Release

#### Cross-Platform Wheel Contamination
- **Windows `.dll` files in Linux wheels**: `src/opensynaptic/utils/c/bin/` is now fully gitignored (`*.dll`, `*.so`, `*.dylib`, `*.lib`, `*.obj`, `*.exp`, `*.tmp.*`). Each platform's CI now rebuilds native libraries fresh.
- **`CIBW_BEFORE_BUILD`** now executes `build_native.py` before maturin packages the wheel, ensuring each wheel contains only the correct platform's shared libraries.
- **Rust/C source files in wheels**: Added `[tool.maturin] exclude` entries to strip `rust/src/**`, `Cargo.toml`, `Cargo.lock`, `.cargo/**`, and C source files from binary wheels.

#### Release Workflow
- Fixed broken `cp -a plugins "$ROOT/"` in developer bundle step — `plugins/` directory was deleted in v1.2.x and this caused CI failures.
- Added `run-main.sh` to developer bundle artifacts.

---

### New Features

#### Cross-Platform Entry Points
- Added `scripts/run-main.sh`, `scripts/venv-python.sh`, `scripts/venv-pip.sh` — bash equivalents of the existing `.cmd` files for Linux/macOS developers cloning the repository.
- Added `run-main.sh` at repo root as a top-level shortcut (mirrors `run-main.cmd`).

#### Tab Completion for Linux/macOS
- Added `scripts/enable_argcomplete.sh` supporting bash, zsh (via `bashcompinit`), and fish (`--fish` flag).
- `--install` flag writes the activation line into the shell profile automatically.

#### ID Allocator — Performance
- Migrated `id_allocator.py` from `plugins/` into `src/opensynaptic/utils/id_allocator.py` (proper package location).
- Replaced `min(self._released)` O(n) scan with `heapq.heappop` O(log n) for released-ID recycling.

---

### Security

#### Plugin System
- **XSS in `display_api.py`**: Three locations used manual `.replace('<', '&lt;')` escaping. Replaced with `html.escape(str(x), quote=True)` which also covers `&` and `"` characters.
- **Silent exception swallowing** in `_auto_load_builtin_providers`: bare `except: pass` replaced with `os_log.warn(...)`.

#### Plugin CLI Argument Handling  
- Replaced three `_actions[-1].completer = ...` accesses in `CLI/parsers/plugin.py` with named option-string lookups (`next(a for a in p._actions if '--name' in (a.option_strings or []))`), eliminating fragile index assumptions.

#### Plugin Registry
- Added recursion depth limit (`_depth=0`, max 10) to `_deep_merge_missing` to prevent stack overflow on malformed plugin config.
- Removed double `dict.get()` calls in `get_plugin_config`.

#### TUI Plugins Panel
- `on_mount` and `query_one` calls wrapped in `try/except` to prevent widget lifecycle crashes from propagating.

---

### Repository Cleanup

- **`libraries/`** migrated into `src/opensynaptic/libraries/` — data files are now part of the installable package.
- **`data/id_allocation.json`**, **`data/secure_sessions.json`**, **`data/env_guard/`** added to `.gitignore` — these are runtime state files, not source artifacts.
- **`data/device_registry/`** was already gitignored; now fully documented.
- **Jekyll GitHub Pages files** (`_config.yml`, `index.html`, `_layouts/`) removed — documentation is served exclusively from the Docusaurus site at `opensynaptic.github.io`.
- Root directory reduced from ~12 visible items to 9 clearly categorized entries.

---

### Upgrade Guide

No breaking API changes. The upgrade path is:

```bash
pip install --upgrade opensynaptic==1.3.0
```

If migrating from a source-tree installation:

1. Run `os-node wizard` once after upgrade to ensure `~/.config/opensynaptic/Config.json` is generated with current defaults.
2. Delete any stale `cache/` directories next to old `Config.json` files — they will be rebuilt automatically.

---

## Compatibility

| Python | Status |
|--------|--------|
| 3.11   | ✅ Supported |
| 3.12   | ✅ Supported |
| 3.13   | ✅ Supported |

| Platform | Architecture | Status |
|----------|-------------|--------|
| Linux    | x86_64      | ✅ |
| Linux    | aarch64     | ✅ |
| Windows  | x86_64      | ✅ |
| macOS    | x86_64      | ✅ |
| macOS    | arm64 (M-series) | ✅ |

---

## Test Coverage

v1.3.0 ships with a fully verified exhaustive test suite across all layers.

| Script / Suite | Tests | Result |
|---|---|---|
| `pytest tests/` (unit + integration) | 9 | ✅ All pass |
| `scripts/integration_test.py` | 9 | ✅ 9/9 pass |
| `scripts/exhaustive_business_logic.py` (A–F) | 985 | ✅ 983 pass, 2 SKIP |
| `scripts/exhaustive_plugin_test.py` (A–E) | 205 | ✅ 205/205 pass |
| `scripts/exhaustive_security_infra_test.py` (A–D) | 43 | ✅ 43/43 pass |
| `scripts/exhaustive_orthogonal_test.py` (EP + XC) | 24 | ✅ 24/24 pass |
| **Total** | **1275** | **✅ 1273 pass, 2 SKIP, 0 fail** |

The 2 SKIPs are intentional: `mol=6.022e+23` and `AU=1e+06` exceed the Base62 int64 encoding ceiling (`~9.22×10¹⁴`) — a known hardware design constraint, not a bug.

See [TEST_REPORT_v1.3.0.md](TEST_REPORT_v1.3.0.md) for the full test report.

---

# OpenSynaptic v1.3.0 发布公告

> 本次发布将 v1.2.x 的所有改进与新特性直接合并进 v1.3.0。  
> v1.2.x 不单独作为正式版本发布。

---

## v1.3.0 新增内容

### 关键 Bug 修复

#### pip 安装与源码运行等效性

`pip install opensynaptic` 现在可以产生与源码直接运行完全等效的安装结果。

- **`standardization.py` 将缓存写入 `site-packages/`**：`standardization_cache.json` 的路径基于 `__file__` 解析，指向安装后只读的 site-packages 目录，导致每次 `OpenSynapticStandardizer` 初始化时报 `PermissionError`。已修复为相对 `project_root`（`Config.json` 所在目录）解析，始终在用户可写位置。
- **`libraries/__init__.py` 模块导入路径错误**：动态导入使用 `importlib.import_module("libraries.xxx")`，安装后模块名应为 `opensynaptic.libraries`，导致 `ModuleNotFoundError`。已修复为 `"opensynaptic.libraries.xxx"`。

#### 运行时数据已打包进 wheel
- `libraries/OS_Symbols.json`、`Prefixes.json` 及所有 `Units/*.json` UCUM 单位数据文件现在作为 `opensynaptic/libraries/` 的一部分打入 wheel。此前这些文件仅存在于源码树，pip 安装后会缺失。
- 各路径解析函数（`solidity.py`、`standardization.py`、`paths.get_lib_path()`）现在优先查找包内路径，再 fallback 到 `ctx.root/libraries`，保持源码运行兼容性。

---

### 构建与发布 Bug 修复

#### 跨平台 wheel 污染
- **Linux wheel 包含 Windows `.dll`**：`src/opensynaptic/utils/c/bin/` 中所有平台编译产物（`*.dll`、`*.so`、`*.dylib`、`*.lib`、`*.obj`、`*.exp`、`*.tmp.*`）已全部加入 `.gitignore`，每个平台 CI 现在独立重新编译原生库。
- **`CIBW_BEFORE_BUILD`** 现在在 maturin 打包 wheel 前执行 `build_native.py`，确保每个 wheel 只包含当前平台的共享库。
- **Rust/C 源码进入 wheel**：在 `[tool.maturin] exclude` 中新增条目，排除 `rust/src/**`、`Cargo.toml`、`Cargo.lock`、`.cargo/**` 及 C 源文件。

#### Release 工作流
- 修复了开发者包构建步骤中 `cp -a plugins "$ROOT/"` 的错误—— `plugins/` 目录在 v1.2.x 中已删除，此错误导致 CI 失败。
- 开发者包产物中新增 `run-main.sh`。

---

### 新特性

#### 跨平台入口脚本
- 新增 `scripts/run-main.sh`、`scripts/venv-python.sh`、`scripts/venv-pip.sh`——对应现有 `.cmd` 文件的 bash 版本，供 Linux/macOS 开发者使用。
- 新增根目录 `run-main.sh` 快捷入口（对应 `run-main.cmd`）。

#### Linux/macOS 命令行补全
- 新增 `scripts/enable_argcomplete.sh`，支持 bash、zsh（通过 `bashcompinit`）及 fish（`--fish` 参数）。
- `--install` 参数自动将激活语句写入 shell 配置文件。

#### ID 分配器性能提升
- 将 `id_allocator.py` 从已删除的 `plugins/` 目录迁移至 `src/opensynaptic/utils/id_allocator.py`（标准包路径）。
- 将已释放 ID 的回收从 `min(self._released)` O(n) 扫描改为 `heapq.heappop` O(log n)。

---

### 安全修复

#### 插件系统
- **`display_api.py` XSS 漏洞**：三处使用手工 `.replace('<','&lt;')` 转义，替换为 `html.escape(str(x), quote=True)`，同时覆盖 `&` 和 `"` 字符。
- **`_auto_load_builtin_providers` 静默吞异常**：裸 `except: pass` 替换为 `os_log.warn(...)` 记录。

#### 插件 CLI 参数处理
- `CLI/parsers/plugin.py` 中三处 `_actions[-1].completer = ...` 替换为按 option_strings 命名查找，消除对列表尾部索引的脆弱依赖。

#### 插件注册表
- `_deep_merge_missing` 新增递归深度限制（`_depth=0`，上限 10），防止恶意插件配置导致栈溢出。
- `get_plugin_config` 移除重复的 `dict.get()` 调用。

#### TUI 插件面板
- `on_mount` 与 `query_one` 调用加入 `try/except`，防止 widget 生命周期异常向上传播。

---

### 仓库清理

- **`libraries/`** 迁移进 `src/opensynaptic/libraries/`，数据文件现在是可安装包的一部分。
- **`data/id_allocation.json`**、**`data/secure_sessions.json`**、**`data/env_guard/`** 加入 `.gitignore`——这些是运行时状态文件，不应提交。
- **Jekyll GitHub Pages 文件**（`_config.yml`、`index.html`、`_layouts/`）已删除——文档统一由 Docusaurus 站（`opensynaptic.github.io`）提供。
- 根目录从 ~12 个可见条目精简为 9 个清晰分类的条目。

---

### 升级指南

无破坏性 API 变更，升级命令：

```bash
pip install --upgrade opensynaptic==1.3.0
```

从源码安装迁移时：

1. 升级后运行一次 `os-node wizard`，确保 `~/.config/opensynaptic/Config.json` 以当前默认值重新生成。
2. 删除旧 `Config.json` 旁边的 `cache/` 目录——会自动重建。

---

## 兼容性

| Python | 状态 |
|--------|------|
| 3.11   | ✅ 支持 |
| 3.12   | ✅ 支持 |
| 3.13   | ✅ 支持 |

| 平台    | 架构         | 状态 |
|---------|------------|------|
| Linux   | x86_64     | ✅ |
| Linux   | aarch64    | ✅ |
| Windows | x86_64     | ✅ |
| macOS   | x86_64     | ✅ |
| macOS   | arm64 (M系列) | ✅ |

---

## 测试覆盖

v1.3.0 随版本附带全层级穷举测试套件，完整验证结果如下。

| 脚本 / 套件 | 测试项 | 结果 |
|---|---|---|
| `pytest tests/`（单元 + 集成） | 9 | ✅ 全部通过 |
| `scripts/integration_test.py` | 9 | ✅ 9/9 通过 |
| `scripts/exhaustive_business_logic.py`（A–F） | 985 | ✅ 983 通过，2 SKIP |
| `scripts/exhaustive_plugin_test.py`（A–E） | 205 | ✅ 205/205 通过 |
| `scripts/exhaustive_security_infra_test.py`（A–D） | 43 | ✅ 43/43 通过 |
| `scripts/exhaustive_orthogonal_test.py`（EP + XC） | 24 | ✅ 24/24 通过 |
| **合计** | **1275** | **✅ 1273 通过，2 SKIP，0 失败** |

2 个 SKIP 为预期行为：`mol=6.022e+23` 与 `AU=1e+06` 超出 Base62 int64 编码上限（`≈9.22×10¹⁴`），属已知设计限制，非缺陷。

完整测试报告详见 [TEST_REPORT_v1.3.0.md](TEST_REPORT_v1.3.0.md)（英文版）。
