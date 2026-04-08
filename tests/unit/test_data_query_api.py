"""Unit tests for the data query API (DatabaseManager query methods + HTTP endpoints)."""

import json
import time
import pytest


# ---------------------------------------------------------------------------
# DatabaseManager query methods
# ---------------------------------------------------------------------------

def _make_db():
    """Return an in-memory SQLiteDriver-backed DatabaseManager."""
    from opensynaptic.services.db_engine import DatabaseManager

    db = DatabaseManager(dialect='sqlite', config={'path': ':memory:'})
    db.connect()
    return db


def _seed(db):
    """Insert two packets with two sensors each, belonging to two devices."""
    facts = [
        {'id': 'DEV_A', 's': 'ONLINE', 't': 1710000100, 's1_id': 'TEMP', 's1_s': 'OK', 's1_u': 'Cel', 's1_v': 22.5,
         's2_id': 'HUM', 's2_s': 'OK', 's2_u': '%', 's2_v': 55.0},
        {'id': 'DEV_A', 's': 'ONLINE', 't': 1710000200, 's1_id': 'TEMP', 's1_s': 'OK', 's1_u': 'Cel', 's1_v': 23.1},
        {'id': 'DEV_B', 's': 'WARN',   't': 1710000300, 's1_id': 'PRES', 's1_s': 'LOW', 's1_u': 'Pa',  's1_v': 900.0},
    ]
    for f in facts:
        db.export_fact(f)


def test_query_packets_all():
    db = _make_db()
    _seed(db)
    result = db.query_packets()
    assert result['total'] == 3
    assert len(result['packets']) == 3
    # Ordered by timestamp DESC
    timestamps = [p['timestamp_raw'] for p in result['packets']]
    assert timestamps == sorted(timestamps, reverse=True)


def test_query_packets_filter_device_id():
    db = _make_db()
    _seed(db)
    result = db.query_packets(device_id='DEV_A')
    assert result['total'] == 2
    assert all(p['device_id'] == 'DEV_A' for p in result['packets'])


def test_query_packets_filter_status():
    db = _make_db()
    _seed(db)
    result = db.query_packets(status='WARN')
    assert result['total'] == 1
    assert result['packets'][0]['device_status'] == 'WARN'


def test_query_packets_time_range():
    db = _make_db()
    _seed(db)
    result = db.query_packets(since=1710000150, until=1710000350)
    assert result['total'] == 2


def test_query_packets_pagination():
    db = _make_db()
    _seed(db)
    page1 = db.query_packets(limit=2, offset=0)
    page2 = db.query_packets(limit=2, offset=2)
    assert len(page1['packets']) == 2
    assert len(page2['packets']) == 1
    uuids = {p['packet_uuid'] for p in page1['packets']} | {p['packet_uuid'] for p in page2['packets']}
    assert len(uuids) == 3


def test_query_packet_by_uuid():
    db = _make_db()
    _seed(db)
    all_packets = db.query_packets()
    uuid = all_packets['packets'][0]['packet_uuid']
    result = db.query_packet(uuid)
    assert result is not None
    assert result['packet']['packet_uuid'] == uuid
    assert isinstance(result['sensors'], list)


def test_query_packet_not_found():
    db = _make_db()
    _seed(db)
    result = db.query_packet('00000000-0000-0000-0000-000000000000')
    assert result is None


def test_query_sensors_all():
    db = _make_db()
    _seed(db)
    result = db.query_sensors()
    # DEV_A pkt1: 2 sensors, DEV_A pkt2: 1 sensor, DEV_B pkt1: 1 sensor → total 4
    assert result['total'] == 4


def test_query_sensors_filter_sensor_id():
    db = _make_db()
    _seed(db)
    result = db.query_sensors(sensor_id='TEMP')
    assert result['total'] == 2
    assert all(s['sensor_id'] == 'TEMP' for s in result['sensors'])


def test_query_sensors_filter_device_id():
    db = _make_db()
    _seed(db)
    result = db.query_sensors(device_id='DEV_B')
    assert result['total'] == 1
    assert result['sensors'][0]['device_id'] == 'DEV_B'


def test_query_sensors_pagination():
    db = _make_db()
    _seed(db)
    page1 = db.query_sensors(limit=2, offset=0)
    page2 = db.query_sensors(limit=2, offset=2)
    assert len(page1['sensors']) == 2
    assert len(page2['sensors']) == 2


def test_query_devices():
    db = _make_db()
    _seed(db)
    result = db.query_devices()
    assert result['total'] == 2
    device_ids = {d['device_id'] for d in result['devices']}
    assert device_ids == {'DEV_A', 'DEV_B'}
    for d in result['devices']:
        assert 'last_seen' in d
        assert 'packet_count' in d


def test_query_devices_dev_a_packet_count():
    db = _make_db()
    _seed(db)
    result = db.query_devices()
    counts = {d['device_id']: d['packet_count'] for d in result['devices']}
    assert counts['DEV_A'] == 2
    assert counts['DEV_B'] == 1


# ---------------------------------------------------------------------------
# HTTP endpoint tests (handler-level, no real network)
# ---------------------------------------------------------------------------

class _FakeService:
    """Minimal stub replicating the bits of WebUserService that the handler uses."""

    def __init__(self, db):
        self._db = db

    def _authorize_request(self, headers, write=False, management=False):
        return True, 200, None

    def _json_response(self, handler, code, payload):
        handler._response_code = code
        handler._response_body = payload

    def _get_db_manager(self):
        return self._db


class _FakeHandler:
    def __init__(self, path, query_string=''):
        from urllib.parse import parse_qs, urlparse
        full = path + (('?' + query_string) if query_string else '')
        parsed = urlparse(full)
        self.path = full
        self._parsed_path = parsed.path
        self._parsed_query = parse_qs(parsed.query)
        self.headers = {}
        self._response_code = None
        self._response_body = None


def _call_get(service, path_with_query):
    """Invoke the handler's do_GET logic and return (status_code, body_dict)."""
    from urllib.parse import parse_qs, urlparse
    from opensynaptic.services.web_user.handlers import create_handler

    HandlerClass = create_handler(service)

    # We can't instantiate BaseHTTPRequestHandler directly without a socket,
    # so we patch the do_GET onto a fake request object.
    parsed = urlparse(path_with_query)

    class _Req:
        path = path_with_query
        headers = {}
        _response_code = None
        _response_body = None

    req = _Req()
    # Monkey-patch the handler class methods onto our fake request
    handler = HandlerClass.__new__(HandlerClass)
    handler.path = path_with_query
    handler.headers = {}
    handler._response_code = None
    handler._response_body = None
    HandlerClass.do_GET(handler)
    return handler._response_code, handler._response_body


def test_http_data_packets_no_db():
    """When db is None the endpoint returns 503."""
    from opensynaptic.services.web_user.handlers import create_handler

    class _NoDb:
        def _authorize_request(self, headers, write=False, management=False):
            return True, 200, None
        def _json_response(self, handler, code, payload):
            handler._response_code = code
            handler._response_body = payload
        def _get_db_manager(self):
            return None

    code, body = _call_get(_NoDb(), '/api/data/packets')
    assert code == 503
    assert body['ok'] is False


def test_http_data_packets_returns_list():
    db = _make_db()
    _seed(db)
    svc = _FakeService(db)
    code, body = _call_get(svc, '/api/data/packets')
    assert code == 200
    assert body['ok'] is True
    assert 'packets' in body
    assert body['total'] == 3


def test_http_data_packets_filter():
    db = _make_db()
    _seed(db)
    svc = _FakeService(db)
    code, body = _call_get(svc, '/api/data/packets?device_id=DEV_B')
    assert code == 200
    assert body['total'] == 1


def test_http_data_sensors_returns_list():
    db = _make_db()
    _seed(db)
    svc = _FakeService(db)
    code, body = _call_get(svc, '/api/data/sensors')
    assert code == 200
    assert body['ok'] is True
    assert body['total'] == 4


def test_http_data_devices_returns_list():
    db = _make_db()
    _seed(db)
    svc = _FakeService(db)
    code, body = _call_get(svc, '/api/data/devices')
    assert code == 200
    assert body['total'] == 2


def test_http_data_packet_by_uuid():
    db = _make_db()
    _seed(db)
    svc = _FakeService(db)
    # Get a real uuid first
    _, all_body = _call_get(svc, '/api/data/packets')
    uuid = all_body['packets'][0]['packet_uuid']
    code, body = _call_get(svc, f'/api/data/packets/{uuid}')
    assert code == 200
    assert body['ok'] is True
    assert body['packet']['packet_uuid'] == uuid
    assert isinstance(body['sensors'], list)


def test_http_data_packet_not_found():
    db = _make_db()
    _seed(db)
    svc = _FakeService(db)
    code, body = _call_get(svc, '/api/data/packets/00000000-0000-0000-0000-000000000000')
    assert code == 404
    assert body['ok'] is False
