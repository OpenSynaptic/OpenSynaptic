# Transporter Plugin Guide

How to write, register, and enable a new transporter for OpenSynaptic.

---

## Overview

OpenSynaptic's transport layer is split into three tiers:

| Tier | Config key | Driver location | Examples |
|---|---|---|---|
| **Application** | `RESOURCES.application_status` | `services/transporters/drivers/` | MQTT |
| **Transport** | `RESOURCES.transport_status` | `core/transport_layer/` | UDP, TCP, QUIC, lwIP, uIP |
| **Physical** | `RESOURCES.physical_status` | `core/physical_layer/` | UART, RS-485, CAN, LoRa |

Discovery behavior is layer-specific:

- Application layer: constrained by `TransporterService.APP_LAYER_DRIVERS`.
- Transport layer: constrained by `TransportLayerManager._CANDIDATES`.
- Physical layer: constrained by `PhysicalLayerManager._CANDIDATES`.

`ServiceManager` handles application-layer drivers; transport and physical layers are managed by their dedicated layer managers.

---

## Required Interface

Every transporter module must expose:

```python
def send(payload: bytes, config: dict) -> bool:
    """
    Send *payload* using whatever medium this driver implements.

    Parameters
    ----------
    payload : bytes   – pre-encoded binary packet (from OSVisualFusionEngine)
    config  : dict    – merged node Config.json (full dict)

    Returns
    -------
    bool – True on success, False on any failure
    """
    ...
```

### Optional interface

```python
def listen(config: dict, callback) -> None:
    """
    Start a blocking (or background-thread) receive loop.

    Parameters
    ----------
    config   : dict       – full node config
    callback : callable   – called with (raw_bytes: bytes, addr: tuple) for every inbound packet
    """
    ...
```

---

## Step-by-step: Adding a Transport-layer Driver

### 1. Create the driver file

For a **transport-layer** driver (e.g. WebSocket), create:

```
src/opensynaptic/core/transport_layer/websocket.py
```

Implement at minimum:

```python
# src/opensynaptic/core/transport_layer/websocket.py
import websocket  # pip install websocket-client

def send(payload: bytes, config: dict) -> bool:
    try:
        ws_cfg = config.get('RESOURCES', {}).get('transport_config', {}).get('websocket', {})
        url = ws_cfg.get('url', 'ws://localhost:8765')
        ws = websocket.create_connection(url, timeout=ws_cfg.get('timeout', 3.0))
        ws.send_binary(payload)
        ws.close()
        return True
    except Exception as exc:
        return False
```

### 2. Register in manager candidates and Config.json

Add your driver key/module to the transport layer candidate tuple (`TransportLayerManager._CANDIDATES`) and then ensure `Config.json` has a status entry:

```json
"RESOURCES": {
    "transport_status": {
        "websocket": false
    }
}
```

Also add matching settings under `RESOURCES.transport_config` when needed.

### 3. Enable the driver

Via CLI:

```powershell
python -u src/main.py transporter-toggle --config Config.json --name websocket --enable
```

Or via `config-set`:

```powershell
python -u src/main.py config-set --config Config.json --key RESOURCES.transport_status.websocket --value true --type bool
```

Or directly in `Config.json`:

```json
"transport_status": {
    "websocket": true
}
```

### 4. Add optional config block

Place driver-specific settings under the matching config key:

```json
"transport_config": {
    "websocket": {
        "url": "ws://192.168.1.100:8765",
        "timeout": 3.0
    }
}
```

Access them inside `send()` via:

```python
ws_cfg = config.get('RESOURCES', {}).get('transport_config', {}).get('websocket', {})
```

---

## Step-by-step: Adding an Application-layer Driver

Application-layer drivers live in `services/transporters/drivers/` and must be listed in `ServiceManager.APP_LAYER_DRIVERS` inside `services/transporters/main.py`.

### 1. Create the driver file

```
src/opensynaptic/services/transporters/drivers/myapp.py
```

Minimal implementation:

```python
def send(payload: bytes, config: dict) -> bool:
    app_opts = config.get('application_options', {})
    # ... send logic ...
    return True
```

### 2. Register in APP_LAYER_DRIVERS

In `services/transporters/main.py`:

```python
class TransporterService:
    APP_LAYER_DRIVERS = {'mqtt', 'myapp'}   # ← add here
```

If the key is not listed here, the app-layer driver will not be loaded even if the file exists.

### 3. Enable in Config.json

```json
"application_status": {
    "myapp": true
},
"application_config": {
    "myapp": {
        "endpoint": "https://..."
    }
}
```

---

## Step-by-step: Adding a Physical-layer Driver

Physical drivers live in `core/physical_layer/` and follow the same `send()` / `listen()` contract.  
Register new protocols in `PhysicalLayerManager._CANDIDATES`, then enable them under `RESOURCES.physical_status`.

Example: add `bluetooth.py`:

```
src/opensynaptic/core/physical_layer/bluetooth.py
```

```json
"physical_status": {
    "bluetooth": true
},
"physical_config": {
    "bluetooth": {
        "address": "AA:BB:CC:DD:EE:FF",
        "port": 1
    }
}
```

---

## Naming Conventions

- File name (lowercase, no hyphens): `udp.py`, `lora.py`, `my_proto.py`
- Status key in Config (same lowercase): `"udp"`, `"lora"`, `"my_proto"`
- `TransporterManager` normalises medium strings to lowercase before lookup

---

## Testing Your Driver

After enabling, verify via CLI:

```powershell
python -u src/main.py transport-status --config Config.json
python -u src/main.py transmit --config Config.json --sensor-id V1 --value 1.0 --unit Pa --medium myapp
```

To test send / receive in isolation, use `inject` + your own listener:

```powershell
python -u src/main.py inject --config Config.json --module full --sensor-id V1 --value 3.14 --unit Pa
```

