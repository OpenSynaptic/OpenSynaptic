import socket

from opensynaptic.utils import os_log, to_wire_payload


def _resolve_cfg(config):
    app_cfg = config.get('application_options', {}) if isinstance(config, dict) else {}
    if isinstance(app_cfg, dict) and app_cfg:
        return app_cfg
    resources = config.get('RESOURCES', {}) if isinstance(config, dict) else {}
    app_map = resources.get('application_config', {}) if isinstance(resources, dict) else {}
    return app_map.get('matter', {}) if isinstance(app_map, dict) else {}


def send(payload, config):
    """Send payload through a simple Matter gateway socket.

    This driver keeps a transport-compatible contract for OpenSynaptic while
    using a lightweight TCP/UDP gateway endpoint on localhost by default.
    """
    matter_cfg = _resolve_cfg(config)
    host = str(matter_cfg.get('host', '127.0.0.1'))
    port = int(matter_cfg.get('port', 5540))
    timeout = float(matter_cfg.get('timeout', 2.0))
    protocol = str(matter_cfg.get('protocol', 'tcp')).strip().lower()

    wire_payload = to_wire_payload(payload, config, force_bytes=True)
    try:
        if protocol == 'udp':
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(timeout)
                sock.sendto(wire_payload, (host, port))
            return True

        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.sendall(wire_payload)
        return True
    except Exception as e:
        os_log.err('MTR', 'SEND', e, {'host': host, 'port': port, 'protocol': protocol})
        return False


def listen(config, callback):
    """Listen on a UDP socket for Matter gateway uplink payloads."""
    matter_cfg = _resolve_cfg(config)
    host = str(matter_cfg.get('listen_host', matter_cfg.get('host', '127.0.0.1')))
    port = int(matter_cfg.get('listen_port', matter_cfg.get('port', 5540)))
    timeout = float(matter_cfg.get('listen_timeout', 1.0))

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            sock.settimeout(timeout)
            os_log.log('MTR', f'Matter UDP listen on {host}:{port}')
            while True:
                try:
                    data, addr = sock.recvfrom(65535)
                except socket.timeout:
                    continue
                if data and callable(callback):
                    callback(data, addr)
    except KeyboardInterrupt:
        os_log.log('MTR', 'Listener interrupted')
    except Exception as e:
        os_log.err('MTR', 'LISTEN', e, {'host': host, 'port': port})

