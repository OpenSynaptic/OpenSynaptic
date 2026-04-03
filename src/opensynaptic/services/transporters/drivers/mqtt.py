from opensynaptic.utils import (
    os_log,
    to_wire_payload,
)

def send(payload, config):
    try:
        import paho.mqtt.client as mqtt
    except Exception as e:
        os_log.err('MQTT', 'IMPORT', e, {})
        return False
    mqtt_cfg = config.get('application_options', {}) if isinstance(config, dict) else {}
    if not mqtt_cfg:
        mqtt_cfg = config.get('RESOURCES', {}).get('mqtt', {})
    host = mqtt_cfg.get('host', 'broker.hivemq.com')
    port = int(mqtt_cfg.get('port', 1883))
    topic = mqtt_cfg.get('topic', 'os/sensors/raw')
    send_payload = to_wire_payload(payload, config, force_bytes=True)
    client = mqtt.Client(client_id=mqtt_cfg.get('client_id', 'OpenSynapticNode'))
    try:
        client.connect(host, port, 60)
        info = client.publish(topic, send_payload)
        client.disconnect()
        return info.rc == 0
    except Exception as e:
        os_log.err('MQTT', 'IO', e, {'host': host, 'port': port, 'topic': topic})
        return False


def listen(config, callback):
    """
    Listen for incoming MQTT messages.
    
    Args:
        config: dict with MQTT config (host, port, topic)
        callback: callable(data, addr) to handle received packets
    
    Returns:
        None (blocking listener)
    """
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        os_log.err('MQTT', 'LISTEN', 'paho-mqtt not installed', {})
        return
    
    mqtt_cfg = config.get('application_options', {}) if isinstance(config, dict) else {}
    if not mqtt_cfg:
        mqtt_cfg = config.get('RESOURCES', {}).get('mqtt', {})
    
    host = mqtt_cfg.get('host', 'broker.hivemq.com')
    port = int(mqtt_cfg.get('port', 1883))
    topic = mqtt_cfg.get('topic', 'os/sensors/#')
    client_id = mqtt_cfg.get('client_id', 'OpenSynapticNode_RX')
    
    def on_message(client, userdata, msg):
        data = msg.payload
        if data and callback and callable(callback):
            callback(data, (host, port))
    
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            os_log.info('MQTT', 'CONNECT', f'Connected to {host}:{port}, subscribing to {topic}', {'host': host, 'port': port, 'topic': topic})
            client.subscribe(topic)
        else:
            os_log.err('MQTT', 'LISTEN', f'Connection failed with code {rc}', {})
    
    client = mqtt.Client(client_id=client_id)
    client.on_message = on_message
    client.on_connect = on_connect
    
    try:
        os_log.info('MQTT', 'LISTEN_START', f'MQTT listening on {host}:{port}', {'host': host, 'port': port, 'topic': topic})
        client.connect(host, port, 60)
        client.loop_forever()
    except KeyboardInterrupt:
        os_log.info('MQTT', 'LISTEN_STOP', 'Listener interrupted')
    except Exception as e:
        os_log.err('MQTT', 'LISTEN', e, {'host': host, 'port': port, 'topic': topic})
    finally:
        client.disconnect()

