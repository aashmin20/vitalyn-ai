"""
Write SUPABASE_URL and SUPABASE_ANON_KEY (staff sign-in) into backend/.env.

    python3 scripts/set_supabase_auth.py

Both values are on Supabase > Project Settings > API (Project URL, and the PUBLIC "anon" /
publishable key). Never paste the service_role / secret key: VITALYN does not need it.
The key is read with hidden input. Only these two lines of backend/.env change.
"""
import getpass
import os
import re
import stat

ENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend", ".env")


def set_line(text: str, key: str, value: str) -> str:
    line = f"{key}={value}"
    if re.search(rf"^{key}=.*$", text, flags=re.M):
        return re.sub(rf"^{key}=.*$", lambda _: line, text, flags=re.M)
    return text + ("" if text.endswith("\n") or not text else "\n") + line + "\n"


def main() -> None:
    url = input("Supabase Project URL (https://<ref>.supabase.co): ").strip().rstrip("/")
    if not re.match(r"^https://[a-z0-9]+\.supabase\.co$", url):
        raise SystemExit("That does not look like a Supabase project URL.")
    key = getpass.getpass("anon / publishable key (hidden): ").strip()
    if not key or key.startswith("sb_secret_"):
        raise SystemExit("Use the public anon / publishable key, not a secret key.")
    try:
        text = open(ENV).read()
    except FileNotFoundError:
        text = ""
    text = set_line(set_line(text, "SUPABASE_URL", url), "SUPABASE_ANON_KEY", key)
    with open(ENV, "w") as f:
        f.write(text)
    os.chmod(ENV, stat.S_IRUSR | stat.S_IWUSR)
    print("Saved. Restart the backend, then sign up in the app and run scripts/make_admin.py <email>.")


if __name__ == "__main__":
    main()
