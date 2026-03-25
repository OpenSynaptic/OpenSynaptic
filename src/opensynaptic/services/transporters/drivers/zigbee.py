import socket

from opensynaptic.utils import os_log, to_wire_payload


def _resolve_cfg(config):
    app_cfg = config.get('application_options', {}) if isinstance(config, dict) else {}
    if isinstance(app_cfg, dict) and app_cfg:
        return app_cfg
    resources = config.get('RESOURCES', {}) if isinstance(config, dict) else {}
    app_map = resources.get('application_config', {}) if isinstance(resources, dict) else {}
    return app_map.get('zigbee', {}) if isinstance(app_map, dict) else {}


def send(payload, config):
    """Send payload through a simple Zigbee gateway socket."""
    zigbee_cfg = _resolve_cfg(config)
    host = str(zigbee_cfg.get('host', '127.0.0.1'))
    port = int(zigbee_cfg.get('port', 6638))
    timeout = float(zigbee_cfg.get('timeout', 2.0))
    protocol = str(zigbee_cfg.get('protocol', 'udp')).strip().lower()

    wire_payload = to_wire_payload(payload, config, force_bytes=True)
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
        os_log.err('ZGB', 'SEND', e, {'host': host, 'port': port, 'protocol': protocol})
        return False


def listen(config, callback):
    """Listen on a UDP socket for Zigbee gateway uplink payloads."""
    zigbee_cfg = _resolve_cfg(config)
    host = str(zigbee_cfg.get('listen_host', zigbee_cfg.get('host', '127.0.0.1')))
    port = int(zigbee_cfg.get('listen_port', zigbee_cfg.get('port', 6638)))
    timeout = float(zigbee_cfg.get('listen_timeout', 1.0))

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            sock.settimeout(timeout)
            os_log.log('ZGB', f'Zigbee UDP listen on {host}:{port}')
            while True:
                try:
                    data, addr = sock.recvfrom(65535)
                except socket.timeout:
                    continue
                if data and callable(callback):
                    callback(data, addr)
    except KeyboardInterrupt:
        os_log.log('ZGB', 'Listener interrupted')
    except Exception as e:
        os_log.err('ZGB', 'LISTEN', e, {'host': host, 'port': port})

