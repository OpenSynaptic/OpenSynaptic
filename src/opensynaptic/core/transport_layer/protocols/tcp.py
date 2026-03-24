import socket
from opensynaptic.utils import (
    os_log,
    to_wire_payload,
)

def send(payload, config):
    opts = config.get('transport_options', {}) if isinstance(config, dict) else {}
    client_cfg = config.get('Client_Core', {})
    ip = opts.get('host') or client_cfg.get('server_host', '127.0.0.1')
    port = int(opts.get('port') or client_cfg.get('server_port', 8888))
    wire = to_wire_payload(payload, config, force_zero_copy=True)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(3.0)
            sock.connect((ip, port))
            sock.sendall(wire)
        return True
    except Exception as exc:
        os_log.err('L4', 'TCP_SEND', exc, {'ip': ip, 'port': port})
        return False


def listen(config, callback):
    """
    Listen for incoming TCP connections and invoke callback for each packet.
    
    Args:
        config: dict with listen_host/listen_port in transport_options
        callback: callable(data, addr) to handle received packets
    
    Returns:
        None (blocking listener)
    """
    opts = config.get('transport_options', {}) if isinstance(config, dict) else {}
    host = opts.get('listen_host', '0.0.0.0')
    port = int(opts.get('listen_port', 8888))
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.listen(5)
        os_log.log('L4', f'TCP listening on {host}:{port}')
        
        while True:
            try:
                conn, addr = sock.accept()
                data = conn.recv(65535)
                if data and callback and callable(callback):
                    callback(data, addr)
                conn.close()
            except KeyboardInterrupt:
                break
            except Exception as e:
                os_log.err('L4', 'TCP_LISTEN', e, {'host': host, 'port': port})
    finally:
        sock.close()

