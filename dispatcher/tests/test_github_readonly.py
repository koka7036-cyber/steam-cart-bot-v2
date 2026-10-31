import unittest
from unittest.mock import patch
from dispatcher.github_readonly import fetch_open_issues

class Response:
    status = 200
    def __init__(self, payload): self.payload = payload
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, limit):
        import json
        return json.dumps(self.payload).encode()

class GitHubReadonlyTests(unittest.TestCase):
    @patch("dispatcher.github_readonly.urllib.request.urlopen")
    def test_fetches_and_normalizes_issues(self, urlopen):
        urlopen.return_value = Response([
            {"number": 1, "title": "Add tests", "body": "Task", "state": "open",
             "labels": [{"name": "codex-ready"}], "html_url": "https://github.com/x/y/issues/1"},
            {"number": 2, "title": "PR", "body": "ignored", "state": "open",
             "labels": [], "pull_request": {"url": "https://api.github.com/pulls/2"}},
        ])
        items = fetch_open_issues("owner/repo", token="test-token")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["number"], 1)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertTrue(request.full_url.startswith("https://api.github.com/repos/owner/repo/issues?"))

    def test_rejects_invalid_repository(self):
        with self.assertRaises(ValueError): fetch_open_issues("not-a-repo")

    def test_rejects_unbounded_pagination(self):
        with self.assertRaises(ValueError): fetch_open_issues("owner/repo", max_pages=100)

    def test_rejects_zero_page_size(self):
        with self.assertRaises(ValueError): fetch_open_issues("owner/repo", per_page=0)

    def test_rejects_empty_labels(self):
        with self.assertRaises(ValueError): fetch_open_issues("owner/repo", labels=())

if __name__ == "__main__":
    unittest.main()
