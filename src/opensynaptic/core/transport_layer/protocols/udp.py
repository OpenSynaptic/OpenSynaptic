import socket
from opensynaptic.utils import (
    os_log,
    as_readonly_view,
)

def send(payload, config):
    opts = config.get('transport_options', {}) if isinstance(config, dict) else {}
    client_cfg = config.get('Client_Core', {})
    ip = opts.get('host') or client_cfg.get('server_host', '127.0.0.1')
    port = int(opts.get('port') or client_cfg.get('server_port', 9999))
    wire = as_readonly_view(payload)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(2.0)
            sock.sendto(wire, (ip, port))
            return True
    except Exception as exc:
        os_log.err('L4', 'UDP_SEND', exc, {'ip': ip, 'port': port})
        return False
