# -*- coding: utf-8 -*-
"""Raw model reply cache.

Every model reply is stored on disk, keyed by exactly what was sent: the
messages, the model, the temperature and the reasoning mode. The same prompt
never pays for a second call, so normaliser changes rescore a full run offline
in seconds.

    key = cache.key(messages, model, temperature, thinking)
    hit = cache.get(key)          # dict or None
    cache.put(key, {...})

Entries live in cache/raw/<key[:2]>/<key>.json at the project root
(git-ignored). Set DNA_CACHE_DIR to move it. Standard library only.
"""

import hashlib
import json
import os
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("DNA_CACHE_DIR") or os.path.join(os.path.dirname(HERE), "cache", "raw")


def prompt_hash(messages):
    """Hash of the messages alone, for provenance in reports."""
    blob = json.dumps(messages, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def key(messages, model, temperature, thinking="on"):
    blob = json.dumps({"m": messages, "model": model, "t": temperature, "thinking": thinking},
                      ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _path(k):
    return os.path.join(ROOT, k[:2], k + ".json")


def get(k):
    try:
        with open(_path(k), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def put(k, entry):
    """Write atomically so parallel workers never leave half a file."""
    path = _path(k)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(entry, fh, ensure_ascii=False)
    os.replace(tmp, path)
