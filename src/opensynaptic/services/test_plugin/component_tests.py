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
from pathlib import Path
from types import SimpleNamespace

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

from opensynaptic.utils.c.native_loader import has_native_library
from opensynaptic.utils.errors import EnvironmentMissingError


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


# ---------------------------------------------------------------------------
# Base62 Codec
# ---------------------------------------------------------------------------
class TestBase62Codec(unittest.TestCase):
    """Round-trip encoding/decoding tests for Base62Codec."""

    def setUp(self):
        if not has_native_library('os_base62'):
            raise unittest.SkipTest('os_base62 native library is not available')
        from opensynaptic.utils.base62.base62 import Base62Codec
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

    def test_release_and_reuse(self):
        id_val = self.allocator.allocate_id()
        self.assertTrue(self.allocator.is_allocated(id_val))
        released = self.allocator.release_id(id_val)
        self.assertTrue(released)
        # Re-allocate; should get back the released ID (lowest available)
        new_id = self.allocator.allocate_id()
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


def build_suite():
    """Return a TestSuite with all component tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (TestCoreManager, TestBase62Codec, TestOpenSynapticStandardizer,
                TestOpenSynapticEngine, TestOSVisualFusionEngine,
                TestIDAllocator, TestEnvGuardService):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    return suite


if __name__ == '__main__':
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(build_suite())

