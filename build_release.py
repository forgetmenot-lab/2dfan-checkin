"""Build a reproducible, allowlisted public distribution (no local secrets)."""
from pathlib import Path
import hashlib
import re
import zipfile

ROOT = Path(__file__).resolve().parent
FILES = (
    "VERSION", "LICENSE", "README.md", "INSTALL_GUIDE_KO.md", "CHANGELOG.md",
    "RELEASE_NOTES.md", "Dockerfile", ".dockerignore", ".env.example",
    "docker-compose.yml", "main.py", "api.py", "results.py", "notify.py",
    "entrypoint.sh", "run-nas.sh", "run-scheduler.sh",
)


def build():
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", version):
        raise ValueError("Invalid VERSION")
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    archive = output / f"2dfan-auto-checkin-v{version}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as bundle:
        for name in sorted(FILES):
            # Normalize Windows checkouts so shell scripts also run on NAS.
            content = (ROOT / name).read_text(encoding="utf-8-sig").replace("\r\n", "\n")
            info = zipfile.ZipInfo(f"2dfan-nas/{name}", date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (0o100644 << 16)
            bundle.writestr(info, content.encode("utf-8"))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / "SHA256SUMS.txt").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    print(f"Built {archive.name} ({archive.stat().st_size} bytes)")
    print(f"SHA256: {digest}")


if __name__ == "__main__":
    build()
