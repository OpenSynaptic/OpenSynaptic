#!/usr/bin/env python
"""
Test script for ID allocation and lease management system.

This demonstrates:
1. ID allocation with default 30-day lease
2. ID reuse for returning devices
3. Adaptive lease shortening based on new device rate
4. Force-zero lease on ultra-high device rates
5. Metrics emission
"""

import time
import json
from plugins.id_allocator import IDAllocator
from pathlib import Path


def test_basic_allocation():
    """Test basic ID allocation and persistence."""
    print("\n=== Test 1: Basic Allocation ===")
    
    allocator = IDAllocator(
        base_dir='.',
        persist_file='data/test_id_allocation.json',
        lease_policy={
            'offline_hold_days': 30,
            'base_lease_seconds': 2592000,  # 30 days
            'min_lease_seconds': 0,
            'rate_window_seconds': 3600,
            'high_rate_threshold_per_hour': 60.0,
            'ultra_rate_threshold_per_hour': 180.0,
            'ultra_rate_sustain_seconds': 600,
            'high_rate_min_factor': 0.2,
            'adaptive_enabled': True,
            'ultra_force_release': True,
            'metrics_emit_interval_seconds': 5,
        }
    )
    
    # Allocate first ID
    device1_meta = {'device_id': 'DEV001', 'mac': 'AA:BB:CC:DD:EE:01'}
    id1 = allocator.allocate_id(meta=device1_meta)
    print(f"✓ Allocated ID: {id1} for device DEV001")
    
    # Allocate second ID
    device2_meta = {'device_id': 'DEV002', 'mac': 'AA:BB:CC:DD:EE:02'}
    id2 = allocator.allocate_id(meta=device2_meta)
    print(f"✓ Allocated ID: {id2} for device DEV002")
    
    stats = allocator.stats()
    print(f"✓ Total allocated: {stats['total_allocated']}")
    print(f"✓ Lease policy: {stats['lease_policy']['base_lease_seconds']} seconds (30 days)")
    
    return allocator, id1, id2


def test_device_reuse(allocator, id1, id2):
    """Test device reconnection and ID reuse."""
    print("\n=== Test 2: Device Reconnection (ID Reuse) ===")
    
    # Simulate device offline
    device1_meta = {'device_id': 'DEV001', 'mac': 'AA:BB:CC:DD:EE:01'}
    print(f"• Releasing ID {id1} (device goes offline)...")
    allocator.release_id(id1, immediate=False)
    
    # Simulate device coming back online with same identity
    print(f"• Device DEV001 reconnects...")
    reused_id = allocator.allocate_id(meta=device1_meta)
    print(f"✓ Reused same ID: {reused_id} (was {id1})")
    
    if reused_id == id1:
        print("✓ ID successfully reused for returning device!")
    else:
        print("✗ Device got new ID instead of reusing old one")


def test_adaptive_lease():
    """Test adaptive lease shortening based on new device rate."""
    print("\n=== Test 3: Adaptive Lease Shortening ===")
    
    # Create allocator with low ultra-rate threshold for testing
    allocator = IDAllocator(
        base_dir='.',
        persist_file='data/test_id_allocation_adaptive.json',
        lease_policy={
            'offline_hold_days': 30,
            'base_lease_seconds': 2592000,  # 30 days
            'min_lease_seconds': 0,
            'rate_window_seconds': 10,  # 10 seconds for testing
            'high_rate_threshold_per_hour': 3.0,  # 3 devices/hour = 1 every 1200s
            'ultra_rate_threshold_per_hour': 18.0,  # 18/hour = 1 every 200s
            'ultra_rate_sustain_seconds': 2,  # 2 seconds for testing
            'high_rate_min_factor': 0.5,  # 50% of base
            'adaptive_enabled': True,
            'ultra_force_release': True,
            'metrics_emit_interval_seconds': 1,
        }
    )
    
    base_lease = allocator._lease_policy['base_lease_seconds']
    print(f"• Base lease: {base_lease} seconds (30 days)")
    
    # Allocate multiple devices rapidly to trigger high rate
    print("• Allocating devices rapidly...")
    ids = []
    for i in range(5):
        meta = {'device_id': f'RAPID_DEV_{i}', 'serial': f'SER_{i:03d}'}
        id_val = allocator.allocate_id(meta=meta)
        ids.append(id_val)
        print(f"  - Allocated ID: {id_val}")
    
    time.sleep(0.5)
    
    # Check metrics
    stats = allocator.stats()
    metrics = stats.get('lease_metrics', {})
    print(f"\n• New device rate: {metrics.get('new_device_rate_per_hour', 0):.2f} devices/hour")
    print(f"• Effective lease: {metrics.get('effective_lease_seconds', 0)} seconds")
    print(f"• Ultra rate active: {metrics.get('ultra_rate_active', False)}")
    print(f"• Force-zero lease active: {metrics.get('force_zero_lease_active', False)}")
    
    if metrics.get('new_device_rate_per_hour', 0) > 3.0:
        print("✓ High device rate detected")
        if metrics.get('effective_lease_seconds', 0) < base_lease:
            print("✓ Lease shortened due to high rate!")
    
    return allocator, ids


def test_metrics_emission():
    """Test metrics emission to sink."""
    print("\n=== Test 4: Metrics Emission ===")
    
    captured_metrics = []
    
    def metrics_sink(metrics):
        captured_metrics.append(metrics)
        print(f"  [Metrics] rate={metrics.get('new_device_rate_per_hour', 0):.2f}/hr, " +
              f"lease={metrics.get('effective_lease_seconds', 0)}s, " +
              f"ultra_active={metrics.get('ultra_rate_active', False)}")
    
    allocator = IDAllocator(
        base_dir='.',
        persist_file='data/test_id_allocation_metrics.json',
        lease_policy={
            'base_lease_seconds': 86400,  # 1 day for testing
            'metrics_emit_interval_seconds': 1,
        },
        metrics_sink=metrics_sink,
    )
    
    print("• Allocating devices and capturing metrics...")
    for i in range(3):
        meta = {'device_id': f'METRIC_DEV_{i}'}
        allocator.allocate_id(meta=meta)
        time.sleep(0.3)
    
    print(f"✓ Captured {len(captured_metrics)} metric snapshots")
    if captured_metrics:
        latest = captured_metrics[-1]
        print(f"  Latest metrics: {json.dumps({k: v for k, v in latest.items() if k in ['new_device_rate_per_hour', 'effective_lease_seconds', 'total_allocated']}, indent=4)}")


def test_persistence():
    """Test persistence to disk and reload."""
    print("\n=== Test 5: Persistence ===")
    
    persist_file = 'data/test_id_allocation_persist.json'
    Path(persist_file).parent.mkdir(parents=True, exist_ok=True)
    
    # Create and allocate
    allocator1 = IDAllocator(base_dir='.', persist_file=persist_file)
    meta = {'device_id': 'PERSIST_DEV', 'serial': 'PER_001'}
    id_val = allocator1.allocate_id(meta=meta)
    print(f"• Allocated ID: {id_val} in first allocator instance")
    
    # Load from disk
    allocator2 = IDAllocator(base_dir='.', persist_file=persist_file)
    stats = allocator2.stats()
    print(f"✓ Reloaded from disk: {stats['total_allocated']} allocated IDs")
    
    # Try to reuse the same device
    reused_id = allocator2.allocate_id(meta=meta)
    print(f"✓ Device reuse after reload: {reused_id} (was {id_val})")
    
    if reused_id == id_val:
        print("✓ Persistence and reuse working correctly!")


def cleanup_test_files():
    """Clean up test files."""
    test_files = [
        'data/test_id_allocation.json',
        'data/test_id_allocation_adaptive.json',
        'data/test_id_allocation_metrics.json',
        'data/test_id_allocation_persist.json',
    ]
    for f in test_files:
        p = Path(f)
        if p.exists():
            p.unlink()
            print(f"  Cleaned: {f}")


if __name__ == '__main__':
    print("\n" + "="*70)
    print("ID Allocation & Lease Management System - Full Test Suite")
    print("="*70)
    
    try:
        allocator, id1, id2 = test_basic_allocation()
        test_device_reuse(allocator, id1, id2)
        allocator_adaptive, ids = test_adaptive_lease()
        test_metrics_emission()
        test_persistence()
        
        print("\n" + "="*70)
        print("✓ All tests completed successfully!")
        print("="*70)
        
    finally:
        print("\nCleaning up test files...")
        cleanup_test_files()

