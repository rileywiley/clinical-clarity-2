"""Phase 0 gate test (PRD §9.2).

Proves the four Phase 0 invariants:
1. Two orgs can be created and each logs in.
2. /orgs/me returns the *signed-in* org, never the other.
3. A direct DB query as app_user with tenant=A cannot see B's rows — this is the
   one that proves Postgres RLS is the safety net, not just the API layer.
4. Role gating works (non-admin → 403 on admin-only route).
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


async def _signup(client: AsyncClient, name: str, email: str) -> dict:
    res = await client.post(
        "/orgs",
        json={
            "org_name": name,
            "default_timezone": "America/New_York",
            "admin_email": email,
            "admin_password": "correct-horse-battery-staple",
            "admin_name": f"{name} admin",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


async def _login(client: AsyncClient, org_id: str, email: str, password: str) -> None:
    res = await client.post(
        "/auth/login",
        json={"email": email, "password": password, "org_id": org_id},
    )
    assert res.status_code == 204, res.text


async def test_two_orgs_isolated_via_api(client: AsyncClient) -> None:
    org_a = await _signup(client, "Org A", "admin@a.example.com")
    org_b = await _signup(client, "Org B", "admin@b.example.com")

    # Login as A and confirm /orgs/me returns A.
    await _login(client, org_a["id"], "admin@a.example.com", "correct-horse-battery-staple")
    me_a = await client.get("/orgs/me")
    assert me_a.status_code == 200
    assert me_a.json()["id"] == org_a["id"]

    # Login as B (replaces cookie) and confirm /orgs/me returns B.
    await _login(client, org_b["id"], "admin@b.example.com", "correct-horse-battery-staple")
    me_b = await client.get("/orgs/me")
    assert me_b.status_code == 200
    assert me_b.json()["id"] == org_b["id"]
    assert me_b.json()["id"] != org_a["id"]


async def test_rls_blocks_cross_org_reads_at_db_level(
    client: AsyncClient,
    user_engine: AsyncEngine,
) -> None:
    """The load-bearing test for CLAUDE.md golden rule #6.

    Bypassing the API and querying directly as ``app_user``, we set the tenant
    context to org A and confirm B's user row is invisible — even though we know
    its primary key. If this ever passes without RLS in place, the safety net is
    gone and the rule is unenforced.
    """
    org_a = await _signup(client, "Org A", "admin@a.example.com")
    org_b = await _signup(client, "Org B", "admin@b.example.com")

    async with user_engine.connect() as conn:
        # Bind tenant to A.
        await conn.execute(
            text("SELECT set_config('app.current_org_id', :v, false)"),
            {"v": org_a["id"]},
        )

        # We should see exactly one user (A's admin) and one org (A).
        users = (await conn.execute(text("SELECT org_id::text FROM users"))).all()
        assert len(users) == 1
        assert users[0][0] == org_a["id"]

        orgs = (await conn.execute(text("SELECT id::text FROM organizations"))).all()
        assert len(orgs) == 1
        assert orgs[0][0] == org_a["id"]

        # Targeted lookup for B's org by id should return zero rows under RLS.
        b_lookup = (
            await conn.execute(
                text("SELECT id FROM organizations WHERE id = :id"),
                {"id": org_b["id"]},
            )
        ).all()
        assert b_lookup == []


async def test_role_gating_blocks_non_admin(client: AsyncClient) -> None:
    """Non-admin → 403 on an admin-only route.

    Phase 0 only seeds Org Admins via signup, so we manually demote our user via
    the privileged engine to exercise the require_role gate.
    """
    from sqlalchemy import update

    from app.models.user import User, UserRole

    org = await _signup(client, "Org Demote", "admin@demote.example.com")
    # Demote the admin we just created.
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.config import get_settings

    admin_engine = create_async_engine(get_settings().database_url_admin)
    async with admin_engine.begin() as conn:
        await conn.execute(update(User).values(role=UserRole.VIEWER).where(User.org_id == org["id"]))
    await admin_engine.dispose()

    await _login(client, org["id"], "admin@demote.example.com", "correct-horse-battery-staple")
    res = await client.get("/orgs/admin-only")
    assert res.status_code == 403, res.text
