"""Small CBDB JSON API client with local cache."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


class CBDBClient:
    """Look up people by name through CBDB's public JSON endpoint."""

    base_url = "https://cbdb.fas.harvard.edu/cbdbapi/person.php"

    def __init__(self, cache_dir: Path, offline: bool = True, delay_seconds: float = 0.5):
        self.cache_dir = cache_dir
        self.offline = offline
        self.delay_seconds = delay_seconds
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def lookup_person(self, name: str) -> dict[str, Any] | None:
        key = self.cache_dir / f"name_{urllib.parse.quote(name, safe='')}.json"
        if key.exists():
            return json.loads(key.read_text(encoding="utf-8"))
        if self.offline:
            return None

        url = f"{self.base_url}?{urllib.parse.urlencode({'name': name, 'o': 'json'})}"
        try:
            with urllib.request.urlopen(url, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return None

        key.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(self.delay_seconds)
        return data

    @staticmethod
    def parse_person(data: dict[str, Any] | None) -> dict[str, Any] | None:
        """Extract a compact link object from a CBDB person response."""

        if not data:
            return None
        try:
            person = data["Package"]["PersonAuthority"]["PersonInfo"]["Person"]
        except (KeyError, TypeError):
            return None

        if isinstance(person, list):
            person = person[0] if person else None
        if not isinstance(person, dict):
            return None

        basic = person.get("BasicInfo") or {}
        person_id = basic.get("PersonId") or basic.get("PersonID") or basic.get("c_personid")
        name = basic.get("ChName") or basic.get("Name") or basic.get("c_name_chn")
        if not (person_id or name):
            return None
        url = None
        if person_id:
            url = f"{CBDBClient.base_url}?id={urllib.parse.quote(str(person_id))}&o=json"
        return {
            "source": "CBDB",
            "id": person_id,
            "name": name,
            "url": url,
        }


def cbdb_name_url(name: str) -> str:
    return f"{CBDBClient.base_url}?{urllib.parse.urlencode({'name': name, 'o': 'json'})}"
