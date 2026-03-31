"""
Port Forwarder Plugin – Usage Examples

Demonstrates how to use the port forwarding plugin with object-based rule configuration.
"""

# ════════════════════════════════════════════════════════════════════════════
# Example 1: Simple Port Forwarding
# ════════════════════════════════════════════════════════════════════════════

def example_1_simple_forwarding():
    """Forward all UDP packets to a TCP service"""
    from opensynaptic import OpenSynaptic
    from opensynaptic.services.port_forwarder import ForwardingRule, ForwardingRuleSet, PortForwarder
    
    # Create node
    node = OpenSynaptic()
    
    # Create a forwarding rule: UDP → TCP
    rule = ForwardingRule(
        from_protocol='UDP',
        to_protocol='TCP',
        to_host='192.168.1.100',
        to_port=8080,
    )
    
    # Create rule set
    rule_set = ForwardingRuleSet(
        name='simple',
        description='Simple UDP to TCP forwarding',
        rules=[rule],
    )
    
    # Create and mount plugin
    plugin = PortForwarder(node=node, rule_sets=[rule_set])
    node.service_manager.mount('port_forwarder', plugin)
    node.service_manager.load('port_forwarder')
    
    # Now all UDP packets will be forwarded to TCP
    sensors = [['V1', 'OK', 25.5, 'Cel']]
    packet, aid, strategy = node.transmit(sensors=sensors)
    node.dispatch(packet, medium='UDP')  # Will be forwarded to TCP
    
    # Cleanup
    plugin.close()


# ════════════════════════════════════════════════════════════════════════════
# Example 2: Multiple Rules with Priority
# ════════════════════════════════════════════════════════════════════════════

def example_2_multiple_rules_with_priority():
    """Route different sensor types to different backends"""
    from opensynaptic import OpenSynaptic
    from opensynaptic.services.port_forwarder import ForwardingRule, ForwardingRuleSet, PortForwarder
    
    node = OpenSynaptic()
    
    # Rule 1: Route to InfluxDB (high priority)
    rule_influx = ForwardingRule(
        from_protocol='UDP',
        to_protocol='TCP',
        to_host='influxdb.example.com',
        to_port=8086,
        priority=100,  # Higher priority
        metadata={'backend': 'InfluxDB', 'purpose': 'time-series storage'},
    )
    
    # Rule 2: Route to Kafka (medium priority)
    rule_kafka = ForwardingRule(
        from_protocol='UDP',
        to_protocol='TCP',
        to_host='kafka.example.com',
        to_port=9092,
        priority=50,
        metadata={'backend': 'Kafka', 'purpose': 'event streaming'},
    )
    
    # Rule 3: Route to MQTT (low priority / default)
    rule_mqtt = ForwardingRule(
        from_protocol='UDP',
        to_protocol='MQTT',
        to_host='mqtt.example.com',
        to_port=1883,
        priority=10,
        metadata={'backend': 'MQTT', 'purpose': 'real-time messaging'},
    )
    
    # Create rule set with all rules
    rule_set = ForwardingRuleSet(
        name='multi_backend',
        description='Multi-backend forwarding with priority',
        rules=[rule_influx, rule_kafka, rule_mqtt],
    )
    
    # Mount plugin
    plugin = PortForwarder(node=node, rule_sets=[rule_set])
    node.service_manager.mount('port_forwarder', plugin)
    node.service_manager.load('port_forwarder')
    
    # Verify rules
    rules = plugin.list_rules()
    print(f"Loaded {len(rules)} forwarding rules")
    
    plugin.close()


# ════════════════════════════════════════════════════════════════════════════
# Example 3: Multiple Rule Sets
# ════════════════════════════════════════════════════════════════════════════

def example_3_multiple_rule_sets():
    """Separate rule sets for different environments"""
    from opensynaptic import OpenSynaptic
    from opensynaptic.services.port_forwarder import ForwardingRule, ForwardingRuleSet, PortForwarder
    
    node = OpenSynaptic()
    
    # Development rule set
    dev_rules = [
        ForwardingRule(
            from_protocol='UDP',
            to_protocol='TCP',
            to_host='localhost',
            to_port=8080,
            metadata={'env': 'development'},
        )
    ]
    dev_rule_set = ForwardingRuleSet(
        name='development',
        description='Development environment rules',
        rules=dev_rules,
        enabled=True,
    )
    
    # Production rule set
    prod_rules = [
        ForwardingRule(
            from_protocol='UDP',
            to_protocol='TCP',
            to_host='prod-server.example.com',
            to_port=443,
            priority=100,
            metadata={'env': 'production'},
        ),
        ForwardingRule(
            from_protocol='TCP',
            to_protocol='TCP',
            to_host='prod-backup.example.com',
            to_port=443,
            priority=50,
            metadata={'env': 'production', 'type': 'backup'},
        ),
    ]
    prod_rule_set = ForwardingRuleSet(
        name='production',
        description='Production environment rules',
        rules=prod_rules,
        enabled=False,  # Disabled by default
    )
    
    # Mount plugin with both rule sets
    plugin = PortForwarder(
        node=node,
        rule_sets=[dev_rule_set, prod_rule_set],
    )
    node.service_manager.mount('port_forwarder', plugin)
    node.service_manager.load('port_forwarder')
    
    # Check status
    status = plugin.handle_status(None)
    print(f"Active rule sets: {status['rule_sets']}")
    
    plugin.close()


# ════════════════════════════════════════════════════════════════════════════
# Example 4: Dynamic Rule Management
# ════════════════════════════════════════════════════════════════════════════

def example_4_dynamic_rules():
    """Add/remove rules at runtime"""
    from opensynaptic import OpenSynaptic
    from opensynaptic.services.port_forwarder import ForwardingRule, ForwardingRuleSet, PortForwarder
    
    node = OpenSynaptic()
    
    # Start with empty rule set
    rule_set = ForwardingRuleSet(name='dynamic', description='Dynamic rules', rules=[])
    
    plugin = PortForwarder(node=node, rule_sets=[rule_set])
    node.service_manager.mount('port_forwarder', plugin)
    node.service_manager.load('port_forwarder')
    
    # Add rules dynamically
    print("Adding rules dynamically...")
    
    rule1 = ForwardingRule(
        from_protocol='UDP',
        to_protocol='TCP',
        to_host='192.168.1.100',
        to_port=8080,
    )
    rule_set.add_rule(rule1)
    print(f"Added rule: UDP→TCP to {rule1.to_host}:{rule1.to_port}")
    
    rule2 = ForwardingRule(
        from_protocol='TCP',
        to_protocol='MQTT',
        to_host='broker.example.com',
        to_port=1883,
    )
    rule_set.add_rule(rule2)
    print(f"Added rule: TCP→MQTT to {rule2.to_host}:{rule2.to_port}")
    
    # List rules
    rules = plugin.list_rules()
    print(f"\nCurrent rules: {len(rules)}")
    for item in rules:
        r = item['rule']
        print(f"  {r['from_protocol']} → {r['to_protocol']} to {r['to_host']}:{r['to_port']}")
    
    # Remove a rule
    print("\nRemoving first rule...")
    rule_set.remove_rule(rule1)
    
    # List again
    rules = plugin.list_rules()
    print(f"Current rules: {len(rules)}")
    
    plugin.close()


# ════════════════════════════════════════════════════════════════════════════
# Example 5: Load/Save Rules from Config
# ════════════════════════════════════════════════════════════════════════════

def example_5_persistent_rules():
    """
    Load and save forwarding rules from/to Config.json
    
    Rules are automatically persisted to data/port_forwarder_rules.json
    """
    from opensynaptic import OpenSynaptic
    from opensynaptic.services.port_forwarder import PortForwarder
    
    # First run: create rules
    node = OpenSynaptic()
    
    plugin = PortForwarder(
        node=node,
        persist_rules=True,
        rules_file='data/port_forwarder_rules.json',
    )
    node.service_manager.mount('port_forwarder', plugin)
    node.service_manager.load('port_forwarder')
    
    # Add some rules programmatically
    from opensynaptic.services.port_forwarder import ForwardingRule, ForwardingRuleSet
    
    rule = ForwardingRule(
        from_protocol='UDP',
        to_protocol='TCP',
        to_host='example.com',
        to_port=8080,
    )
    
    if 'default' not in plugin.rule_sets:
        plugin.rule_sets['default'] = ForwardingRuleSet(
            name='default',
            description='Default rules',
            rules=[]
        )
    
    plugin.rule_sets['default'].add_rule(rule)
    
    # Rules are automatically saved on close
    plugin.close()
    
    # Second run: load rules (rules are automatically loaded from file)
    node2 = OpenSynaptic()
    plugin2 = PortForwarder(
        node=node2,
        persist_rules=True,
        rules_file='data/port_forwarder_rules.json',
    )
    node2.service_manager.mount('port_forwarder', plugin2)
    node2.service_manager.load('port_forwarder')
    
    # Verify rules were loaded
    rules = plugin2.list_rules()
    print(f"Loaded {len(rules)} rules from persistent storage")
    
    plugin2.close()


# ════════════════════════════════════════════════════════════════════════════
# Example 6: Using with Config.json
# ════════════════════════════════════════════════════════════════════════════

"""
Config.json Configuration Example:

{
  "RESOURCES": {
    "service_plugins": {
      "port_forwarder": {
        "enabled": true,
        "mode": "auto",
        "persist_rules": true,
        "rules_file": "data/port_forwarder_rules.json",
        "rule_sets": [
          {
            "name": "default",
            "description": "Default forwarding rules",
            "enabled": true,
            "rules": [
              {
                "from_protocol": "UDP",
                "from_port": null,
                "to_protocol": "TCP",
                "to_host": "192.168.1.100",
                "to_port": 8080,
                "enabled": true,
                "priority": 100,
                "condition": null,
                "metadata": {
                  "backend": "primary"
                }
              },
              {
                "from_protocol": "UDP",
                "from_port": null,
                "to_protocol": "MQTT",
                "to_host": "mqtt.example.com",
                "to_port": 1883,
                "enabled": true,
                "priority": 50,
                "condition": null,
                "metadata": {
                  "backend": "secondary"
                }
              }
            ]
          }
        ]
      }
    }
  }
}

Then use via CLI:
    python -u src/main.py port-forwarder status
    python -u src/main.py port-forwarder list
    python -u src/main.py port-forwarder stats
"""


# ════════════════════════════════════════════════════════════════════════════
# Example 7: CLI Usage
# ════════════════════════════════════════════════════════════════════════════

"""
CLI Commands:

# Show forwarding status
python -u src/main.py port-forwarder status

# List all active forwarding rules
python -u src/main.py port-forwarder list

# Add a new forwarding rule
python -u src/main.py port-forwarder add-rule \\
  --from-protocol UDP \\
  --to-protocol TCP \\
  --to-host 192.168.1.100 \\
  --to-port 8080 \\
  --rule-set default

# Remove a forwarding rule
python -u src/main.py port-forwarder remove-rule \\
  --rule-set default \\
  --index 0

# Show forwarding statistics
python -u src/main.py port-forwarder stats
"""


if __name__ == '__main__':
    # Run examples
    print("Example 1: Simple Forwarding")
    print("=" * 50)
    example_1_simple_forwarding()
    
    print("\n\nExample 2: Multiple Rules with Priority")
    print("=" * 50)
    example_2_multiple_rules_with_priority()
    
    print("\n\nExample 3: Multiple Rule Sets")
    print("=" * 50)
    example_3_multiple_rule_sets()
    
    print("\n\nExample 4: Dynamic Rules")
    print("=" * 50)
    example_4_dynamic_rules()
    
    print("\n\nExample 5: Persistent Rules")
    print("=" * 50)
    example_5_persistent_rules()
    
    print("\n\nAll examples completed!")

