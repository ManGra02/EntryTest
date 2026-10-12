"""Check pinned requirements (name==version) against the PyPI JSON API."""

import json
import sys
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

PYPI_URL = "https://pypi.org/pypi"


def parse_requirements(path):
    """Return a list of (name, version) tuples from a requirements-style file."""
    requirements = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            name, sep, version = line.partition("==")
            requirements.append((name.strip(), version.strip() if sep else ""))
    return requirements


def fetch_json(url):
    """Return the decoded JSON at url, or None if PyPI answers 404."""
    request = Request(url, headers={"User-Agent": "check-requirements/1.0"})
    try:
        with urlopen(request, timeout=15) as response:
            return json.load(response)
    except HTTPError as e:
        if e.code == 404:
            return None
        raise


def check_dependency(name, version):
    """Return (status, upload_time).

    status is "missing_package", "missing_version" or "ok". upload_time is the
    upload_time of the first file listed under "urls" (None if there is none).
    """
    if fetch_json(f"{PYPI_URL}/{quote(name)}/json") is None:
        return "missing_package", None
    if not version:
        return "missing_version", None
    data = fetch_json(f"{PYPI_URL}/{quote(name)}/{quote(version)}/json")
    if data is None:
        return "missing_version", None
    urls = data.get("urls") or []
    return "ok", urls[0].get("upload_time") if urls else None


def check_file(path):
    """Check every requirement in path and return a summary dict."""
    summary = {"checked": 0, "missing_packages": 0, "missing_versions": 0, "oldest": None}
    for name, version in parse_requirements(path):
        summary["checked"] += 1
        status, upload_time = check_dependency(name, version)
        if status == "missing_package":
            summary["missing_packages"] += 1
        elif status == "missing_version":
            summary["missing_versions"] += 1
        elif upload_time and (summary["oldest"] is None or upload_time < summary["oldest"][2]):
            # upload_time is ISO 8601, so string comparison orders chronologically
            summary["oldest"] = (name, version, upload_time)
    return summary


def format_summary(summary):
    oldest = summary["oldest"]
    oldest_text = f"{oldest[0]}=={oldest[1]} ({oldest[2][:4]})" if oldest else "None"
    return "\n".join([
        f"Dependencies Checked: {summary['checked']}",
        f"Packages not on PyPI: {summary['missing_packages']}",
        f"Versions not on PyPI: {summary['missing_versions']}",
        f"Oldest pinned release: {oldest_text}",
    ])


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    path = argv[0] if argv else "requirements.txt"
    print(format_summary(check_file(path)))


if __name__ == "__main__":
    main()
