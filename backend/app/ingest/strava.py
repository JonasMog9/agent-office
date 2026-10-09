"""Strava API client and activity → workout mapping.

Strava's read limit is 100 requests per 15 minutes and 1,000 per day, per app. The 15-minute
window resets on the quarter hour and the daily one at midnight UTC. On a 429 the client waits
for the next quarter hour and retries; past the daily cap it raises ``RateLimited(daily=True)``
so a backfill can stop and resume later.
"""

import time
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

import httpx

from app.config import get_settings

BASE = "https://www.strava.com"
API = f"{BASE}/api/v3"
SCOPES = "read,activity:read_all"
STREAM_KEYS = "time,distance,heartrate,velocity_smooth,cadence,altitude,watts,grade_smooth,moving"


class StravaError(Exception):
    pass


class RateLimited(StravaError):
    def __init__(self, daily: bool) -> None:
        super().__init__("Strava daily rate limit reached" if daily else "Strava rate limited")
        self.daily = daily


def _over_daily_limit(response: httpx.Response) -> bool:
    for usage_h, limit_h in (
        ("X-ReadRateLimit-Usage", "X-ReadRateLimit-Limit"),
        ("X-RateLimit-Usage", "X-RateLimit-Limit"),
    ):
        try:
            used = int(response.headers[usage_h].split(",")[1])
            cap = int(response.headers[limit_h].split(",")[1])
        except (KeyError, IndexError, ValueError):
            continue
        if used >= cap:
            return True
    return False


class StravaClient:
    def __init__(
        self,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.time,
        max_waits: int = 3,
    ) -> None:
        self.http = http or httpx.Client(timeout=30)
        self.sleep = sleep
        self.now = now
        self.max_waits = max_waits
        # Called with the epoch time it will resume at, just before waiting out a rate limit.
        self.on_wait: Callable[[float], None] | None = None

    def _request(
        self, method: str, url: str, token: str | None = None, **kw: Any
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        for _ in range(self.max_waits + 1):
            response = self.http.request(method, url, headers=headers, **kw)
            if response.status_code != 429:
                return response
            if _over_daily_limit(response):
                raise RateLimited(daily=True)
            wait = 900 - (self.now() % 900) + 5  # until just past the next quarter hour
            if self.on_wait:
                self.on_wait(self.now() + wait)
            self.sleep(wait)
        raise RateLimited(daily=False)

    def _json(self, response: httpx.Response) -> Any:
        if response.status_code >= 400:
            raise StravaError(f"Strava {response.status_code}: {response.text[:300]}")
        return response.json()

    # --- OAuth -----------------------------------------------------------------------------
    def _token(self, **data: str) -> dict:
        s = get_settings()
        data |= {"client_id": s.strava_client_id, "client_secret": s.strava_client_secret}
        return self._json(self._request("POST", f"{BASE}/oauth/token", data=data))

    def exchange_code(self, code: str) -> dict:
        return self._token(code=code, grant_type="authorization_code")

    def refresh(self, refresh_token: str) -> dict:
        return self._token(refresh_token=refresh_token, grant_type="refresh_token")

    # --- activities ------------------------------------------------------------------------
    def list_activities(self, token: str, after: int, page: int, per_page: int = 100) -> list:
        params = {"after": after, "page": page, "per_page": per_page}
        r = self._request("GET", f"{API}/athlete/activities", token, params=params)
        return self._json(r)

    def get_activity(self, token: str, activity_id: int) -> dict | None:
        r = self._request("GET", f"{API}/activities/{activity_id}", token)
        return None if r.status_code == 404 else self._json(r)

    def get_streams(self, token: str, activity_id: int) -> dict:
        params = {"keys": STREAM_KEYS, "key_by_type": "true"}
        r = self._request("GET", f"{API}/activities/{activity_id}/streams", token, params=params)
        if r.status_code == 404:
            return {}
        return {key: s.get("data", []) for key, s in self._json(r).items()}

    # --- webhook subscription (one per app) --------------------------------------------------
    def _app_auth(self) -> dict:
        s = get_settings()
        return {"client_id": s.strava_client_id, "client_secret": s.strava_client_secret}

    def list_subscriptions(self) -> list:
        return self._json(
            self._request("GET", f"{API}/push_subscriptions", params=self._app_auth())
        )

    def create_subscription(self, callback_url: str, verify_token: str) -> dict:
        data = self._app_auth() | {"callback_url": callback_url, "verify_token": verify_token}
        return self._json(self._request("POST", f"{API}/push_subscriptions", data=data))


def workout_from_activity(activity: dict, streams: dict | None) -> dict:
    """Map a Strava DetailedActivity (+ streams) to ``workouts`` columns. Pure."""
    # start_date is UTC; start_date_local is the local wall-clock time with a misleading "Z".
    local = activity.get("start_date_local") or activity["start_date"]
    return {
        "id": activity["id"],
        "source": "strava",
        "sport_type": activity.get("sport_type") or activity.get("type") or "Unknown",
        "name": (activity.get("name") or "")[:255],
        "start_at": datetime.fromisoformat(activity["start_date"]),
        "day": date.fromisoformat(local[:10]),
        "elapsed_s": activity.get("elapsed_time"),
        "moving_s": activity.get("moving_time"),
        "distance_m": activity.get("distance"),
        "elevation_gain_m": activity.get("total_elevation_gain"),
        "avg_hr": activity.get("average_heartrate"),
        "max_hr": activity.get("max_heartrate"),
        "avg_speed_mps": activity.get("average_speed"),
        "avg_cadence": activity.get("average_cadence"),
        "avg_watts": activity.get("average_watts"),
        "calories": activity.get("calories"),
        "summary": activity,
        "streams": streams,
    }
