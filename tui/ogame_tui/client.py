from __future__ import annotations

from typing import Any

import httpx


class APIError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"{status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


class OGameClient:
    def __init__(self, base_url: str = "http://localhost:8000", token: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=10.0)
        self._token: str | None = token

    def set_token(self, token: str) -> None:
        self._token = token

    @property
    def token(self) -> str | None:
        return self._token

    @property
    def authenticated(self) -> bool:
        return self._token is not None

    def _headers(self) -> dict[str, str]:
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        r = await self._client.request(method, path, headers=self._headers(), **kwargs)
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", r.text)
            except Exception:
                detail = r.text
            raise APIError(r.status_code, str(detail))
        if r.status_code == 204:
            return None
        return r.json()

    # ----- Auth -----------------------------------------------------------
    async def register(self, username: str, email: str, password: str) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/auth/register",
            json={"username": username, "email": email, "password": password},
        )

    async def login(self, username: str, password: str) -> str:
        # OAuth2 password flow
        r = await self._client.post(
            "/auth/login",
            data={"username": username, "password": password},
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        if r.status_code >= 400:
            raise APIError(r.status_code, str(r.json().get("detail", r.text)))
        self._token = r.json()["access_token"]
        return self._token

    async def me(self) -> dict[str, Any]:
        return await self._request("GET", "/auth/me")

    async def stats(self) -> dict[str, Any]:
        return await self._request("GET", "/stats")

    async def quests(self) -> dict[str, Any]:
        return await self._request("GET", "/api/quests")

    # ----- Planet ---------------------------------------------------------
    async def list_planets(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/planets")

    async def get_planet(self, planet_id: int) -> dict[str, Any]:
        return await self._request("GET", f"/planets/{planet_id}")

    # ----- Buildings ------------------------------------------------------
    async def list_buildings(self, planet_id: int) -> dict[str, Any]:
        return await self._request("GET", f"/planets/{planet_id}/buildings")

    async def upgrade_building(self, planet_id: int, building_type: str) -> dict[str, Any]:
        return await self._request(
            "POST", f"/planets/{planet_id}/buildings/{building_type}/upgrade"
        )

    async def get_queue(self, planet_id: int) -> list[dict[str, Any]]:
        return await self._request("GET", f"/planets/{planet_id}/queue")

    async def cancel_queue(self, queue_id: int) -> dict[str, Any]:
        return await self._request("DELETE", f"/queue/{queue_id}")

    # ----- Research -------------------------------------------------------
    async def list_researches(self) -> dict[str, Any]:
        return await self._request("GET", "/researches")

    async def upgrade_research(self, tech_type: str, planet_id: int) -> dict[str, Any]:
        return await self._request(
            "POST", f"/researches/{tech_type}/upgrade", params={"planet_id": planet_id}
        )

    # ----- Galaxy ---------------------------------------------------------
    async def view_galaxy(self, universe_id: int, galaxy: int, system: int) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/galaxy",
            params={"universe_id": universe_id, "galaxy": galaxy, "system": system},
        )

    # ----- Social ---------------------------------------------------------
    async def list_players(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/api/players")

    async def send_message(self, recipient: str, body: str) -> dict[str, Any]:
        return await self._request(
            "POST", "/messages", json={"recipient_username": recipient, "body": body}
        )

    async def inbox(self, unread_only: bool = False, limit: int = 50) -> list[dict[str, Any]]:
        return await self._request(
            "GET",
            "/messages",
            params={"unread_only": str(unread_only).lower(), "limit": limit},
        )

    async def unread_count(self) -> int:
        r = await self._request("GET", "/messages/unread-count")
        return int(r["count"])

    async def mark_read(self, message_id: int) -> dict[str, Any]:
        return await self._request("POST", f"/messages/{message_id}/read")

    async def threads(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/messages/threads")

    async def conversation(self, username: str, limit: int = 100) -> list[dict[str, Any]]:
        return await self._request("GET", f"/messages/with/{username}", params={"limit": limit})

    async def planet_logs(self, planet_id: int, limit: int = 20) -> list[dict[str, Any]]:
        return await self._request("GET", f"/planets/{planet_id}/logs", params={"limit": limit})

    # ----- Shipyard -------------------------------------------------------
    async def list_ships(self, planet_id: int) -> dict[str, Any]:
        return await self._request("GET", f"/planets/{planet_id}/ships")

    async def build_ship(self, planet_id: int, ship_type: str, count: int) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/planets/{planet_id}/shipyard/build/{ship_type}",
            json={"count": count},
        )

    # ----- Defense -------------------------------------------------------
    async def list_defenses(self, planet_id: int) -> dict[str, Any]:
        return await self._request("GET", f"/planets/{planet_id}/defenses")

    async def build_defense(self, planet_id: int, defense_type: str, count: int) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/planets/{planet_id}/defense/build/{defense_type}",
            json={"count": count},
        )

    # ----- Fleets ---------------------------------------------------------
    async def send_fleet(
        self,
        origin_planet_id: int,
        mission: str,
        target_galaxy: int,
        target_system: int,
        target_position: int,
        ships: dict[str, int],
        cargo_metal: int = 0,
        cargo_crystal: int = 0,
        cargo_deuterium: int = 0,
        speed_percent: int = 100,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/fleets/send",
            json={
                "origin_planet_id": origin_planet_id,
                "mission": mission,
                "target_galaxy": target_galaxy,
                "target_system": target_system,
                "target_position": target_position,
                "ships": ships,
                "cargo_metal": cargo_metal,
                "cargo_crystal": cargo_crystal,
                "cargo_deuterium": cargo_deuterium,
                "speed_percent": speed_percent,
            },
        )

    async def list_fleets(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/fleets")

    async def list_incoming_fleets(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/fleets/incoming")

    # ----- Reports --------------------------------------------------------
    async def list_reports(self, limit: int = 30) -> list[dict[str, Any]]:
        return await self._request("GET", "/reports", params={"limit": limit})

    async def get_report(self, report_id: int) -> dict[str, Any]:
        return await self._request("GET", f"/reports/{report_id}")

    # ----- Leaderboard ----------------------------------------------------
    async def leaderboard(self, limit: int = 50) -> dict[str, Any]:
        return await self._request("GET", "/api/leaderboard", params={"limit": limit})

    # ----- Alliance -------------------------------------------------------
    async def list_alliances(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/api/alliances")

    async def get_alliance(self, tag: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/alliances/{tag}")

    async def create_alliance(self, tag: str, name: str, description: str = "") -> dict[str, Any]:
        return await self._request(
            "POST",
            "/api/alliances",
            json={"tag": tag, "name": name, "description": description},
        )

    async def join_alliance(self, tag: str, message: str = "") -> dict[str, Any]:
        """Submit a join request. Founder must approve before membership."""
        return await self._request("POST", f"/api/alliances/{tag}/join", json={"message": message})

    async def list_alliance_requests(self, tag: str) -> list[dict[str, Any]]:
        return await self._request("GET", f"/api/alliances/{tag}/requests")

    async def approve_alliance_request(self, tag: str, username: str) -> dict[str, Any]:
        return await self._request("POST", f"/api/alliances/{tag}/requests/{username}/approve")

    async def reject_alliance_request(self, tag: str, username: str) -> dict[str, Any]:
        return await self._request("POST", f"/api/alliances/{tag}/requests/{username}/reject")

    async def my_alliance_request(self) -> dict[str, Any] | None:
        # 200 + null when no pending request.
        return await self._request("GET", "/api/me/alliance-request")

    async def withdraw_alliance_request(self) -> dict[str, Any]:
        return await self._request("DELETE", "/api/me/alliance-request")

    async def leave_alliance(self, tag: str) -> dict[str, Any]:
        return await self._request("POST", f"/api/alliances/{tag}/leave")

    async def my_alliance(self) -> dict[str, Any] | None:
        try:
            return await self._request("GET", "/api/me/alliance")
        except APIError as e:
            if e.status_code == 404:
                return None
            raise
