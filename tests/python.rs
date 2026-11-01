#[test]
fn specification_tests() {
    let status = std::process::Command::new("python3")
        .args(["-I", "-B", "tests/test_estimate.py"])
        .current_dir(env!("CARGO_MANIFEST_DIR"))
        .env(
            "BENNETT_ESTIMATE_BIN",
            env!("CARGO_BIN_EXE_bennett-estimate"),
        )
        .status()
        .expect("Python 3 is required by the exact arithmetic engine");
    assert!(status.success(), "spec-derived Python tests failed");
}
