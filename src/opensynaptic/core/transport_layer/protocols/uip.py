from opensynaptic.utils import (
    os_log,
    LogMsg,
    payload_len,
)

def send(payload, config):
    opts = config.get('transport_options', {}) if isinstance(config, dict) else {}
    os_log.log_with_const('info', LogMsg.UIP_SEND, len=payload_len(payload), addr=opts.get('host') or config.get('Client_Core', {}).get('server_host', '127.0.0.1'))
    return True
