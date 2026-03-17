"""Parser for the plugin-test command.

Includes all existing fine-grained flags *and* a ``--profile`` shorthand
that maps to pre-canned concurrency configurations:

=======  =====================================================================
Profile  Equivalent flags
=======  =====================================================================
quick    ``--suite stress --total 5000 --workers 8 --processes 1
          --batch-size 32``
deep     ``--suite stress --total 50000 --workers 16 --processes 4
          --batch-size 64 --auto-profile``
record   ``--suite compare --total 10000 --workers 8 --processes 2 --runs 3``
=======  =====================================================================

The profile is *applied* in ``app.py`` via ``_apply_test_profile(args)`` just
after ``parse_args()`` – the individual flags are only read after that call,
so presets always win over implicit defaults.
"""
import argparse

from .base import add_config_arg

# ---------------------------------------------------------------------------
# Profile presets
# ---------------------------------------------------------------------------
PROFILE_PRESETS: dict = {
    'quick': {
        'suite': 'stress',
        'total': 5000,
        'workers': 8,
        'processes': 1,
        'batch_size': 32,
    },
    'deep': {
        'suite': 'stress',
        'total': 50000,
        'workers': 16,
        'processes': 4,
        'batch_size': 64,
        'auto_profile': True,
    },
    'record': {
        'suite': 'compare',
        'total': 10000,
        'workers': 8,
        'processes': 2,
        'runs': 3,
    },
}


def register(sub: argparse._SubParsersAction) -> None:
    """Attach plugin-test command to *sub*."""

    plugin_test = sub.add_parser(
        'plugin-test', aliases=['os-plugin-test'],
        help='Run component or stress tests (use --profile for one-flag presets)',
    )
    add_config_arg(plugin_test)

    # ------------------------------------------------------------------
    # Profile shorthand (takes priority over individual flags in app.py)
    # ------------------------------------------------------------------
    plugin_test.add_argument(
        '--profile',
        choices=list(PROFILE_PRESETS.keys()),
        default=None,
        help=(
            'Named test profile – overrides individual flags: '
            'quick=fast smoke, deep=auto-profile stress, '
            'record=pycore-vs-rscore compare'
        ),
    )

    # ------------------------------------------------------------------
    # Full fine-grained flags (unchanged from original app.py)
    # ------------------------------------------------------------------
    plugin_test.add_argument(
        '--suite',
        choices=['component', 'stress', 'all', 'compare', 'full_load'],
        default='all',
        help='Test suite (component/stress/all/compare/full_load)',
    )
    plugin_test.add_argument('--workers', type=int, default=8,
                             help='Stress test worker threads')
    plugin_test.add_argument('--total', type=int, default=200,
                             help='Total stress test iterations')
    plugin_test.add_argument('--sources', type=int, default=6,
                             help='Number of rotating sensor source templates')
    plugin_test.add_argument('--no-progress', action='store_true', default=False,
                             help='Disable live progress bar during stress test')
    plugin_test.add_argument('--verbosity', type=int, default=1,
                             help='Component test verbosity level')
    plugin_test.add_argument(
        '--core-backend', dest='core_backend', default=None,
        choices=['pycore', 'rscore'],
        help='Core plugin for stress/all suites (pycore/rscore)',
    )
    plugin_test.add_argument('--runs', type=int, default=1,
                             help='Measured compare runs per backend (suite=compare)')
    plugin_test.add_argument('--warmup', type=int, default=0,
                             help='Warmup compare runs per backend (suite=compare)')
    plugin_test.add_argument('--json-out', dest='json_out', default=None,
                             help='Optional compare report output path (suite=compare)')
    plugin_test.add_argument('--require-rust', action='store_true', default=False,
                             help='Fail when rscore path cannot use os_rscore DLL')
    plugin_test.add_argument(
        '--header-probe-rate', type=float, default=0.0,
        help='Optional packet-header probe sample rate [0.0-1.0] for stress/compare',
    )
    plugin_test.add_argument('--batch-size', type=int, default=1,
                             help='Stress task batch size per future (higher reduces scheduler overhead)')
    plugin_test.add_argument('--processes', type=int, default=1,
                             help='Stress process count (1 = thread-only mode)')
    plugin_test.add_argument(
        '--threads-per-process', type=int, default=None,
        help='Thread count inside each process (default: --workers)',
    )
    plugin_test.add_argument('--auto-profile', action='store_true', default=False,
                             help='Scan candidate stress concurrency combos, then run final with best config')
    plugin_test.add_argument('--profile-total', type=int, default=100000,
                             help='Per-candidate scan workload when --auto-profile is enabled')
    plugin_test.add_argument('--profile-runs', type=int, default=1,
                             help='Measured scan runs per candidate when --auto-profile is enabled')
    plugin_test.add_argument('--final-runs', type=int, default=1,
                             help='Measured final runs with selected best profile config')
    plugin_test.add_argument('--profile-processes', default='1,2,4,8',
                             help='Candidate process counts (CSV), e.g. 1,2,4,8')
    plugin_test.add_argument('--profile-threads', default=None,
                             help='Candidate thread counts per process (CSV), defaults to --workers')
    plugin_test.add_argument('--profile-batches', default='32,64,128',
                             help='Candidate batch sizes (CSV)')
    plugin_test.add_argument('--parallel-component', action='store_true', default=False,
                             help='Run component tests in parallel (thread per class)')
    plugin_test.add_argument(
        '--max-class-workers', type=int, default=None,
        help='Thread count for parallel component runner (suite=component)',
    )
    plugin_test.add_argument(
        '--component-processes', type=int, default=0,
        help='>0: run that many component classes in separate OS processes'
             ' (suite=component, implies --parallel-component)',
    )
    plugin_test.add_argument('--workers-hint', type=int, default=None,
                             help='Override auto-detected process count (suite=full_load)')
    plugin_test.add_argument('--threads-hint', type=int, default=None,
                             help='Override auto-detected threads-per-process (suite=full_load)')
    plugin_test.add_argument('--batch-hint', type=int, default=None,
                             help='Override auto-detected batch size (suite=full_load)')
    plugin_test.add_argument('--with-component', action='store_true', default=False,
                             help='Run parallel component tests before full-load stress (suite=full_load)')

