import sys
import types
import unittest
from unittest import mock

from platforms.chatgpt.sentinel_browser import get_sentinel_token_via_browser


class _FakePage:
    def goto(self, *args, **kwargs):
        return None

    def wait_for_function(self, *args, **kwargs):
        return None

    def evaluate(self, *args, **kwargs):
        return {"success": True, "token": '{"p":"ok","t":"ok","c":"ok"}'}


class _FakeContext:
    def __init__(self):
        self.cookies = None

    def add_cookies(self, cookies):
        self.cookies = cookies

    def new_page(self):
        return _FakePage()


class _FakeBrowser:
    def __init__(self):
        self.context = _FakeContext()

    def new_context(self, **kwargs):
        return self.context

    def close(self):
        return None


class _FakePlaywrightManager:
    def __init__(self):
        self.browser = _FakeBrowser()
        self.chromium = types.SimpleNamespace(launch=lambda **kwargs: self.browser)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class SentinelBrowserTests(unittest.TestCase):
    def test_device_id_cookie_uses_url_shape_for_auth_openai(self):
        fake_manager = _FakePlaywrightManager()
        fake_sync_api = types.ModuleType("playwright.sync_api")
        fake_sync_api.sync_playwright = lambda: fake_manager
        fake_playwright = types.ModuleType("playwright")
        fake_playwright.sync_api = fake_sync_api

        with (
            mock.patch.dict(
                sys.modules,
                {
                    "playwright": fake_playwright,
                    "playwright.sync_api": fake_sync_api,
                },
            ),
            mock.patch(
                "platforms.chatgpt.sentinel_browser.resolve_browser_headless",
                return_value=(True, "test"),
            ),
            mock.patch(
                "platforms.chatgpt.sentinel_browser.ensure_browser_display_available"
            ),
        ):
            token = get_sentinel_token_via_browser(
                flow="authorize_continue",
                device_id="device-fixed",
            )

        self.assertEqual(token, '{"p":"ok","t":"ok","c":"ok"}')
        self.assertEqual(len(fake_manager.browser.context.cookies), 1)
        cookie = fake_manager.browser.context.cookies[0]
        self.assertEqual(cookie["url"], "https://auth.openai.com/")
        self.assertNotIn("path", cookie)
        self.assertNotIn("domain", cookie)


if __name__ == "__main__":
    unittest.main()
