"""Reed-Solomon over GF(2^8), errors-only. Same convention as reedsolo defaults:
primitive polynomial 0x11d, generator 2, first consecutive root alpha^0."""

EXP = [0] * 512
LOG = [0] * 256
_x = 1
for _i in range(255):
    EXP[_i] = _x
    LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    EXP[_i] = EXP[_i - 255]


def _mul(a, b):
    return 0 if a == 0 or b == 0 else EXP[LOG[a] + LOG[b]]


def _div(a, b):
    if b == 0:
        raise ZeroDivisionError("GF(256) division by zero")
    return 0 if a == 0 else EXP[(LOG[a] - LOG[b]) % 255]


def _eval_le(p, x):  # little-endian coefficients: p[i] * x^i
    y = 0
    for c in reversed(p):
        y = _mul(y, x) ^ c
    return y


def _syndromes(code, nsym):  # code bytes are big-endian coefficients
    out = []
    for j in range(nsym):
        x, y = EXP[j], 0
        for c in code:
            y = _mul(y, x) ^ c
        out.append(y)
    return out


def _check_len(n, nsym):
    if not 0 < nsym < 255 or n > 255:
        raise ValueError("Reed-Solomon codeword must be at most 255 bytes, with 0 < nsym < 255")


def encode(data: bytes, nsym: int = 32) -> bytes:
    data = bytes(data)
    _check_len(len(data) + nsym, nsym)
    gen = [1]  # big-endian product of (x - alpha^i), i = 0..nsym-1
    for i in range(nsym):
        gen = [a ^ _mul(b, EXP[i]) for a, b in zip(gen + [0], [0] + gen)]
    rem = list(data) + [0] * nsym
    for i in range(len(data)):
        coef = rem[i]
        if coef:
            for j in range(1, len(gen)):
                rem[i + j] ^= _mul(gen[j], coef)
    return data + bytes(rem[len(data):])


def decode(code: bytes, nsym: int = 32) -> bytes:
    code = bytearray(code)
    n = len(code)
    _check_len(n, nsym)
    if n <= nsym:
        raise ValueError("codeword shorter than its parity")
    synd = _syndromes(code, nsym)
    if not any(synd):
        return bytes(code[:-nsym])
    # Berlekamp-Massey -> error locator lam (little-endian, lam[0] = 1)
    lam, prev, deg, m, b = [1], [1], 0, 1, 1
    for k in range(nsym):
        d = synd[k]
        for i in range(1, deg + 1):
            if i < len(lam):
                d ^= _mul(lam[i], synd[k - i])
        if d == 0:
            m += 1
            continue
        coef = _div(d, b)
        shifted = [0] * m + [_mul(coef, c) for c in prev]
        new = [x ^ y for x, y in zip(lam + [0] * (len(shifted) - len(lam)),
                                     shifted + [0] * (len(lam) - len(shifted)))]
        if 2 * deg <= k:
            prev, deg, b, m = lam, k + 1 - deg, d, 1
        else:
            m += 1
        lam = new
    lam = lam[:deg + 1]
    if deg == 0 or 2 * deg > nsym:
        raise ValueError("too many errors to correct")
    # Chien search: byte at index i is the coefficient of x^(n-1-i)
    pos = [i for i in range(n) if _eval_le(lam, EXP[(255 - (n - 1 - i)) % 255]) == 0]
    if len(pos) != deg:
        raise ValueError("too many errors to correct")
    # Forney (first root alpha^0): e = X * omega(X^-1) / lam'(X^-1)
    omega = [0] * nsym
    for i, s in enumerate(synd):
        for j, l in enumerate(lam):
            if i + j < nsym:
                omega[i + j] ^= _mul(s, l)
    dlam = [lam[i] if i % 2 else 0 for i in range(1, len(lam))]
    for i in pos:
        x = EXP[n - 1 - i]
        xinv = EXP[(255 - (n - 1 - i)) % 255]
        den = _eval_le(dlam, xinv)
        if den == 0:
            raise ValueError("too many errors to correct")
        code[i] ^= _mul(x, _div(_eval_le(omega, xinv), den))
    if any(_syndromes(code, nsym)):
        raise ValueError("too many errors to correct")
    return bytes(code[:-nsym])
