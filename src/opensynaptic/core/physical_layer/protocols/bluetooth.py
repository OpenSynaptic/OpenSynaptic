import socket

from opensynaptic.utils import os_log, to_wire_payload


def _resolve_opts(config):
    if not isinstance(config, dict):
        return {}
    opts = config.get('physical_options', {})
    if isinstance(opts, dict) and opts:
        return opts
    resources = config.get('RESOURCES', {}) if isinstance(config.get('RESOURCES', {}), dict) else {}
    phy_cfg = resources.get('physical_config', {}) if isinstance(resources.get('physical_config', {}), dict) else {}
    return phy_cfg.get('bluetooth', {}) if isinstance(phy_cfg.get('bluetooth', {}), dict) else {}


def send(payload, config):
    """Send data through a Bluetooth gateway endpoint (UDP/TCP shim)."""
    opts = _resolve_opts(config)
    host = str(opts.get('host', '127.0.0.1'))
    port = int(opts.get('port', 5454))
    timeout = float(opts.get('timeout', 2.0))
    protocol = str(opts.get('protocol', 'udp')).strip().lower()

    wire_payload = to_wire_payload(payload, config)
    try:
        if protocol == 'tcp':
            with socket.create_connection((host, port), timeout=timeout) as sock:
                sock.sendall(wire_payload)
            return True

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sock.sendto(wire_payload, (host, port))
        return True
    except Exception as e:
        os_log.err('PHY', 'BT_SEND', e, {'host': host, 'port': port, 'protocol': protocol})
        return False


def listen(config, callback):
    """Listen for incoming packets from a Bluetooth gateway (UDP shim)."""
    opts = _resolve_opts(config)
    host = str(opts.get('listen_host', opts.get('host', '127.0.0.1')))
    port = int(opts.get('listen_port', opts.get('port', 5454)))
    timeout = float(opts.get('listen_timeout', 1.0))

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            sock.settimeout(timeout)
            os_log.info('PHY', 'BT_LISTEN_START', f'Bluetooth gateway listen on {host}:{port}', {'host': host, 'port': port})
            while True:
                try:
                    data, addr = sock.recvfrom(65535)
                except socket.timeout:
                    continue
                if data and callable(callback):
                    callback(data, addr)
    except KeyboardInterrupt:
        os_log.info('PHY', 'BT_LISTEN_STOP', 'Bluetooth listener interrupted')
    except Exception as e:
        os_log.err('PHY', 'BT_LISTEN', e, {'host': host, 'port': port})

