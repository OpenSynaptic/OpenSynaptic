import socket
from opensynaptic.utils import (
    os_log,
    as_readonly_view,
)

def send(payload, config):
    opts = config.get('transport_options', {}) if isinstance(config, dict) else {}
    client_cfg = config.get('Client_Core', {})
    ip = opts.get('host') or client_cfg.get('server_host', '127.0.0.1')
    port = int(opts.get('port') or client_cfg.get('server_port', 8888))
    wire = as_readonly_view(payload)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(3.0)
            sock.connect((ip, port))
            sock.sendall(wire)
        return True
    except Exception as exc:
        os_log.err('L4', 'TCP_SEND', exc, {'ip': ip, 'port': port})
        return False
