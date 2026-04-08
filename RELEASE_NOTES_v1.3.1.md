# OpenSynaptic v1.3.1 Release Notes

> **English** | [中文](#opensynaptic-v131-更新说明)

---

## What's New in v1.3.1

### New Features

#### Data Query REST API

OpenSynaptic v1.3.1 introduces a complete read-only data query API, exposing the SQL storage layer (`os_packets` / `os_sensors`) via HTTP for the first time.

All four endpoints require the standard `X-Admin-Token` header when `auth_enabled = true`, and return `503` if the database backend is not configured.

| Endpoint | Description |
|----------|-------------|
| `GET /api/data/devices` | List all known devices with `last_seen` timestamp and `packet_count`. Supports `limit` / `offset` pagination. |
| `GET /api/data/packets` | Paginated packet list. Filter by `device_id`, `status`, `since` (Unix epoch), `until`, `limit`, `offset`. Results ordered by `timestamp_raw` descending. |
| `GET /api/data/packets/{uuid}` | Retrieve a single packet by UUID along with its full sensor array. Returns `404` if not found. |
| `GET /api/data/sensors` | Paginated sensor readings joined with packet metadata. Filter by `device_id`, `sensor_id`, `since`, `until`, `limit`, `offset`. |

#### DatabaseManager Query Methods

Four new read-only methods added to `DatabaseManager`:

- `query_devices(limit, offset)` — distinct device summary
- `query_packets(device_id, since, until, status, limit, offset)` — packet listing
- `query_packet(packet_uuid)` — single packet + sensors
- `query_sensors(device_id, sensor_id, since, until, limit, offset)` — sensor listing

All queries use parameterized SQL and are compatible with all three supported dialects (SQLite, MySQL, PostgreSQL).

---

### Bug Fixes

- `pyproject.toml` now sets `pythonpath = ["src"]` for pytest, making the test suite runnable directly via `python -m pytest` without a prior `pip install -e .`.

---

### Tests

- Added `tests/unit/test_data_query_api.py` with **20 new test cases** covering:
  - All four `DatabaseManager` query methods (filter, pagination, time range, not-found)
  - All four HTTP endpoints (auth bypass stub, 503 on missing DB, 404 on missing UUID)

---

### Upgrade Notes

- **No breaking changes.** v1.3.1 is fully backward-compatible with v1.3.0.
- SQL storage must be enabled in `Config.json` for data query endpoints to respond with data:

```json
{
  "storage": {
    "sql": {
      "enabled": true,
      "dialect": "sqlite",
      "driver": { "path": "data/opensynaptic.db" }
    }
  }
}
```

---

---

# OpenSynaptic v1.3.1 更新说明

> [English](#opensynaptic-v131-release-notes) | **中文**

---

## v1.3.1 新增内容

### 新功能

#### 数据查询 REST API

OpenSynaptic v1.3.1 首次将 SQL 存储层（`os_packets` / `os_sensors`）通过 HTTP 对外开放，提供完整的只读数据查询接口。

当 `auth_enabled = true` 时，所有端点均需在请求头中携带 `X-Admin-Token`。若数据库后端未配置，则返回 `503`。

| 端点 | 说明 |
|------|------|
| `GET /api/data/devices` | 列出所有已知设备，包含 `last_seen` 时间戳与 `packet_count`，支持 `limit` / `offset` 分页。 |
| `GET /api/data/packets` | 分页列出数据包，支持按 `device_id`、`status`、`since`（Unix 时间戳）、`until`、`limit`、`offset` 过滤，结果按 `timestamp_raw` 降序排列。 |
| `GET /api/data/packets/{uuid}` | 按 UUID 查询单条数据包及其完整传感器数组，未找到时返回 `404`。 |
| `GET /api/data/sensors` | 分页列出传感器读数（与数据包元数据联表），支持按 `device_id`、`sensor_id`、`since`、`until`、`limit`、`offset` 过滤。 |

#### DatabaseManager 查询方法

`DatabaseManager` 新增四个只读方法：

- `query_devices(limit, offset)` — 获取设备摘要
- `query_packets(device_id, since, until, status, limit, offset)` — 列出数据包
- `query_packet(packet_uuid)` — 获取单条数据包及传感器
- `query_sensors(device_id, sensor_id, since, until, limit, offset)` — 列出传感器读数

所有查询均使用参数化 SQL，兼容三种支持的数据库（SQLite、MySQL、PostgreSQL）。

---

### 缺陷修复

- `pyproject.toml` 新增 `pythonpath = ["src"]` pytest 配置项，无需 `pip install -e .` 即可直接通过 `python -m pytest` 运行测试套件。

---

### 测试

- 新增 `tests/unit/test_data_query_api.py`，包含 **20 个测试用例**，覆盖：
  - 全部四个 `DatabaseManager` 查询方法（过滤、分页、时间范围、未命中）
  - 全部四个 HTTP 端点（鉴权存根、数据库未配置返回 503、UUID 未命中返回 404）

---

### 升级说明

- **无破坏性变更。** v1.3.1 与 v1.3.0 完全向下兼容。
- 数据查询端点需在 `Config.json` 中启用 SQL 存储才会返回数据：

```json
{
  "storage": {
    "sql": {
      "enabled": true,
      "dialect": "sqlite",
      "driver": { "path": "data/opensynaptic.db" }
    }
  }
}
```

---

*Released: 2026-04-08*
