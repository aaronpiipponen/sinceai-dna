# -*- coding: utf-8 -*-
"""Offline tests for the HTTP transport. No network.

    python3 -m unittest app/test_chat.py
"""

import io
import json
import os
import sys
import unittest
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import chat  # noqa: E402

OK = {"choices": [{"message": {"content": "hi"}}]}


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return json.dumps(OK).encode("utf-8")


class FakeClock:
    """Monotonic clock whose sleep advances time, like the real clock."""

    def __init__(self, start=1000.0):
        self.now = start
        self.slept = []

    def monotonic(self):
        return self.now

    def sleep(self, delay):
        self.slept.append(delay)
        self.now += delay


class PostRetryTest(unittest.TestCase):
    def setUp(self):
        self.original_open = chat.urllib.request.urlopen
        self.original_time = chat.time

    def tearDown(self):
        chat.urllib.request.urlopen = self.original_open
        chat.time = self.original_time

    def test_retries_transient_error_but_never_a_timeout(self):
        clock = FakeClock()
        chat.time = clock
        calls = {"n": 0}
        timeouts = []

        def transient(request, timeout):
            calls["n"] += 1
            timeouts.append(timeout)
            if calls["n"] == 1:
                raise urllib.error.HTTPError(
                    "http://x", 503, "busy", None, io.BytesIO(b"busy"))
            return FakeResponse()

        chat.urllib.request.urlopen = transient
        data = chat._post({"model": "m"}, 5)
        self.assertEqual(calls["n"], 2)
        self.assertEqual(timeouts, [5, 4], "a retry gets the remaining budget")
        self.assertEqual(clock.slept, [1])
        self.assertEqual(data["choices"][0]["message"]["content"], "hi")

        clock = FakeClock()
        chat.time = clock
        timeouts = []

        def throttled(request, timeout):
            timeouts.append(timeout)
            if len(timeouts) == 1:
                raise urllib.error.HTTPError(
                    "http://x", 429, "slow down",
                    {"Retry-After": "-3"}, io.BytesIO(b"slow"))
            return FakeResponse()

        chat.urllib.request.urlopen = throttled
        chat._post({"model": "m"}, 5)
        self.assertEqual(len(timeouts), 2)
        self.assertEqual(clock.slept, [0], "a negative Retry-After clamps to zero")

        clock = FakeClock()
        chat.time = clock
        calls["n"] = 0

        def timeout(request, timeout):
            calls["n"] += 1
            raise TimeoutError("timed out")

        chat.urllib.request.urlopen = timeout
        with self.assertRaises(RuntimeError):
            chat._post({"model": "m"}, 5)
        self.assertEqual(calls["n"], 1, "a timeout already spent the budget")
        self.assertEqual(clock.slept, [])

    def test_exhausted_budget_stops_retry_instead_of_sleeping(self):
        clock = FakeClock()
        chat.time = clock
        calls = {"n": 0}

        def busy(request, timeout):
            calls["n"] += 1
            raise urllib.error.HTTPError(
                "http://x", 503, "busy", None, io.BytesIO(b"busy"))

        chat.urllib.request.urlopen = busy
        with self.assertRaises(RuntimeError):
            chat._post({"model": "m"}, 0.5)
        self.assertEqual(calls["n"], 1)
        self.assertEqual(clock.slept, [], "no sleep when the backoff cannot fit")


if __name__ == "__main__":
    unittest.main()
