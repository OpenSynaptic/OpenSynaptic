import asyncio
from opensynaptic.utils import os_log, as_readonly_view

def is_supported():
    try:
        import aioquic
        return True
    except Exception:
        return False

def send(payload, config):
    if not is_supported():
        return False
    wire = as_readonly_view(payload)
    opts = config.get('transport_options', {}) if isinstance(config, dict) else {}
    client_cfg = config.get('Client_Core', {}) if isinstance(config, dict) else {}
    host = opts.get('host') or client_cfg.get('server_host', '127.0.0.1')
    port = int(opts.get('port') or client_cfg.get('server_port', 4433))
    timeout_s = float(opts.get('timeout', 2.0))
    insecure = bool(opts.get('insecure', True))
    server_name = opts.get('server_name') or host

    async def _run_once():
        from aioquic.asyncio.client import connect
        from aioquic.quic.configuration import QuicConfiguration
        qconf = QuicConfiguration(is_client=True)
        qconf.verify_mode = 0 if insecure else 2
        async with connect(host, port, configuration=qconf, server_name=server_name, wait_connected=True) as client:
            reader, writer = await client.create_stream()
            writer.write(wire)
            await writer.drain()
            writer.write_eof()
            await writer.drain()
            try:
                await asyncio.wait_for(reader.read(1), timeout=timeout_s)
            except Exception:
                pass
            writer.close()
        return True
    try:
        asyncio.run(_run_once())
        return True
    except Exception as exc:
        os_log.err('L4', 'QUIC_SEND', exc, {'host': host, 'port': port, 'len': len(wire)})
        return False
