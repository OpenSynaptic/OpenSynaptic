from opensynaptic.utils.logger import os_log
from opensynaptic.utils.constants import LogMsg

def send(payload, config):
    opts = config.get('transport_options', {}) if isinstance(config, dict) else {}
    os_log.log_with_const('info', LogMsg.UIP_SEND, len=len(payload) if hasattr(payload, '__len__') else 0, addr=opts.get('host') or config.get('Client_Core', {}).get('server_host', '127.0.0.1'))
    return True
