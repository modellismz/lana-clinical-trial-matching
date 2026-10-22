"""Check publication links, approved assets and frozen source integrity."""
from pathlib import Path
import ast
import hashlib
import json
import re
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = json.loads((ROOT / "assets/manifest.json").read_text())
    assert manifest["primary_asset_count"] == len(manifest["assets"]) == 11
    for row in manifest["assets"]:
        path = ROOT / row["file"]
        assert path.exists(), row["file"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"], row["file"]
    kernel = ROOT / "research/medgemma-kernel"
    hashes = json.loads((kernel / "source-manifest.json").read_text())
    protocol = json.loads((ROOT / "benchmarks/results/confirmation-665/protocol.json").read_text())
    for name, expected in hashes.items():
        assert hashlib.sha256((kernel / name).read_bytes()).hexdigest() == expected == protocol["code_sha256"][name]

    links = 0
    for path in ROOT.rglob("*.md"):
        if ".venv" in path.parts or ".git" in path.parts:
            continue
        text = path.read_text()
        targets = re.findall(r"!?\[[^\]]*\]\(([^\s)]+)(?:\s+[^)]*)?\)", text)
        targets += re.findall(r'(?:href|src)="([^"#]+)"', text)
        for target in targets:
            target = target.strip("<>")
            if urlsplit(target).scheme or target.startswith("#"):
                continue
            target = unquote(target.split("#", 1)[0].split("?", 1)[0])
            assert (path.parent / target).exists(), f"Broken link: {path.relative_to(ROOT)} -> {target}"
            links += 1

    # Report filenames, never credential values.
    patterns = [r"sk-(?:proj-|or-v1-)[A-Za-z0-9_-]{20,}", r"gh[pousr]_[A-Za-z0-9]{30,}", r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"]
    files = 0
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or ".venv" in path.parts:
            continue
        assert path.stat().st_size < 10_000_000, f"Unexpected large file: {path.relative_to(ROOT)}"
        assert path.suffix not in {".key", ".pem", ".safetensors", ".pth", ".pt", ".ckpt", ".zip"}, path.name
        if path.suffix in {".py", ".md", ".json", ".jsonl", ".txt", ".html", ".js", ".mjs", ".yml", ".yaml", ".csv", ".svg", ".mmd"}:
            text = path.read_text()
            for pattern in patterns:
                assert not re.search(pattern, text), f"Possible credential in {path.relative_to(ROOT)}"
        if path.suffix == ".py":
            ast.parse(path.read_text(), filename=str(path))
        if path.suffix == ".json":
            json.loads(path.read_text())
        files += 1
    print(f"Checked {files} files, {links} local documentation links, 11 approved images and {len(hashes)} frozen kernel files.")


if __name__ == "__main__":
    main()
