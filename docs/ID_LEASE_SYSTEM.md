# ID Lease & Adaptive Rate Policy System

## Overview

The OpenSynaptic ID allocation system implements a sophisticated lease-based ID reuse mechanism with adaptive rate-based policy shortening. This document describes the complete lifecycle and configuration of ID management.

## System Architecture

### Core Components

1. **IDAllocator** (`plugins/id_allocator.py`)
   - Manages uint32 ID pool allocation and reuse
   - Handles lease expiration and device state tracking
   - Implements adaptive rate-based policy
   - Persists all state to `data/id_allocation.json`

2. **Lease Configuration** (Config.json: `security_settings.id_lease`)
   - All policy parameters are centrally configured
   - Read at startup and re-evaluated on each allocation
   - Can be updated without code changes

3. **Metrics Sink** (optional callback)
   - Emits real-time metrics on device rate and lease effectiveness
   - Can connect to monitoring/alerting systems
   - Includes new device rate, effective lease duration, and ultra-rate flags

## ID Lifecycle

### States

Each allocated ID has the following possible states:

- **Active**: Device is online, ID in use, lease resets on touch
- **Offline**: Device is offline, lease countdown active, ID may be reused when lease expires
- **Released**: ID returned to pool after lease expiration, available for new devices

### Allocation Flow

```
New Device → Lookup Device Key (MAC/Serial/UUID)
             ↓
    Found in _device_index? → YES → Reactivate & Reset Lease
                            → NO   → Allocate from _released pool or increment counter
                                   → Record device_key mapping
                                   → Update rate metrics
```

### Device Reconnection

When a device with the same stable key reconnects:

1. System detects returning device by stable key (MAC, serial, UUID, etc.)
2. ID is reactivated immediately if not yet released
3. Lease is reset to base duration (default: 30 days)
4. `state` changed from "offline" to "active"
5. `last_seen` and `offline_since` counters updated

## Lease Policy Parameters

All parameters are in `Config.json` under `security_settings.id_lease`:

### Base Configuration

| Parameter | Default | Type | Description |
|-----------|---------|------|-------------|
| `offline_hold_days` | 30 | int | Human-readable hold period (converted to `base_lease_seconds`) |
| `base_lease_seconds` | 2592000 | int | Base lease for newly assigned or re-touched IDs (30 days) |
| `min_lease_seconds` | 0 | int | Floor for adaptive shortening (0 = adaptive can reduce to zero) |

### Rate-Based Adaptive Shortening

| Parameter | Default | Type | Description |
|-----------|---------|------|-------------|
| `rate_window_seconds` | 3600 | int | Observation window for new device rate (1 hour) |
| `high_rate_threshold_per_hour` | 60 | float | Threshold to trigger lease shortening (devices/hour) |
| `ultra_rate_threshold_per_hour` | 180 | float | Threshold to trigger force-zero lease (devices/hour) |
| `ultra_rate_sustain_seconds` | 600 | int | Duration ultra-rate must sustain before force-zero applies (10 minutes) |
| `high_rate_min_factor` | 0.2 | float | Multiplier for lease during high-rate (0.2 = 20% of base) |
| `adaptive_enabled` | true | bool | Enable/disable adaptive lease shortening |
| `ultra_force_release` | true | bool | Immediately expire offline IDs when ultra-rate active |

### Metrics & Monitoring

| Parameter | Default | Type | Description |
|-----------|---------|------|-------------|
| `metrics_emit_interval_seconds` | 5 | int | How often to emit metrics to sink |

## Adaptive Lease Algorithm

The effective lease duration is calculated as follows:

```python
def calculate_effective_lease(rate_per_hour, base_lease):
    if not adaptive_enabled:
        return base_lease
    
    if rate_per_hour >= ultra_rate_threshold:
        if ultra_rate_sustained_for >= ultra_rate_sustain_seconds:
            return 0  # Force-zero: immediate reclaim
    
    if rate_per_hour <= high_rate_threshold:
        return base_lease  # Normal rate: full lease
    
    # High rate detected: apply factor
    factor = high_rate_threshold / rate_per_hour
    factor = max(high_rate_min_factor, min(1.0, factor))
    return max(min_lease_seconds, int(base_lease * factor))
```

### Example Scenarios

**Scenario 1: Normal Device Rate (0-60/hour)**
- Rate: 30 devices/hour
- Result: Full 30-day lease
- Behavior: Devices offline for up to 30 days can reclaim their ID

**Scenario 2: High Device Rate (60-180/hour)**
- Rate: 120 devices/hour
- Calculation: factor = 60 / 120 = 0.5
- Result: 15-day lease (50% of base)
- Behavior: Faster ID recycling to prevent pool exhaustion

**Scenario 3: Ultra-High Rate (>180/hour for 10+ minutes)**
- Rate: 240 devices/hour for 15 minutes
- Result: 0-second lease (immediate reclaim)
- Behavior: All offline IDs force-expired immediately, rapid recycling

## Metrics & Monitoring

### Emitted Metrics

The `metrics_sink` callable receives the following metrics every 5 seconds:

```python
{
    'base_lease_seconds': 2592000,  # Base configuration
    'effective_lease_seconds': 1296000,  # After adaptive shortening
    'new_device_rate_per_hour': 120.5,  # Rolling rate of new allocations
    'ultra_rate_active': True,  # Ultra-rate threshold sustained
    'force_zero_lease_active': False,  # Force-zero lease currently applied
    'last_reclaim_count': 5,  # IDs reclaimed in last interval
    'last_reclaim_at': 1234567890,  # Timestamp of last reclaim
    'total_reclaimed': 847,  # Cumulative reclaimed count
    'allocated_count': 3421,  # Currently allocated IDs
    'released_count': 2108,  # IDs in released pool
    'updated_at': 1234567895,  # Metrics timestamp
}
```

### Integration Example

```python
def my_metrics_sink(metrics):
    # Send to monitoring system
    prometheus_gauge('id_new_device_rate', metrics['new_device_rate_per_hour'])
    prometheus_gauge('id_effective_lease_seconds', metrics['effective_lease_seconds'])
    prometheus_gauge('id_allocated_count', metrics['allocated_count'])
    if metrics['ultra_rate_active']:
        alert_on_ultra_rate(metrics)

allocator = IDAllocator(
    lease_policy=config['security_settings']['id_lease'],
    metrics_sink=my_metrics_sink,
)
```

## Persistence & Recovery

### Storage Format

State is persisted to `data/id_allocation.json`:

```json
{
  "allocated": {
    "1": {
      "meta": {"device_id": "DEV001", "mac": "AA:BB:CC:DD:EE:01"},
      "ts": 1234567890,
      "last_seen": 1234567890,
      "lease_expires_at": 1237159890,
      "device_key": "mac:AA:BB:CC:DD:EE:01",
      "state": "active",
      "offline_since": 0
    }
  },
  "released": [101, 202, 303],
  "next_candidate": 5,
  "lease_metrics": {
    "base_lease_seconds": 2592000,
    "effective_lease_seconds": 2592000,
    "new_device_rate_per_hour": 0.0,
    "ultra_rate_active": false,
    "force_zero_lease_active": false,
    "total_reclaimed": 0,
    "updated_at": 1234567895
  }
}
```

### Recovery on Startup

1. All allocated IDs are loaded with their lease expiration times
2. Expired IDs are immediately reclaimed and moved to released pool
3. Lease policy is applied from current Config.json
4. New device rate is recalculated from recent allocation events
5. Device index is rebuilt for fast stable-key lookups

## API Reference

### Primary Methods

```python
# Allocate ID for a new/returning device
id_val = allocator.allocate_id(meta={'device_id': 'DEV001'})

# Allocate multiple IDs
ids = allocator.allocate_pool(count=10, meta={...})

# Release ID (device going offline)
allocator.release_id(id_val, immediate=False)
# immediate=True: expunge immediately (overrides lease)
# immediate=False: respect adaptive lease policy

# Update device metadata and reset lease
allocator.touch(aid=id_val, meta={'device_id': 'DEV001', 'battery': 75})

# Check if ID is currently allocated
is_active = allocator.is_allocated(id_val)

# Get device metadata
meta = allocator.get_meta(id_val)

# Force reclaim expired IDs
reclaimed_count = allocator.reclaim_expired()

# Get comprehensive statistics
stats = allocator.stats()
```

### Configuration Updates

To change lease policy at runtime:

1. Update `Config.json` `security_settings.id_lease` values
2. Recreate `IDAllocator` instance with new config
3. On next allocation, new lease policy is applied

**Note:** Policy changes are immediate for new allocations but don't retroactively modify existing lease expirations. This allows gradual rollout of policy changes.

## Best Practices

### 1. Device Key Stability

Ensure stable device keys are provided at allocation:
```python
# GOOD: Stable, device-specific
meta = {
    'device_id': 'sensor_12345',
    'mac': 'AA:BB:CC:DD:EE:FF',
    'serial': 'SER_2024_001'
}

# BAD: Changes per connection
meta = {
    'ip_address': '192.168.1.100',  # Often changes
    'connection_time': 1234567890,  # Always unique
}
```

### 2. Lease Policy Tuning

Start conservative, adjust based on observed device patterns:
- **Initial**: 30-day default with 60/hr high-rate threshold
- **Monitor**: Observe new device rate distribution
- **Tune**: If >80% devices come back within 24h, reduce lease to 3-5 days
- **Threshold**: If new device rate frequently exceeds 60/hr, lower threshold or shorten base lease

### 3. Metrics Integration

Always connect a metrics sink for operational visibility:
```python
allocator = IDAllocator(
    lease_policy=config['security_settings']['id_lease'],
    metrics_sink=central_monitoring.emit,
)
```

### 4. Pool Sizing

The ID range default (1 to 4294967294) is enormous. If using smaller range:
- Ensure `high_rate_threshold` and `ultra_rate_threshold` are scaled appropriately
- Consider external ID reuse for even smaller pools
- Monitor `released_count` to ensure pool doesn't deplete

## Troubleshooting

### Issue: IDs Running Out Quickly

**Symptoms**: Frequent "ID pool exhausted" errors

**Root Causes**:
1. Lease too long for device return rate
2. High-rate threshold too high, adaptive policy not kicking in
3. Devices not being properly released when offline

**Solutions**:
- Lower `high_rate_threshold_per_hour` to trigger adaptive shortening sooner
- Reduce `base_lease_seconds` if most devices return within days, not months
- Verify devices call `release_id()` when going offline

### Issue: IDs Being Reused Too Quickly

**Symptoms**: Recently-offline devices can't reconnect (ID already reused)

**Root Causes**:
1. Lease too short
2. Ultra-rate threshold triggered unnecessarily
3. Device keys not stable

**Solutions**:
- Increase `base_lease_seconds`
- Raise `ultra_rate_threshold_per_hour` if false triggers
- Ensure stable device key (MAC/Serial, not IP/timestamp)
- Reduce `ultra_rate_sustain_seconds` if high device rate is legitimate

### Issue: Metrics Not Being Emitted

**Symptoms**: `metrics_sink` callable never invoked

**Root Causes**:
1. `metrics_sink` not provided to `IDAllocator.__init__`
2. `metrics_emit_interval_seconds` too large
3. No allocations happening (metrics only emitted on changes)

**Solutions**:
- Verify `metrics_sink=my_function` passed during init
- Reduce `metrics_emit_interval_seconds` for more frequent updates
- Allocations or reclaims trigger emissions

## Integration with OpenSynaptic Node

The `IDAllocator` is integrated into the node startup sequence:

```python
from opensynaptic import OpenSynaptic
from plugins.id_allocator import IDAllocator

node = OpenSynaptic()
allocator = IDAllocator(
    base_dir=node.config_path,
    lease_policy=node.config.get('security_settings', {}).get('id_lease', {}),
    metrics_sink=node.metrics.emit,  # Optional
)

# Request ID from server if not assigned
if node.config.get('assigned_id') == 4294967295:
    node.ensure_id('192.168.1.100', 8080, device_meta={...})
```

The node automatically uses the lease policy defined in `Config.json`.

