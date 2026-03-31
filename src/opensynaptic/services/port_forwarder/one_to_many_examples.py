"""
Port Forwarder 插件 - 一对多转发示例

演示如何配置一个源协议发送到多个不同的目标协议/主机/端口
"""

# ════════════════════════════════════════════════════════════════════════════
# 示例 1：UDP 分发到多个后端
# ════════════════════════════════════════════════════════════════════════════

def example_1_udp_to_multiple_backends():
    """
    实现：所有 UDP 数据包分发到 3 个不同的后端服务
    
    UDP → TCP:InfluxDB (8086)
    UDP → TCP:Kafka (9092)
    UDP → MQTT:Broker (1883)
    
    这通过创建 3 条转发规则来实现
    """
    from opensynaptic import OpenSynaptic
    from opensynaptic.services.port_forwarder import (
        PortForwarder,
        ForwardingRule,
        ForwardingRuleSet,
    )
    
    node = OpenSynaptic()
    
    # 创建 3 条规则，都是从 UDP 出发，但目标不同
    rules = [
        # 规则 1：UDP → InfluxDB (TCP)
        ForwardingRule(
            from_protocol='UDP',
            to_protocol='TCP',
            to_host='influxdb.example.com',
            to_port=8086,
            priority=100,  # 优先级最高
            metadata={'backend': 'InfluxDB', 'purpose': 'time-series storage'},
        ),
        
        # 规则 2：UDP → Kafka (TCP)
        ForwardingRule(
            from_protocol='UDP',
            to_protocol='TCP',
            to_host='kafka.example.com',
            to_port=9092,
            priority=50,   # 中等优先级
            metadata={'backend': 'Kafka', 'purpose': 'event streaming'},
        ),
        
        # 规则 3：UDP → MQTT Broker
        ForwardingRule(
            from_protocol='UDP',
            to_protocol='MQTT',
            to_host='mqtt.example.com',
            to_port=1883,
            priority=10,   # 最低优先级
            metadata={'backend': 'MQTT', 'purpose': 'real-time messaging'},
        ),
    ]
    
    # 创建规则集包含所有规则
    rule_set = ForwardingRuleSet(
        name='multi_backend',
        description='UDP to multiple backends',
        rules=rules,
    )
    
    # 挂载插件
    plugin = PortForwarder(node=node, rule_sets=[rule_set])
    node.service_manager.mount('port_forwarder', plugin)
    node.service_manager.load('port_forwarder')
    
    # 验证配置
    print("=" * 60)
    print("UDP 一对多转发规则")
    print("=" * 60)
    
    rules_list = plugin.list_rules()
    print(f"\n配置的规则数：{len(rules_list)}")
    
    for i, item in enumerate(rules_list, 1):
        r = item['rule']
        print(f"\n规则 {i}:")
        print(f"  来源：{r['from_protocol']}")
        print(f"  目标：{r['to_protocol']} → {r['to_host']}:{r['to_port']}")
        print(f"  优先级：{r['priority']}")
        print(f"  元数据：{r['metadata']}")
    
    # 现在，每当有 UDP 数据包到达时，会依次尝试匹配这 3 条规则
    # 第一条匹配的规则会被应用
    sensors = [['V1', 'OK', 25.5, 'Cel']]
    packet, aid, strategy = node.transmit(sensors=sensors)
    
    print(f"\n发送 UDP 数据包...")
    success = node.dispatch(packet, medium='UDP')
    print(f"转发结果：{'成功' if success else '失败'}")
    
    # 查看统计
    stats = plugin.get_stats()
    print(f"\n统计数据：")
    print(f"  总数据包数：{stats['total_packets']}")
    print(f"  转发的数据包：{stats['forwarded_packets']}")
    print(f"  规则应用情况：{stats['rules_applied']}")
    
    plugin.close()


# ════════════════════════════════════════════════════════════════════════════
# 示例 2：TCP 分发到多个不同的协议
# ════════════════════════════════════════════════════════════════════════════

def example_2_tcp_to_multiple_protocols():
    """
    实现：所有 TCP 数据包分发到不同的协议
    
    TCP → TCP:备用服务器
    TCP → MQTT:消息队列
    TCP → UART:串口设备
    """
    from opensynaptic import OpenSynaptic
    from opensynaptic.services.port_forwarder import (
        PortForwarder,
        ForwardingRule,
        ForwardingRuleSet,
    )
    
    node = OpenSynaptic()
    
    rules = [
        # TCP → 备用 TCP 服务器
        ForwardingRule(
            from_protocol='TCP',
            to_protocol='TCP',
            to_host='backup-server.example.com',
            to_port=443,
            priority=100,
        ),
        
        # TCP → MQTT 消息队列
        ForwardingRule(
            from_protocol='TCP',
            to_protocol='MQTT',
            to_host='message-broker.example.com',
            to_port=1883,
            priority=50,
        ),
        
        # TCP → UART 串口设备
        ForwardingRule(
            from_protocol='TCP',
            to_protocol='UART',
            to_host='/dev/ttyUSB0',
            to_port=9600,
            priority=10,
        ),
    ]
    
    rule_set = ForwardingRuleSet(
        name='tcp_to_all',
        description='TCP to multiple protocols',
        rules=rules,
    )
    
    plugin = PortForwarder(node=node, rule_sets=[rule_set])
    node.service_manager.mount('port_forwarder', plugin)
    node.service_manager.load('port_forwarder')
    
    print("\nTCP 一对多转发规则已配置")
    print(f"总规则数：{len(plugin.list_rules())}")
    
    plugin.close()


# ════════════════════════════════════════════════════════════════════════════
# 示例 3：MQTT 分发到多个数据库
# ════════════════════════════════════════════════════════════════════════════

def example_3_mqtt_to_multiple_databases():
    """
    实现：所有 MQTT 消息分发到多个存储系统
    
    MQTT → TCP:MongoDB (27017)
    MQTT → TCP:PostgreSQL (5432)
    MQTT → TCP:ClickHouse (8123)
    """
    from opensynaptic import OpenSynaptic
    from opensynaptic.services.port_forwarder import (
        PortForwarder,
        ForwardingRule,
        ForwardingRuleSet,
    )
    
    node = OpenSynaptic()
    
    rules = [
        # MQTT → MongoDB
        ForwardingRule(
            from_protocol='MQTT',
            to_protocol='TCP',
            to_host='mongodb.example.com',
            to_port=27017,
            priority=100,
            metadata={'db': 'MongoDB', 'purpose': 'document storage'},
        ),
        
        # MQTT → PostgreSQL
        ForwardingRule(
            from_protocol='MQTT',
            to_protocol='TCP',
            to_host='postgres.example.com',
            to_port=5432,
            priority=80,
            metadata={'db': 'PostgreSQL', 'purpose': 'relational storage'},
        ),
        
        # MQTT → ClickHouse
        ForwardingRule(
            from_protocol='MQTT',
            to_protocol='TCP',
            to_host='clickhouse.example.com',
            to_port=8123,
            priority=60,
            metadata={'db': 'ClickHouse', 'purpose': 'analytics'},
        ),
    ]
    
    rule_set = ForwardingRuleSet(
        name='mqtt_multi_db',
        description='MQTT to multiple databases',
        rules=rules,
    )
    
    plugin = PortForwarder(node=node, rule_sets=[rule_set])
    node.service_manager.mount('port_forwarder', plugin)
    node.service_manager.load('port_forwarder')
    
    print("\nMQTT 一对多转发规则已配置")
    print(f"目标数据库数：{len(plugin.list_rules())}")
    
    plugin.close()


# ════════════════════════════════════════════════════════════════════════════
# 示例 4：通过 Config.json 配置一对多转发
# ════════════════════════════════════════════════════════════════════════════

"""
Config.json 配置示例：

{
  "RESOURCES": {
    "service_plugins": {
      "port_forwarder": {
        "enabled": true,
        "mode": "auto",
        "rule_sets": [
          {
            "name": "udp_to_multiple",
            "description": "UDP 一对多转发",
            "enabled": true,
            "rules": [
              {
                "from_protocol": "UDP",
                "to_protocol": "TCP",
                "to_host": "server1.example.com",
                "to_port": 8080,
                "priority": 100,
                "metadata": {"backend": "primary"}
              },
              {
                "from_protocol": "UDP",
                "to_protocol": "TCP",
                "to_host": "server2.example.com",
                "to_port": 8080,
                "priority": 50,
                "metadata": {"backend": "secondary"}
              },
              {
                "from_protocol": "UDP",
                "to_protocol": "MQTT",
                "to_host": "broker.example.com",
                "to_port": 1883,
                "priority": 10,
                "metadata": {"backend": "mqtt"}
              }
            ]
          }
        ]
      }
    }
  }
}
"""


# ════════════════════════════════════════════════════════════════════════════
# 示例 5：一对多转发的工作流程
# ════════════════════════════════════════════════════════════════════════════

def example_5_workflow_explanation():
    """
    详细解释一对多转发的工作原理
    """
    print("\n" + "=" * 70)
    print("一对多转发的工作原理")
    print("=" * 70)
    
    workflow = """
    配置：3 条规则，都是 UDP 来源
    ┌─────────────────────────────────────────────────────────┐
    │ 规则 1: UDP → TCP:server1:8080 (优先级 100)            │
    │ 规则 2: UDP → TCP:server2:8080 (优先级 50)             │
    │ 规则 3: UDP → MQTT:broker:1883 (优先级 10)             │
    └─────────────────────────────────────────────────────────┘
    
    执行流程：
    UDP 数据包到达
         ↓
    规则按优先级排序：规则1 > 规则2 > 规则3
         ↓
    逐个尝试匹配规则
         ├─ 规则 1：from_protocol == 'UDP' ? ✅ 匹配！
         │   └─ 应用：转发到 TCP:server1:8080
         │
         ├─ （规则 2、3 不再检查，因为已找到匹配）
         
    结果：
    UDP 数据包 → TCP:server1:8080
    """
    
    print(workflow)
    
    print("\n关键点：")
    print("1️⃣  每条规则都是独立的")
    print("2️⃣  规则按优先级排序（高优先级先匹配）")
    print("3️⃣  第一条匹配的规则被应用")
    print("4️⃣  可以有任意数量的规则")
    print("5️⃣  不同的源协议也可以")


# ════════════════════════════════════════════════════════════════════════════
# 示例 6：高级：同一个源但目标不同的场景
# ════════════════════════════════════════════════════════════════════════════

def example_6_advanced_filtering():
    """
    高级用法：根据数据内容分发到不同的目标
    
    虽然当前版本使用优先级来选择规则，
    但可以通过以下方式实现更复杂的转发：
    
    1. 根据数据包内容分类
    2. 根据时间条件
    3. 根据负载轮转
    """
    from opensynaptic import OpenSynaptic
    from opensynaptic.services.port_forwarder import (
        PortForwarder,
        ForwardingRule,
        ForwardingRuleSet,
    )
    
    node = OpenSynaptic()
    
    # 场景：传感器数据根据类型分发到不同的系统
    rules = [
        # 高优先级规则：关键数据（温度过高）
        # → 实时监控系统
        ForwardingRule(
            from_protocol='UDP',
            to_protocol='TCP',
            to_host='realtime-monitor.example.com',
            to_port=8080,
            priority=100,
            metadata={
                'type': 'critical',
                'condition': 'temperature > 50',
                'system': 'real-time alerting'
            },
        ),
        
        # 中等优先级：时间序列数据
        # → 时序数据库
        ForwardingRule(
            from_protocol='UDP',
            to_protocol='TCP',
            to_host='influxdb.example.com',
            to_port=8086,
            priority=50,
            metadata={
                'type': 'timeseries',
                'system': 'historical data storage'
            },
        ),
        
        # 低优先级：备份
        # → 消息队列进行异步处理
        ForwardingRule(
            from_protocol='UDP',
            to_protocol='MQTT',
            to_host='kafka.example.com',
            to_port=9092,
            priority=10,
            metadata={
                'type': 'backup',
                'system': 'async processing'
            },
        ),
    ]
    
    rule_set = ForwardingRuleSet(
        name='smart_routing',
        description='Smart data routing based on priority',
        rules=rules,
    )
    
    plugin = PortForwarder(node=node, rule_sets=[rule_set])
    node.service_manager.mount('port_forwarder', plugin)
    node.service_manager.load('port_forwarder')
    
    print("\n智能数据路由规则已配置")
    print("UDP 数据包会根据优先级转发到：")
    for i, item in enumerate(plugin.list_rules(), 1):
        r = item['rule']
        print(f"{i}. {r['to_protocol']} → {r['to_host']}:{r['to_port']} "
              f"(优先级: {r['priority']})")
    
    plugin.close()


# ════════════════════════════════════════════════════════════════════════════
# 示例 7：动态添加/删除一对多规则
# ════════════════════════════════════════════════════════════════════════════

def example_7_dynamic_one_to_many():
    """
    运行时动态配置一对多转发
    """
    from opensynaptic import OpenSynaptic
    from opensynaptic.services.port_forwarder import (
        PortForwarder,
        ForwardingRule,
        ForwardingRuleSet,
    )
    
    node = OpenSynaptic()
    
    # 从空的规则集开始
    rule_set = ForwardingRuleSet(name='dynamic', rules=[])
    plugin = PortForwarder(node=node, rule_sets=[rule_set])
    node.service_manager.mount('port_forwarder', plugin)
    node.service_manager.load('port_forwarder')
    
    print("\n" + "=" * 60)
    print("动态配置一对多转发")
    print("=" * 60)
    
    # 动态添加第一个规则
    print("\n[步骤 1] 添加规则 1: UDP → TCP:server1")
    rule1 = ForwardingRule(
        from_protocol='UDP',
        to_protocol='TCP',
        to_host='server1.example.com',
        to_port=8080,
        priority=100,
    )
    rule_set.add_rule(rule1)
    print(f"  ✅ 已添加，当前规则数：{len(rule_set.rules)}")
    
    # 动态添加第二个规则
    print("\n[步骤 2] 添加规则 2: UDP → MQTT:broker")
    rule2 = ForwardingRule(
        from_protocol='UDP',
        to_protocol='MQTT',
        to_host='broker.example.com',
        to_port=1883,
        priority=50,
    )
    rule_set.add_rule(rule2)
    print(f"  ✅ 已添加，当前规则数：{len(rule_set.rules)}")
    
    # 动态添加第三个规则
    print("\n[步骤 3] 添加规则 3: UDP → UART")
    rule3 = ForwardingRule(
        from_protocol='UDP',
        to_protocol='UART',
        to_host='/dev/ttyUSB0',
        to_port=9600,
        priority=10,
    )
    rule_set.add_rule(rule3)
    print(f"  ✅ 已添加，当前规则数：{len(rule_set.rules)}")
    
    # 列出所有规则
    print("\n[结果] 当前配置的转发规则：")
    for i, item in enumerate(plugin.list_rules(), 1):
        r = item['rule']
        print(f"  {i}. UDP → {r['to_protocol']}:{r['to_host']}:{r['to_port']} "
              f"(优先级: {r['priority']})")
    
    # 动态删除规则
    print("\n[步骤 4] 删除规则 2（MQTT）")
    rule_set.remove_rule(rule2)
    print(f"  ✅ 已删除，当前规则数：{len(rule_set.rules)}")
    
    # 验证
    print("\n[验证] 删除后的规则：")
    for i, item in enumerate(plugin.list_rules(), 1):
        r = item['rule']
        print(f"  {i}. UDP → {r['to_protocol']}:{r['to_host']}:{r['to_port']}")
    
    plugin.close()


if __name__ == '__main__':
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 68 + "║")
    print("║" + "Port Forwarder 一对多转发完整示例".center(68) + "║")
    print("║" + " " * 68 + "║")
    print("╚" + "=" * 68 + "╝")
    
    print("\n\n📝 示例 1: UDP 分发到 3 个不同的后端")
    print("-" * 70)
    example_1_udp_to_multiple_backends()
    
    print("\n\n📝 示例 2: TCP 分发到多个不同的协议")
    print("-" * 70)
    example_2_tcp_to_multiple_protocols()
    
    print("\n\n📝 示例 3: MQTT 分发到多个数据库")
    print("-" * 70)
    example_3_mqtt_to_multiple_databases()
    
    print("\n\n📝 示例 5: 工作原理详解")
    print("-" * 70)
    example_5_workflow_explanation()
    
    print("\n\n📝 示例 6: 高级场景")
    print("-" * 70)
    example_6_advanced_filtering()
    
    print("\n\n📝 示例 7: 动态配置")
    print("-" * 70)
    example_7_dynamic_one_to_many()
    
    print("\n\n" + "=" * 70)
    print("所有示例完成！")
    print("=" * 70)

