# db_engine

`db_engine` provides SQL export for OpenSynaptic facts using a single manager and pluggable drivers.

## Files
- `main.py`: `DatabaseManager` facade (`connect`, `export_fact`, `export_many`, `close`)
- `drivers/`: SQL adapters for `SQLite`, `MySQL`, `PostgreSQL`
- `manager.py` and `drivers.py`: backward-compatible re-export shims

## Service mount
- Service name: `db_engine`
- Mount point: `opensynaptic.services.service_manager.ServiceManager`
- Runtime/config index source: `storage.sql`

## Safety rule (SQL injection)
- No value string concatenation is used.
- All inserts use parameter binding (`?` / `%s`) with DB driver APIs.
- Schema SQL is static and fixed to `os_packets` and `os_sensors`.

## Minimal config

```json
{
  "storage": {
    "sql": {
      "enabled": true,
      "dialect": "sqlite",
      "driver": {
        "path": "data/opensynaptic.db"
      }
    }
  }
}
```

For MySQL/PostgreSQL, place connection settings under `storage.sql.driver`:
- MySQL: `host`, `port`, `user`, `password`, `database`
- PostgreSQL: `host`, `port`, `user`, `password`, `database`

