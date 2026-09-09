# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 AI Power Grid
"""Check packaged Grid auth offline; this is not a startup or paid canary."""

import asyncio
import json
import os

import httpx


async def main() -> None:
    assert os.environ.get("AUTH_TYPE") == "basic", "Run with AUTH_TYPE=basic"
    from onyx.main import app as app_factory

    app = app_factory()
    assert not app.dependency_overrides, "Use the real authentication dependencies"
    results: dict[str, int] = {}
    # ASGITransport skips lifespan: no DB initialization or startup side effects.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://offline.test"
    ) as client:
        for path in (
            "/grid/account",
            "/grid/images?message_id=1",
            "/grid/images/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "/grid/images/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/content",
        ):
            response = await client.get(path)
            results[path] = response.status_code
            assert response.status_code == 403, (path, response.status_code)
            assert response.json() == {
                "detail": "Access denied. User is not authenticated."
            }, path
        response = await client.post(
            "/grid/images/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", json={}
        )
        results["POST recovery"] = response.status_code
        assert response.status_code == 405
    print(json.dumps({"version": os.environ["ONYX_VERSION"], "checks": results}))


if __name__ == "__main__":
    asyncio.run(main())
