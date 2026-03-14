"""
test_plugin/main.py – ServiceManager-mountable test plugin for OpenSynaptic.

Exposes component tests and stress tests as a service with CLI sub-commands.

Usage via CLI:
    python -u src/main.py plugin-test --suite component
    python -u src/main.py plugin-test --suite stress --workers 8 --total 200
    python -u src/main.py plugin-test --suite all
"""
import json
import sys
import unittest
from pathlib import Path

from opensynaptic.utils.logger import os_log
from opensynaptic.utils.constants import LogMsg


class TestPlugin:
    """ServiceManager-mountable test plugin.

    Runs component and/or stress tests for the OpenSynaptic pipeline.
    Mount it via:
        node.service_manager.mount('test_plugin', TestPlugin(node), config={}, mode='runtime')
        node.service_manager.load('test_plugin')
    """

    def __init__(self, node=None):
        self.node = node
        self._config_path = getattr(node, 'config_path', None) if node else None

    def auto_load(self):
        os_log.log_with_const('info', LogMsg.PLUGIN_TEST_START, plugin='test_plugin', suite='init')
        return self

    # ------------------------------------------------------------------ #
    #  Suite runners                                                       #
    # ------------------------------------------------------------------ #

    def run_component(self, verbosity=1):
        """Run all unit (component) tests and return (ok_count, fail_count, result)."""
        from opensynaptic.services.test_plugin.component_tests import build_suite
        suite = build_suite()
        runner = unittest.TextTestRunner(verbosity=verbosity, stream=sys.stdout)
        result = runner.run(suite)
        ok = result.testsRun - len(result.failures) - len(result.errors)
        fail = len(result.failures) + len(result.errors)
        return ok, fail, result

    def run_stress(self, total=200, workers=8, sources=6, progress=True):
        """Run concurrent pipeline stress test and return (summary_dict, fail_count)."""
        from opensynaptic.services.test_plugin.stress_tests import run_stress
        result, summary = run_stress(
            total=total, workers=workers, sources=sources,
            config_path=self._config_path, progress=progress
        )
        return summary, result.fail

    def run_all(self, stress_total=200, stress_workers=8, verbosity=1):
        """Run both component and stress suites. Returns combined report dict."""
        print('\n=== Component Tests ===', flush=True)
        c_ok, c_fail, _ = self.run_component(verbosity=verbosity)
        print('\n=== Stress Tests ===', flush=True)
        s_summary, s_fail = self.run_stress(total=stress_total, workers=stress_workers)
        report = {
            'component': {'ok': c_ok, 'fail': c_fail},
            'stress': s_summary,
            'overall_fail': c_fail + s_fail,
        }
        return report

    # ------------------------------------------------------------------ #
    #  Plugin CLI integration                                              #
    # ------------------------------------------------------------------ #

    def get_cli_commands(self):
        """Expose test sub-commands to ServiceManager.dispatch_plugin_cli()."""

        def _component(argv):
            import argparse
            p = argparse.ArgumentParser(prog='test_plugin component')
            p.add_argument('--verbosity', type=int, default=1)
            ns = p.parse_args(argv)
            ok, fail, _ = self.run_component(verbosity=ns.verbosity)
            os_log.log_with_const('info', LogMsg.PLUGIN_TEST_RESULT,
                                  plugin='test_plugin', suite='component', ok=ok, fail=fail)
            print(json.dumps({'ok': ok, 'fail': fail}, ensure_ascii=False))
            return 0 if fail == 0 else 1

        def _stress(argv):
            import argparse
            p = argparse.ArgumentParser(prog='test_plugin stress')
            p.add_argument('--total', type=int, default=200)
            p.add_argument('--workers', type=int, default=8)
            p.add_argument('--sources', type=int, default=6)
            p.add_argument('--no-progress', action='store_true', default=False)
            ns = p.parse_args(argv)
            summary, fail = self.run_stress(
                total=ns.total, workers=ns.workers,
                sources=ns.sources, progress=not ns.no_progress
            )
            os_log.log_with_const('info', LogMsg.PLUGIN_TEST_RESULT,
                                  plugin='test_plugin', suite='stress', ok=summary.get('ok', 0), fail=fail)
            print(json.dumps(summary, indent=2, ensure_ascii=False))
            return 0 if fail == 0 else 1

        def _all(argv):
            import argparse
            p = argparse.ArgumentParser(prog='test_plugin all')
            p.add_argument('--total', type=int, default=200)
            p.add_argument('--workers', type=int, default=8)
            p.add_argument('--verbosity', type=int, default=1)
            ns = p.parse_args(argv)
            report = self.run_all(stress_total=ns.total, stress_workers=ns.workers,
                                  verbosity=ns.verbosity)
            print(json.dumps(report, indent=2, ensure_ascii=False))
            return 0 if report['overall_fail'] == 0 else 1

        return {
            'component': _component,
            'stress': _stress,
            'all': _all,
        }

