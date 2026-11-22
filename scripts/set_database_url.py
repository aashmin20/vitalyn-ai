"""
Write DATABASE_URL into backend/.env without the password ever appearing in a chat,
a shell history line or a screen.

    python3 scripts/set_database_url.py [project-ref]
    python3 scripts/set_database_url.py --pooler          (asks for the pooler host or region)

It asks for your Supabase database password with hidden input, URL-encodes it (so
characters like @ : / # ? work), and updates only the DATABASE_URL line of
backend/.env (permissions stay 600). Find or reset the password in:
Supabase > Project Settings > Database > Database password.
"""
import getpass
import os
import re
import stat
import sys
from urllib.parse import quote

ENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend", ".env")


def existing_ref() -> str:
    try:
        text = open(ENV).read()
    except FileNotFoundError:
        return ""
    m = (re.search(r"https?://([a-z0-9]{15,25})\.supabase\.co", text)
         or re.search(r"@db\.([a-z0-9]{15,25})\.supabase\.co", text)
         or re.search(r"//postgres\.([a-z0-9]{15,25}):", text))
    return m.group(1) if m else ""


def detect_pooler_host(region_host: str, ref: str, password: str) -> str:
    """For a region-only answer, try the newer aws-1 pooler first, then aws-0, and keep the one that
    knows this project. 'tenant not found' is answered before any password check, so this is safe."""
    m = re.match(r"aws-\d+-(.+)", region_host)
    if not m:
        return region_host
    try:
        import psycopg
    except ImportError:
        return region_host
    for prefix in ("aws-1", "aws-0"):
        host = f"{prefix}-{m.group(1)}"
        try:
            with psycopg.connect(host=host, port=5432, user=f"postgres.{ref}", password=password,
                                 dbname="postgres", connect_timeout=8) as c:
                c.execute("select 1")
            return host
        except Exception as exc:
            if "not found" in str(exc).lower() or "ENOTFOUND" in str(exc):
                continue                       # wrong pooler for this project
            return host                        # right pooler (e.g. wrong password): keep it
    return region_host


def normalise_pooler(text: str):
    """Accept a full pooler host, a host with a user@ or :port around it, or just a region."""
    text = text.strip().lower()
    m = re.search(r"([a-z0-9-]+\.pooler\.supabase\.com)", text)
    if m:
        return m.group(1)
    if re.fullmatch(r"[a-z]{2}-[a-z]+-\d", text):          # e.g. ap-south-1
        return f"aws-0-{text}.pooler.supabase.com"
    return None


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    pooler = None
    if "--pooler" in sys.argv:
        i = sys.argv.index("--pooler")
        given = sys.argv[i + 1].strip() if i + 1 < len(sys.argv) and not sys.argv[i + 1].startswith("--") else ""
        args = [a for a in args if a != given]
        if not given:
            print("Session pooler: find it in Supabase > Connect > Session pooler.")
            given = input("Paste the pooler host (aws-0-....pooler.supabase.com) or just the region (e.g. ap-south-1): ").strip()
        pooler = normalise_pooler(given)
        if pooler is None:
            print("That does not look like a pooler host or region. Nothing changed."); return 1
    ref = (args[0] if args else existing_ref()).strip()
    if not re.fullmatch(r"[a-z0-9]{15,25}", ref):
        ref = input("Supabase project ref (the part before .supabase.co): ").strip()
    if not re.fullmatch(r"[a-z0-9]{15,25}", ref):
        print("That does not look like a project ref."); return 1

    password = getpass.getpass("Supabase database password (hidden): ")
    if not password:
        print("No password entered; nothing changed."); return 1
    if pooler:   # Session pooler: IPv4-friendly, user is postgres.<project-ref>
        pooler = detect_pooler_host(pooler, ref, password)
        url = f"postgresql://postgres.{ref}:{quote(password, safe='')}@{pooler}:5432/postgres"
        where = pooler
    else:
        url = f"postgresql://postgres:{quote(password, safe='')}@db.{ref}.supabase.co:5432/postgres"
        where = f"db.{ref}.supabase.co"

    lines = open(ENV).read().splitlines() if os.path.exists(ENV) else []
    out, replaced = [], False
    for line in lines:
        if re.match(r"\s*DATABASE_URL\s*=", line):
            out.append(f"DATABASE_URL={url}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"DATABASE_URL={url}")
    with open(ENV, "w") as f:
        f.write("\n".join(out) + "\n")
    os.chmod(ENV, stat.S_IRUSR | stat.S_IWUSR)        # 600
    print(f"Saved DATABASE_URL to backend/.env (host {where}). The password was not displayed.")
    print("Next: python3 scripts/check_database.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
