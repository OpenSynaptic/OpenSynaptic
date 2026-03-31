from enum import Enum

class LogMsg(Enum):
    READY = 'READY'
    CONFIG_SAVED = 'CONFIG_SAVED'
    TIME_SYNCED = 'TIME_SYNCED'
    LIBRARY_INDEXED = 'LIBRARY_INDEXED'
    LIBRARY_INDEX_FAILED = 'LIBRARY_INDEX_FAILED'
    LIBRARY_SYNCED = 'LIBRARY_SYNCED'
    LIBRARY_SYNC_FAILED = 'LIBRARY_SYNC_FAILED'
    LIBRARY_HEADER_EXPORTED = 'LIBRARY_HEADER_EXPORTED'
    DRIVER_MOUNT = 'DRIVER_MOUNT'
    DRIVER_ACTIVATED = 'DRIVER_ACTIVATED'
    DRIVER_SLEEP = 'DRIVER_SLEEP'
    NEW_DRIVER_REGISTERED = 'NEW_DRIVER_REGISTERED'
    PROTOCOL_REFRESHED = 'PROTOCOL_REFRESHED'
    PROTOCOL_INVALIDATED = 'PROTOCOL_INVALIDATED'
    ID_ASSIGNED = 'ID_ASSIGNED'
    ID_RECEIVED = 'ID_RECEIVED'
    ID_POOL_ISSUED = 'ID_POOL_ISSUED'
    ID_POOL_RECEIVED = 'ID_POOL_RECEIVED'
    ID_REQUEST_TIMEOUT = 'ID_REQUEST_TIMEOUT'
    SUCCESS_SEND = 'SUCCESS_SEND'
    FAILED_SEND = 'FAILED_SEND'
    LORA_CONNECTED = 'LORA_CONNECTED'
    LORA_CLOSED = 'LORA_CLOSED'
    LORA_SENDING = 'LORA_SENDING'
    LORA_RESPONSE = 'LORA_RESPONSE'
    LORA_NOT_READY = 'LORA_NOT_READY'
    TEMPLATE_LEARNED = 'TEMPLATE_LEARNED'
    CAN_SEND = 'CAN_SEND'
    IWIP_START = 'IWIP_START'
    IWIP_SEND = 'IWIP_SEND'
    APP_RECV = 'APP_RECV'
    RS485_SEND = 'RS485_SEND'
    UART_SEND = 'UART_SEND'
    UART_DURATION = 'UART_DURATION'
    UART_LINE = 'UART_LINE'
    UIP_LISTEN = 'UIP_LISTEN'
    UIP_SEND = 'UIP_SEND'
    UIP_RECV = 'UIP_RECV'
    RX_SERVER_START = 'RX_SERVER_START'
    RX_SIGNAL_STOP = 'RX_SIGNAL_STOP'
    RX_PACKET_IN = 'RX_PACKET_IN'
    RX_DATA_PACKET = 'RX_DATA_PACKET'
    RX_CTRL_PACKET = 'RX_CTRL_PACKET'
    RX_RESPONSE_SENT = 'RX_RESPONSE_SENT'
    RX_UNKNOWN_PACKET = 'RX_UNKNOWN_PACKET'
    RX_WORKERS_READY = 'RX_WORKERS_READY'
    RX_PERF = 'RX_PERF'
    RX_FINAL_STATS = 'RX_FINAL_STATS'
    RX_OVERLOAD_DROP = 'RX_OVERLOAD_DROP'
    RX_WORKER_ERROR = 'RX_WORKER_ERROR'
    RX_SOCKET_ERROR = 'RX_SOCKET_ERROR'
    CLI_READY = 'CLI_READY'
    CLI_ACTION = 'CLI_ACTION'
    CLI_RESULT = 'CLI_RESULT'
    TUI_READY = 'TUI_READY'
    TUI_RENDER = 'TUI_RENDER'
    LTE_SENDING = 'LTE_SENDING'
    LTE_RESPONSE = 'LTE_RESPONSE'
    INJECT_STAGE = 'INJECT_STAGE'
    WATCH_TICK = 'WATCH_TICK'
    WATCH_CHANGED = 'WATCH_CHANGED'
    DECODE_RESULT = 'DECODE_RESULT'
    TRANSPORTER_TOGGLED = 'TRANSPORTER_TOGGLED'
    CONFIG_SHOW = 'CONFIG_SHOW'
    CONFIG_GET = 'CONFIG_GET'
    CONFIG_SET = 'CONFIG_SET'
    PLUGIN_INIT = 'PLUGIN_INIT'
    PLUGIN_READY = 'PLUGIN_READY'
    PLUGIN_CLOSED = 'PLUGIN_CLOSED'
    PLUGIN_CMD = 'PLUGIN_CMD'
    PLUGIN_TEST_START = 'PLUGIN_TEST_START'
    PLUGIN_TEST_RESULT = 'PLUGIN_TEST_RESULT'
    TUI_SECTION = 'TUI_SECTION'
    TUI_INTERACTIVE = 'TUI_INTERACTIVE'
    STATUS_SHOW = 'STATUS_SHOW'
    ID_INFO = 'ID_INFO'
    LOG_LEVEL_SET = 'LOG_LEVEL_SET'
    PIPELINE_INFO = 'PIPELINE_INFO'

MESSAGES = {LogMsg.READY: 'OpenSynaptic base is ready | Root: {root}', LogMsg.CONFIG_SAVED: 'Configuration saved: {field}={value}', LogMsg.TIME_SYNCED: 'Time synchronized successfully: server_time={server_time} | {host}:{port}', LogMsg.LIBRARY_INDEXED: 'Library indexing completed: {modules}', LogMsg.LIBRARY_INDEX_FAILED: 'Library indexing failed: {module}', LogMsg.LIBRARY_SYNCED: 'Library sync completed: {output}', LogMsg.LIBRARY_SYNC_FAILED: 'Library sync failed: {target}', LogMsg.LIBRARY_HEADER_EXPORTED: 'Protocol header exported: {output}', LogMsg.DRIVER_MOUNT: 'Driver mounted {module} | Source: {source}', LogMsg.DRIVER_ACTIVATED: 'Driver activated {module} | Status: running', LogMsg.DRIVER_SLEEP: 'Driver sleeping {module} | Status: disabled', LogMsg.NEW_DRIVER_REGISTERED: "New driver '{module}' discovered and registered in Config (disabled by default)", LogMsg.PROTOCOL_REFRESHED: 'Protocol refreshed {layer}:{protocol}', LogMsg.PROTOCOL_INVALIDATED: 'Protocol cache invalidated {layer}:{protocol}', LogMsg.ID_ASSIGNED: 'Device {addr} → ID={assigned}', LogMsg.ID_RECEIVED: 'Server assigned ID={assigned}', LogMsg.ID_POOL_ISSUED: 'ID pool issued {addr} → {count} IDs', LogMsg.ID_POOL_RECEIVED: 'ID pool received {count} IDs: {pool}', LogMsg.ID_REQUEST_TIMEOUT: 'ID request timeout ({timeout}s)', LogMsg.SUCCESS_SEND: 'Send succeeded: {info}', LogMsg.FAILED_SEND: 'Send failed: {info}', LogMsg.LORA_CONNECTED: 'LoRa successfully connected to device: {port}', LogMsg.LORA_CLOSED: 'LoRa serial port closed', LogMsg.LORA_SENDING: 'LoRa transmitting ({len} Bytes): {hex}', LogMsg.LORA_RESPONSE: 'LoRa received response: {hex}', LogMsg.LORA_NOT_READY: 'LoRa send failed: serial port not ready.', LogMsg.TEMPLATE_LEARNED: 'Receiver learned template TID={tid} | src={src} | vars={vars}', LogMsg.CAN_SEND: 'CAN Bus ID:{can_id} splitting data into {chunks} frames to send...', LogMsg.IWIP_START: 'lwIP core started: {host}:{port}', LogMsg.IWIP_SEND: 'lwIP network sent {bytes} bytes to {addr}', LogMsg.APP_RECV: 'App received data from {addr}: {preview}', LogMsg.RS485_SEND: 'RS485 sending {len} bytes through {port}...', LogMsg.UART_SEND: 'UART sent {total_len} bytes via {port}...', LogMsg.UART_DURATION: 'Physical estimated baud duration: {duration:.4f}s', LogMsg.UART_LINE: 'Data on physical wire: {preview}', LogMsg.UIP_LISTEN: 'uIP Sim listening on {host}:{port}...', LogMsg.UIP_SEND: 'uIP sent {len} bytes -> {addr}', LogMsg.UIP_RECV: 'uIP received: {received}', LogMsg.RX_SERVER_START: 'UDP Server started successfully | Port: {port}', LogMsg.RX_SIGNAL_STOP: 'Server stop signal received', LogMsg.RX_PACKET_IN: 'Received packet {addr} | CMD={cmd} | {size}B', LogMsg.RX_DATA_PACKET: 'Data packet parsed: {preview}', LogMsg.RX_CTRL_PACKET: 'Control packet parsed: {preview}', LogMsg.RX_RESPONSE_SENT: 'Response sent {addr} | {size}B', LogMsg.RX_UNKNOWN_PACKET: 'Unknown command: {preview}', LogMsg.RX_WORKERS_READY: 'Shard worker threads ready: {shards} | per-shard queue: {queue_size} | total capacity: {capacity}', LogMsg.RX_PERF: 'Performance stats recv={received} ok={completed} fail={failed} drop={dropped} backlog={backlog}/{max_backlog} avg={avg_latency_ms}ms max={max_latency_ms}ms pps(in/out)={ingress_pps}/{complete_pps}', LogMsg.RX_FINAL_STATS: 'Final stats: {snapshot}', LogMsg.RX_OVERLOAD_DROP: 'Overload drop shard={shard} backlog={backlog} cap={capacity}', LogMsg.RX_WORKER_ERROR: 'Worker thread error shard={shard}: {error}', LogMsg.RX_SOCKET_ERROR: 'Receive error: {error}', LogMsg.CLI_READY: 'CLI ready: {mode}', LogMsg.CLI_ACTION: 'CLI action executed: {action}', LogMsg.CLI_RESULT: 'CLI result: {result}', LogMsg.TUI_READY: 'TUI ready', LogMsg.TUI_RENDER: 'TUI rendered: {section}', LogMsg.LTE_SENDING: '5G/LTE sending via cellular network...', LogMsg.LTE_RESPONSE: '5G server response: {res_data}', LogMsg.INJECT_STAGE: 'Pipeline inject stage [{stage}]: {summary}', LogMsg.WATCH_TICK: '[{ts}] Watch module [{module}] no change', LogMsg.WATCH_CHANGED: '[{ts}] Watch module [{module}] state changed', LogMsg.DECODE_RESULT: 'Decode result: {result}', LogMsg.TRANSPORTER_TOGGLED: 'Transporter [{name}] → {state}'}

MESSAGES.update({
    LogMsg.CONFIG_SHOW: 'Config show: {section}',
    LogMsg.CONFIG_GET: 'Config get: {key} = {value}',
    LogMsg.CONFIG_SET: 'Config set: {key} = {value}',
    LogMsg.PLUGIN_INIT: 'Plugin initialized: {plugin}',
    LogMsg.PLUGIN_READY: 'Plugin ready: {plugin}',
    LogMsg.PLUGIN_CLOSED: 'Plugin closed: {plugin}',
    LogMsg.PLUGIN_CMD: 'Plugin command routing: {plugin}.{sub_cmd}',
    LogMsg.PLUGIN_TEST_START: 'Plugin test started: {plugin} suite={suite}',
    LogMsg.PLUGIN_TEST_RESULT: 'Plugin test completed: {plugin} suite={suite} ok={ok} fail={fail}',
    LogMsg.TUI_SECTION: 'TUI section rendered: {section}',
    LogMsg.TUI_INTERACTIVE: 'TUI interactive mode started interval={interval}s',
    LogMsg.STATUS_SHOW: 'Node status requested device_id={device_id}',
    LogMsg.ID_INFO: 'Device ID info requested assigned_id={assigned_id}',
    LogMsg.LOG_LEVEL_SET: 'Log level set to {new_level}',
    LogMsg.PIPELINE_INFO: 'Pipeline info requested backend={backend}',
})

CLI_HELP_TABLE = {
    'run': {'aliases': ['os-run'], 'desc': 'Main daemon persistent run mode. After starting, maintain the protocol management heartbeat until interrupted or until --duration.'},
    'snapshot': {'aliases': ['os-snapshot'], 'desc': 'Output current node, services, and transporters snapshot as JSON.'},
    'receive': {'aliases': ['os-receive'], 'desc': 'Start UDP receiver (server receive mode).'},
    'tui': {'aliases': ['os-tui'], 'desc': 'Render a TUI plugin snapshot once.'},
    'time-sync': {'aliases': ['os-time-sync'], 'desc': 'Request a timestamp from the server and synchronize.'},
    'ensure-id': {'aliases': ['os-ensure-id'], 'desc': 'Request a device ID from the server and persist it to Config.'},
    'transmit': {'aliases': ['os-transmit'], 'desc': 'Pack sensor data and send once.'},
    'reload-protocol': {'aliases': ['os-reload-protocol'], 'desc': 'Refresh transport/physical layer adapters by protocol name.'},
    'plugin-list': {'aliases': ['os-plugin-list'], 'desc': 'List mounted plugins and their running status.'},
    'plugin-load': {'aliases': ['os-plugin-load'], 'desc': 'Load a plugin by name once.'},
    'transport-status': {'aliases': ['os-transport-status'], 'desc': 'View application/transport/physical layer status and activation.'},
    'db-status': {'aliases': ['os-db-status'], 'desc': 'View whether db_engine is enabled and the current dialect.'},
    'inject': {'aliases': ['os-inject'], 'desc': 'Inject sensor data into the specified pipeline module and show outputs of each stage (--module: standardize/compress/fuse/full).'},
    'decode': {'aliases': ['os-decode'], 'desc': 'Decode a binary packet (hex) or a Base62 compressed string back to readable JSON (--format: hex/b62).'},
    'watch': {'aliases': ['os-watch'], 'desc': 'Poll and monitor the state changes of the specified module in real time (--module: config/registry/transport/pipeline).'},
    'transporter-toggle': {'aliases': ['os-transporter-toggle'], 'desc': 'Enable or disable a transporter in Config.json (--name <name> --enable | --disable).'},
    'config-show': {'aliases': ['os-config-show'], 'desc': 'Show entire Config.json or a specified section (--section <name>).'},
    'config-get': {'aliases': ['os-config-get'], 'desc': 'Read the value at a dotted path in Config.json (--key a.b.c).'},
    'config-set': {'aliases': ['os-config-set'], 'desc': 'Set the value at a dotted path in Config.json (--key a.b.c --value <v> [--type int|float|bool|str|json]).'},
    'wizard': {'aliases': ['init', 'os-wizard', 'os-init'], 'desc': 'Interactive Config.json generator; use --default for one-shot localhost defaults.'},
    'core': {'aliases': ['os-core'], 'desc': 'Show current/available cores, and optionally switch core (--set pycore|rscore [--persist]).'},
    'plugin-cmd': {'aliases': ['os-plugin-cmd'], 'desc': 'Route a command to the specified plugin\'s CLI handler (--plugin <name> --cmd <subcommand> [args...]).'},
    'plugin-test': {'aliases': ['os-plugin-test'], 'desc': 'Run test suites (--suite component|stress|all|compare). Stress supports --auto-profile for concurrency tuning.'},
    'native-check': {'aliases': ['os-native-check'], 'desc': 'Check native compiler environment and selected toolchain before building C bindings.'},
    'native-build': {'aliases': ['os-native-build'], 'desc': 'Build native C bindings with real-time compiler output streaming.'},
    'env-guard': {'aliases': ['os-env-guard'], 'desc': 'Environment guard plugin (error monitor + auto-install attempts + local JSON resource/status file).'},
    'web-user': {'aliases': ['os-web-user', 'os-web'], 'desc': 'Direct CLI entry for the web_user management plugin (--cmd start|stop|status|dashboard|cli|options-schema|options-set|options-apply|list|add|update|delete).'},
    'deps': {'aliases': ['os-deps'], 'desc': 'Direct CLI entry for dependency_manager (--cmd check|doctor|sync|repair|install).'},
    'help': {'aliases': ['os-help'], 'desc': 'Show this help and command annotations.'},
    'status': {'aliases': ['os-status'], 'desc': 'Quick human-readable node status overview: device ID, transporters, services, core backend.'},
    'id-info': {'aliases': ['os-id-info'], 'desc': 'Show device_id, assigned_id, assignment status, and configured server address.'},
    'log-level': {'aliases': ['os-log-level'], 'desc': 'Adjust os_log verbosity for the current process (--set debug|info|warning|error|critical).'},
    'pipeline-info': {'aliases': ['os-pipeline-info'], 'desc': 'Show pipeline configuration: stage toggles, precision, zero-copy flag, cache state.'},
    'doctor': {'aliases': ['diagnose', 'os-doctor', 'os-diagnose'], 'desc': 'Run diagnostics for environment/config/transporter health and print repair suggestions.'},
}

