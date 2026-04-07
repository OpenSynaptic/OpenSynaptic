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
    if target_os != "linux" && target_os != "android" {
        return;
    }

    let out_dir = std::env::var("OUT_DIR").expect("Cargo must set OUT_DIR");
    let out_path = std::path::PathBuf::from(&out_dir);

    // All C-ABI bridge symbols that must be visible via dlsym / ctypes.
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
        // worker pool
        "os_worker_create_v1",
        "os_worker_submit_v1",
        "os_worker_destroy_v1",
        // misc
        "os_standardize_json_v1",
        "os_handshake_negotiate_v1",
        "os_transporter_send_v1",
        "os_transporter_listen_v1",
    ];

    // Write an anonymous version-script that forces our symbols into
    // the merged `global:` set.
    let vs_path = out_path.join("os_abi_exports.ver");
    let mut content = String::from("{\n    global:\n");
    for sym in extra_globals {
        content.push_str(&format!("        {};\n", sym));
    }
    content.push_str("};\n");

    std::fs::write(&vs_path, &content)
        .expect("failed to write version-script");

    println!(
        "cargo:rustc-cdylib-link-arg=-Wl,--version-script={}",
        vs_path.display()
    );
}
