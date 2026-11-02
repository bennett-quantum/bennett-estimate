fn suite(group: &str) {
    let status = std::process::Command::new("python3")
        .args(["-I", "-B", "tests/run_suite.py", group])
        .current_dir(env!("CARGO_MANIFEST_DIR"))
        .env(
            "BENNETT_ESTIMATE_BIN",
            env!("CARGO_BIN_EXE_bennett-estimate"),
        )
        .status()
        .expect("Python 3 is required by the exact arithmetic engine");
    assert!(status.success(), "spec-derived Python tests failed");
}

#[test]
fn object_and_resource_tests() {
    suite("objects");
}

#[test]
fn scheduled_accounting_tests() {
    suite("accounting");
}

#[test]
fn published_selector_tests() {
    suite("selectors");
}

#[test]
fn remaining_discovered_tests() {
    suite("other");
}
