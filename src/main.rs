fn main() {
    match bennett_estimate::run(&std::env::args().skip(1).collect::<Vec<_>>()) {
        Ok(status) => std::process::exit(status.code().unwrap_or(1)),
        Err(error) => {
            eprintln!("bennett-estimate: {error}");
            std::process::exit(1);
        }
    }
}
