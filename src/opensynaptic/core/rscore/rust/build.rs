//! Build script for opensynaptic_rscore.
//!
//! On Linux (ELF targets), PyO3's `extension-module` feature emits a linker
//! version script `{ global: PyInit_*; local: *; }` via its build-config
//! crate.  That version script hides every symbol that does not start with
//! `PyInit_` from the shared-object's dynamic symbol table (.dynsym).
//!
//! As a result, the `#[no_mangle] pub unsafe extern "C"` C-ABI bridge
//! functions (`os_b62_encode_i64`, `os_b62_decode_i64`, `os_crc8`, …) are
//! compiled into the `.so` but are **not** reachable via `ctypes.CDLL` /
//! `dlsym`, breaking the Python `native_loader.py` fallback path that lets
//! the interpreter use the Rust extension as a drop-in replacement for the
//! standalone C shared libraries (`os_base62.so`, `os_security.so`).
//!
//! This script writes a *companion* GNU ld version script that explicitly
//! lists the ABI bridge symbols as `global`.  When the linker is invoked with
//! two `--version-script` arguments, it merges the anonymous version node
//! (`{…}`) from each file.  Explicit `global:` entries win over the wildcard
//! `local: *`, so the named symbols end up in `.dynsym` and become accessible
//! to `ctypes.CDLL` at runtime.

fn main() {
    // Emit a rerun-if-changed guard first so incremental builds work.
    println!("cargo:rerun-if-changed=build.rs");

    // The version-script mechanism is only supported on ELF targets.
    // macOS uses a different export list syntax; Windows uses .def files.
    // Both already expose C-ABI symbols without extra configuration.
    let target_os = std::env::var("CARGO_CFG_TARGET_OS").unwrap_or_default();
    if target_os != "linux" && target_os != "android" {
        return;
    }

    let out_dir = std::env::var("OUT_DIR").expect("Cargo must set OUT_DIR");
    let script_path = std::path::PathBuf::from(&out_dir).join("os_abi_exports.ld");

    // The companion version script re-adds each C-ABI bridge symbol to the
    // global export set.  The `local: *;` line here is redundant (PyO3's
    // script already provides it) but makes the file self-contained and safe
    // to use standalone.
    let content = "\
{\n\
  global:\n\
    os_b62_encode_i64;\n\
    os_b62_decode_i64;\n\
    os_crc8;\n\
    os_crc16_ccitt;\n\
    os_crc16_ccitt_pub;\n\
    os_xor_payload;\n\
    os_derive_session_key;\n\
  local: *;\n\
};\n";

    std::fs::write(&script_path, content)
        .expect("failed to write os_abi_exports.ld linker version script");

    println!(
        "cargo:rustc-link-arg=-Wl,--version-script={}",
        script_path.display()
    );
}
