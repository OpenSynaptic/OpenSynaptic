//! Build script for opensynaptic_rscore.
//!
//! # Problem
//!
//! PyO3's `extension-module` Cargo feature causes `pyo3-build-config` to emit:
//!
//! ```text
//! cargo:rustc-cdylib-link-arg=-Wl,--version-script=<path>/pyo3_init.ld
//! ```
//!
//! where `pyo3_init.ld` contains:
//!
//! ```text
//! { global: PyInit_opensynaptic_rscore; local: *; };
//! ```
//!
//! The `local: *` wildcard hides **every** symbol that does not match
//! `global:`, including all the `#[no_mangle] pub unsafe extern "C"` C-ABI
//! bridge functions (`os_b62_encode_i64`, `os_b62_decode_i64`, `os_crc8`, …).
//! Those symbols end up **absent** from `.dynsym`, making them invisible to
//! `ctypes.CDLL` / `dlsym`.
//!
//! # Fix
//!
//! We emit a **second** `--version-script` containing a **named** version
//! node (`OSCORE_ABI`).  Unlike an anonymous node, a named version node is
//! never merged with PyO3's anonymous node — the linker keeps them separate.
//! Symbols listed in `global:` of the named node are unconditionally placed
//! into `.dynsym` and survive thin-LTO + `strip = true`, regardless of the
//! `local: *` wildcard in the anonymous node.
//!
//! Previous approach (`--dynamic-list`) failed on manylinux2014 (binutils
//! 2.27) when combined with `lto = "thin"` + `strip = true` in the Cargo
//! release profile: the linker / LTO pass treated `local: *`-hidden symbols
//! as dead before `--dynamic-list` could re-export them.
//!
//! The named-version-node approach is reliable on all binutils ≥ 2.14 and
//! does not interfere with PyO3's anonymous-node symbol visibility.

fn main() {
    // Incremental-build guard.
    println!("cargo:rerun-if-changed=build.rs");

    // Version-script symbol export is an ELF / GNU ld concept.  macOS uses
    // an export list (`-exported_symbols_list`) and Windows uses a `.def`
    // file; both expose C-ABI symbols without extra configuration, so we
    // only act on Linux / Android (ELF targets where PyO3 emits the
    // problematic version script).
    let target_os = std::env::var("CARGO_CFG_TARGET_OS").unwrap_or_default();
    if target_os != "linux" && target_os != "android" {
        return;
    }

    let out_dir = std::env::var("OUT_DIR").expect("Cargo must set OUT_DIR");
    let vs_path = std::path::PathBuf::from(&out_dir).join("os_abi_exports.ver");

    // Named version node — symbols listed here are exported to .dynsym
    // even when PyO3's anonymous node contains `local: *`.
    // dlsym(handle, "os_b62_encode_i64") resolves the default (@@) version.
    let content = "\
OSCORE_ABI {\n\
    global:\n\
        os_b62_encode_i64;\n\
        os_b62_decode_i64;\n\
        os_crc8;\n\
        os_crc16_ccitt;\n\
        os_crc16_ccitt_pub;\n\
        os_xor_payload;\n\
        os_derive_session_key;\n\
};\n";

    std::fs::write(&vs_path, content)
        .expect("failed to write os_abi_exports.ver version-script file");

    // Pass --version-script to the linker through the compiler driver.
    // This is added AFTER PyO3's --version-script (dependency link args
    // precede the crate's own); the named node supplements rather than
    // conflicts with PyO3's anonymous node.
    println!(
        "cargo:rustc-link-arg=-Wl,--version-script={}",
        vs_path.display()
    );
}
