"""
component_tests.py – Unit tests for individual OpenSynaptic pipeline components.

Run via:
    python -u src/main.py plugin-test --suite component
"""
import sys
import time
import unittest
import tempfile
import shutil
import json
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

# Ensure package is importable when run directly
_ROOT = None
for _p in Path(__file__).resolve().parents:
    if (_p / 'Config.json').exists():
        _ROOT = str(_p)
        break
if _ROOT and str(Path(_ROOT) / 'src') not in sys.path:
    sys.path.insert(0, str(Path(_ROOT) / 'src'))
if _ROOT and _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from opensynaptic.utils import (
    has_native_library,
    EnvironmentMissingError,
)


class TestUtilsEntryPointImports(unittest.TestCase):
    """Unified `opensynaptic.utils` entry-point contract checks."""

    def test_entry_point_exports_basic_symbols(self):
        from opensynaptic import utils as u
        from opensynaptic.utils import (
            Base62Codec,
            LogMsg,
            build_native_all,
            build_guidance,
            get_toolchain_report,
            crc8,
            crc16,
            crc16_ccitt,
            ctx,
            os_log,
            read_json,
            write_json,
        )

        self.assertIn('crc16', getattr(u, '__all__', []))
        self.assertIs(crc16, crc16_ccitt)
        self.assertTrue(callable(read_json))
        self.assertTrue(callable(write_json))
        self.assertTrue(callable(crc8))
        self.assertTrue(callable(Base62Codec))
        self.assertTrue(callable(build_native_all))
        self.assertTrue(callable(build_guidance))
        self.assertTrue(callable(get_toolchain_report))
        self.assertTrue(hasattr(LogMsg, 'READY'))
        self.assertTrue(hasattr(os_log, 'info'))
        self.assertTrue(bool(getattr(ctx, 'root', None)))

    def test_crc16_alias_runtime_parity(self):
        if not has_native_library('os_security'):
            raise unittest.SkipTest('os_security native library is not available')

        from opensynaptic.utils import crc16, crc16_ccitt
        payload = b'OpenSynaptic'
        self.assertEqual(crc16(payload), crc16_ccitt(payload))


class TestCoreManager(unittest.TestCase):
    """Core plugin discovery / symbol resolution."""

    def test_pycore_discovered(self):
        from opensynaptic.core import get_core_manager
        manager = get_core_manager()
        self.assertIn('pycore', manager.available_cores())

    def test_can_resolve_opensynaptic_symbol(self):
        from opensynaptic.core import get_core_manager
        manager = get_core_manager()
        symbol = manager.get_symbol('OpenSynaptic')
        self.assertEqual(symbol.__name__, 'OpenSynaptic')

    def test_rscore_discovered(self):
        from opensynaptic.core import get_core_manager
        manager = get_core_manager()
        self.assertIn('rscore', manager.available_cores())

    def test_rscore_loadable(self):
        from opensynaptic.core import get_core_manager
        manager = get_core_manager()
        plugin = manager.load_core('rscore')
        try:
            self.assertEqual(plugin.get('name'), 'rscore')
            self.assertIn('OpenSynapticEngine', plugin.get('symbols', {}))
        finally:
            manager.load_core('pycore')

    def test_rscore_has_no_direct_pycore_imports(self):
        root = Path(_ROOT) if _ROOT else Path(__file__).resolve().parents[5]
        rscore_dir = root / 'src' / 'opensynaptic' / 'core' / 'rscore'
        py_files = list(rscore_dir.glob('*.py'))
        self.assertTrue(py_files, 'rscore source files not found')
        blocked = 'opensynaptic.core.pycore'
        violations = []
        for file_path in py_files:
            text = file_path.read_text(encoding='utf-8')
            if blocked in text:
                violations.append(str(file_path))
        self.assertFalse(violations, 'rscore has forbidden pycore imports: {}'.format(violations))


# ---------------------------------------------------------------------------
# Base62 Codec
# ---------------------------------------------------------------------------
class TestBase62Codec(unittest.TestCase):
    """Round-trip encoding/decoding tests for Base62Codec."""

    def setUp(self):
        if not has_native_library('os_base62'):
            raise unittest.SkipTest('os_base62 native library is not available')
        from opensynaptic.utils import Base62Codec
        self.codec = Base62Codec(precision=4)

    def test_encode_positive(self):
        encoded = self.codec.encode(12345.6789)
        self.assertIsInstance(encoded, str)
        self.assertTrue(len(encoded) > 0)

    def test_roundtrip_float(self):
        for val in [0.0, 1.0, -1.0, 3.14159, 99999.9999, 0.0001]:
            enc = self.codec.encode(val)
            dec = self.codec.decode(enc)
            self.assertAlmostEqual(val, dec, places=3,
                                   msg=f'Round-trip failed for {val}')

    def test_encode_zero(self):
        enc = self.codec.encode(0)
        dec = self.codec.decode(enc)
        self.assertAlmostEqual(dec, 0.0, places=4)

    def test_negative_values(self):
        enc = self.codec.encode(-42.5)
        dec = self.codec.decode(enc)
        self.assertAlmostEqual(dec, -42.5, places=3)


# ---------------------------------------------------------------------------
# Standardizer
# ---------------------------------------------------------------------------
class TestOpenSynapticStandardizer(unittest.TestCase):
    """Tests for UCUM-based sensor standardization."""

    @classmethod
    def setUpClass(cls):
        from opensynaptic.core import OpenSynapticStandardizer
        cfg = str(Path(_ROOT) / 'Config.json') if _ROOT else None
        cls.std = OpenSynapticStandardizer(cfg)

    def test_standardize_returns_dict(self):
        result = self.std.standardize('DEV_01', 'ONLINE', [['V1', 'OK', 101325.0, 'Pa']])
        self.assertIsInstance(result, dict)

    def test_standardize_has_device_id(self):
        result = self.std.standardize('TEST_DEV', 'ONLINE', [['S1', 'OK', 25.0, 'Cel']])
        # The fact dict should contain device information
        self.assertTrue(len(result) > 0)

    def test_multiple_sensors(self):
        sensors = [['V1', 'OK', 3.14, 'Pa'], ['T1', 'OK', 22.5, 'Cel'], ['H1', 'OK', 60.0, '%']]
        result = self.std.standardize('DEV_MULTI', 'ONLINE', sensors)
        self.assertIsInstance(result, dict)

    def test_standardize_with_timestamp(self):
        t = int(time.time())
        result = self.std.standardize('DEV_TS', 'ONLINE', [['V1', 'OK', 1.0, 'Pa']], t=t)
        self.assertIsInstance(result, dict)


# ---------------------------------------------------------------------------
# Engine (Base62 compression)
# ---------------------------------------------------------------------------
class TestOpenSynapticEngine(unittest.TestCase):
    """Tests for Base62 solidity compress / decompress round-trip."""

    @classmethod
    def setUpClass(cls):
        if not has_native_library('os_base62'):
            raise unittest.SkipTest('os_base62 native library is not available')
        from opensynaptic.core import OpenSynapticStandardizer, OpenSynapticEngine
        cfg = str(Path(_ROOT) / 'Config.json') if _ROOT else None
        std = OpenSynapticStandardizer(cfg)
        cls.engine = OpenSynapticEngine(cfg)
        cls.fact = std.standardize('ENG_TEST', 'ONLINE', [['V1', 'OK', 101325.0, 'Pa']])

    def test_compress_returns_str(self):
        compressed = self.engine.compress(self.fact)
        self.assertIsInstance(compressed, str)
        self.assertTrue(len(compressed) > 0)

    def test_decompress_returns_dict(self):
        compressed = self.engine.compress(self.fact)
        decompressed = self.engine.decompress(compressed)
        self.assertIsInstance(decompressed, dict)

    def test_roundtrip_values_preserved(self):
        compressed = self.engine.compress(self.fact)
        decompressed = self.engine.decompress(compressed)
        # Both should be non-empty dicts
        self.assertTrue(len(self.fact) > 0)
        self.assertTrue(len(decompressed) > 0)


# ---------------------------------------------------------------------------
# OSVisualFusionEngine (binary packet encoding)
# ---------------------------------------------------------------------------
class TestOSVisualFusionEngine(unittest.TestCase):
    """Tests for binary packet encode/decode (FULL / DIFF strategies)."""

    @classmethod
    def setUpClass(cls):
        if not has_native_library('os_base62') or not has_native_library('os_security'):
            raise unittest.SkipTest('required native libraries are not available')
        from opensynaptic.core import OpenSynapticStandardizer, OpenSynapticEngine, OSVisualFusionEngine
        cfg = str(Path(_ROOT) / 'Config.json') if _ROOT else None
        std = OpenSynapticStandardizer(cfg)
        eng = OpenSynapticEngine(cfg)
        cls.fusion = OSVisualFusionEngine(cfg)
        fact = std.standardize('FUS_TEST', 'ONLINE', [['V1', 'OK', 101325.0, 'Pa']])
        compressed = eng.compress(fact)
        cls.raw_input = f'42;{compressed}'

    def test_full_packet_is_bytes(self):
        pkt = self.fusion.run_engine(self.raw_input, strategy='FULL')
        self.assertIsInstance(pkt, (bytes, bytearray))
        self.assertTrue(len(pkt) > 0)

    def test_decompress_full_packet(self):
        pkt = self.fusion.run_engine(self.raw_input, strategy='FULL')
        decoded = self.fusion.decompress(pkt)
        self.assertIsInstance(decoded, dict)

    def test_diff_packet_after_full(self):
        # Generate a template first
        self.fusion.run_engine(self.raw_input, strategy='FULL')
        # DIFF should now be possible
        pkt = self.fusion.run_engine(self.raw_input, strategy='DIFF')
        self.assertIsInstance(pkt, (bytes, bytearray))
        self.assertTrue(len(pkt) > 0)

    def test_run_engine_accepts_bytearray_input(self):
        pkt = self.fusion.run_engine(bytearray(self.raw_input, 'utf-8'), strategy='FULL')
        self.assertIsInstance(pkt, (bytes, bytearray))
        self.assertTrue(len(pkt) > 0)

    def test_decompress_accepts_memoryview_packet(self):
        pkt = self.fusion.run_engine(self.raw_input, strategy='FULL')
        decoded = self.fusion.decompress(memoryview(pkt))
        self.assertIsInstance(decoded, dict)

    def test_relay_accepts_bytearray_packet(self):
        pkt = self.fusion.run_engine(self.raw_input, strategy='FULL')
        relayed = self.fusion.relay(bytearray(pkt))
        self.assertIsInstance(relayed, (bytes, bytearray))
        self.assertTrue(len(relayed) > 0)


# ---------------------------------------------------------------------------
# Plugin test end-to-end pipeline
# ---------------------------------------------------------------------------
class TestPluginE2EPipeline(unittest.TestCase):
    """End-to-end checks for standardize -> compress -> fuse -> dispatch flow."""

    def setUp(self):
        if not has_native_library('os_base62') or not has_native_library('os_security'):
            raise unittest.SkipTest('required native libraries are not available')
        if not _ROOT:
            raise unittest.SkipTest('project root with Config.json is not available')

        from opensynaptic.core.pycore.core import OpenSynaptic

        self.tmp_dir = tempfile.mkdtemp()
        self.config_path = Path(self.tmp_dir) / 'Config.json'
        src_cfg = Path(_ROOT) / 'Config.json'
        cfg = json.loads(src_cfg.read_text(encoding='utf-8'))
        cfg.setdefault('engine_settings', {})['core_backend'] = 'pycore'
        cfg['assigned_id'] = 42
        self.config_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=4), encoding='utf-8')

        self.node = OpenSynaptic(config_path=str(self.config_path))
        self.node.assigned_id = 42
        self.node.config['assigned_id'] = 42
        self.node._sync_assigned_id_to_fusion()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_e2e_standardize_compress_fuse_transmit(self):
        packet, aid, strategy = self.node.transmit(
            sensors=[['V1', 'OK', 101325.0, 'Pa']],
            device_status='ONLINE',
        )
        self.assertIsInstance(packet, (bytes, bytearray))
        self.assertGreater(len(packet), 0)
        self.assertEqual(aid, 42)
        self.assertIn(strategy, {'FULL_PACKET', 'DIFF_PACKET'})

    def test_e2e_dispatch_transport_send_success(self):
        class _FakeUDPDriver:
            def __init__(self):
                self.calls = []

            def send(self, payload, config):
                self.calls.append((payload, config))
                return True

        packet, aid, _ = self.node.transmit(
            sensors=[['V1', 'OK', 12.34, 'Pa']],
            device_status='ONLINE',
        )
        self.assertEqual(aid, 42)

        fake_driver = _FakeUDPDriver()
        self.node.transporter_manager = SimpleNamespace(get_driver=lambda medium: None)
        self.node.active_transporters['udp'] = fake_driver

        ok = self.node.dispatch(packet, medium='UDP')
        self.assertTrue(ok)
        self.assertEqual(len(fake_driver.calls), 1)

        sent_payload, sent_config = fake_driver.calls[0]
        self.assertEqual(bytes(sent_payload), bytes(packet))
        self.assertIs(sent_config, self.node.config)


# ---------------------------------------------------------------------------
# IDAllocator
# ---------------------------------------------------------------------------
class TestIDAllocator(unittest.TestCase):
    """Tests for the ID pool allocator."""

    @classmethod
    def setUpClass(cls):
        import tempfile
        from plugins.id_allocator import IDAllocator
        cls.tmp_dir = tempfile.mkdtemp()
        cls.allocator = IDAllocator(base_dir=cls.tmp_dir, start_id=1000, end_id=2000)

    def test_allocate_returns_int(self):
        id_val = self.allocator.allocate_id({'test': True})
        self.assertIsInstance(id_val, int)
        self.assertGreaterEqual(id_val, 1000)

    def test_allocate_unique_ids(self):
        ids = [self.allocator.allocate_id() for _ in range(10)]
        self.assertEqual(len(ids), len(set(ids)))

    def test_release_holds_id_during_lease(self):
        id_val = self.allocator.allocate_id({'device_id': 'lease-test-a'})
        self.assertTrue(self.allocator.is_allocated(id_val))
        released = self.allocator.release_id(id_val)
        self.assertTrue(released)
        # Different device should not immediately reuse an offline-held ID.
        new_id = self.allocator.allocate_id({'device_id': 'lease-test-b'})
        self.assertNotEqual(new_id, id_val)

    def test_reconnect_reuses_id_within_lease(self):
        id_val = self.allocator.allocate_id({'device_id': 'stable-reconnect'})
        self.assertTrue(self.allocator.release_id(id_val))
        new_id = self.allocator.allocate_id({'device_id': 'stable-reconnect'})
        self.assertEqual(new_id, id_val)

    def test_release_and_reuse_immediate(self):
        id_val = self.allocator.allocate_id({'device_id': 'immediate-release'})
        self.assertTrue(self.allocator.release_id(id_val, immediate=True))
        new_id = self.allocator.allocate_id({'device_id': 'another-device'})
        self.assertEqual(new_id, id_val)

    def test_stats(self):
        stats = self.allocator.stats()
        self.assertIn('total_allocated', stats)
        self.assertIn('range', stats)

    def test_pool_allocation(self):
        pool = self.allocator.allocate_pool(5)
        self.assertEqual(len(pool), 5)
        self.assertEqual(len(set(pool)), 5)


class TestEnvGuardService(unittest.TestCase):
    """Checks env_guard local JSON lifecycle and issue capture."""

    def setUp(self):
        from opensynaptic.services.env_guard.main import EnvironmentGuardService
        self.tmp_dir = tempfile.mkdtemp()
        cfg = {
            'RESOURCES': {
                'service_plugins': {
                    'env_guard': {
                        'auto_start': False,
                        'auto_install': False,
                        'resource_library_json_path': 'data/env_guard/resources.json',
                        'status_json_path': 'data/env_guard/status.json',
                    },
                },
            },
        }
        node = SimpleNamespace(base_dir=self.tmp_dir, config=cfg)
        self.svc = EnvironmentGuardService(node=node)

    def tearDown(self):
        self.svc.close()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_start_creates_json_files(self):
        self.svc.start()
        status_path = Path(self.tmp_dir) / 'data' / 'env_guard' / 'status.json'
        resources_path = Path(self.tmp_dir) / 'data' / 'env_guard' / 'resources.json'
        self.assertTrue(status_path.exists())
        self.assertTrue(resources_path.exists())
        data = json.loads(status_path.read_text(encoding='utf-8'))
        self.assertIn('resource_library_json_path', data)

    def test_environment_error_updates_status(self):
        self.svc.start()
        exc = EnvironmentMissingError(
            message='No compiler detected',
            missing_kind='compiler',
            resource='toolchain',
        )
        self.svc._on_error({
            'error': exc,
            'payload': {
                'eid': 'PRECHECK_ENV_MISSING',
                'mid': 'NATIVE',
                'category': 'environment_missing',
                'error_type': 'EnvironmentMissingError',
            },
        })
        status_path = Path(self.tmp_dir) / 'data' / 'env_guard' / 'status.json'
        data = json.loads(status_path.read_text(encoding='utf-8'))
        self.assertEqual(data.get('issues_total'), 1)
        self.assertEqual(data.get('issues', [])[0].get('environment', {}).get('missing_kind'), 'compiler')

    def test_auto_install_uses_resource_commands(self):
        self.svc.config['auto_install'] = True
        self.svc.start()

        resources_path = Path(self.tmp_dir) / 'data' / 'env_guard' / 'resources.json'
        resources = json.loads(resources_path.read_text(encoding='utf-8'))
        resources['resources']['compiler']['toolchain']['commands'] = ['echo env-guard-auto-install']
        resources_path.write_text(json.dumps(resources, indent=2, ensure_ascii=False), encoding='utf-8')

        self.svc._run_shell_command = staticmethod(lambda command: {
            'ok': True,
            'command': command,
            'return_code': 0,
            'stdout': 'mock-ok',
            'stderr': '',
            'ts': round(time.time(), 3),
        })

        exc = EnvironmentMissingError(
            message='No compiler detected',
            missing_kind='compiler',
            resource='toolchain',
        )
        self.svc._on_error({
            'error': exc,
            'payload': {
                'eid': 'PRECHECK_ENV_MISSING',
                'mid': 'NATIVE',
                'category': 'environment_missing',
                'error_type': 'EnvironmentMissingError',
            },
        })

        deadline = time.time() + 2.0
        attempts = []
        while time.time() < deadline:
            payload = self.svc._status_payload()
            attempts = list(payload.get('attempts', []))
            if attempts:
                break
            time.sleep(0.05)
        self.assertTrue(attempts)
        self.assertEqual(attempts[0].get('command'), 'echo env-guard-auto-install')


class TestWebUserAdminService(unittest.TestCase):
    """Checks web_user management entry behavior."""

    def setUp(self):
        from opensynaptic.services import ServiceManager
        from opensynaptic.services.web_user import WebUserService

        self.tmp_dir = tempfile.mkdtemp()
        self.save_calls = 0
        cfg = {
            'engine_settings': {'core_backend': 'pycore', 'precision': 4},
            'RESOURCES': {
                'application_status': {'mqtt': False},
                'transport_status': {'udp': True},
                'physical_status': {'uart': False},
                'transporters_status': {'udp': True},
                'service_plugins': {
                    'web_user': {
                        'enabled': True,
                        'auto_start': True,
                        'host': '127.0.0.1',
                        'port': 0,
                        'management_enabled': True,
                        'auth_enabled': False,
                        'admin_token': '',
                        'read_only': False,
                        'writable_config_prefixes': ['engine_settings', 'RESOURCES.service_plugins'],
                    },
                },
            },
        }
        node = SimpleNamespace(
            base_dir=self.tmp_dir,
            config=cfg,
            device_id='UT-DEVICE',
            assigned_id=1001,
            active_transporters={},
        )
        node._save_config = self._on_save
        node.service_manager = ServiceManager(config=cfg, mode='runtime')
        self.svc = WebUserService(node=node)

    def tearDown(self):
        self.svc.stop()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _on_save(self):
        self.save_calls += 1

    def _http_get_json(self, path):
        if not self.svc.status().get('running'):
            self.svc.start(host='127.0.0.1', port=0)
        port = int(self.svc._server.server_address[1])
        req = urllib.request.Request('http://127.0.0.1:{}{}'.format(port, path), method='GET')
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            body = resp.read().decode('utf-8')
            return int(resp.status), json.loads(body or '{}')

    def _http_put_json(self, path, payload):
        if not self.svc.status().get('running'):
            self.svc.start(host='127.0.0.1', port=0)
        port = int(self.svc._server.server_address[1])
        req = urllib.request.Request(
            'http://127.0.0.1:{}{}'.format(port, path),
            data=json.dumps(payload).encode('utf-8'),
            method='PUT',
            headers={'Content-Type': 'application/json'},
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            body = resp.read().decode('utf-8')
            return int(resp.status), json.loads(body or '{}')

    def _http_post_json(self, path, payload):
        if not self.svc.status().get('running'):
            self.svc.start(host='127.0.0.1', port=0)
        port = int(self.svc._server.server_address[1])
        req = urllib.request.Request(
            'http://127.0.0.1:{}{}'.format(port, path),
            data=json.dumps(payload).encode('utf-8'),
            method='POST',
            headers={'Content-Type': 'application/json'},
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            body = resp.read().decode('utf-8')
            return int(resp.status), json.loads(body or '{}')

    def test_auto_load_starts_when_auto_start_enabled(self):
        self.svc.auto_load()
        self.assertTrue(self.svc.status().get('running'))

    def test_dashboard_contains_management_sections(self):
        dashboard = self.svc.build_dashboard()
        self.assertIn('identity', dashboard)
        self.assertIn('plugins', dashboard)
        self.assertIn('transport', dashboard)
        self.assertIn('pipeline', dashboard)
        self.assertIn('users', dashboard)

    def test_http_management_and_display_endpoints_are_healthy(self):
        endpoints = [
            '/api/health',
            '/api/display/providers',
            '/api/display/all',
            '/api/dashboard',
            '/api/plugins',
            '/api/transport',
        ]
        for endpoint in endpoints:
            status, payload = self._http_get_json(endpoint)
            self.assertEqual(status, 200, msg='endpoint={} payload={}'.format(endpoint, payload))
        status, providers = self._http_get_json('/api/display/providers')
        self.assertEqual(status, 200)
        self.assertTrue(providers.get('ok'))
        metadata = providers.get('metadata', {})
        self.assertGreaterEqual(int(metadata.get('total_providers', 0) or 0), 1)

    def test_display_provider_metadata_includes_render_mode(self):
        _status, providers = self._http_get_json('/api/display/providers')
        metadata = providers.get('metadata', {}) if isinstance(providers, dict) else {}
        rows = metadata.get('providers', []) if isinstance(metadata, dict) else []
        self.assertTrue(rows)
        first = rows[0] if rows else {}
        self.assertIn('render_mode', first)
        self.assertIn(first.get('render_mode'), ('safe_html', 'trusted_html', 'json_only'))

    def test_display_render_endpoint_returns_render_mode(self):
        _status, providers = self._http_get_json('/api/display/providers')
        metadata = providers.get('metadata', {}) if isinstance(providers, dict) else {}
        rows = metadata.get('providers', []) if isinstance(metadata, dict) else []
        self.assertTrue(rows)
        section_path = rows[0].get('section_path')
        self.assertTrue(section_path)
        status, payload = self._http_get_json('/api/display/render/{}?format=json'.format(section_path))
        self.assertEqual(status, 200)
        self.assertTrue(payload.get('ok'))
        self.assertIn('render_mode', payload)
        self.assertIn(payload.get('render_mode'), ('safe_html', 'trusted_html', 'json_only'))

    def test_plugin_config_schema_and_update_api(self):
        status, schema_payload = self._http_get_json('/api/plugins/config?plugin=web_user&only_writable=1')
        self.assertEqual(status, 200)
        self.assertTrue(schema_payload.get('ok'))
        schema = schema_payload.get('schema', {})
        cats = schema.get('categories', []) if isinstance(schema, dict) else []
        self.assertTrue(cats)

        status, update_payload = self._http_put_json('/api/plugins/config', {
            'plugin': 'web_user',
            'updates': [
                {
                    'key': 'RESOURCES.service_plugins.web_user.ui_compact',
                    'value_type': 'bool',
                    'value': True,
                }
            ],
        })
        self.assertEqual(status, 200)
        self.assertTrue(update_payload.get('ok'))
        self.assertTrue(
            self.svc.node.config.get('RESOURCES', {}).get('service_plugins', {}).get('web_user', {}).get('ui_compact')
        )

    def test_plugin_config_update_blocks_out_of_scope_keys(self):
        status, payload = self._http_put_json('/api/plugins/config', {
            'plugin': 'web_user',
            'updates': [
                {'key': 'engine_settings.precision', 'value_type': 'int', 'value': 9},
            ],
        })
        self.assertEqual(status, 200)
        self.assertFalse(payload.get('ok'))
        failed = payload.get('failed', [])
        self.assertTrue(failed)

    def test_plugin_commands_metadata_and_execute(self):
        class _DummyPlugin:
            def get_cli_commands(self):
                return {'ping': lambda argv: 0 if argv == ['ok'] else 1}

            def get_cli_completions(self):
                return {'ping': 'health check'}

        self.svc.node.service_manager.mount('dummy', _DummyPlugin(), config={'enabled': True}, mode='runtime')
        status, meta = self._http_get_json('/api/plugins/commands?plugin=dummy')
        self.assertEqual(status, 200)
        self.assertTrue(meta.get('ok'))
        commands = meta.get('commands', [])
        self.assertTrue(any((row or {}).get('name') == 'ping' for row in commands))

        status, out = self._http_post_json('/api/plugins', {
            'plugin': 'dummy',
            'action': 'cmd',
            'sub_cmd': 'ping',
            'args': ['ok'],
        })
        self.assertEqual(status, 200)
        self.assertTrue(out.get('ok'))
        self.assertEqual(int(out.get('exit_code', 1)), 0)

    def test_plugin_visual_schema_endpoint(self):
        status, payload = self._http_get_json('/api/plugins/visual-schema?plugin=test_plugin')
        self.assertEqual(status, 200)
        self.assertTrue(payload.get('ok'))
        self.assertIn('sections', payload)
        self.assertIsInstance(payload.get('sections', []), list)

    def test_plugin_cmd_action_dispatches_to_service_manager(self):
        class _DummyPlugin:
            def get_cli_commands(self):
                return {'ping': lambda argv: 0 if argv == ['ok'] else 1}

        self.svc.node.service_manager.mount('dummy', _DummyPlugin(), config={'enabled': True}, mode='runtime')
        ok, payload = self.svc._run_plugin_action('dummy', 'cmd', sub_cmd='ping', args=['ok'])
        self.assertTrue(ok)
        self.assertEqual(payload.get('exit_code'), 0)

    def test_plugin_cmd_action_stringifies_non_string_args(self):
        class _DummyPlugin:
            def get_cli_commands(self):
                return {
                    'echo': lambda argv: 0 if argv == ['123', 'True'] else 1,
                }

        self.svc.node.service_manager.mount('dummy_cast', _DummyPlugin(), config={'enabled': True}, mode='runtime')
        ok, payload = self.svc._run_plugin_action('dummy_cast', 'cmd', sub_cmd='echo', args=[123, True])
        self.assertTrue(ok)
        self.assertEqual(int(payload.get('exit_code', 1)), 0)

    def test_read_only_and_auth_guards_and_config_write_whitelist(self):
        self.svc.node.config['RESOURCES']['service_plugins']['web_user']['read_only'] = True
        self.svc.node.config['RESOURCES']['service_plugins']['web_user']['auth_enabled'] = True
        self.svc.node.config['RESOURCES']['service_plugins']['web_user']['admin_token'] = 'secret'
        self.svc._refresh_settings()

        ok, code, _ = self.svc._authorize_request({}, write=True, management=True)
        self.assertFalse(ok)
        self.assertEqual(code, 403)

        self.svc.node.config['RESOURCES']['service_plugins']['web_user']['read_only'] = False
        self.svc._refresh_settings()
        ok, code, _ = self.svc._authorize_request({}, write=False, management=True)
        self.assertFalse(ok)
        self.assertEqual(code, 401)
        ok, code, _ = self.svc._authorize_request({'X-Admin-Token': 'secret'}, write=True, management=True)
        self.assertTrue(ok)
        self.assertEqual(code, 200)

        allowed, _payload = self.svc._config_set_payload('assigned_id', 10, value_type='int')
        self.assertFalse(allowed)

        allowed, payload = self.svc._config_set_payload('engine_settings.precision', 6, value_type='int')
        self.assertTrue(allowed)
        self.assertEqual(payload.get('new'), 6)
        self.assertGreaterEqual(self.save_calls, 1)

    def test_option_schema_and_batch_updates_are_typed(self):
        schema = self.svc.build_option_schema(only_writable=True)
        categories = schema.get('categories', [])
        self.assertTrue(categories)
        all_fields = []
        for cat in categories:
            all_fields.extend(cat.get('fields', []))
        keys = {item.get('key'): item for item in all_fields}
        self.assertIn('engine_settings.precision', keys)
        self.assertEqual(keys['engine_settings.precision'].get('type'), 'int')

        ok, out = self.svc.apply_option_updates([
            {'key': 'engine_settings.precision', 'value': '7', 'value_type': 'int'},
            {'key': 'RESOURCES.service_plugins.web_user.ui_compact', 'value': 'true', 'value_type': 'bool'},
        ])
        self.assertTrue(ok)
        self.assertTrue(out.get('ok'))
        self.assertEqual(self.svc.node.config.get('engine_settings', {}).get('precision'), 7)
        self.assertTrue(self.svc.node.config.get('RESOURCES', {}).get('service_plugins', {}).get('web_user', {}).get('ui_compact'))

    def test_cli_commands_include_option_management(self):
        cmds = self.svc.get_cli_commands()
        self.assertIn('cli', cmds)
        self.assertIn('options-schema', cmds)
        self.assertIn('options-set', cmds)
        self.assertIn('options-apply', cmds)

    def test_control_cli_executes_opensynaptic_cli_bridge(self):
        self.svc._run_opensynaptic_cli_tokens = lambda tokens: (0, 'ok-out', '')
        ok, out = self.svc.execute_control_cli('status')
        self.assertTrue(ok)
        self.assertEqual(out.get('exit_code'), 0)
        self.assertEqual(out.get('stdout'), 'ok-out')

    def test_os_cli_job_and_metrics_ingest(self):
        def _fake_runner(tokens):
            _ = tokens
            self.svc._ingest_cli_output_line('{"run_stats":{"status":"idle","uptime_s":60,"packets_processed":0,"avg_packet_latency_ms":0.0,"tick_errors":0}}')
            self.svc._ingest_cli_output_line('00:43:22 [INFO] OS: Performance stats recv=0 ok=0 fail=0 drop=0 backlog=0/0 avg=0.0ms max=0.0ms pps(in/out)=0.0/0.0')
            return (
                0,
                '{"run_stats":{"status":"idle","uptime_s":60,"packets_processed":0,"avg_packet_latency_ms":0.0,"tick_errors":0}}\n'
                '00:43:22 [INFO] OS: Performance stats recv=0 ok=0 fail=0 drop=0 backlog=0/0 avg=0.0ms max=0.0ms pps(in/out)=0.0/0.0\n',
                '',
            )

        self.svc._run_opensynaptic_cli_tokens = _fake_runner
        ok, payload = self.svc.submit_os_cli_job('status', background=False)
        self.assertTrue(ok)
        job = payload.get('job', {})
        self.assertEqual(job.get('status'), 'succeeded')

        metrics = self.svc.get_overview_metrics()
        run = metrics.get('run_stats', {})
        perf = metrics.get('performance_stats', {})
        self.assertEqual(run.get('status'), 'idle')
        self.assertEqual(run.get('uptime_s'), 60)
        self.assertEqual(perf.get('recv'), 0)
        self.assertEqual(perf.get('ok'), 0)


# ---------------------------------------------------------------------------
# RSCore native library (Rust DLL)
# ---------------------------------------------------------------------------
class TestRscore(unittest.TestCase):
    """Tests for the Rust-compiled os_rscore native library."""

    @classmethod
    def setUpClass(cls):
        from opensynaptic.core.rscore.codec import has_rs_native
        if not has_rs_native():
            raise unittest.SkipTest(
                'os_rscore DLL not found. '
                'Build it with: python -u src/opensynaptic/core/rscore/build_rscore.py'
            )

    # ------------------------------------------------------------------
    # has_rs_native / version
    # ------------------------------------------------------------------
    def test_has_rs_native_returns_true(self):
        from opensynaptic.core.rscore.codec import has_rs_native
        self.assertTrue(has_rs_native())

    def test_rs_version_non_empty(self):
        from opensynaptic.core.rscore.codec import rs_version
        ver = rs_version()
        self.assertIsInstance(ver, str)
        self.assertTrue(len(ver) > 0)
        self.assertIn('rscore', ver)

    # ------------------------------------------------------------------
    # RsBase62Codec encode / decode round-trips
    # ------------------------------------------------------------------
    def test_rs_codec_encode_positive(self):
        from opensynaptic.core.rscore.codec import RsBase62Codec
        codec = RsBase62Codec(precision=4)
        enc = codec.encode(12345.6789)
        self.assertIsInstance(enc, str)
        self.assertTrue(len(enc) > 0)

    def test_rs_codec_roundtrip(self):
        from opensynaptic.core.rscore.codec import RsBase62Codec
        codec = RsBase62Codec(precision=4)
        for val in [0.0, 1.0, -1.0, 3.14159, 99999.9999, 0.0001, -42.5]:
            enc = codec.encode(val)
            dec = codec.decode(enc)
            self.assertAlmostEqual(val, dec, places=3,
                                   msg='Rust round-trip failed for {}'.format(val))

    def test_rs_codec_zero(self):
        from opensynaptic.core.rscore.codec import RsBase62Codec
        codec = RsBase62Codec(precision=4)
        enc = codec.encode(0)
        dec = codec.decode(enc)
        self.assertAlmostEqual(dec, 0.0, places=4)

    # ------------------------------------------------------------------
    # Parity: Rust codec must produce identical output to the C codec
    # ------------------------------------------------------------------
    def test_rs_codec_parity_with_c_codec(self):
        if not has_native_library('os_base62'):
            raise unittest.SkipTest('os_base62 C library not available for parity check')
        from opensynaptic.utils import Base62Codec
        from opensynaptic.core.rscore.codec import RsBase62Codec
        c_codec = Base62Codec(precision=4)
        rs_codec = RsBase62Codec(precision=4)
        for val in [0.0, 1.0, -1.0, 42.0, 3.14159, 99999.9999, 0.0001, -42.5, 1234567.89]:
            c_enc = c_codec.encode(val)
            rs_enc = rs_codec.encode(val)
            self.assertEqual(c_enc, rs_enc,
                             msg='Encode parity failed for {}: C={!r} Rust={!r}'.format(val, c_enc, rs_enc))
            c_dec = c_codec.decode(c_enc)
            rs_dec = rs_codec.decode(rs_enc)
            self.assertAlmostEqual(c_dec, rs_dec, places=7,
                                   msg='Decode parity failed for {}'.format(val))

    # ------------------------------------------------------------------
    # CMD helpers
    # ------------------------------------------------------------------
    def test_cmd_is_data_true_for_data_cmds(self):
        from opensynaptic.core.rscore.codec import cmd_is_data
        from opensynaptic.core.pycore.handshake import CMD
        for cmd_val in CMD.DATA_CMDS:
            self.assertTrue(cmd_is_data(cmd_val),
                            msg='cmd_is_data should be True for cmd={}'.format(cmd_val))

    def test_cmd_is_data_false_for_ctrl_cmds(self):
        from opensynaptic.core.rscore.codec import cmd_is_data
        from opensynaptic.core.pycore.handshake import CMD
        for cmd_val in CMD.CTRL_CMDS:
            self.assertFalse(cmd_is_data(cmd_val),
                             msg='cmd_is_data should be False for ctrl cmd={}'.format(cmd_val))

    def test_cmd_normalize_data_secure_to_plain(self):
        from opensynaptic.core.rscore.codec import cmd_normalize_data
        from opensynaptic.core.pycore.handshake import CMD
        for sec, base in CMD.BASE_DATA_CMD.items():
            self.assertEqual(cmd_normalize_data(sec), base,
                             msg='normalize_data({}) expected {} got {}'.format(
                                 sec, base, cmd_normalize_data(sec)))

    def test_cmd_secure_variant_plain_to_secure(self):
        from opensynaptic.core.rscore.codec import cmd_secure_variant
        from opensynaptic.core.pycore.handshake import CMD
        for plain, sec in CMD.SECURE_DATA_CMD.items():
            self.assertEqual(cmd_secure_variant(plain), sec,
                             msg='secure_variant({}) expected {} got {}'.format(
                                 plain, sec, cmd_secure_variant(plain)))

    # ------------------------------------------------------------------
    # Packet header parser (Rust fast-path)
    # ------------------------------------------------------------------
    def test_parse_packet_header_valid(self):
        from opensynaptic.core.rscore.codec import has_header_parser, parse_packet_header
        if not has_header_parser():
            raise unittest.SkipTest('os_parse_header_min symbol is not available in loaded os_rscore DLL')
        from opensynaptic.core.pycore.standardization import OpenSynapticStandardizer
        from opensynaptic.core.pycore.solidity import OpenSynapticEngine
        from opensynaptic.core.pycore.unified_parser import OSVisualFusionEngine

        cfg = str(Path(_ROOT) / 'Config.json') if _ROOT else None
        std = OpenSynapticStandardizer(cfg)
        eng = OpenSynapticEngine(cfg)
        fus = OSVisualFusionEngine(cfg)
        fact = std.standardize('RS_HDR', 'ONLINE', [['V1', 'OK', 101325.0, 'Pa']])
        compressed = eng.compress(fact)
        pkt = fus.run_engine('42;{}'.format(compressed), strategy='FULL')

        meta = parse_packet_header(pkt)
        self.assertIsInstance(meta, dict)
        self.assertTrue(meta.get('crc16_ok'))
        self.assertEqual(meta.get('cmd'), 63)
        self.assertEqual(meta.get('base_cmd'), 63)
        self.assertEqual(meta.get('source_aid'), int(getattr(fus, 'local_id', 0)))

    def test_parse_packet_header_crc_mismatch(self):
        from opensynaptic.core.rscore.codec import has_header_parser, parse_packet_header
        if not has_header_parser():
            raise unittest.SkipTest('os_parse_header_min symbol is not available in loaded os_rscore DLL')
        from opensynaptic.core.pycore.standardization import OpenSynapticStandardizer
        from opensynaptic.core.pycore.solidity import OpenSynapticEngine
        from opensynaptic.core.pycore.unified_parser import OSVisualFusionEngine

        cfg = str(Path(_ROOT) / 'Config.json') if _ROOT else None
        std = OpenSynapticStandardizer(cfg)
        eng = OpenSynapticEngine(cfg)
        fus = OSVisualFusionEngine(cfg)
        fact = std.standardize('RS_HDR_BAD', 'ONLINE', [['V1', 'OK', 3.14, 'Pa']])
        compressed = eng.compress(fact)
        pkt = bytearray(fus.run_engine('42;{}'.format(compressed), strategy='FULL'))
        pkt[-1] ^= 0x01

        meta = parse_packet_header(pkt)
        self.assertIsInstance(meta, dict)
        self.assertFalse(meta.get('crc16_ok'))

    def test_parse_packet_header_short_packet(self):
        from opensynaptic.core.rscore.codec import has_header_parser, parse_packet_header
        if not has_header_parser():
            raise unittest.SkipTest('os_parse_header_min symbol is not available in loaded os_rscore DLL')
        self.assertIsNone(parse_packet_header(b'\x01\x02\x03'))

    # ------------------------------------------------------------------
    # Input auto-decompose fast-path (Rust)
    # ------------------------------------------------------------------
    def test_auto_decompose_available(self):
        from opensynaptic.core.rscore.codec import has_auto_decompose
        self.assertTrue(has_auto_decompose())

    def test_auto_decompose_parity_with_pycore(self):
        from opensynaptic.core.rscore.codec import has_auto_decompose, auto_decompose_input
        if not has_auto_decompose():
            raise unittest.SkipTest('os_auto_decompose_input symbol is not available in loaded os_rscore DLL')
        from opensynaptic.core.pycore.standardization import OpenSynapticStandardizer
        from opensynaptic.core.pycore.solidity import OpenSynapticEngine
        from opensynaptic.core.pycore.unified_parser import OSVisualFusionEngine

        cfg = str(Path(_ROOT) / 'Config.json') if _ROOT else None
        std = OpenSynapticStandardizer(cfg)
        eng = OpenSynapticEngine(cfg)
        fus = OSVisualFusionEngine(cfg)
        fact = std.standardize('RS_DECOMP', 'ONLINE', [['V1', 'OK', 101325.0, 'Pa']])
        compressed = eng.compress(fact)
        raw_input = '42;{}'.format(compressed)

        py_decomp = fus._auto_decompose(raw_input)
        rs_decomp = auto_decompose_input(raw_input)

        self.assertIsNotNone(py_decomp)
        self.assertIsNotNone(rs_decomp)
        self.assertEqual(py_decomp[0], rs_decomp[0])
        self.assertEqual(py_decomp[1], rs_decomp[1])
        self.assertEqual(py_decomp[2], rs_decomp[2])

    def test_auto_decompose_accepts_memoryview(self):
        from opensynaptic.core.rscore.codec import has_auto_decompose, auto_decompose_input
        if not has_auto_decompose():
            raise unittest.SkipTest('os_auto_decompose_input symbol is not available in loaded os_rscore DLL')
        sample = memoryview(b'42;DEV.OK.AQIDBA|V1>OK.Pa:abc|')
        out = auto_decompose_input(sample)
        self.assertIsInstance(out, tuple)
        self.assertEqual(len(out), 3)

    def test_solidity_compressor_available(self):
        from opensynaptic.core.rscore.codec import has_solidity_compressor
        self.assertTrue(has_solidity_compressor())

    def test_fusion_state_available(self):
        from opensynaptic.core.rscore.codec import has_fusion_state
        self.assertTrue(has_fusion_state())

    # ------------------------------------------------------------------
    # rscore plugin metadata
    # ------------------------------------------------------------------
    def test_rscore_plugin_rs_native_flag_true(self):
        from opensynaptic.core import get_core_manager
        plugin = get_core_manager().load_core('rscore')
        try:
            self.assertTrue(plugin.get('rs_native'),
                            msg='CORE_PLUGIN.rs_native should be True when DLL is loaded')
            self.assertIn('rs_auto_decompose', plugin)
            self.assertIn('rs_solidity_compressor', plugin)
            self.assertIn('rs_fusion_state', plugin)
        finally:
            get_core_manager().load_core('pycore')

    # ------------------------------------------------------------------
    # CRC helpers (Rust vs C parity)
    # ------------------------------------------------------------------
    def test_rs_crc_helpers_available(self):
        """has_crc_helpers() must be True when the new DLL is loaded."""
        from opensynaptic.core.rscore.codec import has_crc_helpers
        self.assertTrue(has_crc_helpers(),
                        msg='os_crc8 + os_crc16_ccitt_pub should be exported by current DLL')

    def test_rs_crc8_known_vectors(self):
        """CRC-8 must match known-good values."""
        from opensynaptic.core.rscore.codec import has_crc_helpers, rs_crc8
        if not has_crc_helpers():
            raise unittest.SkipTest('CRC helpers not available in loaded DLL')
        # CRC-8(poly=7, init=0) for b'' must be 0
        self.assertEqual(rs_crc8(b''), 0)
        # CRC-8 of b'\x00' with poly=7, init=0 = 0
        self.assertEqual(rs_crc8(b'\x00'), 0)
        # Verify non-trivial value is consistent (deterministic)
        v1 = rs_crc8(b'OpenSynaptic')
        v2 = rs_crc8(b'OpenSynaptic')
        self.assertEqual(v1, v2)
        self.assertIsInstance(v1, int)
        self.assertGreaterEqual(v1, 0)
        self.assertLessEqual(v1, 255)

    def test_rs_crc8_parity_with_c(self):
        """Rust CRC-8 must produce the same result as the C implementation."""
        from opensynaptic.core.rscore.codec import has_crc_helpers, rs_crc8
        if not has_crc_helpers():
            raise unittest.SkipTest('CRC helpers not available in loaded DLL')
        from opensynaptic.utils import crc8 as c_crc8
        for payload in [b'', b'\x00', b'hello', b'OpenSynaptic', bytes(range(256))]:
            rs_val = rs_crc8(payload)
            c_val = c_crc8(payload)
            self.assertEqual(rs_val, c_val,
                             msg='CRC8 parity failed for payload={!r}: Rust={} C={}'.format(
                                 payload[:16], rs_val, c_val))

    def test_rs_crc16_known_vectors(self):
        """CRC-16/CCITT must match known-good values."""
        from opensynaptic.core.rscore.codec import has_crc_helpers, rs_crc16_ccitt
        if not has_crc_helpers():
            raise unittest.SkipTest('CRC helpers not available in loaded DLL')
        # CRC-16/CCITT(b'') with init=0xFFFF = 0xFFFF
        self.assertEqual(rs_crc16_ccitt(b''), 0xFFFF)
        v1 = rs_crc16_ccitt(b'OpenSynaptic')
        v2 = rs_crc16_ccitt(b'OpenSynaptic')
        self.assertEqual(v1, v2)
        self.assertIsInstance(v1, int)
        self.assertGreaterEqual(v1, 0)
        self.assertLessEqual(v1, 0xFFFF)

    def test_rs_crc16_parity_with_c(self):
        """Rust CRC-16/CCITT must produce the same result as the C implementation."""
        from opensynaptic.core.rscore.codec import has_crc_helpers, rs_crc16_ccitt
        if not has_crc_helpers():
            raise unittest.SkipTest('CRC helpers not available in loaded DLL')
        from opensynaptic.utils import crc16_ccitt as c_crc16
        for payload in [b'', b'\x00', b'hello', b'OpenSynaptic', bytes(range(256))]:
            rs_val = rs_crc16_ccitt(payload)
            c_val = c_crc16(payload)
            self.assertEqual(rs_val, c_val,
                             msg='CRC16 parity failed for payload={!r}: Rust={} C={}'.format(
                                 payload[:16], rs_val, c_val))


# ---------------------------------------------------------------------------
# RSCore hybrid engine (compress/decompress parity vs pycore)
# ---------------------------------------------------------------------------
class TestRscoreEngine(unittest.TestCase):
    """Verify the rscore OpenSynapticEngine uses RsBase62Codec and produces
    output that round-trips identically to the pycore engine."""

    @classmethod
    def setUpClass(cls):
        if not has_native_library('os_base62'):
            raise unittest.SkipTest('os_base62 C library not available')
        from opensynaptic.core.rscore.codec import has_rs_native
        if not has_rs_native():
            raise unittest.SkipTest('os_rscore Rust DLL not available')

        from opensynaptic.core.pycore.standardization import OpenSynapticStandardizer
        from opensynaptic.core.pycore.solidity import OpenSynapticEngine as PyEngine
        from opensynaptic.core.rscore.api import OpenSynapticEngine as RsEngine

        cfg = str(Path(_ROOT) / 'Config.json') if _ROOT else None
        std = OpenSynapticStandardizer(cfg)
        cls.py_engine = PyEngine(cfg)
        cls.rs_engine = RsEngine(cfg)
        cls.fact = std.standardize('RS_ENG_TEST', 'ONLINE', [['V1', 'OK', 101325.0, 'Pa']])

    # ------------------------------------------------------------------
    def test_rs_engine_codec_is_rust(self):
        """RsEngine.codec should be RsBase62Codec when Rust DLL is present."""
        from opensynaptic.core.rscore.codec import RsBase62Codec
        self.assertIsInstance(self.rs_engine.codec, RsBase62Codec,
                              msg='Expected RsBase62Codec but got {}'.format(
                                  type(self.rs_engine.codec).__name__))

    def test_rs_engine_precision_preserved(self):
        """The Rust codec must use the same precision as the C codec."""
        self.assertEqual(
            self.py_engine.codec.precision_val,
            self.rs_engine.codec.precision_val,
            msg='precision_val mismatch: C={} Rust={}'.format(
                self.py_engine.codec.precision_val,
                self.rs_engine.codec.precision_val),
        )

    def test_rs_engine_solidity_fast_path_active(self):
        """RsEngine should attach a Rust solidity compressor when the symbol is available."""
        from opensynaptic.core.rscore.codec import has_solidity_compressor
        if not has_solidity_compressor():
            raise unittest.SkipTest('Rust solidity compressor symbol not available')
        self.assertIsNotNone(getattr(self.rs_engine, '_rs_solidity', None))

    def test_rs_solidity_direct_parity(self):
        """The direct Rust compressor helper must match pycore compress() exactly."""
        from opensynaptic.core.rscore.codec import has_solidity_compressor
        if not has_solidity_compressor():
            raise unittest.SkipTest('Rust solidity compressor symbol not available')
        py_out = self.py_engine.compress(self.fact)
        rs_out = self.rs_engine._rs_solidity.compress(self.fact)
        self.assertEqual(py_out, rs_out)

    def test_compress_output_identical(self):
        """compress() must produce identical strings for both engines."""
        py_out = self.py_engine.compress(self.fact)
        rs_out = self.rs_engine.compress(self.fact)
        self.assertEqual(py_out, rs_out,
                         msg='compress() output differs:\n  pycore: {}\n  rscore: {}'.format(
                             py_out, rs_out))

    def test_decompress_round_trip(self):
        """decompress(compress(fact)) must return a non-empty dict for rscore."""
        compressed = self.rs_engine.compress(self.fact)
        decompressed = self.rs_engine.decompress(compressed)
        self.assertIsInstance(decompressed, dict)
        self.assertTrue(len(decompressed) > 0)

    def test_cross_engine_interop(self):
        """pycore compress → rscore decompress and vice versa must work."""
        py_compressed = self.py_engine.compress(self.fact)
        rs_decoded = self.rs_engine.decompress(py_compressed)
        self.assertIsInstance(rs_decoded, dict)
        self.assertTrue(len(rs_decoded) > 0)

        rs_compressed = self.rs_engine.compress(self.fact)
        py_decoded = self.py_engine.decompress(rs_compressed)
        self.assertIsInstance(py_decoded, dict)
        self.assertTrue(len(py_decoded) > 0)

    def test_multi_sensor_parity(self):
        """Multi-sensor facts compress identically on both engines."""
        from opensynaptic.core.pycore.standardization import OpenSynapticStandardizer
        cfg = str(Path(_ROOT) / 'Config.json') if _ROOT else None
        std = OpenSynapticStandardizer(cfg)
        fact = std.standardize(
            'RS_MULTI', 'ONLINE',
            [['V1', 'OK', 3.14, 'Pa'], ['T1', 'OK', 22.5, 'Cel'], ['H1', 'OK', 60.0, '%']],
        )
        py_out = self.py_engine.compress(fact)
        rs_out = self.rs_engine.compress(fact)
        self.assertEqual(py_out, rs_out)

    def test_compress_optional_fields_parity(self):
        """Rust solidity compressor must preserve geohash/url/msg formatting exactly."""
        fact = dict(self.fact)
        fact['geohash'] = 'wx4g0ec1'
        fact['url'] = 'https://example.com/device/42'
        fact['msg'] = 'hello-rscore'
        py_out = self.py_engine.compress(fact)
        rs_out = self.rs_engine.compress(fact)
        self.assertEqual(py_out, rs_out)

    def test_rs_solidity_direct_optional_fields_parity(self):
        """The direct Rust compressor helper must preserve optional fields exactly."""
        from opensynaptic.core.rscore.codec import has_solidity_compressor
        if not has_solidity_compressor():
            raise unittest.SkipTest('Rust solidity compressor symbol not available')
        fact = dict(self.fact)
        fact['geohash'] = 'wx4g0ec1'
        fact['url'] = 'https://example.com/device/42'
        fact['msg'] = 'hello-rscore'
        py_out = self.py_engine.compress(fact)
        rs_out = self.rs_engine._rs_solidity.compress(fact)
        self.assertEqual(py_out, rs_out)

    def test_stress_summary_reports_rust_backend(self):
        """Stress summary should report requested backend and active Rust codec."""
        from opensynaptic.services.test_plugin.stress_tests import run_stress
        _, summary = run_stress(
            total=20,
            workers=1,
            sources=2,
            progress=False,
            core_name='rscore',
            expect_core='rscore',
            expect_codec_class='RsBase62Codec',
            config_path=str(Path(_ROOT) / 'Config.json') if _ROOT else None,
        )
        self.assertEqual(summary.get('requested_core'), 'rscore')
        self.assertEqual(summary.get('core_backend'), 'rscore')
        self.assertEqual(summary.get('codec_class'), 'RsBase62Codec')

    def test_require_rust_rejects_pycore_runtime(self):
        """Hard validation must fail when require_rust=True but runtime is pycore/C codec."""
        from opensynaptic.services.test_plugin.stress_tests import run_stress
        with self.assertRaises(RuntimeError) as cm:
            run_stress(
                total=10,
                workers=1,
                sources=2,
                progress=False,
                core_name='pycore',
                expect_core='pycore',
                expect_codec_class='RsBase62Codec',
                config_path=str(Path(_ROOT) / 'Config.json') if _ROOT else None,
            )
        self.assertIn('codec expectation failed', str(cm.exception))

    def test_header_probe_summary_fields(self):
        """Header probe mode should publish probe summary fields without backend coupling."""
        from opensynaptic.services.test_plugin.stress_tests import run_stress
        _, summary = run_stress(
            total=30,
            workers=1,
            sources=2,
            progress=False,
            core_name='pycore',
            expect_core='pycore',
            header_probe_rate=1.0,
            config_path=str(Path(_ROOT) / 'Config.json') if _ROOT else None,
        )
        hp = summary.get('header_probe')
        self.assertIsInstance(hp, dict)
        self.assertTrue(hp.get('enabled'))
        self.assertGreaterEqual(int(hp.get('attempted', 0)), 0)
        self.assertIn('parser_available', hp)

    def test_rscore_node_fusion_is_rust(self):
        """OpenSynaptic (rscore) must have an rscore OSVisualFusionEngine as self.fusion."""
        from opensynaptic.core.rscore.api import OpenSynaptic as RsNode
        from opensynaptic.core.rscore.api import OSVisualFusionEngine as RsFusion
        cfg = str(Path(_ROOT) / 'Config.json') if _ROOT else None
        node = RsNode(cfg)
        self.assertIsInstance(
            node.fusion, RsFusion,
            msg='node.fusion must be rscore.OSVisualFusionEngine, got {}'.format(
                type(node.fusion).__name__),
        )

    def test_rscore_node_transmit_uses_rust_path(self):
        """Transmit via rscore node must succeed and return bytes (integration smoke)."""
        from opensynaptic.core.rscore.api import OpenSynaptic as RsNode
        cfg = str(Path(_ROOT) / 'Config.json') if _ROOT else None
        node = RsNode(cfg)
        # Temporarily assign a valid ID so transmit does not raise
        node.assigned_id = 42
        node._sync_assigned_id_to_fusion()
        pkt, aid, strategy = node.transmit(
            sensors=[['V1', 'OK', 101325.0, 'Pa']],
            device_id='RSCORE_SMOKE',
        )
        self.assertIsInstance(pkt, (bytes, bytearray))
        self.assertGreater(len(pkt), 0)
        self.assertEqual(int(aid), 42)


# ---------------------------------------------------------------------------
# Full-load config helper
# ---------------------------------------------------------------------------
class TestFullLoadConfig(unittest.TestCase):
    """Unit tests for get_full_load_config() auto-CPU-detection helper."""

    def test_returns_required_keys(self):
        from opensynaptic.services.test_plugin.stress_tests import get_full_load_config
        cfg = get_full_load_config()
        for key in ('processes', 'threads_per_process', 'workers', 'batch_size', 'cpu_count'):
            self.assertIn(key, cfg, msg='Missing key: {}'.format(key))

    def test_all_values_positive(self):
        from opensynaptic.services.test_plugin.stress_tests import get_full_load_config
        cfg = get_full_load_config()
        for key, val in cfg.items():
            self.assertGreater(int(val), 0, msg='{}={} must be > 0'.format(key, val))

    def test_cpu_count_matches_os(self):
        import os
        from opensynaptic.services.test_plugin.stress_tests import get_full_load_config
        cfg = get_full_load_config()
        expected_cpu = max(1, os.cpu_count() or 4)
        self.assertEqual(cfg['cpu_count'], expected_cpu)

    def test_workers_hint_overrides_processes(self):
        from opensynaptic.services.test_plugin.stress_tests import get_full_load_config
        cfg = get_full_load_config(workers_hint=3)
        self.assertEqual(cfg['processes'], 3)

    def test_threads_hint_overrides_tpp(self):
        from opensynaptic.services.test_plugin.stress_tests import get_full_load_config
        cfg = get_full_load_config(threads_hint=7)
        self.assertEqual(cfg['threads_per_process'], 7)
        self.assertEqual(cfg['workers'], 7)

    def test_batch_hint_overrides_batch(self):
        from opensynaptic.services.test_plugin.stress_tests import get_full_load_config
        cfg = get_full_load_config(batch_hint=256)
        self.assertEqual(cfg['batch_size'], 256)

    def test_default_batch_is_128(self):
        from opensynaptic.services.test_plugin.stress_tests import get_full_load_config
        cfg = get_full_load_config()
        self.assertEqual(cfg['batch_size'], 128)

    def test_threads_per_process_zero_uses_workers_in_hybrid_mode(self):
        from opensynaptic.services.test_plugin.stress_tests import run_stress

        _, summary = run_stress(
            total=20,
            workers=4,
            sources=2,
            progress=False,
            core_name='pycore',
            config_path=str(Path(_ROOT) / 'Config.json') if _ROOT else None,
            processes=2,
            threads_per_process=0,
        )
        self.assertEqual(int(summary.get('processes', 0) or 0), 2)
        self.assertEqual(int(summary.get('threads_per_process', 0) or 0), 4)


class TestStressAutoProfile(unittest.TestCase):

    @staticmethod
    def _mk_summary(throughput, fail=0, avg=1.0, p95=1.5, p99=None, p99_9=None, p99_99=None, ok=20, total=20, max_lat=2.0):
        p99 = p95 if p99 is None else p99
        p99_9 = p95 if p99_9 is None else p99_9
        p99_99 = p95 if p99_99 is None else p99_99
        return {
            'total': total,
            'ok': ok,
            'fail': fail,
            'throughput_pps': throughput,
            'avg_latency_ms': avg,
            'p95_latency_ms': p95,
            'p99_latency_ms': p99,
            'p99_9_latency_ms': p99_9,
            'p99_99_latency_ms': p99_99,
            'max_latency_ms': max_lat,
        }

    def test_aggregate_series_includes_tail_latency_means(self):
        from opensynaptic.services.test_plugin import stress_tests

        aggregate = stress_tests._aggregate_series([
            self._mk_summary(100.0, p95=1.1, p99=1.4, p99_9=1.8, p99_99=2.2),
            self._mk_summary(120.0, p95=1.3, p99=1.7, p99_9=2.0, p99_99=2.5),
        ])

        self.assertIn('p99_latency_ms_mean', aggregate)
        self.assertIn('p99_9_latency_ms_mean', aggregate)
        self.assertIn('p99_99_latency_ms_mean', aggregate)
        self.assertEqual(aggregate['p99_latency_ms_mean'], 1.55)
        self.assertEqual(aggregate['p99_9_latency_ms_mean'], 1.9)
        self.assertEqual(aggregate['p99_99_latency_ms_mean'], 2.35)

    def test_metrics_helpers_handle_latency_fallback_and_header_probe_rollup(self):
        from opensynaptic.services.test_plugin.metrics import (
            aggregate_header_probe,
            summary_latency_values,
        )

        summary = {
            'avg_latency_ms': 1.0,
            'p95_latency_ms': 2.0,
            # p99/p99_9/p99_99 intentionally omitted to validate fallback.
        }
        lat = summary_latency_values(summary)
        self.assertEqual(lat['avg_latency_ms'], 1.0)
        self.assertEqual(lat['p95_latency_ms'], 2.0)
        self.assertEqual(lat['p99_latency_ms'], 2.0)
        self.assertEqual(lat['p99_9_latency_ms'], 2.0)
        self.assertEqual(lat['p99_99_latency_ms'], 2.0)

        hp = aggregate_header_probe([
            {'header_probe': {'attempted': 10, 'parsed': 8, 'crc16_ok': 7}},
            {'header_probe': {'attempted': 5, 'parsed': 4, 'crc16_ok': 4}},
            {'header_probe': None},
        ])
        self.assertEqual(hp['attempted'], 15)
        self.assertEqual(hp['parsed'], 12)
        self.assertEqual(hp['crc16_ok'], 11)
        self.assertEqual(hp['parse_hit_rate'], 0.8)
        self.assertEqual(hp['crc16_ok_rate'], 0.7333)

    def test_auto_profile_selects_highest_throughput_when_all_zero_fail(self):
        from opensynaptic.services.test_plugin import stress_tests

        side_effect = [
            (SimpleNamespace(fail=0), self._mk_summary(100.0, fail=0)),
            (SimpleNamespace(fail=0), self._mk_summary(220.0, fail=0)),
            (SimpleNamespace(fail=0), self._mk_summary(210.0, fail=0, total=100, ok=100)),
            (SimpleNamespace(fail=0), self._mk_summary(205.0, fail=0, total=100, ok=100)),
        ]
        with patch.object(stress_tests, 'run_stress', side_effect=side_effect):
            report = stress_tests.run_auto_profile(
                total=100,
                workers=8,
                sources=2,
                profile_total=20,
                profile_runs=1,
                final_runs=2,
                process_candidates=[1, 2],
                thread_candidates=[4],
                batch_candidates=[64],
                default_batch_size=64,
                progress=False,
            )

        best_cfg = report.get('best', {}).get('config', {})
        self.assertEqual(best_cfg.get('processes'), 2)
        self.assertEqual(best_cfg.get('threads_per_process'), 4)
        self.assertEqual(best_cfg.get('batch_size'), 64)
        final_agg = report.get('final', {}).get('aggregate', {})
        self.assertEqual(final_agg.get('runs'), 2)
        self.assertEqual(final_agg.get('fail'), 0)

    def test_auto_profile_prefers_zero_fail_candidate(self):
        from opensynaptic.services.test_plugin import stress_tests

        side_effect = [
            (SimpleNamespace(fail=1), self._mk_summary(300.0, fail=1, ok=19)),
            (SimpleNamespace(fail=0), self._mk_summary(250.0, fail=0)),
            (SimpleNamespace(fail=0), self._mk_summary(245.0, fail=0, total=100, ok=100)),
        ]
        with patch.object(stress_tests, 'run_stress', side_effect=side_effect):
            report = stress_tests.run_auto_profile(
                total=100,
                workers=8,
                sources=2,
                profile_total=20,
                profile_runs=1,
                final_runs=1,
                process_candidates=[1, 2],
                thread_candidates=[4],
                batch_candidates=[64],
                default_batch_size=64,
                progress=False,
            )

        best_cfg = report.get('best', {}).get('config', {})
        self.assertEqual(best_cfg.get('processes'), 2)
        self.assertEqual(report.get('final', {}).get('aggregate', {}).get('fail'), 0)


# ---------------------------------------------------------------------------
# RSCore OSVisualFusionEngine (Rust header fast-path)
# ---------------------------------------------------------------------------
class TestRscoreFusionEngine(unittest.TestCase):
    """Verify rscore OSVisualFusionEngine uses Rust header fast-path on decompress."""

    @classmethod
    def setUpClass(cls):
        if not has_native_library('os_base62') or not has_native_library('os_security'):
            raise unittest.SkipTest('required native libraries not available')
        from opensynaptic.core.rscore.codec import has_rs_native
        if not has_rs_native():
            raise unittest.SkipTest('os_rscore DLL not available')

        from opensynaptic.core.pycore.standardization import OpenSynapticStandardizer
        from opensynaptic.core.pycore.solidity import OpenSynapticEngine
        from opensynaptic.core.rscore.api import OSVisualFusionEngine as RsFusion
        from opensynaptic.core.pycore.unified_parser import OSVisualFusionEngine as PyFusion

        cfg_src = Path(_ROOT) / 'Config.json' if _ROOT else None
        cls._tmp_dir = tempfile.mkdtemp(prefix='rs_fusion_component_')
        cfg = str(Path(cls._tmp_dir) / 'Config.json')
        if cfg_src and cfg_src.exists():
            data = json.loads(cfg_src.read_text(encoding='utf-8'))
        else:
            data = {}
        resources = data.setdefault('RESOURCES', {})
        resources['registry'] = str(Path(cls._tmp_dir) / 'device_registry')
        Path(resources['registry']).mkdir(parents=True, exist_ok=True)
        Path(cfg).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        cls.cfg_path = cfg
        std = OpenSynapticStandardizer(cfg)
        eng = OpenSynapticEngine(cfg)
        cls.rs_fusion = RsFusion(cfg)
        cls.py_fusion = PyFusion(cfg)

        fact = std.standardize('RS_FUS', 'ONLINE', [['V1', 'OK', 101325.0, 'Pa']])
        compressed = eng.compress(fact)
        cls.raw_input = '42;{}'.format(compressed)
        # Build a canonical FULL packet using pycore as reference
        cls.pkt_full = cls.py_fusion.run_engine(cls.raw_input, strategy='FULL')

    @classmethod
    def tearDownClass(cls):
        tmp_dir = getattr(cls, '_tmp_dir', None)
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Rust header parser activation
    # ------------------------------------------------------------------
    def test_rs_header_parser_active(self):
        """_rs_parse_header must be populated when Rust DLL has os_parse_header_min."""
        from opensynaptic.core.rscore.codec import has_header_parser
        if not has_header_parser():
            raise unittest.SkipTest('os_parse_header_min not exported by loaded DLL')
        self.assertIsNotNone(
            self.rs_fusion._rs_parse_header,
            msg='_rs_parse_header should be set when os_parse_header_min is available',
        )

    def test_rs_auto_decompose_active(self):
        """_rs_auto_decompose must be populated when Rust DLL has os_auto_decompose_input."""
        from opensynaptic.core.rscore.codec import has_auto_decompose
        if not has_auto_decompose():
            raise unittest.SkipTest('os_auto_decompose_input not exported by loaded DLL')
        self.assertIsNotNone(
            self.rs_fusion._rs_auto_decompose,
            msg='_rs_auto_decompose should be set when os_auto_decompose_input is available',
        )

    def test_rs_fusion_state_active(self):
        """_rs_fusion_state must be populated when Rust DLL has os_fusion_state_* ABI."""
        from opensynaptic.core.rscore.codec import has_fusion_state
        if not has_fusion_state():
            raise unittest.SkipTest('os_fusion_state_* not exported by loaded DLL')
        self.assertIsNotNone(
            self.rs_fusion._rs_fusion_state,
            msg='_rs_fusion_state should be set when os_fusion_state_* is available',
        )

    # ------------------------------------------------------------------
    # Decompress: valid packet
    # ------------------------------------------------------------------
    def test_decompress_valid_packet(self):
        decoded = self.rs_fusion.decompress(self.pkt_full)
        self.assertIsInstance(decoded, dict)
        self.assertNotIn('error', decoded, msg='Valid packet must not produce error key')

    def test_decompress_full_seeds_rs_fusion_state(self):
        """Receiving a FULL packet should seed native fusion state for that source AID."""
        from opensynaptic.core.rscore.codec import has_fusion_state
        from opensynaptic.core.rscore.codec import parse_packet_header
        if not has_fusion_state():
            raise unittest.SkipTest('native fusion state ABI not available')
        fusion = type(self.rs_fusion)(self.cfg_path)
        decoded = fusion.decompress(self.pkt_full)
        self.assertNotIn('error', decoded)
        meta = parse_packet_header(self.pkt_full) or {}
        self.assertIn(int(meta.get('source_aid', -1)), getattr(fusion, '_rs_seeded_aids', set()))

    def test_decompress_parity_with_pycore(self):
        """rscore decompress must produce the same result dict as pycore for a valid packet."""
        py_dec = self.py_fusion.decompress(self.pkt_full)
        rs_dec = self.rs_fusion.decompress(self.pkt_full)
        # Both must be non-error dicts
        self.assertNotIn('error', py_dec)
        self.assertNotIn('error', rs_dec)
        # Core payload keys must be present in both
        for k in py_dec:
            if k.startswith('__'):
                continue  # skip meta-keys
            self.assertIn(k, rs_dec, msg='key {!r} missing from rscore result'.format(k))

    def test_decompress_heart_parity_with_pycore(self):
        """After a FULL learn, HEART receive should match pycore output."""
        cfg = self.cfg_path
        py_fusion = type(self.py_fusion)(cfg)
        rs_fusion = type(self.rs_fusion)(cfg)
        py_fusion.run_engine(self.raw_input, strategy='FULL')
        rs_fusion.run_engine(self.raw_input, strategy='FULL')
        heart_pkt = rs_fusion.run_engine(self.raw_input, strategy='DIFF')
        py_fusion.decompress(self.pkt_full)
        rs_fusion.decompress(self.pkt_full)
        py_dec = py_fusion.decompress(heart_pkt)
        rs_dec = rs_fusion.decompress(heart_pkt)
        self.assertEqual(py_dec.get('id'), rs_dec.get('id'))
        self.assertEqual(py_dec.get('s1_v'), rs_dec.get('s1_v'))

    def test_decompress_diff_parity_with_pycore(self):
        """After a FULL learn, DIFF receive with changed values should match pycore output."""
        from opensynaptic.core.pycore.standardization import OpenSynapticStandardizer
        from opensynaptic.core.pycore.solidity import OpenSynapticEngine
        cfg = self.cfg_path
        std = OpenSynapticStandardizer(cfg)
        eng = OpenSynapticEngine(cfg)
        fact = std.standardize('RS_FUS', 'ONLINE', [['V1', 'OK', 101326.0, 'Pa']])
        changed_input = '42;{}'.format(eng.compress(fact))
        py_fusion = type(self.py_fusion)(cfg)
        rs_fusion = type(self.rs_fusion)(cfg)
        py_fusion.run_engine(self.raw_input, strategy='FULL')
        rs_fusion.run_engine(self.raw_input, strategy='FULL')
        diff_pkt = py_fusion.run_engine(changed_input, strategy='DIFF')
        py_dec = py_fusion.decompress(diff_pkt)
        rs_dec = rs_fusion.decompress(diff_pkt)
        self.assertEqual(py_dec, rs_dec)

    def test_decompress_memoryview_input(self):
        """decompress must accept memoryview input."""
        decoded = self.rs_fusion.decompress(memoryview(self.pkt_full))
        self.assertIsInstance(decoded, dict)
        self.assertNotIn('error', decoded)

    # ------------------------------------------------------------------
    # Decompress: corrupt packet – fast rejection via Rust
    # ------------------------------------------------------------------
    def test_decompress_corrupt_crc16_rejected(self):
        """Corrupt CRC16 must be caught and returned as an error dict."""
        corrupt = bytearray(self.pkt_full)
        corrupt[-1] ^= 0xFF  # flip last CRC16 byte
        result = self.rs_fusion.decompress(bytes(corrupt))
        self.assertIsInstance(result, dict)
        meta = result.get('__packet_meta__', {})
        self.assertFalse(
            meta.get('crc16_ok', True),
            msg='CRC16 mismatch must be surfaced in __packet_meta__',
        )

    def test_decompress_corrupt_short_packet(self):
        """A 4-byte packet (too short) must not crash."""
        result = self.rs_fusion.decompress(b'\x3f\x01\x00\x00')
        self.assertIsInstance(result, dict)

    # ------------------------------------------------------------------
    # run_engine delegated to pycore path
    # ------------------------------------------------------------------
    def test_run_engine_full_strategy(self):
        pkt = self.rs_fusion.run_engine(self.raw_input, strategy='FULL')
        self.assertIsInstance(pkt, (bytes, bytearray))
        self.assertTrue(len(pkt) > 0)

    def test_run_engine_accepts_memoryview_raw_input(self):
        pkt = self.rs_fusion.run_engine(memoryview(self.raw_input.encode('utf-8')), strategy='FULL')
        self.assertIsInstance(pkt, (bytes, bytearray))
        self.assertTrue(len(pkt) > 0)

    def test_run_engine_diff_after_full(self):
        """DIFF strategy must produce a valid packet after a FULL template is established."""
        self.rs_fusion.run_engine(self.raw_input, strategy='FULL')
        pkt = self.rs_fusion.run_engine(self.raw_input, strategy='DIFF')
        self.assertIsInstance(pkt, (bytes, bytearray))
        self.assertTrue(len(pkt) > 0)

    def test_run_engine_output_parity(self):
        """rscore run_engine must produce bit-for-bit identical output to pycore."""
        py_pkt = self.py_fusion.run_engine(self.raw_input, strategy='FULL')
        rs_pkt = self.rs_fusion.run_engine(self.raw_input, strategy='FULL')
        self.assertEqual(
            py_pkt, rs_pkt,
            msg='run_engine FULL output must be identical for pycore and rscore',
        )

    def test_run_engine_heart_parity(self):
        """After FULL warmup, DIFF on unchanged payload should match pycore HEART output."""
        py_fusion = type(self.py_fusion)(self.cfg_path)
        rs_fusion = type(self.rs_fusion)(self.cfg_path)
        py_fusion.run_engine(self.raw_input, strategy='FULL')
        rs_fusion.run_engine(self.raw_input, strategy='FULL')
        py_pkt = py_fusion.run_engine(self.raw_input, strategy='DIFF')
        rs_pkt = rs_fusion.run_engine(self.raw_input, strategy='DIFF')
        self.assertEqual(py_pkt, rs_pkt)

    def test_run_engine_diff_changed_parity(self):
        """After FULL warmup, DIFF on changed payload should match pycore output."""
        from opensynaptic.core.pycore.standardization import OpenSynapticStandardizer
        from opensynaptic.core.pycore.solidity import OpenSynapticEngine
        cfg = self.cfg_path
        std = OpenSynapticStandardizer(cfg)
        eng = OpenSynapticEngine(cfg)
        fact = std.standardize('RS_FUS', 'ONLINE', [['V1', 'OK', 101325.0, 'Pa']])  # Changed to same value as raw_input for HEART test
        changed_input = '42;{}'.format(eng.compress(fact))
        py_fusion = type(self.py_fusion)(cfg)
        rs_fusion = type(self.rs_fusion)(cfg)
        py_fusion.run_engine(self.raw_input, strategy='FULL')
        rs_fusion.run_engine(self.raw_input, strategy='FULL')
        diff_pkt = py_fusion.run_engine(changed_input, strategy='DIFF')
        py_dec = py_fusion.decompress(diff_pkt)
        rs_dec = rs_fusion.decompress(diff_pkt)
        self.assertEqual(py_dec, rs_dec)

    def test_round_trip_via_rs_fusion(self):
        """Encode with rscore run_engine, decode with rscore decompress."""
        pkt = self.rs_fusion.run_engine(self.raw_input, strategy='FULL')
        decoded = self.rs_fusion.decompress(pkt)
        self.assertIsInstance(decoded, dict)
        self.assertNotIn('error', decoded)

    # ------------------------------------------------------------------
    # _finalize_bin: Rust CRC path
    # ------------------------------------------------------------------
    def test_finalize_bin_uses_rust_crc(self):
        """_rs_crc8_fn + _rs_crc16_fn must be populated when DLL has CRC helpers."""
        from opensynaptic.core.rscore.codec import has_crc_helpers
        if not has_crc_helpers():
            raise unittest.SkipTest('CRC helpers not in loaded DLL')
        self.assertIsNotNone(
            self.rs_fusion._rs_crc8_fn,
            msg='_rs_crc8_fn should be set when os_crc8 is available',
        )
        self.assertIsNotNone(
            self.rs_fusion._rs_crc16_fn,
            msg='_rs_crc16_fn should be set when os_crc16_ccitt_pub is available',
        )

    def test_finalize_bin_parity_full_strategy(self):
        """_finalize_bin (Rust CRC) must produce bit-identical packets to pycore."""
        rs_pkt = self.rs_fusion.run_engine(self.raw_input, strategy='FULL')
        py_pkt = self.py_fusion.run_engine(self.raw_input, strategy='FULL')
        self.assertEqual(
            rs_pkt, py_pkt,
            msg='Packet bytes must be identical: rscore (Rust CRC) vs pycore (C CRC)',
        )

    def test_finalize_bin_parity_diff_strategy(self):
        """DIFF packets from rscore must decode successfully with pycore (cross-decode)."""
        # Seed the templates for both engines with the same FULL packet
        self.rs_fusion.run_engine(self.raw_input, strategy='FULL')
        self.py_fusion.run_engine(self.raw_input, strategy='FULL')
        rs_diff = self.rs_fusion.run_engine(self.raw_input, strategy='DIFF')
        py_diff = self.py_fusion.run_engine(self.raw_input, strategy='DIFF')
        # Both DIFF packets should decode successfully
        self.assertNotIn('error', self.rs_fusion.decompress(rs_diff))
        self.assertNotIn('error', self.py_fusion.decompress(py_diff))


# ---------------------------------------------------------------------------
# RSCore OSHandshakeManager (Rust CMD helpers)
# ---------------------------------------------------------------------------
class TestRscoreHandshakeManager(unittest.TestCase):
    """Verify rscore OSHandshakeManager uses Rust CMD helpers for routing."""

    @classmethod
    def setUpClass(cls):
        from opensynaptic.core.rscore.codec import has_rs_native
        if not has_rs_native():
            raise unittest.SkipTest('os_rscore DLL not available')
        from opensynaptic.core.rscore.api import OSHandshakeManager as RsHandshake
        from opensynaptic.core.pycore.handshake import CMD
        cls.mgr = RsHandshake(target_sync_count=3)
        cls.CMD = CMD

    # ------------------------------------------------------------------
    # Rust helper activation
    # ------------------------------------------------------------------
    def test_rust_cmd_helpers_active(self):
        self.assertIsNotNone(self.mgr._rs_cmd_is_data,   msg='_rs_cmd_is_data must be set')
        self.assertIsNotNone(self.mgr._rs_cmd_normalize, msg='_rs_cmd_normalize must be set')
        self.assertIsNotNone(self.mgr._rs_cmd_secure,    msg='_rs_cmd_secure must be set')

    # ------------------------------------------------------------------
    # is_secure_data_cmd
    # ------------------------------------------------------------------
    def test_is_secure_data_cmd_true_for_secure(self):
        for cmd in self.CMD.SECURE_DATA_CMDS:
            self.assertTrue(
                self.mgr.is_secure_data_cmd(cmd),
                msg='is_secure_data_cmd should be True for cmd={}'.format(cmd),
            )

    def test_is_secure_data_cmd_false_for_plain(self):
        for cmd in self.CMD.PLAIN_DATA_CMDS:
            self.assertFalse(
                self.mgr.is_secure_data_cmd(cmd),
                msg='is_secure_data_cmd should be False for plain cmd={}'.format(cmd),
            )

    def test_is_secure_data_cmd_false_for_ctrl(self):
        for cmd in self.CMD.CTRL_CMDS:
            self.assertFalse(
                self.mgr.is_secure_data_cmd(cmd),
                msg='is_secure_data_cmd should be False for ctrl cmd={}'.format(cmd),
            )

    # ------------------------------------------------------------------
    # normalize_data_cmd
    # ------------------------------------------------------------------
    def test_normalize_data_cmd_secure_to_plain(self):
        for sec, base in self.CMD.BASE_DATA_CMD.items():
            self.assertEqual(
                self.mgr.normalize_data_cmd(sec), base,
                msg='normalize({}) expected {} got {}'.format(
                    sec, base, self.mgr.normalize_data_cmd(sec)),
            )

    def test_normalize_data_cmd_plain_passthrough(self):
        for cmd in self.CMD.PLAIN_DATA_CMDS:
            self.assertEqual(
                self.mgr.normalize_data_cmd(cmd), cmd,
                msg='normalize({}) should be identity for plain cmd'.format(cmd),
            )

    # ------------------------------------------------------------------
    # secure_variant_cmd
    # ------------------------------------------------------------------
    def test_secure_variant_cmd_plain_to_secure(self):
        for plain, sec in self.CMD.SECURE_DATA_CMD.items():
            self.assertEqual(
                self.mgr.secure_variant_cmd(plain), sec,
                msg='secure_variant({}) expected {} got {}'.format(
                    plain, sec, self.mgr.secure_variant_cmd(plain)),
            )

    def test_secure_variant_cmd_passthrough_ctrl(self):
        """Control commands should pass through unchanged."""
        for cmd in self.CMD.CTRL_CMDS:
            self.assertEqual(
                self.mgr.secure_variant_cmd(cmd), cmd,
                msg='secure_variant({}) should pass through ctrl cmd'.format(cmd),
            )

    # ------------------------------------------------------------------
    # Parity: rscore must produce identical results to pycore
    # ------------------------------------------------------------------
    def test_cmd_parity_with_pycore(self):
        """All three CMD methods must produce identical results to pycore."""
        from opensynaptic.core.pycore.handshake import OSHandshakeManager as PyHandshake
        py_mgr = PyHandshake(target_sync_count=3)
        all_cmds = (
            list(self.CMD.DATA_CMDS) +
            list(self.CMD.CTRL_CMDS) +
            [0, 255, 128]
        )
        for cmd in all_cmds:
            self.assertEqual(
                self.mgr.is_secure_data_cmd(cmd),
                py_mgr.is_secure_data_cmd(cmd),
                msg='is_secure_data_cmd parity failed for cmd={}'.format(cmd),
            )
            self.assertEqual(
                self.mgr.normalize_data_cmd(cmd),
                py_mgr.normalize_data_cmd(cmd),
                msg='normalize_data_cmd parity failed for cmd={}'.format(cmd),
            )
            self.assertEqual(
                self.mgr.secure_variant_cmd(cmd),
                py_mgr.secure_variant_cmd(cmd),
                msg='secure_variant_cmd parity failed for cmd={}'.format(cmd),
            )


def build_suite():
    """Return a TestSuite with all component tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (TestUtilsEntryPointImports, TestCoreManager, TestBase62Codec, TestOpenSynapticStandardizer,
                TestOpenSynapticEngine, TestOSVisualFusionEngine, TestPluginE2EPipeline,
                TestIDAllocator, TestEnvGuardService, TestWebUserAdminService, TestRscore, TestRscoreEngine,
                TestFullLoadConfig, TestStressAutoProfile,
                TestRscoreFusionEngine, TestRscoreHandshakeManager):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    return suite


if __name__ == '__main__':
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(build_suite())

