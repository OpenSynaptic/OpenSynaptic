from opensynaptic.utils import (
    os_log,
    LogMsg,
    payload_len,
)

def send(payload, config):
    opts = config.get('transport_options', {}) if isinstance(config, dict) else {}
    os_log.log_with_const('info', LogMsg.UIP_SEND, len=payload_len(payload), addr=opts.get('host') or config.get('Client_Core', {}).get('server_host', '127.0.0.1'))
    return True


def listen(config, callback):
    """
    Listen for incoming UIP (Contiki-NG) simulator packets.
    
    Args:
        config: dict with listen configuration
        callback: callable(data, addr) to handle received packets
    
    Returns:
        None (blocking listener stub)
    """
    opts = config.get('transport_options', {}) if isinstance(config, dict) else {}
    host = opts.get('listen_host', '127.0.0.1')
    port = int(opts.get('listen_port', 6001))
    os_log.info('L4', 'UIP_LISTEN_START', f'UIP listening on {host}:{port} (simulator mode)', {'host': host, 'port': port})
    # UIP simulator listener would integrate with Contiki-NG callback system
    # This is a placeholder for full implementation

