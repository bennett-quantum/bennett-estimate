//! Independent ISA estimator using Python's arbitrary-precision rational engine.
use std::io::Write;
use std::process::{Command, Stdio};

pub fn run(args: &[String]) -> std::io::Result<std::process::ExitStatus> {
    let mut child = Command::new("python3")
        .args(["-I", "-"])
        .args(args)
        .stdin(Stdio::piped())
        .spawn()?;
    let mut input = child.stdin.take().expect("piped stdin");
    let source = concat!(
        "CATALOG_TEXT = r'''",
        include_str!("../data/ref-0.9.json"),
        "'''\n",
        include_str!("estimate.py")
    );
    input.write_all(source.as_bytes())?;
    drop(input);
    child.wait()
}
