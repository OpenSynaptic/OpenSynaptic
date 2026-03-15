from opensynaptic.utils.logger import os_log
from opensynaptic.utils.buffer import ensure_bytes

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
    send_payload = ensure_bytes(payload)
    client = mqtt.Client(client_id=mqtt_cfg.get('client_id', 'OpenSynapticNode'))
    try:
        client.connect(host, port, 60)
        info = client.publish(topic, send_payload)
        client.disconnect()
        return info.rc == 0
    except Exception as e:
        os_log.err('MQTT', 'IO', e, {'host': host, 'port': port, 'topic': topic})
        return False
