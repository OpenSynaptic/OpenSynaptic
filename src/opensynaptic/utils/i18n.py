"""
Multi-language support module for OpenSynaptic.
Supports message translation with fallback to English.
"""
from enum import Enum
from typing import Optional, Dict, Any

class Language(Enum):
    """Supported languages"""
    EN = 'en'
    ZH = 'zh'

# English messages (imported from constants)
MESSAGES_EN = {
    'OpenSynaptic base is ready | Root: {root}': 'OpenSynaptic base is ready | Root: {root}',
    'Configuration saved: {field}={value}': 'Configuration saved: {field}={value}',
    'Time synchronized successfully: server_time={server_time} | {host}:{port}': 'Time synchronized successfully: server_time={server_time} | {host}:{port}',
    'Library indexing completed: {modules}': 'Library indexing completed: {modules}',
    'Library indexing failed: {module}': 'Library indexing failed: {module}',
    'Library sync completed: {output}': 'Library sync completed: {output}',
    'Library sync failed: {target}': 'Library sync failed: {target}',
    'Protocol header exported: {output}': 'Protocol header exported: {output}',
    'Driver mounted {module} | Source: {source}': 'Driver mounted {module} | Source: {source}',
    'Driver activated {module} | Status: running': 'Driver activated {module} | Status: running',
    'Driver sleeping {module} | Status: disabled': 'Driver sleeping {module} | Status: disabled',
    "New driver '{module}' discovered and registered in Config (disabled by default)": "New driver '{module}' discovered and registered in Config (disabled by default)",
    'Protocol refreshed {layer}:{protocol}': 'Protocol refreshed {layer}:{protocol}',
    'Protocol cache invalidated {layer}:{protocol}': 'Protocol cache invalidated {layer}:{protocol}',
    'Device {addr} → ID={assigned}': 'Device {addr} → ID={assigned}',
    'Server assigned ID={assigned}': 'Server assigned ID={assigned}',
    'ID pool issued {addr} → {count} IDs': 'ID pool issued {addr} → {count} IDs',
    'ID pool received {count} IDs: {pool}': 'ID pool received {count} IDs: {pool}',
    'ID request timeout ({timeout}s)': 'ID request timeout ({timeout}s)',
    'Send succeeded: {info}': 'Send succeeded: {info}',
    'Send failed: {info}': 'Send failed: {info}',
    'LoRa successfully connected to device: {port}': 'LoRa successfully connected to device: {port}',
    'LoRa serial port closed': 'LoRa serial port closed',
    'LoRa transmitting ({len} Bytes): {hex}': 'LoRa transmitting ({len} Bytes): {hex}',
    'LoRa received response: {hex}': 'LoRa received response: {hex}',
    'LoRa send failed: serial port not ready.': 'LoRa send failed: serial port not ready.',
    'Receiver learned template TID={tid} | src={src} | vars={vars}': 'Receiver learned template TID={tid} | src={src} | vars={vars}',
    'CAN Bus ID:{can_id} splitting data into {chunks} frames to send...': 'CAN Bus ID:{can_id} splitting data into {chunks} frames to send...',
    'lwIP core started: {host}:{port}': 'lwIP core started: {host}:{port}',
    'lwIP network sent {bytes} bytes to {addr}': 'lwIP network sent {bytes} bytes to {addr}',
    'App received data from {addr}: {preview}': 'App received data from {addr}: {preview}',
    'RS485 sending {len} bytes through {port}...': 'RS485 sending {len} bytes through {port}...',
    'UART sent {total_len} bytes via {port}...': 'UART sent {total_len} bytes via {port}...',
    'Physical estimated baud duration: {duration:.4f}s': 'Physical estimated baud duration: {duration:.4f}s',
    'Data on physical wire: {preview}': 'Data on physical wire: {preview}',
    'uIP Sim listening on {host}:{port}...': 'uIP Sim listening on {host}:{port}...',
    'uIP sent {len} bytes -> {addr}': 'uIP sent {len} bytes -> {addr}',
    'uIP received: {received}': 'uIP received: {received}',
    'UDP Server started successfully | Port: {port}': 'UDP Server started successfully | Port: {port}',
    'Server stop signal received': 'Server stop signal received',
    'Received packet {addr} | CMD={cmd} | {size}B': 'Received packet {addr} | CMD={cmd} | {size}B',
    'Data packet parsed: {preview}': 'Data packet parsed: {preview}',
    'Control packet parsed: {preview}': 'Control packet parsed: {preview}',
    'Response sent {addr} | {size}B': 'Response sent {addr} | {size}B',
    'Unknown command: {preview}': 'Unknown command: {preview}',
    'Shard worker threads ready: {shards} | per-shard queue: {queue_size} | total capacity: {capacity}': 'Shard worker threads ready: {shards} | per-shard queue: {queue_size} | total capacity: {capacity}',
    'Performance stats recv={received} ok={completed} fail={failed} drop={dropped} backlog={backlog}/{max_backlog} avg={avg_latency_ms}ms max={max_latency_ms}ms pps(in/out)={ingress_pps}/{complete_pps}': 'Performance stats recv={received} ok={completed} fail={failed} drop={dropped} backlog={backlog}/{max_backlog} avg={avg_latency_ms}ms max={max_latency_ms}ms pps(in/out)={ingress_pps}/{complete_pps}',
    'Final stats: {snapshot}': 'Final stats: {snapshot}',
    'Overload drop shard={shard} backlog={backlog} cap={capacity}': 'Overload drop shard={shard} backlog={backlog} cap={capacity}',
    'Worker thread error shard={shard}: {error}': 'Worker thread error shard={shard}: {error}',
    'Receive error: {error}': 'Receive error: {error}',
    'CLI ready: {mode}': 'CLI ready: {mode}',
    'CLI action executed: {action}': 'CLI action executed: {action}',
    'CLI result: {result}': 'CLI result: {result}',
    'TUI ready': 'TUI ready',
    'TUI rendered: {section}': 'TUI rendered: {section}',
    '5G/LTE sending via cellular network...': '5G/LTE sending via cellular network...',
    '5G server response: {res_data}': '5G server response: {res_data}',
    'Pipeline inject stage [{stage}]: {summary}': 'Pipeline inject stage [{stage}]: {summary}',
    '[{ts}] Watch module [{module}] no change': '[{ts}] Watch module [{module}] no change',
    '[{ts}] Watch module [{module}] state changed': '[{ts}] Watch module [{module}] state changed',
    'Decode result: {result}': 'Decode result: {result}',
    'Transporter [{name}] → {state}': 'Transporter [{name}] → {state}',
    'Config show: {section}': 'Config show: {section}',
    'Config get: {key} = {value}': 'Config get: {key} = {value}',
    'Config set: {key} = {value}': 'Config set: {key} = {value}',
    'Plugin initialized: {plugin}': 'Plugin initialized: {plugin}',
    'Plugin ready: {plugin}': 'Plugin ready: {plugin}',
    'Plugin closed: {plugin}': 'Plugin closed: {plugin}',
    'Plugin command routing: {plugin}.{sub_cmd}': 'Plugin command routing: {plugin}.{sub_cmd}',
    'Plugin test started: {plugin} suite={suite}': 'Plugin test started: {plugin} suite={suite}',
    'Plugin test completed: {plugin} suite={suite} ok={ok} fail={fail}': 'Plugin test completed: {plugin} suite={suite} ok={ok} fail={fail}',
    'TUI section rendered: {section}': 'TUI section rendered: {section}',
    'TUI interactive mode started interval={interval}s': 'TUI interactive mode started interval={interval}s',
    'Node status requested device_id={device_id}': 'Node status requested device_id={device_id}',
    'Device ID info requested assigned_id={assigned_id}': 'Device ID info requested assigned_id={assigned_id}',
    'Log level set to {new_level}': 'Log level set to {new_level}',
    'Pipeline info requested backend={backend}': 'Pipeline info requested backend={backend}',
}

# Chinese (Simplified) translations
MESSAGES_ZH = {
    'OpenSynaptic base is ready | Root: {root}': 'OpenSynaptic 已准备就绪 | 根目录: {root}',
    'Configuration saved: {field}={value}': '配置已保存: {field}={value}',
    'Time synchronized successfully: server_time={server_time} | {host}:{port}': '时间同步成功: server_time={server_time} | {host}:{port}',
    'Library indexing completed: {modules}': '库索引完成: {modules}',
    'Library indexing failed: {module}': '库索引失败: {module}',
    'Library sync completed: {output}': '库同步完成: {output}',
    'Library sync failed: {target}': '库同步失败: {target}',
    'Protocol header exported: {output}': '协议头已导出: {output}',
    'Driver mounted {module} | Source: {source}': '驱动已挂载 {module} | 来源: {source}',
    'Driver activated {module} | Status: running': '驱动已激活 {module} | 状态: 运行中',
    'Driver sleeping {module} | Status: disabled': '驱动已暂停 {module} | 状态: 禁用',
    "New driver '{module}' discovered and registered in Config (disabled by default)": "发现新驱动 '{module}' 并在配置中注册 (默认禁用)",
    'Protocol refreshed {layer}:{protocol}': '协议已刷新 {layer}:{protocol}',
    'Protocol cache invalidated {layer}:{protocol}': '协议缓存已失效 {layer}:{protocol}',
    'Device {addr} → ID={assigned}': '设备 {addr} → ID={assigned}',
    'Server assigned ID={assigned}': '服务器分配 ID={assigned}',
    'ID pool issued {addr} → {count} IDs': 'ID 池已分配 {addr} → {count} 个 ID',
    'ID pool received {count} IDs: {pool}': '已接收 ID 池 {count} 个 ID: {pool}',
    'ID request timeout ({timeout}s)': 'ID 请求超时 ({timeout}s)',
    'Send succeeded: {info}': '发送成功: {info}',
    'Send failed: {info}': '发送失败: {info}',
    'LoRa successfully connected to device: {port}': 'LoRa 已成功连接到设备: {port}',
    'LoRa serial port closed': 'LoRa 串口已关闭',
    'LoRa transmitting ({len} Bytes): {hex}': 'LoRa 传输中 ({len} 字节): {hex}',
    'LoRa received response: {hex}': 'LoRa 已接收响应: {hex}',
    'LoRa send failed: serial port not ready.': 'LoRa 发送失败: 串口未就绪',
    'Receiver learned template TID={tid} | src={src} | vars={vars}': '接收器已学习模板 TID={tid} | src={src} | vars={vars}',
    'CAN Bus ID:{can_id} splitting data into {chunks} frames to send...': 'CAN 总线 ID:{can_id} 将数据分割为 {chunks} 帧发送...',
    'lwIP core started: {host}:{port}': 'lwIP 内核已启动: {host}:{port}',
    'lwIP network sent {bytes} bytes to {addr}': 'lwIP 网络已向 {addr} 发送 {bytes} 字节',
    'App received data from {addr}: {preview}': '应用已接收来自 {addr} 的数据: {preview}',
    'RS485 sending {len} bytes through {port}...': 'RS485 正通过 {port} 发送 {len} 字节...',
    'UART sent {total_len} bytes via {port}...': 'UART 已通过 {port} 发送 {total_len} 字节...',
    'Physical estimated baud duration: {duration:.4f}s': '物理估计波特率持续时间: {duration:.4f}s',
    'Data on physical wire: {preview}': '物理线路上的数据: {preview}',
    'uIP Sim listening on {host}:{port}...': 'uIP 模拟器在 {host}:{port} 监听中...',
    'uIP sent {len} bytes -> {addr}': 'uIP 已向 {addr} 发送 {len} 字节',
    'uIP received: {received}': 'uIP 已接收: {received}',
    'UDP Server started successfully | Port: {port}': 'UDP 服务器启动成功 | 端口: {port}',
    'Server stop signal received': '收到服务器停止信号',
    'Received packet {addr} | CMD={cmd} | {size}B': '已接收数据包 {addr} | CMD={cmd} | {size}B',
    'Data packet parsed: {preview}': '数据包已解析: {preview}',
    'Control packet parsed: {preview}': '控制包已解析: {preview}',
    'Response sent {addr} | {size}B': '已向 {addr} 发送响应 | {size}B',
    'Unknown command: {preview}': '未知命令: {preview}',
    'Shard worker threads ready: {shards} | per-shard queue: {queue_size} | total capacity: {capacity}': '分片工作线程已就绪: {shards} | 分片队列: {queue_size} | 总容量: {capacity}',
    'Performance stats recv={received} ok={completed} fail={failed} drop={dropped} backlog={backlog}/{max_backlog} avg={avg_latency_ms}ms max={max_latency_ms}ms pps(in/out)={ingress_pps}/{complete_pps}': '性能统计 recv={received} ok={completed} fail={failed} drop={dropped} backlog={backlog}/{max_backlog} avg={avg_latency_ms}ms max={max_latency_ms}ms pps(in/out)={ingress_pps}/{complete_pps}',
    'Final stats: {snapshot}': '最终统计: {snapshot}',
    'Overload drop shard={shard} backlog={backlog} cap={capacity}': '过载丢弃 shard={shard} backlog={backlog} cap={capacity}',
    'Worker thread error shard={shard}: {error}': '工作线程错误 shard={shard}: {error}',
    'Receive error: {error}': '接收错误: {error}',
    'CLI ready: {mode}': 'CLI 已就绪: {mode}',
    'CLI action executed: {action}': 'CLI 操作已执行: {action}',
    'CLI result: {result}': 'CLI 结果: {result}',
    'TUI ready': 'TUI 已就绪',
    'TUI rendered: {section}': 'TUI 已渲染: {section}',
    '5G/LTE sending via cellular network...': '5G/LTE 通过蜂窝网络发送中...',
    '5G server response: {res_data}': '5G 服务器响应: {res_data}',
    'Pipeline inject stage [{stage}]: {summary}': '管道注入阶段 [{stage}]: {summary}',
    '[{ts}] Watch module [{module}] no change': '[{ts}] 监视模块 [{module}] 无变化',
    '[{ts}] Watch module [{module}] state changed': '[{ts}] 监视模块 [{module}] 状态已更改',
    'Decode result: {result}': '解码结果: {result}',
    'Transporter [{name}] → {state}': '传输器 [{name}] → {state}',
    'Config show: {section}': '配置显示: {section}',
    'Config get: {key} = {value}': '配置获取: {key} = {value}',
    'Config set: {key} = {value}': '配置设置: {key} = {value}',
    'Plugin initialized: {plugin}': '插件已初始化: {plugin}',
    'Plugin ready: {plugin}': '插件已就绪: {plugin}',
    'Plugin closed: {plugin}': '插件已关闭: {plugin}',
    'Plugin command routing: {plugin}.{sub_cmd}': '插件命令路由: {plugin}.{sub_cmd}',
    'Plugin test started: {plugin} suite={suite}': '插件测试已启动: {plugin} suite={suite}',
    'Plugin test completed: {plugin} suite={suite} ok={ok} fail={fail}': '插件测试已完成: {plugin} suite={suite} ok={ok} fail={fail}',
    'TUI section rendered: {section}': 'TUI 部分已渲染: {section}',
    'TUI interactive mode started interval={interval}s': 'TUI 交互模式已启动 interval={interval}s',
    'Node status requested device_id={device_id}': '已请求节点状态 device_id={device_id}',
    'Device ID info requested assigned_id={assigned_id}': '已请求设备 ID 信息 assigned_id={assigned_id}',
    'Log level set to {new_level}': '日志级别设置为 {new_level}',
    'Pipeline info requested backend={backend}': '已请求管道信息 backend={backend}',
}

class Translator:
    """Multi-language translator for OpenSynaptic messages."""
    
    def __init__(self, language: Language = Language.EN):
        self.language = language
        self.translations: Dict[Language, Dict[str, str]] = {
            Language.EN: MESSAGES_EN,
            Language.ZH: MESSAGES_ZH,
        }
    
    def translate(self, message: str, **kwargs) -> str:
        """
        Translate and format a message.
        
        Args:
            message: The message template (typically from MESSAGES)
            **kwargs: Format arguments
            
        Returns:
            Translated and formatted message, or original if translation not found.
        """
        trans_dict = self.translations.get(self.language, MESSAGES_EN)
        translated = trans_dict.get(message, message)
        
        if kwargs:
            try:
                return translated.format(**kwargs)
            except KeyError:
                # If formatting fails, return unformatted translated message
                return translated
        
        return translated
    
    def set_language(self, language: Language):
        """Switch to a different language."""
        if language in self.translations:
            self.language = language
        else:
            # Fallback to English if unsupported language
            self.language = Language.EN
    
    def get_language(self) -> str:
        """Get current language code."""
        return self.language.value


# Global translator instance
_translator = Translator(Language.EN)


def set_language(language: Language) -> None:
    """Set global language for all messages."""
    _translator.set_language(language)


def set_language_by_code(code: str) -> None:
    """Set language by language code (e.g., 'en', 'zh')."""
    try:
        lang = Language[code.upper()]
        _translator.set_language(lang)
    except KeyError:
        # Fallback to English for invalid codes
        _translator.set_language(Language.EN)


def get_current_language() -> str:
    """Get current language code."""
    return _translator.get_language()


def translate(message: str, **kwargs) -> str:
    """
    Translate and format a message using current global language.
    
    Example:
        translate('OpenSynaptic base is ready | Root: {root}', root='/path/to/root')
    """
    return _translator.translate(message, **kwargs)
