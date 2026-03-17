from opensynaptic.core.transport_layer import get_transport_layer_manager

def send(payload, config):
    return get_transport_layer_manager().send('tcp', payload, config)

def listen(config, callback):
    port = config.get('Server_Core', {}).get('port', 8888)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('0.0.0.0', port))
        s.listen()
        while True:
            conn, _addr = s.accept()
            with conn:
                data = conn.recv(4096)
                if data:
                    callback(data)
