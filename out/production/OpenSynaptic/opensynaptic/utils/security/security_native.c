#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>

#ifdef _WIN32
#define OS_EXPORT __declspec(dllexport)
#else
#define OS_EXPORT
#endif

#define ROTR(x, n) (((x) >> (n)) | ((x) << (32 - (n))))

static const uint32_t K[64] = {
    0x428a2f98U, 0x71374491U, 0xb5c0fbcfU, 0xe9b5dba5U, 0x3956c25bU, 0x59f111f1U, 0x923f82a4U, 0xab1c5ed5U,
    0xd807aa98U, 0x12835b01U, 0x243185beU, 0x550c7dc3U, 0x72be5d74U, 0x80deb1feU, 0x9bdc06a7U, 0xc19bf174U,
    0xe49b69c1U, 0xefbe4786U, 0x0fc19dc6U, 0x240ca1ccU, 0x2de92c6fU, 0x4a7484aaU, 0x5cb0a9dcU, 0x76f988daU,
    0x983e5152U, 0xa831c66dU, 0xb00327c8U, 0xbf597fc7U, 0xc6e00bf3U, 0xd5a79147U, 0x06ca6351U, 0x14292967U,
    0x27b70a85U, 0x2e1b2138U, 0x4d2c6dfcU, 0x53380d13U, 0x650a7354U, 0x766a0abbU, 0x81c2c92eU, 0x92722c85U,
    0xa2bfe8a1U, 0xa81a664bU, 0xc24b8b70U, 0xc76c51a3U, 0xd192e819U, 0xd6990624U, 0xf40e3585U, 0x106aa070U,
    0x19a4c116U, 0x1e376c08U, 0x2748774cU, 0x34b0bcb5U, 0x391c0cb3U, 0x4ed8aa4aU, 0x5b9cca4fU, 0x682e6ff3U,
    0x748f82eeU, 0x78a5636fU, 0x84c87814U, 0x8cc70208U, 0x90befffaU, 0xa4506cebU, 0xbef9a3f7U, 0xc67178f2U
};

static void sha256_bytes(const uint8_t* data, size_t len, uint8_t out[32]) {
    uint32_t h[8] = {
        0x6a09e667U, 0xbb67ae85U, 0x3c6ef372U, 0xa54ff53aU,
        0x510e527fU, 0x9b05688cU, 0x1f83d9abU, 0x5be0cd19U
    };

    uint8_t block[64];
    uint64_t bit_len = (uint64_t)len * 8ULL;
    size_t full = len / 64;
    size_t rem = len % 64;

    for (size_t bi = 0; bi < full + 1; ++bi) {
        uint32_t w[64];
        memset(block, 0, sizeof(block));

        if (bi < full) {
            memcpy(block, data + (bi * 64), 64);
        } else {
            if (rem > 0) {
                memcpy(block, data + (full * 64), rem);
            }
            block[rem] = 0x80;
            if (rem >= 56) {
                // process this block first, then one extra with length
            }
        }

        int process_twice = (bi == full && rem >= 56) ? 1 : 0;
        int rounds = process_twice ? 2 : 1;

        for (int pass = 0; pass < rounds; ++pass) {
            if (pass == 1) {
                memset(block, 0, sizeof(block));
            }
            if (bi == full && pass == rounds - 1) {
                block[56] = (uint8_t)((bit_len >> 56) & 0xFFU);
                block[57] = (uint8_t)((bit_len >> 48) & 0xFFU);
                block[58] = (uint8_t)((bit_len >> 40) & 0xFFU);
                block[59] = (uint8_t)((bit_len >> 32) & 0xFFU);
                block[60] = (uint8_t)((bit_len >> 24) & 0xFFU);
                block[61] = (uint8_t)((bit_len >> 16) & 0xFFU);
                block[62] = (uint8_t)((bit_len >> 8) & 0xFFU);
                block[63] = (uint8_t)(bit_len & 0xFFU);
            }

            for (int i = 0; i < 16; ++i) {
                w[i] = ((uint32_t)block[i * 4] << 24) |
                       ((uint32_t)block[i * 4 + 1] << 16) |
                       ((uint32_t)block[i * 4 + 2] << 8) |
                       ((uint32_t)block[i * 4 + 3]);
            }
            for (int i = 16; i < 64; ++i) {
                uint32_t s0 = ROTR(w[i - 15], 7) ^ ROTR(w[i - 15], 18) ^ (w[i - 15] >> 3);
                uint32_t s1 = ROTR(w[i - 2], 17) ^ ROTR(w[i - 2], 19) ^ (w[i - 2] >> 10);
                w[i] = w[i - 16] + s0 + w[i - 7] + s1;
            }

            uint32_t a = h[0], b = h[1], c = h[2], d = h[3];
            uint32_t e = h[4], f = h[5], g = h[6], hh = h[7];

            for (int i = 0; i < 64; ++i) {
                uint32_t S1 = ROTR(e, 6) ^ ROTR(e, 11) ^ ROTR(e, 25);
                uint32_t ch = (e & f) ^ ((~e) & g);
                uint32_t temp1 = hh + S1 + ch + K[i] + w[i];
                uint32_t S0 = ROTR(a, 2) ^ ROTR(a, 13) ^ ROTR(a, 22);
                uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
                uint32_t temp2 = S0 + maj;

                hh = g;
                g = f;
                f = e;
                e = d + temp1;
                d = c;
                c = b;
                b = a;
                a = temp1 + temp2;
            }

            h[0] += a; h[1] += b; h[2] += c; h[3] += d;
            h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
        }
    }

    for (int i = 0; i < 8; ++i) {
        out[i * 4] = (uint8_t)((h[i] >> 24) & 0xFFU);
        out[i * 4 + 1] = (uint8_t)((h[i] >> 16) & 0xFFU);
        out[i * 4 + 2] = (uint8_t)((h[i] >> 8) & 0xFFU);
        out[i * 4 + 3] = (uint8_t)(h[i] & 0xFFU);
    }
}

OS_EXPORT uint8_t os_crc8(const uint8_t* data, size_t len, uint16_t poly, uint8_t init) {
    uint8_t crc = init;
    if (!data || len == 0) {
        return crc;
    }
    for (size_t i = 0; i < len; ++i) {
        crc ^= data[i];
        for (int j = 0; j < 8; ++j) {
            if (crc & 0x80U) {
                crc = (uint8_t)(((crc << 1) ^ (uint8_t)poly) & 0xFFU);
            } else {
                crc = (uint8_t)((crc << 1) & 0xFFU);
            }
        }
    }
    return crc;
}

OS_EXPORT uint16_t os_crc16_ccitt(const uint8_t* data, size_t len, uint16_t poly, uint16_t init) {
    uint16_t crc = init;
    if (!data || len == 0) {
        return crc;
    }
    for (size_t i = 0; i < len; ++i) {
        crc ^= (uint16_t)(data[i] << 8);
        for (int j = 0; j < 8; ++j) {
            if (crc & 0x8000U) {
                crc = (uint16_t)(((crc << 1) ^ poly) & 0xFFFFU);
            } else {
                crc = (uint16_t)((crc << 1) & 0xFFFFU);
            }
        }
    }
    return crc;
}

OS_EXPORT void os_xor_payload(
    const uint8_t* payload,
    size_t payload_len,
    const uint8_t* key,
    size_t key_len,
    uint32_t offset,
    uint8_t* out
) {
    if (!out) {
        return;
    }
    if (!payload || payload_len == 0) {
        return;
    }
    uint8_t off = (uint8_t)(offset & 31U);
    if (!key || key_len == 0) {
        memcpy(out, payload, payload_len);
        return;
    }
    for (size_t i = 0; i < payload_len; ++i) {
        out[i] = (uint8_t)(payload[i] ^ key[(i + off) % key_len] ^ off);
    }
}

OS_EXPORT void os_derive_session_key(uint64_t assigned_id, uint64_t timestamp_raw, uint8_t out32[32]) {
    if (!out32) {
        return;
    }
    uint64_t seed = assigned_id * timestamp_raw;
    char buf[64];
    int len = snprintf(buf, sizeof(buf), "%llu", (unsigned long long)seed);
    if (len < 0) {
        memset(out32, 0, 32);
        return;
    }
    sha256_bytes((const uint8_t*)buf, (size_t)len, out32);
}

