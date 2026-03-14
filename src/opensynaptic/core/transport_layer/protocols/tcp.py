import socket
from opensynaptic.utils.logger import os_log

def send(payload, config):
    opts = config.get('transport_options', {}) if isinstance(config, dict) else {}
    client_cfg = config.get('Client_Core', {})
    ip = opts.get('host') or client_cfg.get('server_host', '127.0.0.1')
    port = int(opts.get('port') or client_cfg.get('server_port', 8888))
    if isinstance(payload, str):
        payload = payload.encode('utf-8')
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(3.0)
            sock.connect((ip, port))
            sock.sendall(payload)
        return True
    except Exception as exc:
        os_log.err('L4', 'TCP_SEND', exc, {'ip': ip, 'port': port})
        return False
