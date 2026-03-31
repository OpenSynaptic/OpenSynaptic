"""
增强的 Port Forwarder - 功能开关示例

演示如何动态启用/禁用各个功能
"""

# ════════════════════════════════════════════════════════════════════════════
# 示例 1：初始化时指定功能启用状态
# ════════════════════════════════════════════════════════════════════════════

def example_1_init_with_features():
    """在初始化时指定哪些功能启用"""
    from opensynaptic import OpenSynaptic
    from opensynaptic.services.port_forwarder.enhanced import EnhancedPortForwarder
    
    node = OpenSynaptic()
    
    # 初始化时指定功能启用状态
    forwarder = EnhancedPortForwarder(
        node=node,
        firewall_enabled=True,           # ✅ 启用防火墙
        traffic_shaping_enabled=False,   # ❌ 禁用流量整形
        protocol_conversion_enabled=True,# ✅ 启用协议转换
        middleware_enabled=False,        # ❌ 禁用中间件
        proxy_enabled=True,              # ✅ 启用代理
    )
    
    print("=" * 60)
    print("示例 1: 初始化时指定功能状态")
    print("=" * 60)
    
    # 查看功能状态
    status = forwarder.get_feature_status()
    for feature, enabled in status.items():
        emoji = "✅" if enabled else "❌"
        print(f"{emoji} {feature}: {enabled}")
    
    node.service_manager.mount('enhanced_pf', forwarder)
    node.service_manager.load('enhanced_pf')
    
    forwarder.close()


# ════════════════════════════════════════════════════════════════════════════
# 示例 2：运行时启用/禁用功能
# ════════════════════════════════════════════════════════════════════════════

def example_2_runtime_toggle():
    """在运行时动态启用/禁用功能"""
    from opensynaptic import OpenSynaptic
    from opensynaptic.services.port_forwarder.enhanced import EnhancedPortForwarder
    
    node = OpenSynaptic()
    
    # 创建转发器，所有功能默认启用
    forwarder = EnhancedPortForwarder(node=node)
    
    print("\n" + "=" * 60)
    print("示例 2: 运行时动态启用/禁用功能")
    print("=" * 60)
    
    # 初始状态
    print("\n[初始状态]")
    status = forwarder.get_feature_status()
    for feature, enabled in status.items():
        emoji = "✅" if enabled else "❌"
        print(f"  {emoji} {feature}")
    
    # 禁用防火墙
    print("\n[操作] 禁用防火墙")
    forwarder.disable_feature('firewall')
    status = forwarder.get_feature_status()
    print(f"  防火墙: {'✅ 启用' if status['firewall'] else '❌ 禁用'}")
    
    # 禁用流量整形
    print("\n[操作] 禁用流量整形")
    forwarder.disable_feature('traffic_shaping')
    status = forwarder.get_feature_status()
    print(f"  流量整形: {'✅ 启用' if status['traffic_shaping'] else '❌ 禁用'}")
    
    # 重新启用防火墙
    print("\n[操作] 重新启用防火墙")
    forwarder.enable_feature('firewall')
    status = forwarder.get_feature_status()
    print(f"  防火墙: {'✅ 启用' if status['firewall'] else '❌ 禁用'}")
    
    forwarder.close()


# ════════════════════════════════════════════════════════════════════════════
# 示例 3：切换功能状态
# ════════════════════════════════════════════════════════════════════════════

def example_3_toggle_features():
    """使用 toggle 切换功能的启用/禁用状态"""
    from opensynaptic import OpenSynaptic
    from opensynaptic.services.port_forwarder.enhanced import EnhancedPortForwarder
    
    node = OpenSynaptic()
    forwarder = EnhancedPortForwarder(node=node)
    
    print("\n" + "=" * 60)
    print("示例 3: 切换功能状态")
    print("=" * 60)
    
    features = ['firewall', 'traffic_shaping', 'protocol_conversion', 'middleware', 'proxy']
    
    for feature in features:
        # 初始状态
        status = forwarder.get_feature_status()
        initial = status[feature]
        
        # 切换
        new_status = forwarder.toggle_feature(feature)
        
        # 显示
        initial_str = "✅ 启用" if initial else "❌ 禁用"
        new_str = "✅ 启用" if new_status else "❌ 禁用"
        print(f"{feature:20} {initial_str} → {new_str}")
    
    forwarder.close()


# ════════════════════════════════════════════════════════════════════════════
# 示例 4：批量设置功能
# ════════════════════════════════════════════════════════════════════════════

def example_4_batch_set():
    """一次性设置多个功能的状态"""
    from opensynaptic import OpenSynaptic
    from opensynaptic.services.port_forwarder.enhanced import EnhancedPortForwarder
    
    node = OpenSynaptic()
    forwarder = EnhancedPortForwarder(node=node)
    
    print("\n" + "=" * 60)
    print("示例 4: 批量设置功能")
    print("=" * 60)
    
    # 批量设置
    print("\n[操作] 批量设置所有功能")
    result = forwarder.set_features(
        firewall=True,
        traffic_shaping=False,
        protocol_conversion=True,
        middleware=True,
        proxy=False,
    )
    
    print("\n[结果]")
    for feature, enabled in result.items():
        emoji = "✅" if enabled else "❌"
        print(f"  {emoji} {feature}: {enabled}")
    
    forwarder.close()


# ════════════════════════════════════════════════════════════════════════════
# 示例 5：不同的工作模式
# ════════════════════════════════════════════════════════════════════════════

def example_5_work_modes():
    """
    不同的工作模式示例
    
    - 最小模式：只开启基本转发
    - 安全模式：开启防火墙和中间件
    - 性能模式：开启流量整形
    - 企业模式：全功能
    """
    from opensynaptic import OpenSynaptic
    from opensynaptic.services.port_forwarder.enhanced import EnhancedPortForwarder
    
    print("\n" + "=" * 60)
    print("示例 5: 不同的工作模式")
    print("=" * 60)
    
    # 最小模式（只有基本转发）
    print("\n📦 最小模式（轻量级转发）")
    node1 = OpenSynaptic()
    forwarder1 = EnhancedPortForwarder(node=node1)
    forwarder1.set_features(
        firewall=False,
        traffic_shaping=False,
        protocol_conversion=False,
        middleware=False,
        proxy=False,
    )
    print("  只做基本的数据包转发，最高性能")
    forwarder1.close()
    
    # 安全模式
    print("\n🔒 安全模式（防火墙 + 审计）")
    node2 = OpenSynaptic()
    forwarder2 = EnhancedPortForwarder(node=node2)
    forwarder2.set_features(
        firewall=True,      # 防火墙
        traffic_shaping=False,
        protocol_conversion=False,
        middleware=True,    # 审计日志
        proxy=False,
    )
    print("  启用防火墙和中间件进行安全监控")
    forwarder2.close()
    
    # 性能模式
    print("\n⚡ 性能模式（流量控制）")
    node3 = OpenSynaptic()
    forwarder3 = EnhancedPortForwarder(node=node3)
    forwarder3.set_features(
        firewall=False,
        traffic_shaping=True,   # 速率控制
        protocol_conversion=False,
        middleware=False,
        proxy=False,
    )
    print("  开启流量整形进行速率控制")
    forwarder3.close()
    
    # 企业模式（全功能）
    print("\n🏢 企业模式（完整功能）")
    node4 = OpenSynaptic()
    forwarder4 = EnhancedPortForwarder(node=node4)
    forwarder4.set_features(
        firewall=True,
        traffic_shaping=True,
        protocol_conversion=True,
        middleware=True,
        proxy=True,
    )
    print("  全功能启用，完整的网络管理")
    forwarder4.close()


# ════════════════════════════════════════════════════════════════════════════
# 示例 6：CLI 命令使用
# ════════════════════════════════════════════════════════════════════════════

"""
CLI 命令示例：

# 查看所有功能的启用状态
python -u src/main.py enhanced-port-forwarder features

# 启用防火墙
python -u src/main.py enhanced-port-forwarder enable --feature firewall

# 禁用流量整形
python -u src/main.py enhanced-port-forwarder disable --feature traffic_shaping

# 切换中间件状态
python -u src/main.py enhanced-port-forwarder toggle --feature middleware

# 查看详细状态
python -u src/main.py enhanced-port-forwarder status
"""


# ════════════════════════════════════════════════════════════════════════════
# 示例 7：动态启用功能以响应条件
# ════════════════════════════════════════════════════════════════════════════

def example_7_adaptive_features():
    """根据运行条件动态启用/禁用功能"""
    from opensynaptic import OpenSynaptic
    from opensynaptic.services.port_forwarder.enhanced import EnhancedPortForwarder
    import time
    
    node = OpenSynaptic()
    forwarder = EnhancedPortForwarder(node=node)
    
    print("\n" + "=" * 60)
    print("示例 7: 动态适应性功能控制")
    print("=" * 60)
    
    # 模拟不同的场景
    scenarios = [
        {
            'name': '正常流量',
            'high_traffic': False,
            'need_audit': True,
            'config': {
                'firewall': True,
                'traffic_shaping': False,  # 不需要限流
                'protocol_conversion': True,
                'middleware': True,        # 需要审计
                'proxy': True,
            }
        },
        {
            'name': '高流量检测',
            'high_traffic': True,
            'need_audit': False,
            'config': {
                'firewall': True,
                'traffic_shaping': True,   # 启用限流！
                'protocol_conversion': True,
                'middleware': False,       # 关闭审计以提升性能
                'proxy': True,
            }
        },
        {
            'name': '安全审计模式',
            'high_traffic': False,
            'need_audit': True,
            'config': {
                'firewall': True,
                'traffic_shaping': False,
                'protocol_conversion': True,
                'middleware': True,        # 启用审计
                'proxy': True,
            }
        },
    ]
    
    for scenario in scenarios:
        print(f"\n📊 场景: {scenario['name']}")
        forwarder.set_features(**scenario['config'])
        
        status = forwarder.get_feature_status()
        for feature, enabled in status.items():
            emoji = "✅" if enabled else "❌"
            print(f"  {emoji} {feature}")
    
    forwarder.close()


if __name__ == '__main__':
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 68 + "║")
    print("║" + "增强的 Port Forwarder - 功能开关完整示例".center(68) + "║")
    print("║" + " " * 68 + "║")
    print("╚" + "=" * 68 + "╝")
    
    print("\n\n📝 示例 1: 初始化时指定功能")
    print("-" * 70)
    example_1_init_with_features()
    
    print("\n\n📝 示例 2: 运行时启用/禁用")
    print("-" * 70)
    example_2_runtime_toggle()
    
    print("\n\n📝 示例 3: 切换功能状态")
    print("-" * 70)
    example_3_toggle_features()
    
    print("\n\n📝 示例 4: 批量设置功能")
    print("-" * 70)
    example_4_batch_set()
    
    print("\n\n📝 示例 5: 不同的工作模式")
    print("-" * 70)
    example_5_work_modes()
    
    print("\n\n📝 示例 7: 动态适应性控制")
    print("-" * 70)
    example_7_adaptive_features()
    
    print("\n\n" + "=" * 70)
    print("所有示例完成！")
    print("=" * 70)

