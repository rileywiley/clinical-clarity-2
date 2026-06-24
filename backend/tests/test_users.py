"""Phase 6 — user management CRUD + site assignments.

Admin-only for writes; RLS for cross-org isolation.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _signup(client: AsyncClient, name: str) -> dict:
    res = await client.post(
        "/orgs",
        json={
            "org_name": name,
            "default_timezone": "America/New_York",
            "admin_email": f"admin@{name.lower()}.example.com",
            "admin_password": "correct-horse-battery-staple",
            "admin_name": f"{name} admin",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


async def _login(client: AsyncClient, org_id: str, email: str) -> None:
    res = await client.post(
        "/auth/login",
        json={"email": email, "password": "correct-horse-battery-staple", "org_id": org_id},
    )
    assert res.status_code == 204


@pytest.fixture
async def admin_session(client: AsyncClient) -> dict:
    org = await _signup(client, "P6UsersOrg")
    await _login(client, org["id"], "admin@p6usersorg.example.com")
    return org


async def test_admin_can_list_users(client: AsyncClient, admin_session: dict) -> None:
    res = await client.get("/users")
    assert res.status_code == 200, res.text
    users = res.json()
    # Signup already created one Org Admin.
    assert len(users) == 1
    assert users[0]["role"] == "org_admin"


async def test_admin_can_create_a_user(
    client: AsyncClient, admin_session: dict
) -> None:
    res = await client.post(
        "/users",
        json={
            "email": "site-mgr@p6usersorg.example.com",
            "name": "Site Manager Steve",
            "password": "another-correct-horse-staple",
            "role": "site_manager",
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["role"] == "site_manager"
    assert body["active"] is True


async def test_duplicate_email_within_org_rejected(
    client: AsyncClient, admin_session: dict
) -> None:
    payload = {
        "email": "dup@p6usersorg.example.com",
        "name": "First",
        "password": "another-correct-horse-staple",
        "role": "viewer",
    }
    res = await client.post("/users", json=payload)
    assert res.status_code == 201
    res = await client.post("/users", json=payload)
    assert res.status_code == 409


async def test_non_admin_cannot_list_users(client: AsyncClient) -> None:
    from sqlalchemy import update
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.config import get_settings
    from app.models.user import User, UserRole

    org = await _signup(client, "P6NonAdmin")
    # Demote the seeded admin so we can test 403 with the same cookie.
    engine = create_async_engine(get_settings().database_url_admin)
    async with engine.begin() as conn:
        await conn.execute(
            update(User).values(role=UserRole.VIEWER).where(User.org_id == org["id"])
        )
    await engine.dispose()

    await _login(client, org["id"], "admin@p6nonadmin.example.com")
    res = await client.get("/users")
    assert res.status_code == 403


async def test_cannot_remove_last_active_admin(
    client: AsyncClient, admin_session: dict
) -> None:
    """Locking yourself out is too easy to do by accident; we block it explicitly."""
    me = (await client.get("/auth/me")).json()
    res = await client.patch(f"/users/{me['user_id']}", json={"active": False})
    assert res.status_code == 409
    assert "last active Org Admin" in res.json()["detail"]


async def test_admin_can_demote_self_when_a_second_admin_exists(
    client: AsyncClient, admin_session: dict
) -> None:
    """Locking the *only* admin out is blocked; a self-demotion when another
    admin is around is fine."""
    # Create a second admin so the safety check passes.
    second = (
        await client.post(
            "/users",
            json={
                "email": "second-admin@p6usersorg.example.com",
                "name": "Second Admin",
                "password": "another-correct-horse-staple",
                "role": "org_admin",
            },
        )
    ).json()
    assert second["role"] == "org_admin"

    me = (await client.get("/auth/me")).json()
    res = await client.patch(f"/users/{me['user_id']}", json={"role": "viewer"})
    assert res.status_code == 200, res.text


async def test_rls_blocks_cross_org_user_reads(client: AsyncClient) -> None:
    """Org B's admin cannot list or modify Org A's users."""
    org_a = await _signup(client, "RlsAUsers")
    await _login(client, org_a["id"], "admin@rlsausers.example.com")
    # Capture A's user id to attempt cross-org reach.
    me_a = (await client.get("/auth/me")).json()

    org_b = await _signup(client, "RlsBUsers")
    await _login(client, org_b["id"], "admin@rlsbusers.example.com")

    # B's /users only returns B's users.
    res = await client.get("/users")
    assert res.status_code == 200
    assert all(u["id"] != me_a["user_id"] for u in res.json())

    # B can't patch A's user — 404 (RLS hides the row).
    res = await client.patch(
        f"/users/{me_a['user_id']}", json={"active": False}
    )
    assert res.status_code == 404


# --- Site assignments -------------------------------------------------


async def test_admin_can_assign_user_to_site(
    client: AsyncClient, admin_session: dict
) -> None:
    site = (
        await client.post(
            "/sites",
            json={"name": "Boston", "timezone": "America/New_York"},
        )
    ).json()
    new_user = (
        await client.post(
            "/users",
            json={
                "email": "site-user@p6usersorg.example.com",
                "name": "Site User",
                "password": "another-correct-horse-staple",
                "role": "site_manager",
            },
        )
    ).json()

    res = await client.post(
        f"/sites/{site['id']}/users", json={"user_id": new_user["id"]}
    )
    assert res.status_code == 201, res.text

    # Listing the site's users shows the assignment.
    res = await client.get(f"/sites/{site['id']}/users")
    assert res.status_code == 200
    users = res.json()
    assert len(users) == 1
    assert users[0]["user_id"] == new_user["id"]

    # Duplicate assignment rejected.
    res = await client.post(
        f"/sites/{site['id']}/users", json={"user_id": new_user["id"]}
    )
    assert res.status_code == 409

    # Unassign.
    res = await client.delete(f"/sites/{site['id']}/users/{new_user['id']}")
    assert res.status_code == 204
    res = await client.get(f"/sites/{site['id']}/users")
    assert res.json() == []
