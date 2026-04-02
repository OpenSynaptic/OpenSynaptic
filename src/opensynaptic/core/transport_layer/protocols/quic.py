import asyncio
from opensynaptic.utils import os_log, to_wire_payload

def is_supported():
    try:
        import aioquic
        return True
    except Exception:
        return False

def send(payload, config):
    if not is_supported():
        return False
    wire = to_wire_payload(payload, config, force_zero_copy=True)
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

def listen(config, callback):
    """
    Listen for incoming QUIC connections (server mode).
    Requires aioquic library.
    
    Args:
        config: dict with listen_host/listen_port in transport_options
        callback: callable(data, addr) to handle received packets
    
    Returns:
        None (blocking listener)
    """
    if not is_supported():
        os_log.err('L4', 'QUIC_LISTEN', 'aioquic not installed', {})
        return
    
    opts = config.get('transport_options', {}) if isinstance(config, dict) else {}
    host = opts.get('listen_host', '127.0.0.1')
    port = int(opts.get('listen_port', 4433))
    
    async def _listen_once():
        from aioquic.asyncio.server import serve
        from aioquic.quic.configuration import QuicConfiguration
        import ssl
        
        qconf = QuicConfiguration(is_client=False)
        qconf.load_cert_chain(certfile=opts.get('cert_file'), keyfile=opts.get('key_file'))
        
        async def quic_handler(reader, writer):
            data = await reader.read(65535)
            if data and callback and callable(callback):
                callback(data, (host, port))
            writer.close()
        
        try:
            async with serve(host, port, configuration=qconf, stream_handler=quic_handler):
                os_log.info('L4', 'QUIC_LISTEN_START', f'QUIC listening on {host}:{port}', {'host': host, 'port': port})
                await asyncio.sleep(float('inf'))
        except KeyboardInterrupt:
            pass
        except Exception as e:
            os_log.err('L4', 'QUIC_LISTEN', e, {'host': host, 'port': port})
    
    try:
        asyncio.run(_listen_once())
    except Exception as e:
        os_log.err('L4', 'QUIC_INIT', e, {'host': host, 'port': port})
