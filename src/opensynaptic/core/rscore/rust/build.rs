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
//! GNU ld's `--dynamic-list=FILE` option explicitly overrides the version
//! script's `local:` assignment for the listed symbols and forces them into
//! `.dynsym`.  From the binutils manual:
//!
//! > "Note that this option allows **overriding the binding** of symbols that
//! > are **normally local** to the shared library or executable."
//!
//! A companion `--version-script` approach (merging two anonymous version
//! nodes) is unreliable on binutils ≤ 2.27 (manylinux2014): the `local: *`
//! wildcard from PyO3's script can win over explicit `global:` entries from a
//! second anonymous node, depending on node-merging order.  `--dynamic-list`
//! has no such ambiguity — it is a hard override.

fn main() {
    // Incremental-build guard.
    println!("cargo:rerun-if-changed=build.rs");

    // `--dynamic-list` is an ELF / GNU ld concept.  macOS uses an export list
    // (`-exported_symbols_list`) and Windows uses a `.def` file; both expose
    // C-ABI symbols without extra configuration, so we only act on Linux /
    // Android (ELF targets where PyO3 emits the problematic version script).
    let target_os = std::env::var("CARGO_CFG_TARGET_OS").unwrap_or_default();
    if target_os != "linux" && target_os != "android" {
        return;
    }

    let out_dir = std::env::var("OUT_DIR").expect("Cargo must set OUT_DIR");
    let list_path = std::path::PathBuf::from(&out_dir).join("os_abi_exports.list");

    // Dynamic-list format: symbol names inside `{ … };`.
    // No `global:` / `local:` keywords — just bare names.
    let content = "\
{\n\
    os_b62_encode_i64;\n\
    os_b62_decode_i64;\n\
    os_crc8;\n\
    os_crc16_ccitt;\n\
    os_crc16_ccitt_pub;\n\
    os_xor_payload;\n\
    os_derive_session_key;\n\
};\n";

    std::fs::write(&list_path, content)
        .expect("failed to write os_abi_exports.list dynamic-list file");

    // Pass --dynamic-list to the linker through the compiler driver.
    // Using -Wl,flag=value keeps the argument as a single shell token,
    // avoiding any whitespace-splitting issues with the path.
    println!(
        "cargo:rustc-link-arg=-Wl,--dynamic-list={}",
        list_path.display()
    );
}
