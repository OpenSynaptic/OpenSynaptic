# Config.json Schema Reference

`Config.json` lives at the project root and is the **single source of truth** for all runtime behaviour.  
`OSContext` auto-detects it by walking up from `__file__` until the file is found.

---

## Top-level Keys

| Key | Type | Default | Description |
|---|---|---|---|
| `VERSION` | `string` | `"1.0.0"` | Protocol version string |
| `assigned_id` | `uint32` | `4294967295` | Device ID. `4294967295` (MAX_UINT32) is the sentinel for *unassigned*. Never use it as a real ID. |
| `device_id` | `string` | `"UNKNOWN"` | Human-readable node identifier used in sensor payloads |

---

## `OpenSynaptic_Setting`

High-level feature toggles.

```json
"OpenSynaptic_Setting": {
    "Server_Core": true,
    "Node_Core":   true,
    "Client_Core": true
}
```

| Key | Type | Default | Effect |
|---|---|---|---|
| `Server_Core` | bool | `true` | Enable server-side ID allocation and packet reception |
| `Node_Core` | bool | `true` | Enable node-mode (data generation + transmission) |
| `Client_Core` | bool | `true` | Enable client handshake / ID request |
| `default_medium` | string | `"UDP"` | Fallback transport medium used by `dispatch()` when no medium is specified |

---

## `Server_Core`

Configuration for the built-in UDP server.

```json
"Server_Core": {
    "port":     8080,
    "host":     "0.0.0.0",
    "Start_ID": 1,
    "End_ID":   4294967294
}
```

| Key | Type | Default | Description |
|---|---|---|---|
| `port` | int | `8080` | UDP listen port |
| `host` | string | `"0.0.0.0"` | Bind address |
| `Start_ID` | int | `1` | First ID in the allocatable pool |
| `End_ID` | int | `4294967294` | Last ID in the allocatable pool |

---

## `Client_Core`

Server endpoint for the client handshake.

```json
"Client_Core": {
    "server_host": "localhost",
    "server_port": 8080
}
```

---

## `Node_Core`

Node identity and sub-pool configuration.

```json
"Node_Core": {
    "node_id":     "",
    "template_id": "",
    "pool":        0,
    "Start_ID":    0,
    "End_ID":      0
}
```

---

## `RESOURCES`

All resource paths, transporter registries, and driver configurations.

```json
"RESOURCES": {
    "root":     "OS_library/opensynaptic_core/",
    "registry": "data/device_registry/",
    "symbols":  "data/symbols.json",

    "transporters_status":   { "<name>": true|false },
    "transport_status":      { "<name>": true|false },
    "physical_status":       { "<name>": true|false },
    "application_status":    { "<name>": true|false },

    "transport_config":      { "<name>": { ... } },
    "physical_config":       { "<name>": { ... } },
    "application_config":    { "<name>": { ... } }
}
```

### Sub-keys

| Key | Type | Description |
|---|---|---|
| `root` | string (path) | Library root directory (relative to project root) |
| `registry` | string (path) | Device registry base directory |
| `symbols` | string (path) | Compiled OS symbol table (`data/symbols.json`) |
| `prefixes` | string (path) | Prefix definition file (alternative to `symbols`) |
| `transporters_status` | map | **Master enable map** for all transporters — `TransporterManager` reads this. Keys are lowercase driver names; values are `true`/`false`. New drivers are auto-registered here as `false`. |
| `transport_status` | map | Transport-layer driver enable map (UDP, TCP, QUIC, lwIP, uIP) |
| `physical_status` | map | Physical-layer driver enable map (UART, RS-485, CAN, LoRa) |
| `application_status` | map | Application-layer driver enable map (MQTT) |
| `transport_config` | map-of-dicts | Per-driver config dicts for transport layer |
| `physical_config` | map-of-dicts | Per-driver config dicts for physical layer |
| `application_config` | map-of-dicts | Per-driver config dicts for application layer |

### `physical_config` examples

```json
"physical_config": {
    "uart":  { "port": "UART0", "baudrate": 115200 },
    "rs485": { "port": "COM1",  "baudrate": 9600 },
    "can":   { "can_id": 291 },
    "lora":  { "baudrate": 9600, "timeout": 2 }
}
```

### `transport_config` examples

```json
"transport_config": {
    "udp":  {},
    "tcp":  {},
    "quic": { "port": 4433, "timeout": 2.0, "insecure": true }
}
```

### `application_config` examples

```json
"application_config": {
    "mqtt": {
        "host":      "broker.hivemq.com",
        "port":      1883,
        "topic":     "os/sensors/raw",
        "client_id": "OpenSynapticNode"
    }
}
```

---

## `engine_settings`

Pipeline behaviour and precision controls.

```json
"engine_settings": {
    "global_secret_key":       "2B",
    "precision":               4,
    "lock_threshold":          3,
    "active_standardization":  true,
    "active_compression":      true,
    "active_collapse":         true,
    "sharding_level":          3,
    "skip_on_error":           true,
    "allow_nonlinear_prefix":  false,
    "time_precision":          4,
    "epoch_base":              0,
    "use_ms":                  true
}
```

| Key | Type | Default | Effect |
|---|---|---|---|
| `global_secret_key` | string | `"2B"` | Shared secret used for packet signing |
| `precision` | int | `4` | Number of Base62 decimal places for sensor values |
| `lock_threshold` | int | `3` | Number of successful sends before switching from FULL to DIFF strategy |
| `active_standardization` | bool | `true` | Enable the UCUM normalisation stage |
| `active_compression` | bool | `true` | Enable the Base62 compression stage |
| `active_collapse` | bool | `true` | Enable binary packet collapsing (template diff) |
| `sharding_level` | int | `3` | Registry shard depth |
| `skip_on_error` | bool | `true` | Continue pipeline on non-fatal errors instead of raising |
| `allow_nonlinear_prefix` | bool | `false` | Allow non-SI prefix chains during normalisation |
| `time_precision` | int | `4` | Decimal places for timestamp compression |
| `epoch_base` | int | `0` | Epoch offset (seconds) subtracted from UNIX timestamps before compression |
| `use_ms` | bool | `true` | Store timestamps in milliseconds |

---

## `security_settings`

Packet validation and session security.

```json
"security_settings": {
    "time_sync_threshold":           1000000,
    "drop_on_crc16_failure":         true,
    "secure_session_expire_seconds": 86400
}
```

| Key | Type | Default | Effect |
|---|---|---|---|
| `time_sync_threshold` | int | `1000000` | Minimum acceptable UNIX timestamp; packets with older timestamps are treated as unsynced |
| `drop_on_crc16_failure` | bool | `true` | Drop packets whose CRC-16 does not match |
| `secure_session_expire_seconds` | int | `86400` | Session key TTL in seconds (24 h) |

---

## `payload_switches`

Fine-grained control over which fields are included in each encoded packet.

```json
"payload_switches": {
    "DeviceId":           true,
    "DeviceStatus":       true,
    "Timestamp":          true,
    "SubTemplateId":      true,
    "SensorId":           true,
    "SensorStatus":       true,
    "PhysicalAttribute":  false,
    "NormalizedValue":    true,
    "GeohashId":          false,
    "SupplementaryMessage": true,
    "ResourceUrl":        false
}
```

Setting a field to `false` omits it from every packet, reducing bandwidth at the cost of that data field.

---

## `storage`

Logging, SQL backend, and backup configuration.

```json
"storage": {
    "directory":         "os_log",
    "registry_sharding": true,
    "sql": {
        "enabled": false,
        "dialect": "sqlite",
        "driver":  { "path": "data/opensynaptic.db" }
    },
    "standard_backup": {
        "enable":   true,
        "filename": "os_log/physics_fact_backup.jsonl"
    },
    "compressed_backup": {
        "enable":   true,
        "filename": "os_log/os_protocol_backup.os"
    }
}
```

| Key | Type | Default | Effect |
|---|---|---|---|
| `directory` | string | `"os_log"` | Log output directory |
| `registry_sharding` | bool | `true` | Split device registry across subdirectories (`id[0:2]/id[2:4]/`) |
| `sql.enabled` | bool | `false` | Enable SQL export via `DatabaseManager` |
| `sql.dialect` | string | `"sqlite"` | `"sqlite"`, `"mysql"`, or `"postgresql"` |
| `sql.driver.path` | string | — | SQLite file path |
| `standard_backup.enable` | bool | `true` | Append raw fact dicts to a JSONL file |
| `compressed_backup.enable` | bool | `true` | Append raw binary packets to an `.os` file |

---

## `automation`

Code generation helpers.

```json
"automation": {
    "cpp_header": "os_symbols.hpp"
}
```

| Key | Type | Description |
|---|---|---|
| `cpp_header` | string | Output path for the C++ symbol header generated by the library harvester |

---

## Editing Config at Runtime

Use the CLI commands to safely modify Config.json without manual file editing:

```powershell
# View a section
python -u src/main.py config-show --config Config.json --section engine_settings

# Read a specific key
python -u src/main.py config-get --config Config.json --key engine_settings.precision

# Write a typed value
python -u src/main.py config-set --config Config.json --key engine_settings.precision --value 6 --type int

# Enable a transporter
python -u src/main.py transporter-toggle --config Config.json --name udp --enable
```

