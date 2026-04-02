import socket
from opensynaptic.utils import (
    os_log,
    to_wire_payload,
)

def send(payload, config):
    opts = config.get('transport_options', {}) if isinstance(config, dict) else {}
    client_cfg = config.get('Client_Core', {})
    ip = opts.get('host') or client_cfg.get('server_host', '127.0.0.1')
    port = int(opts.get('port') or client_cfg.get('server_port', 9999))
    wire = to_wire_payload(payload, config, force_zero_copy=True)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(2.0)
            sock.sendto(wire, (ip, port))
            return True
    except Exception as exc:
        os_log.err('L4', 'UDP_SEND', exc, {'ip': ip, 'port': port})
        return False


def listen(config, callback):
    """
    Listen for incoming UDP packets and invoke callback for each packet.
    
    Args:
        config: dict with listen_host/listen_port in transport_options
        callback: callable(data, addr) to handle received packets
    
    Returns:
        None (blocking listener)
    """
    opts = config.get('transport_options', {}) if isinstance(config, dict) else {}
    host = opts.get('listen_host', '0.0.0.0')
    port = int(opts.get('listen_port', 9999))
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((host, port))
        os_log.info('L4', 'UDP_LISTEN_START', f'UDP listening on {host}:{port}', {'host': host, 'port': port})
        
        while True:
            try:
                data, addr = sock.recvfrom(65535)
                if callback and callable(callback):
                    callback(data, addr)
            except KeyboardInterrupt:
                break
            except Exception as e:
                os_log.err('L4', 'UDP_LISTEN', e, {'host': host, 'port': port})
    finally:
        sock.close()

