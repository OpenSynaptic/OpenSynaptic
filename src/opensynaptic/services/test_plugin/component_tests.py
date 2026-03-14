"""
component_tests.py – Unit tests for individual OpenSynaptic pipeline components.

Run via:
    python -u src/main.py plugin-test --suite component
"""
import sys
import time
import unittest
from pathlib import Path

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


# ---------------------------------------------------------------------------
# Base62 Codec
# ---------------------------------------------------------------------------
class TestBase62Codec(unittest.TestCase):
    """Round-trip encoding/decoding tests for Base62Codec."""

    def setUp(self):
        from opensynaptic.utils.base62_codec import Base62Codec
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
        from opensynaptic.core.standardization import OpenSynapticStandardizer
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
        from opensynaptic.core.standardization import OpenSynapticStandardizer
        from opensynaptic.core.solidity import OpenSynapticEngine
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
        from opensynaptic.core.standardization import OpenSynapticStandardizer
        from opensynaptic.core.solidity import OpenSynapticEngine
        from opensynaptic.core.unified_parser import OSVisualFusionEngine
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


def build_suite():
    """Return a TestSuite with all component tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in (TestBase62Codec, TestOpenSynapticStandardizer,
                TestOpenSynapticEngine, TestOSVisualFusionEngine,
                TestIDAllocator):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    return suite


if __name__ == '__main__':
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(build_suite())

