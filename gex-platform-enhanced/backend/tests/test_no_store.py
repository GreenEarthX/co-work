"""
Cache-Control: no-store on pre-FID, derived and returns responses (handoff v4, task 9).

Pinned on the real app: the header is set whatever the answer — a 401 or 403
from the access middleware included — and only on the listed paths.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core import no_store
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("path", [
    "/api/v1/packages/project/P1", "/api/v1/packages/project/P1/summary",
    "/api/v1/spend-wave/P1", "/api/v1/capital-bridge/projects/P1/full",
    "/api/v1/capital-bridge/projects/P1/spend-wave", "/api/v1/devex-brief/P1",
    "/api/v1/pre-cod-metrics/portfolio/summary?project_ids=P1", "/api/v1/lineage/project/P1",
    "/api/v1/returns-cases/P1", "/api/v1/projects/P1/datasets/spend_wave",
    "/api/v1/ic-pack/P1/export/json",
])
def test_every_pre_fid_and_returns_path_is_no_store(path):
    r = client.get(path)
    assert r.headers.get("cache-control") == no_store.NO_STORE, (path, r.status_code)


def test_other_paths_are_untouched():
    assert "cache-control" not in client.get("/health").headers


def test_the_list_covers_every_router_that_reads_pre_fid_data():
    for prefix in ("/api/v1/packages", "/api/v1/spend-wave", "/api/v1/capital-bridge", "/api/v1/devex-brief",
                   "/api/v1/pre-cod-metrics", "/api/v1/lineage", "/api/v1/returns-cases"):
        assert no_store.applies(prefix + "/x")
