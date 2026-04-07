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
//! `lto = "thin"`, several of these symbols are **not** present in
//! `.dynsym` after linking.
//!
//! # Fix
//!
//! We use two per-symbol linker flags:
//!
//!   1. `-Wl,--export-dynamic-symbol=SYM`
//!      Overrides `local: *` in rustc's version-script and ensures the
//!      symbol appears in `.dynsym`.  Both GNU ld (≥ 2.39) and lld
//!      support this flag.
//!
//!   2. `-Wl,--undefined=SYM`
//!      Creates a synthetic linker-level reference, which prevents
//!      thin LTO from eliminating the function body before the linker
//!      can process it.
//!
//! Previous approaches that failed:
//!   - Second anonymous version-script: GNU ld rejects "anonymous
//!     version tag cannot be combined with other version tags".
//!   - `--dynamic-list`: ignored when a version-script with `local: *`
//!     is also present (older binutils).
//!   - Named version-script node (`OSCORE_ABI { … }`): named and
//!     anonymous nodes do not merge; `local: *` still wins.

fn main() {
    println!("cargo:rerun-if-changed=build.rs");

    let target_os = std::env::var("CARGO_CFG_TARGET_OS").unwrap_or_default();
    let target_arch = std::env::var("CARGO_CFG_TARGET_ARCH").unwrap_or_default();
    let target_env = std::env::var("CARGO_CFG_TARGET_ENV").unwrap_or_default();

    eprintln!("[build.rs] target_os={target_os} target_arch={target_arch} target_env={target_env}");

    if target_os != "linux" && target_os != "android" {
        eprintln!("[build.rs] non-ELF target – skipping symbol export flags");
        return;
    }

    // All C-ABI bridge symbols that must be visible via dlsym / ctypes.
    // Symbols behind optional Cargo features (e.g. `worker`) are listed
    // separately so their --undefined flag is only emitted when the
    // feature is active.
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

    #[cfg(feature = "worker")]
    let worker_globals: &[&str] = &[
        "os_worker_create_v1",
        "os_worker_submit_v1",
        "os_worker_destroy_v1",
    ];
    #[cfg(not(feature = "worker"))]
    let worker_globals: &[&str] = &[];

    let all_symbols: Vec<&&str> = extra_globals.iter().chain(worker_globals.iter()).collect();

    for sym in &all_symbols {
        // --export-dynamic-symbol overrides rustc's version-script `local: *`
        println!("cargo:rustc-cdylib-link-arg=-Wl,--export-dynamic-symbol={}", sym);
        // --undefined prevents thin LTO from dropping the function body
        println!("cargo:rustc-cdylib-link-arg=-Wl,--undefined={}", sym);
    }

    eprintln!(
        "[build.rs] emitted --export-dynamic-symbol + --undefined for {} symbols ({} base + {} worker)",
        all_symbols.len(),
        extra_globals.len(),
        worker_globals.len(),
    );
}
