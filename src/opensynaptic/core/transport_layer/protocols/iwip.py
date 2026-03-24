from opensynaptic.utils import (
    os_log,
    LogMsg,
    payload_len,
)

def send(payload, config):
    opts = config.get('transport_options', {}) if isinstance(config, dict) else {}
    os_log.log_with_const('info', LogMsg.IWIP_SEND, bytes=payload_len(payload), addr=opts.get('host') or config.get('Client_Core', {}).get('server_host', '127.0.0.1'))
    return True


def listen(config, callback):
    """
    Listen for incoming IWIP (lwIP embedded stack) packets.
    
    Args:
        config: dict with listen configuration
        callback: callable(data, addr) to handle received packets
    
    Returns:
        None (blocking listener stub)
    """
    opts = config.get('transport_options', {}) if isinstance(config, dict) else {}
    host = opts.get('listen_host', '127.0.0.1')
    port = int(opts.get('listen_port', 8000))
    os_log.log('L4', f'IWIP listening on {host}:{port} (embedded stack mode)')
    # IWIP embedded stack listener would integrate with lwIP callback system
    # This is a placeholder for full implementation

