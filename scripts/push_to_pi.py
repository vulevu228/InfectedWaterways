"""Push web/ to the Pi (/mnt/ssd/waterways/web/site) and the server code (/home/emir/waterways).
Text files get a pre-gzipped twin (x.geojson -> x.geojson.gz) that waterways_web.py sends as is.
Run: .venv/Scripts/python scripts/push_to_pi.py [--server]
"""
import gzip
import io
import pathlib
import subprocess
import sys
import tarfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEXT = {".html", ".js", ".css", ".json", ".geojson", ".svg"}


def main():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", compresslevel=1) as tar:
        for f in sorted((ROOT / "web").rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(ROOT / "web").as_posix()
            tar.add(f, arcname=rel)
            if f.suffix in TEXT and f.stat().st_size > 1024:
                gz = gzip.compress(f.read_bytes(), 9, mtime=0)
                info = tarfile.TarInfo(rel + ".gz")
                info.size, info.mtime = len(gz), int(f.stat().st_mtime)
                tar.addfile(info, io.BytesIO(gz))
    data = buf.getvalue()
    subprocess.run(["ssh", "pi", "mkdir -p /mnt/ssd/waterways/web/site && tar -C /mnt/ssd/waterways/web/site -xzf -"], input=data, check=True)
    print(f"web pushed ({len(data) / 1e6:.1f} MB)")
    if "--server" in sys.argv:
        subprocess.run(["scp", "-q", str(ROOT / "pi/web/waterways_web.py"), "pi:/home/emir/waterways/pi/web/"], check=True)
        subprocess.run(["ssh", "pi", "sudo -n systemctl restart waterways-web"], check=True)
        print("server restarted")


if __name__ == "__main__":
    main()
