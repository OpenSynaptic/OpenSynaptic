# Standalone Localhost Simulator

This script is fully independent from OpenSynaptic protocol internals and uses only Python stdlib `socket` + `threading`.

## File

- `scripts/standalone_localhost_sim.py`

## Quick Start

### Demo mode (server + client in one process)

```powershell
python -u scripts/standalone_localhost_sim.py --mode demo --protocol udp
python -u scripts/standalone_localhost_sim.py --mode demo --protocol tcp
```

### Split mode (run server and client separately)

```powershell
python -u scripts/standalone_localhost_sim.py --mode server --protocol udp --host 127.0.0.1 --port 19090
python -u scripts/standalone_localhost_sim.py --mode client --protocol udp --host 127.0.0.1 --port 19090 --count 10 --interval 0.1
```

```powershell
python -u scripts/standalone_localhost_sim.py --mode server --protocol tcp --host 127.0.0.1 --port 19090
python -u scripts/standalone_localhost_sim.py --mode client --protocol tcp --host 127.0.0.1 --port 19090 --count 10 --interval 0.1
```

## Output

- Server prints received JSON payloads
- Client prints ACK and RTT per message

