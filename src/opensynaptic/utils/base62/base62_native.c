#include <stdint.h>
#include <stddef.h>

#ifdef _WIN32
#define OS_EXPORT __declspec(dllexport)
#else
#define OS_EXPORT
#endif

static const char OS_B62_CHARS[] = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";

OS_EXPORT int os_b62_encode_i64(long long value, char* out, size_t out_len) {
    if (!out || out_len < 2) {
        return 0;
    }
    if (value == 0) {
        out[0] = '0';
        out[1] = '\0';
        return 1;
    }
    unsigned long long n = (value < 0) ? (unsigned long long)(-value) : (unsigned long long)value;
    char buf[96];
    size_t idx = 0;
    while (n > 0 && idx < sizeof(buf) - 1) {
        buf[idx++] = OS_B62_CHARS[n % 62ULL];
        n /= 62ULL;
    }
    size_t needed = idx + ((value < 0) ? 1 : 0) + 1;
    if (needed > out_len) {
        return 0;
    }
    size_t w = 0;
    if (value < 0) {
        out[w++] = '-';
    }
    while (idx > 0) {
        out[w++] = buf[--idx];
    }
    out[w] = '\0';
    return 1;
}

OS_EXPORT long long os_b62_decode_i64(const char* s, int* ok) {
    if (ok) {
        *ok = 0;
    }
    if (!s || !*s) {
        return 0;
    }
    int neg = 0;
    const char* p = s;
    if (*p == '-') {
        neg = 1;
        p++;
        if (!*p) {
            return 0;
        }
    }
    unsigned long long val = 0;
    while (*p) {
        unsigned char c = (unsigned char)*p;
        int d = -1;
        if (c >= '0' && c <= '9') {
            d = (int)(c - '0');
        } else if (c >= 'a' && c <= 'z') {
            d = 10 + (int)(c - 'a');
        } else if (c >= 'A' && c <= 'Z') {
            d = 36 + (int)(c - 'A');
        } else {
            return 0;
        }
        val = val * 62ULL + (unsigned long long)d;
        p++;
    }
    if (ok) {
        *ok = 1;
    }
    return neg ? -(long long)val : (long long)val;
}

