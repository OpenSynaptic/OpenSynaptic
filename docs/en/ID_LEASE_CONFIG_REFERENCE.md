# ID Lease Configuration Quick Reference

## Config.json Settings

Located under `security_settings.id_lease`:

```json
{
  "security_settings": {
    "id_lease": {
      "persist_file": "data/id_allocation.json",
      
      "offline_hold_days": 30,
      "base_lease_seconds": 2592000,
      "min_lease_seconds": 0,
      
      "rate_window_seconds": 3600,
      "high_rate_threshold_per_hour": 60.0,
      "ultra_rate_threshold_per_hour": 180.0,
      "ultra_rate_sustain_seconds": 600,
      "high_rate_min_factor": 0.2,
      
      "adaptive_enabled": true,
      "ultra_force_release": true,
      "metrics_emit_interval_seconds": 5
    }
  }
}
```

## Common Configuration Scenarios

### Scenario A: IoT Network with Frequent Churn (Mobile Devices)

```json
{
  "offline_hold_days": 7,
  "base_lease_seconds": 604800,
  "high_rate_threshold_per_hour": 120.0,
  "ultra_rate_threshold_per_hour": 300.0,
  "high_rate_min_factor": 0.3,
  "adaptive_enabled": true
}
```

**Reasoning**: Short default lease (7 days), higher rate thresholds to allow burst device enrollment, aggressive adaptive shortening (30% factor).

### Scenario B: Industrial Monitoring (Low Churn, Long Lifecycle)

```json
{
  "offline_hold_days": 90,
  "base_lease_seconds": 7776000,
  "high_rate_threshold_per_hour": 10.0,
  "ultra_rate_threshold_per_hour": 30.0,
  "high_rate_min_factor": 0.5,
  "adaptive_enabled": true
}
```

**Reasoning**: Long default lease (90 days) for stable devices, low rate thresholds (production anomaly if exceeded), conservative shortening (50% factor).

### Scenario C: Development/Testing (Rapid Device Allocation)

```json
{
  "offline_hold_days": 1,
  "base_lease_seconds": 86400,
  "high_rate_threshold_per_hour": 1000.0,
  "ultra_rate_threshold_per_hour": 5000.0,
  "high_rate_min_factor": 0.1,
  "adaptive_enabled": false
}
```

**Reasoning**: Very short lease, extremely high thresholds, adaptive disabled for predictability.

## Performance Tuning

### If ID Pool Exhaustion Occurs

**Priority 1**: Lower `high_rate_threshold_per_hour`
```json
"high_rate_threshold_per_hour": 30.0  // From 60.0
```
This triggers adaptive shortening sooner, recycling IDs faster.

**Priority 2**: Reduce `base_lease_seconds`
```json
"base_lease_seconds": 604800  // 7 days, from 30
```
Assumes most devices return within a week.

**Priority 3**: Enable `ultra_force_release`
```json
"ultra_force_release": true,
"ultra_rate_threshold_per_hour": 100.0
```
Immediately expire offline IDs during high device allocation.

### If IDs Being Reused Prematurely

**Priority 1**: Increase `base_lease_seconds`
```json
"base_lease_seconds": 5184000  // 60 days
```

**Priority 2**: Raise `high_rate_threshold_per_hour`
```json
"high_rate_threshold_per_hour": 100.0  // From 60.0
```
Requires higher rate to trigger adaptive shortening.

**Priority 3**: Increase `high_rate_min_factor`
```json
"high_rate_min_factor": 0.5  // From 0.2, only shorten to 50%
```

## Debugging

### Check Current Lease Policy

```python
from plugins.id_allocator import IDAllocator
allocator = IDAllocator(base_dir='.')
stats = allocator.stats()
print(stats['lease_policy'])
```

### Monitor Metrics in Real-Time

```python
import json
from pathlib import Path

def watch_metrics():
    while True:
        data = json.loads(Path('data/id_allocation.json').read_text())
        metrics = data.get('lease_metrics', {})
        print(f"Rate: {metrics.get('new_device_rate_per_hour')}dev/hr | "
              f"Lease: {metrics.get('effective_lease_seconds')}s | "
              f"Ultra: {metrics.get('ultra_rate_active')}")
        time.sleep(1)
```

### Force Reclaim Expired IDs

```python
from plugins.id_allocator import IDAllocator
allocator = IDAllocator(base_dir='.')
reclaimed = allocator.reclaim_expired()
print(f"Reclaimed {reclaimed} IDs")
```

### Verify Device Key Stability

```python
def stable_key_for_device(device):
    # Use in order of preference
    if device.get('serial'):
        return f"serial:{device['serial']}"
    if device.get('mac'):
        return f"mac:{device['mac']}"
    if device.get('uuid'):
        return f"uuid:{device['uuid']}"
    if device.get('device_id'):
        return f"device_id:{device['device_id']}"
    return None  # Will use hash of full meta
```

## CLI Commands

### View Current Lease Policy

```bash
python -c "from plugins.id_allocator import IDAllocator; import json; a = IDAllocator(base_dir='.'); print(json.dumps(a.stats()['lease_policy'], indent=2))"
```

### Allocate Test ID

```bash
python -c "from plugins.id_allocator import IDAllocator; a = IDAllocator(base_dir='.'); print(f'Allocated: {a.allocate_id({\"test\": True})}')"
```

### Check Pool Status

```bash
python -c "from plugins.id_allocator import IDAllocator; import json; a = IDAllocator(base_dir='.'); s = a.stats(); print(f'Allocated: {s[\"total_allocated\"]}, Released: {s[\"total_released\"]}')"
```

## Metrics Interpretation

| Metric | Interpretation | Action |
|--------|-----------------|--------|
| `new_device_rate_per_hour` > `high_rate_threshold_per_hour` | System experiencing high device churn | Monitor adoption patterns; may be normal |
| `effective_lease_seconds` < `base_lease_seconds` | Adaptive shortening active | High device rate detected; ID recycling accelerated |
| `ultra_rate_active: true` | Ultra-high rate sustained | Manual tuning may be needed; check for enrollment surge |
| `force_zero_lease_active: true` | IDs being force-expired immediately | ID pool under pressure; consider scaling device infrastructure |
| `total_reclaimed` growing slowly | Normal operation | ✓ System is stable |
| `total_reclaimed` stalled | Possible memory leak or offline devices piling up | Check device offline patterns; may need different policy |

## Common Mistakes

### ❌ NOT Providing Stable Device Key

```python
# BAD: Every connection gets a new ID
allocator.allocate_id(meta={'timestamp': time.time()})

# GOOD: Reuses ID for returning device
allocator.allocate_id(meta={'device_id': 'sensor_123', 'mac': 'AA:BB:CC:DD:EE:FF'})
```

### ❌ Setting `min_lease_seconds` Too High

```python
# BAD: Adaptive shortening can't help
"min_lease_seconds": 604800  # 7 days minimum
"high_rate_threshold_per_hour": 60.0

# GOOD: Adaptive can reduce to zero if needed
"min_lease_seconds": 0  # Allow force-zero
```

### ❌ Forgetting to Call `release_id()` on Disconnect

```python
# BAD: Device offline but ID held indefinitely
if device_disconnects:
    pass  # Forgot to release!

# GOOD: Mark ID as offline, start lease countdown
if device_disconnects:
    allocator.release_id(device_id, immediate=False)
```

### ❌ Not Monitoring Metrics

```python
# BAD: No visibility into ID allocation health
allocator = IDAllocator(base_dir='.')

# GOOD: Real-time metrics for debugging
def metrics_sink(metrics):
    log_to_monitoring_system(metrics)

allocator = IDAllocator(base_dir='.', metrics_sink=metrics_sink)
```

## When to Adjust Config

1. **After Initial Deployment**
   - Run for 1-2 weeks in production
   - Monitor `new_device_rate_per_hour` and `effective_lease_seconds`
   - Adjust thresholds based on observed patterns

2. **During Scaling Events**
   - Expected enrollment surge? Increase `ultra_rate_threshold_per_hour`
   - Device lifecycle shortening? Reduce `base_lease_seconds`
   - Network migration? Temporarily disable `adaptive_enabled`

3. **In Response to Alerts**
   - Pool exhaustion: Lower `high_rate_threshold_per_hour`
   - Premature reuse: Increase `base_lease_seconds`
   - Unexpected ultra-rate: Review device enrollment patterns

## Support & Troubleshooting

See `docs/ID_LEASE_SYSTEM.md` for detailed architecture and troubleshooting guide.

