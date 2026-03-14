CHARS = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
_ENCODE_TABLE = {i: CHARS[i] for i in range(62)}
_DECODE_TABLE = {c: i for i, c in enumerate(CHARS)}

class Base62Codec:

    def __init__(self, precision=4):
        self.precision_val = 10 ** precision

    def encode(self, n, use_precision=True):
        try:
            val = int(round(float(n) * self.precision_val)) if use_precision else int(float(n))
        except:
            return '0'
        if val == 0:
            return '0'
        sign, n = ('-', abs(val)) if val < 0 else ('', val)
        res = []
        _table = _ENCODE_TABLE
        while n > 0:
            res.append(_table[n % 62])
            n //= 62
        return sign + ''.join(reversed(res))

    def decode(self, s, use_precision=True):
        if not s or s == '0':
            return 0.0
        sign, data = (-1, s[1:]) if s.startswith('-') else (1, s)
        val = 0
        _table = _DECODE_TABLE
        for char in data:
            val = val * 62 + _table[char]
        if not use_precision:
            return float(val * sign)
        return round(val * sign / self.precision_val, 8)
