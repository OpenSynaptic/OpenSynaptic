from enum import Enum
from typing import Dict

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
    PLUGIN_CMD = 'PLUGIN_CMD'
    PLUGIN_TEST_START = 'PLUGIN_TEST_START'
    PLUGIN_TEST_RESULT = 'PLUGIN_TEST_RESULT'
    TUI_SECTION = 'TUI_SECTION'
    TUI_INTERACTIVE = 'TUI_INTERACTIVE'

MESSAGES = {LogMsg.READY: 'OpenSynaptic 地基已就緒 | Root: {root}', LogMsg.CONFIG_SAVED: '配置已保存: {field}={value}', LogMsg.TIME_SYNCED: '時間同步成功: server_time={server_time} | {host}:{port}', LogMsg.LIBRARY_INDEXED: '資源庫索引完成: {modules}', LogMsg.LIBRARY_INDEX_FAILED: '資源庫索引失敗: {module}', LogMsg.LIBRARY_SYNCED: '資源庫同步完成: {output}', LogMsg.LIBRARY_SYNC_FAILED: '資源庫同步失敗: {target}', LogMsg.LIBRARY_HEADER_EXPORTED: '協議頭文件已導出: {output}', LogMsg.DRIVER_MOUNT: '驅動掛載 {module} | 來源: {source}', LogMsg.DRIVER_ACTIVATED: '驅動激活 {module} | 狀態: 運行中', LogMsg.DRIVER_SLEEP: '驅動休眠 {module} | 狀態: 已停用', LogMsg.NEW_DRIVER_REGISTERED: "新發現 驅動 '{module}' 已登記至 Config (預設關閉)", LogMsg.PROTOCOL_REFRESHED: '協議已刷新 {layer}:{protocol}', LogMsg.PROTOCOL_INVALIDATED: '協議緩存已失效 {layer}:{protocol}', LogMsg.ID_ASSIGNED: '設備 {addr} → ID={assigned}', LogMsg.ID_RECEIVED: '服務器分配 ID={assigned}', LogMsg.ID_POOL_ISSUED: 'ID 池下發 {addr} → {count} 個 ID', LogMsg.ID_POOL_RECEIVED: 'ID 池收到 {count} 個 ID: {pool}', LogMsg.ID_REQUEST_TIMEOUT: 'ID 申請 超時 ({timeout}s)', LogMsg.SUCCESS_SEND: '發送成功: {info}', LogMsg.FAILED_SEND: '發送失敗: {info}', LogMsg.LORA_CONNECTED: 'LoRa 成功連接至設備: {port}', LogMsg.LORA_CLOSED: 'LoRa 串口已關閉', LogMsg.LORA_SENDING: 'LoRa 正在發射 ({len} Bytes): {hex}', LogMsg.LORA_RESPONSE: 'LoRa 收到回傳: {hex}', LogMsg.LORA_NOT_READY: 'LoRa 發送失敗：串口未就緒。', LogMsg.TEMPLATE_LEARNED: '接收端 學習模板 TID={tid} | src={src} | vars={vars}', LogMsg.CAN_SEND: 'CAN Bus ID:{can_id} 将数据拆分为 {chunks} 帧发送...', LogMsg.IWIP_START: 'lwIP Core 內核啟動: {host}:{port}', LogMsg.IWIP_SEND: 'lwIP Net 已發送 {bytes} bytes 至 {addr}', LogMsg.APP_RECV: 'App Recv 來自 {addr} 的數據: {preview}', LogMsg.RS485_SEND: 'RS485 正在通过 {port} 发送 {len} 字节...', LogMsg.UART_SEND: 'UART 通過 {port} 噴出 {total_len} bytes...', LogMsg.UART_DURATION: 'Physical 預計波特率耗時: {duration:.4f}s', LogMsg.UART_LINE: 'Wire 物理線路上的數據: {preview}', LogMsg.UIP_LISTEN: 'uIP Sim 正在監聽 {host}:{port}...', LogMsg.UIP_SEND: 'uIP Send {len} bytes -> {addr}', LogMsg.UIP_RECV: 'uIP Recv 內容: {received}', LogMsg.RX_SERVER_START: 'UDP Server 啟動成功 | 端口: {port}', LogMsg.RX_SIGNAL_STOP: 'Server 停止信號已接收', LogMsg.RX_PACKET_IN: '接收數據包 {addr} | CMD={cmd} | {size}B', LogMsg.RX_DATA_PACKET: '數據包解析完成: {preview}', LogMsg.RX_CTRL_PACKET: '控制包解析完成: {preview}', LogMsg.RX_RESPONSE_SENT: '回覆已發送 {addr} | {size}B', LogMsg.RX_UNKNOWN_PACKET: '未知指令: {preview}', LogMsg.RX_WORKERS_READY: '分片工作線程就緒: {shards} | 每分片佇列: {queue_size} | 總容量: {capacity}', LogMsg.RX_PERF: '性能統計 recv={received} ok={completed} fail={failed} drop={dropped} backlog={backlog}/{max_backlog} avg={avg_latency_ms}ms max={max_latency_ms}ms pps(in/out)={ingress_pps}/{complete_pps}', LogMsg.RX_FINAL_STATS: '最終統計: {snapshot}', LogMsg.RX_OVERLOAD_DROP: '過載丟包 shard={shard} backlog={backlog} cap={capacity}', LogMsg.RX_WORKER_ERROR: '工作線程錯誤 shard={shard}: {error}', LogMsg.RX_SOCKET_ERROR: '接收錯誤: {error}', LogMsg.CLI_READY: 'CLI 已就緒: {mode}', LogMsg.CLI_ACTION: 'CLI 執行操作: {action}', LogMsg.CLI_RESULT: 'CLI 結果: {result}', LogMsg.TUI_READY: 'TUI 已就緒', LogMsg.TUI_RENDER: 'TUI 畫面已刷新: {section}', LogMsg.LTE_SENDING: '5G/LTE 正在通過高速蜂窩網路發送...', LogMsg.LTE_RESPONSE: '5G 伺服器響應: {res_data}', LogMsg.INJECT_STAGE: '管道注入階段 [{stage}]: {summary}', LogMsg.WATCH_TICK: '[{ts}] 監控模塊 [{module}] 無變化', LogMsg.WATCH_CHANGED: '[{ts}] 監控模塊 [{module}] 狀態變更', LogMsg.DECODE_RESULT: '解碼結果: {result}', LogMsg.TRANSPORTER_TOGGLED: '傳輸器 [{name}] → {state}'}

MESSAGES.update({
    LogMsg.CONFIG_SHOW: 'Config 顯示: {section}',
    LogMsg.CONFIG_GET: 'Config 讀取: {key} = {value}',
    LogMsg.CONFIG_SET: 'Config 設置: {key} = {value}',
    LogMsg.PLUGIN_CMD: '插件指令路由: {plugin}.{sub_cmd}',
    LogMsg.PLUGIN_TEST_START: '測試套件啟動: {plugin} suite={suite}',
    LogMsg.PLUGIN_TEST_RESULT: '測試套件完成: {plugin} suite={suite} ok={ok} fail={fail}',
    LogMsg.TUI_SECTION: 'TUI 區段渲染: {section}',
    LogMsg.TUI_INTERACTIVE: 'TUI 互動模式啟動 interval={interval}s',
})

CLI_HELP_TABLE = {
    'run': {'aliases': ['os-run'], 'desc': '主端持久運行模式。啟動後維持協議管理心跳，直到中斷或達到 --duration。'},
    'snapshot': {'aliases': ['os-snapshot'], 'desc': '輸出當前節點、服務、傳輸器快照 JSON。'},
    'receive': {'aliases': ['os-receive'], 'desc': '啟動 UDP 接收端（服務端接收模式）。'},
    'tui': {'aliases': ['os-tui'], 'desc': '渲染一次 TUI 插件快照。'},
    'time-sync': {'aliases': ['os-time-sync'], 'desc': '向服務端申請時間戳並同步。'},
    'ensure-id': {'aliases': ['os-ensure-id'], 'desc': '向服務端申請設備 ID 並持久化到 Config。'},
    'transmit': {'aliases': ['os-transmit'], 'desc': '打包一次感測器資料並發送。'},
    'reload-protocol': {'aliases': ['os-reload-protocol'], 'desc': '按協議名稱刷新傳輸/物理層適配器。'},
    'plugin-list': {'aliases': ['os-plugin-list'], 'desc': '列出已掛載插件及其運行狀態。'},
    'plugin-load': {'aliases': ['os-plugin-load'], 'desc': '按插件名執行一次載入。'},
    'transport-status': {'aliases': ['os-transport-status'], 'desc': '查看應用/傳輸/物理層狀態與激活情況。'},
    'db-status': {'aliases': ['os-db-status'], 'desc': '查看 db_engine 是否啟用與當前方言。'},
    'inject': {'aliases': ['os-inject'], 'desc': '向指定管道模塊注入感測器數據並顯示各階段輸出 (--module: standardize/compress/fuse/full)。'},
    'decode': {'aliases': ['os-decode'], 'desc': '解碼二進制包 (hex) 或 Base62 壓縮字串，還原為可讀 JSON (--format: hex/b62)。'},
    'watch': {'aliases': ['os-watch'], 'desc': '實時輪詢監控指定模塊的狀態變化 (--module: config/registry/transport/pipeline)。'},
    'transporter-toggle': {'aliases': ['os-transporter-toggle'], 'desc': '在 Config.json 中啟用或禁用傳輸器 (--name <名稱> --enable | --disable)。'},
    'config-show': {'aliases': ['os-config-show'], 'desc': '顯示 Config.json 全部或指定 section (--section <名稱>)。'},
    'config-get': {'aliases': ['os-config-get'], 'desc': '讀取 Config.json 點號路徑的值 (--key a.b.c)。'},
    'config-set': {'aliases': ['os-config-set'], 'desc': '設置 Config.json 點號路徑的值 (--key a.b.c --value <v> [--type int|float|bool|str|json])。'},
    'plugin-cmd': {'aliases': ['os-plugin-cmd'], 'desc': '路由指令到指定插件的 CLI 處理器 (--plugin <名稱> --cmd <子命令> [args...])。'},
    'plugin-test': {'aliases': ['os-plugin-test'], 'desc': '執行測試套件 (--suite component|stress|all [--workers N] [--total N])。'},
    'help': {'aliases': ['os-help'], 'desc': '顯示本幫助（含中文命令註解）。'}
}

