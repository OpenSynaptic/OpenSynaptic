import hashlib
CRC8_POLY = 7
CRC16_POLY = 4129
CRC16_INIT = 65535

def crc8(data, poly=CRC8_POLY, init=0):
    crc = init & 255
    for byte in data or b'':
        crc ^= byte
        for _ in range(8):
            if crc & 128:
                crc = (crc << 1 ^ poly) & 255
            else:
                crc = crc << 1 & 255
    return crc & 255

def crc16_ccitt(data, poly=CRC16_POLY, init=CRC16_INIT):
    crc = init & 65535
    for byte in data or b'':
        crc ^= byte << 8 & 65535
        for _ in range(8):
            if crc & 32768:
                crc = (crc << 1 ^ poly) & 65535
            else:
                crc = crc << 1 & 65535
    return crc & 65535

def derive_session_key(assigned_id, timestamp_raw):
    aid = max(0, int(assigned_id or 0))
    ts = max(0, int(timestamp_raw or 0))
    seed = ts * aid
    return hashlib.sha256(str(seed).encode('utf-8')).digest()

def xor_payload(payload, key, offset):
    if not payload:
        return b''
    if not key:
        return bytes(payload)
    key_len = len(key)
    off = int(offset or 0) & 31
    out = bytearray(len(payload))
    for idx, byte in enumerate(payload):
        out[idx] = byte ^ key[(idx + off) % key_len] ^ off
    return bytes(out)
