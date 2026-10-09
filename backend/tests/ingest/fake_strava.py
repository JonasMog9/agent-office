"""An in-memory stand-in for the Strava API, served through httpx.MockTransport."""

import json
from urllib.parse import parse_qs

import httpx

OWNER = 42


def activity(activity_id: int, day: str = "2026-10-07", owner: int = OWNER) -> dict:
    return {
        "id": activity_id,
        "athlete": {"id": owner},
        "name": f"Run {activity_id}",
        "sport_type": "Run",
        "start_date": f"{day}T10:00:00Z",
        "start_date_local": f"{day}T06:00:00Z",
        "elapsed_time": 3000,
        "moving_time": 2900,
        "distance": 10000.0,
        "total_elevation_gain": 50.0,
        "average_heartrate": 150.0,
        "max_heartrate": 175.0,
        "average_speed": 3.45,
        "average_cadence": 85.0,
        "calories": 700.0,
        "best_efforts": [{"name": "5k", "elapsed_time": 1380}],
    }


class FakeStrava:
    def __init__(self) -> None:
        self.activities: dict[int, dict] = {}
        self.subscriptions: list[dict] = []
        self.calls: list[str] = []
        self.token_athlete = OWNER
        self.refresh_count = 0
        self.rate_limit_next: list[str] = []  # "short" or "daily", consumed per request

    def client_transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        self.calls.append(f"{method} {path}")
        if self.rate_limit_next:
            kind = self.rate_limit_next.pop(0)
            daily = "1000" if kind == "daily" else "10"
            return httpx.Response(
                429,
                headers={
                    "X-ReadRateLimit-Usage": f"100,{daily}",
                    "X-ReadRateLimit-Limit": "100,1000",
                },
                json={"message": "Rate Limit Exceeded"},
            )
        form = parse_qs(request.content.decode()) if request.content else {}
        if path == "/oauth/token":
            grant = form["grant_type"][0]
            if grant == "authorization_code":
                return httpx.Response(
                    200,
                    json={
                        "access_token": "access-1",
                        "refresh_token": "refresh-1",
                        "expires_at": 2_000_000_000,
                        "athlete": {"id": self.token_athlete},
                    },
                )
            self.refresh_count += 1
            n = self.refresh_count
            return httpx.Response(
                200,
                json={
                    "access_token": f"access-r{n}",
                    "refresh_token": f"refresh-r{n}",
                    "expires_at": 2_000_000_000,
                },
            )
        if path == "/api/v3/athlete/activities":
            page = int(request.url.params["page"])
            per_page = int(request.url.params["per_page"])
            items = sorted(self.activities.values(), key=lambda a: a["id"])
            return httpx.Response(200, json=items[(page - 1) * per_page : page * per_page])
        if path.startswith("/api/v3/activities/"):
            parts = path.split("/")
            activity_id = int(parts[4])
            if activity_id not in self.activities:
                return httpx.Response(404, json={"message": "Record Not Found"})
            if path.endswith("/streams"):
                return httpx.Response(
                    200,
                    json={
                        "time": {"data": [0, 1, 2]},
                        "heartrate": {"data": [140, 141, 142]},
                        "velocity_smooth": {"data": [3.4, 3.5, 3.5]},
                    },
                )
            return httpx.Response(200, json=self.activities[activity_id])
        if path == "/api/v3/push_subscriptions":
            if method == "GET":
                return httpx.Response(200, json=self.subscriptions)
            sub = {"id": 777, "callback_url": form["callback_url"][0]}
            self.subscriptions.append(sub)
            return httpx.Response(201, json=sub)
        return httpx.Response(404, content=json.dumps({"path": path}))
