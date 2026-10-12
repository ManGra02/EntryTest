import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import check_requirements as cr

BASE = cr.PYPI_URL

# Canned PyPI responses keyed by URL; any other URL answers 404.
FAKE_PYPI = {
    f"{BASE}/requests/json": {"info": {"name": "requests"}},
    f"{BASE}/requests/2.31.0/json": {"urls": [{"upload_time": "2023-05-22T15:12:42"}]},
    f"{BASE}/numpy/json": {"info": {"name": "numpy"}},
    f"{BASE}/numpy/1.16.0/json": {
        "urls": [{"upload_time": "2019-01-14T02:15:33"}, {"upload_time": "2010-01-01T00:00:00"}]
    },
    f"{BASE}/flask/json": {"info": {"name": "flask"}},
    f"{BASE}/nofiles/json": {"info": {"name": "nofiles"}},
    f"{BASE}/nofiles/0.1/json": {"urls": []},
}


def fake_urlopen(request, timeout=None):
    url = request.full_url
    if url not in FAKE_PYPI:
        raise HTTPError(url, 404, "Not Found", None, None)
    return io.BytesIO(json.dumps(FAKE_PYPI[url]).encode())


def write_temp(content):
    f = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


class ParseTests(unittest.TestCase):
    def test_skips_blank_lines_and_comments(self):
        path = write_temp("# header\n\n  requests==2.31.0  \nnumpy == 1.16.0 # pinned\n")
        self.addCleanup(os.remove, path)
        self.assertEqual(
            cr.parse_requirements(path), [("requests", "2.31.0"), ("numpy", "1.16.0")]
        )


@mock.patch("check_requirements.urlopen", side_effect=fake_urlopen)
class CheckTests(unittest.TestCase):
    def test_counts_and_oldest(self, _):
        path = write_temp(
            "requests==2.31.0\n"
            "flask==1.3.0\n"          # package exists, version does not
            "\n"
            "# comment\n"
            "huggingface-cli==0.1.0\n"  # package does not exist
            "numpy==1.16.0\n"
            "nofiles==0.1\n"          # exists but has no files -> ignored for oldest
        )
        self.addCleanup(os.remove, path)
        summary = cr.check_file(path)
        self.assertEqual(summary["checked"], 5)
        self.assertEqual(summary["missing_packages"], 1)
        self.assertEqual(summary["missing_versions"], 1)
        # Uses the FIRST file under urls (2019), not the earliest one (2010)
        self.assertEqual(summary["oldest"], ("numpy", "1.16.0", "2019-01-14T02:15:33"))

    def test_printed_output(self, _):
        path = write_temp("requests==2.31.0\nflask==1.3.0\nhuggingface-cli==0.1.0\nnumpy==1.16.0\n")
        self.addCleanup(os.remove, path)
        out = io.StringIO()
        with redirect_stdout(out):
            cr.main([path])
        self.assertEqual(
            out.getvalue(),
            "Dependencies Checked: 4\n"
            "Packages not on PyPI: 1\n"
            "Versions not on PyPI: 1\n"
            "Oldest pinned release: numpy==1.16.0 (2019)\n",
        )

    def test_no_valid_dependency(self, _):
        path = write_temp("huggingface-cli==0.1.0\n")
        self.addCleanup(os.remove, path)
        out = io.StringIO()
        with redirect_stdout(out):
            cr.main([path])
        self.assertIn("Oldest pinned release: None", out.getvalue())


def pypi_reachable():
    try:
        urlopen(f"{BASE}/pip/json", timeout=5).close()
        return True
    except (URLError, OSError):
        return False


@unittest.skipUnless(pypi_reachable(), "PyPI not reachable")
class LiveTests(unittest.TestCase):
    def test_sample_requirements_against_real_pypi(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.txt")
        out = io.StringIO()
        with redirect_stdout(out):
            cr.main([path])
        self.assertEqual(
            out.getvalue(),
            "Dependencies Checked: 5\n"
            "Packages not on PyPI: 1\n"
            "Versions not on PyPI: 1\n"
            "Oldest pinned release: numpy==1.16.0 (2019)\n",
        )

    def test_second_requirements_against_real_pypi(self):
        # pandas 0.99.0 was never released; beatifulsoup4 (typo),
        # langchain-agents-toolkit and openai-function-caller are not on PyPI.
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements2.txt")
        out = io.StringIO()
        with redirect_stdout(out):
            cr.main([path])
        self.assertEqual(
            out.getvalue(),
            "Dependencies Checked: 8\n"
            "Packages not on PyPI: 3\n"
            "Versions not on PyPI: 1\n"
            "Oldest pinned release: six==1.10.0 (2015)\n",
        )


if __name__ == "__main__":
    unittest.main()
