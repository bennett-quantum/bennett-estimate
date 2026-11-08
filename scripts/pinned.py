"""Resolve published test inputs only at the commits in gate.toml."""
from pathlib import Path
import os
import tomllib


def revision(path):
    marker = path / ".gate-pin"
    if marker.is_file():
        return marker.read_text().strip()
    metadata = path / ".git"
    if metadata.is_file():
        metadata = Path(metadata.read_text().strip().removeprefix("gitdir: "))
        if not metadata.is_absolute():
            metadata = path / metadata
    head = metadata / "HEAD"
    return head.read_text().strip() if head.is_file() else "unknown"


def sibling(root, name):
    root = Path(root)
    pin = tomllib.loads((root / "gate.toml").read_text())["siblings"][name]
    sha = pin["sha"]
    candidates = [root / ".tmp/gate/cache" / f"{name}@{sha[:12]}" / name,
                  root / ".tmp/gate-siblings" / f"{name}@{sha}"]
    layout = os.environ.get("BENNETT_GATE_LAYOUT")
    if layout:
        candidates.insert(0, Path(layout) / name)
    # A gate's clean checkout can share the main checkout's immutable cache.
    metadata = root / ".git"
    if metadata.is_file():
        directory = Path(metadata.read_text().strip().removeprefix("gitdir: "))
        if not directory.is_absolute():
            directory = root / directory
        common = directory / "commondir"
        if common.is_file():
            main = (directory / common.read_text().strip()).resolve().parent
            candidates.append(main / ".tmp/gate/cache" / f"{name}@{sha[:12]}" / name)
    for path in candidates:
        if path.is_dir():
            actual = revision(path)
            if actual != sha:
                raise RuntimeError(f"{name}@{sha}: checkout revision {actual}")
            for relative, expected in pin.get("files", {}).items():
                import hashlib
                actual = hashlib.sha256((path / relative).read_bytes()).hexdigest()
                if actual != expected:
                    raise RuntimeError(f"{name}@{sha}: {relative} hash {actual}, expected {expected}")
            return path
    tried = ", ".join(str(path) for path in candidates)
    raise RuntimeError(f"missing gate pin {name}@{sha}; tried: {tried}; populate the gate cache")
