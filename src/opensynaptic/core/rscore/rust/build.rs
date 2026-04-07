//! Build script for opensynaptic_rscore.
//!
//! # Problem
//!
//! On ELF / Linux targets the Rust compiler (`rustc`) generates its own
//! linker version-script for `cdylib` crates.  That script contains an
//! anonymous node of the form:
//!
//! ```text
//! {
//!     global:
//!         PyInit_opensynaptic_rscore;
//!         /* …other exported Rust symbols… */
//!     local:
//!         *;
//! };
//! ```
//!
//! `local: *` hides every symbol not explicitly listed in `global:`.
//! Whether the `#[no_mangle] pub extern "C"` C-ABI bridge functions
//! (like `os_b62_encode_i64`) end up in `global:` depends on how `rustc`
//! resolves "exported symbols" for the cdylib – and in practice, under
//! `lto = "thin"` on manylinux2014 (binutils ≤ 2.35), several of these
//! symbols are **not** present in `.dynsym` after linking.
//!
//! # Fix
//!
//! We emit an additional **anonymous** GNU ld version-script that
//! explicitly lists every C-ABI symbol in its `global:` section.
//!
//! When GNU ld encounters multiple anonymous version-script nodes it
//! **merges** them: a symbol is global if it appears in `global:` in
//! *any* of the anonymous nodes, regardless of `local: *` in other
//! nodes.  This guarantees our symbols end up in `.dynsym`.
//!
//! Previous approaches that failed:
//!   - `--dynamic-list`: ignored by older binutils when a version-script
//!     with `local: *` is also present.
//!   - Named version-script node (`OSCORE_ABI { … }`): named and
//!     anonymous nodes do not merge the same way; `local: *` still wins.

fn main() {
    println!("cargo:rerun-if-changed=build.rs");

    let target_os = std::env::var("CARGO_CFG_TARGET_OS").unwrap_or_default();
    let target_arch = std::env::var("CARGO_CFG_TARGET_ARCH").unwrap_or_default();
    let target_env = std::env::var("CARGO_CFG_TARGET_ENV").unwrap_or_default();

    eprintln!("[build.rs] target_os={target_os} target_arch={target_arch} target_env={target_env}");

    if target_os != "linux" && target_os != "android" {
        eprintln!("[build.rs] non-ELF target – skipping version-script emission");
        return;
    }

    let out_dir = std::env::var("OUT_DIR").expect("Cargo must set OUT_DIR");
    let out_path = std::path::PathBuf::from(&out_dir);

    // All C-ABI bridge symbols that must be visible via dlsym / ctypes.
    // NOTE: symbols behind optional Cargo features (e.g. `worker`) are listed
    // separately so their --undefined flag is only emitted when the feature is
    // active (otherwise the linker would fail with an unresolved symbol error).
    let extra_globals: &[&str] = &[
        // os_base62
        "os_b62_encode_i64",
        "os_b62_decode_i64",
        // os_security
        "os_crc8",
        "os_crc16_ccitt",
        "os_crc16_ccitt_pub",
        "os_xor_payload",
        "os_derive_session_key",
        // command helpers
        "os_cmd_is_data",
        "os_cmd_normalize_data",
        "os_cmd_secure_variant",
        // protocol / parsing
        "os_parse_header_min",
        "os_auto_decompose_input",
        // compressor
        "os_compressor_create_v1",
        "os_compressor_free_v1",
        "os_compress_fact_v1",
        // fusion state
        "os_fusion_state_create_v1",
        "os_fusion_state_free_v1",
        "os_fusion_state_seed_v1",
        "os_fusion_state_apply_v1",
        "os_fusion_state_receive_apply_v1",
        // version
        "os_rscore_version",
        // JSON APIs
        "os_fusion_run_json_v1",
        "os_fusion_decompress_json_v1",
        "os_fusion_relay_json_v1",
        "os_node_ensure_id_json_v1",
        "os_node_transmit_json_v1",
        "os_node_dispatch_json_v1",
        "os_pipeline_batch_v1",
        // misc
        "os_standardize_json_v1",
        "os_handshake_negotiate_v1",
        "os_transporter_send_v1",
        "os_transporter_listen_v1",
    ];

    // Worker pool symbols – only present when the `worker` Cargo feature is
    // enabled.  Including them unconditionally in --undefined would cause a
    // linker error when the feature is off.
    #[cfg(feature = "worker")]
    let worker_globals: &[&str] = &[
        "os_worker_create_v1",
        "os_worker_submit_v1",
        "os_worker_destroy_v1",
    ];
    #[cfg(not(feature = "worker"))]
    let worker_globals: &[&str] = &[];

    // Write an anonymous version-script that forces our symbols into
    // the merged `global:` set.  Include worker symbols in the
    // version-script unconditionally (listing a nonexistent symbol in
    // `global:` is harmless — the linker just ignores it).
    let vs_path = out_path.join("os_abi_exports.ver");
    let mut content = String::from("{\n    global:\n");
    for sym in extra_globals.iter().chain(worker_globals.iter()) {
        content.push_str(&format!("        {};\n", sym));
    }
    content.push_str("};\n");

    let all_count = extra_globals.len() + worker_globals.len();

    std::fs::write(&vs_path, &content)
        .expect("failed to write version-script");

    eprintln!("[build.rs] wrote version-script to {}", vs_path.display());
    eprintln!("[build.rs] version-script content ({} symbols):\n{}", all_count, content);

    println!(
        "cargo:rustc-cdylib-link-arg=-Wl,--version-script={}",
        vs_path.display()
    );

    // Force the linker to keep every C-ABI symbol via --undefined.
    //
    // The version-script marks them `global:` but thin LTO can eliminate
    // unreachable function bodies *before* the linker processes the
    // version-script.  --undefined creates a synthetic reference from
    // the link root, preventing LTO from dropping the symbol.
    for sym in extra_globals.iter().chain(worker_globals.iter()) {
        println!("cargo:rustc-cdylib-link-arg=-Wl,--undefined={}", sym);
    }
    eprintln!("[build.rs] emitted --undefined for {} symbols", all_count);

    eprintln!(
        "[build.rs] emitted: cargo:rustc-cdylib-link-arg=-Wl,--version-script={}",
        vs_path.display()
    );
}
