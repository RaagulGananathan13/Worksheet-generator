"""Explicit download and verification of the free local handwriting models.

Run from this project:  python tools/download_model.py
Verify without network: python tools/download_model.py --verify-only

The web application never downloads models. This command uses no API key or
paid service, fetches only the pinned revisions, accepts only safetensors
weights whose SHA-256 matches the value pinned in app/ocr.py, and never runs
remote Python code. Large files are fetched in resumable, checked ranges.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.ocr import ENGINES, engine_path, files_ready

CHUNK = 16 * 1024 * 1024
SMALL_FILE_LIMIT = 64 * 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_url(engine, filename: str) -> str:
    return f"https://huggingface.co/{engine.repo}/resolve/{engine.revision}/{filename}"


def download_small(client, url: str, target: Path) -> None:
    response = client.get(url)
    response.raise_for_status()
    if len(response.content) > SMALL_FILE_LIMIT:
        raise RuntimeError(f"{target.name} is unexpectedly large.")
    temporary = target.with_name(target.name + ".download")
    temporary.write_bytes(response.content)
    temporary.replace(target)


def download_ranges(client, url: str, size: int, target: Path, expected_sha256: str, label: str) -> None:
    """Resumable bounded ranges; the assembled file must match the pinned SHA-256."""
    parts = target.parent / f".parts-{target.name}"
    parts.mkdir(exist_ok=True)
    starts = list(range(0, size, CHUNK))

    def fetch(start: int) -> None:
        end = min(size, start + CHUNK) - 1
        piece = parts / f"{start:012d}"
        if piece.is_file() and piece.stat().st_size == end - start + 1:
            return
        failure = None
        for retry in range(8):
            try:
                with client.stream("GET", url, headers={"Range": f"bytes={start}-{end}"}) as response:
                    response.raise_for_status()
                    if response.status_code != 206:
                        raise RuntimeError("The server did not return the requested byte range.")
                    temporary = piece.with_suffix(".download")
                    written = 0
                    with temporary.open("wb") as handle:
                        for block in response.iter_bytes(1024 * 1024):
                            written += len(block)
                            if written > end - start + 1:
                                raise RuntimeError("A byte range exceeded its declared size.")
                            handle.write(block)
                    if written != end - start + 1:
                        raise RuntimeError("A byte range was incomplete.")
                    temporary.replace(piece)
                    return
            except Exception as error:
                failure = type(error).__name__
                time.sleep(min(20, 2 ** retry))
        raise RuntimeError(f"Download of {label} failed ({failure}). Run the command again to resume.")

    done = 0
    with ThreadPoolExecutor(max_workers=6) as pool:
        for future in as_completed([pool.submit(fetch, start) for start in starts]):
            future.result()
            done += 1
            if done % 20 == 0 or done == len(starts):
                print(f"  {label}: {done}/{len(starts)} parts", flush=True)
    digest = hashlib.sha256()
    temporary = target.with_name(target.name + ".assembling")
    with temporary.open("wb") as output:
        for start in starts:
            data = (parts / f"{start:012d}").read_bytes()
            digest.update(data)
            output.write(data)
    if digest.hexdigest() != expected_sha256:
        temporary.unlink()
        raise RuntimeError(f"{label} failed its pinned SHA-256 check. It was not installed.")
    temporary.replace(target)
    for start in starts:
        (parts / f"{start:012d}").unlink()
    parts.rmdir()


def verify(engine, folder: Path) -> dict:
    hashes = {name: sha256_file(folder / name) for name in engine.files}
    if hashes[engine.weights] != engine.weights_sha256:
        raise RuntimeError(f"{engine.label} weights do not match the pinned SHA-256. Do not use them.")
    from safetensors import safe_open

    with safe_open(str(folder / engine.weights), framework="pt", device="cpu") as tensors:
        tensor_count = len(list(tensors.keys()))
    if tensor_count < 100:
        raise RuntimeError(f"{engine.label} weights appear incomplete.")
    return {"hashes": hashes, "tensor_count": tensor_count}


def install(engine) -> None:
    folder = engine_path(engine)
    if not folder.is_relative_to(ROOT):
        raise RuntimeError("The model directory must be inside automatic grading.")
    folder.mkdir(parents=True, exist_ok=True)
    import httpx

    with httpx.Client(timeout=httpx.Timeout(30, read=120), follow_redirects=True) as client:
        response = client.get(f"https://huggingface.co/api/models/{engine.repo}/revision/{engine.revision}", params={"blobs": "true"})
        response.raise_for_status()
        published = {item["rfilename"]: item for item in response.json().get("siblings", [])}
        for name in engine.files:
            item = published.get(name)
            if item is None:
                raise RuntimeError(f"{engine.label} revision {engine.revision} does not contain {name}.")
            target = folder / name
            if name == engine.weights:
                if (item.get("lfs") or {}).get("sha256") != engine.weights_sha256:
                    raise RuntimeError(f"The published {engine.label} weights differ from the pinned fingerprint.")
                if target.is_file() and target.stat().st_size == item["size"] and sha256_file(target) == engine.weights_sha256:
                    continue
                print(f"Downloading {engine.label} weights ({item['size'] / 1e9:.2f} GB)…", flush=True)
                download_ranges(client, file_url(engine, name), item["size"], target, engine.weights_sha256, f"{engine.label} weights")
            elif not (target.is_file() and target.stat().st_size == item.get("size")):
                download_small(client, file_url(engine, name), target)
    checked = verify(engine, folder)
    manifest = {
        "model": engine.repo, "revision": engine.revision, "license": engine.license,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "sha256": checked["hashes"], "tensor_count": checked["tensor_count"],
    }
    temporary = folder / "verified-model.json.tmp"
    temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    temporary.replace(folder / "verified-model.json")
    print(f"Verified {engine.label}: {checked['tensor_count']} tensors in {folder}", flush=True)


def verify_installed(engine) -> None:
    folder = engine_path(engine)
    if not files_ready(engine, folder):
        raise RuntimeError(f"{engine.label} is not installed or verified. Run python tools/download_model.py.")
    manifest = json.loads((folder / "verified-model.json").read_text(encoding="utf-8"))
    checked = verify(engine, folder)
    if any(checked["hashes"][name] != manifest["sha256"].get(name) for name in engine.files):
        raise RuntimeError(f"{engine.label} files differ from their verified manifest. Run python tools/download_model.py again.")
    print(f"Verified {engine.label}: {checked['tensor_count']} tensors, pinned revision {engine.revision}.", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--verify-only", action="store_true", help="Check installed files without using the network")
    args = parser.parse_args()
    for engine in ENGINES:
        (verify_installed if args.verify_only else install)(engine)
    print("Runtime recognition is offline. Readings are fallible; uncertain answers go to teacher review.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Model setup failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
