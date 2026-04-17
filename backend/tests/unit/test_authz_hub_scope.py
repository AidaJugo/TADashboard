"""Unit tests for the single-source hub scope filter (FR-AUTHZ-3..5).

docs/testing.md §3.3:
    TC-U-AUTHZ-2: A viewer with no hub scopes sees every hub.
    TC-U-AUTHZ-3: A viewer with ["Sarajevo", "Skopje"] does not see Belgrade.
    TC-U-AUTHZ-4: Filter is pure: input lists are not mutated.

Additional invariants tested here:
    - Empty allowed list returns a *new* list, not a reference to the input.
    - ``filter_by_hub`` accepts an arbitrary ``key`` callable (decoupled from
      HireRow so the M5 report pipeline can pass in its own key function).
    - ``hub_scope_clause`` builds an ``IN (...)`` clause for non-empty scopes
      and a constant ``true`` for empty scopes.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy import Column, String, Table, and_
from sqlalchemy.sql.elements import BooleanClauseList
from sqlalchemy.sql.schema import MetaData

from app.authz.hub_scope import (
    filter_by_hub,
    filter_hub_names,
    hub_scope_clause,
    is_hub_allowed,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# is_hub_allowed
# ---------------------------------------------------------------------------


def test_tc_u_authz_2_empty_allowed_hubs_allows_every_hub() -> None:
    """TC-U-AUTHZ-2: empty scope means all hubs."""
    assert is_hub_allowed("Sarajevo", []) is True
    assert is_hub_allowed("Belgrade", []) is True
    assert is_hub_allowed("Anywhere", []) is True


def test_tc_u_authz_3_scoped_hub_rejects_unlisted() -> None:
    """TC-U-AUTHZ-3: a scoped user cannot see hubs outside their list."""
    allowed = ["Sarajevo", "Skopje"]
    assert is_hub_allowed("Sarajevo", allowed) is True
    assert is_hub_allowed("Skopje", allowed) is True
    assert is_hub_allowed("Belgrade", allowed) is False
    assert is_hub_allowed("Zagreb", allowed) is False


def test_is_hub_allowed_is_case_sensitive_by_default() -> None:
    """Hub names are stored as-written.  Case-insensitive matching is a
    separate helper that does not exist yet; this test pins the default."""
    assert is_hub_allowed("Sarajevo", ["sarajevo"]) is False


# ---------------------------------------------------------------------------
# filter_hub_names
# ---------------------------------------------------------------------------


def test_filter_hub_names_empty_scope_returns_all() -> None:
    hubs = ["Sarajevo", "Belgrade", "Skopje"]
    result = filter_hub_names(hubs, [])
    assert result == hubs


def test_filter_hub_names_narrows_to_allowed() -> None:
    hubs = ["Sarajevo", "Belgrade", "Skopje", "Zagreb"]
    result = filter_hub_names(hubs, ["Sarajevo", "Skopje"])
    assert result == ["Sarajevo", "Skopje"]


def test_filter_hub_names_preserves_input_order() -> None:
    hubs = ["Zagreb", "Sarajevo", "Belgrade", "Skopje"]
    result = filter_hub_names(hubs, ["Sarajevo", "Skopje"])
    assert result == ["Sarajevo", "Skopje"]


# ---------------------------------------------------------------------------
# filter_by_hub
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Row:
    hub: str
    salary: int


def test_filter_by_hub_uses_key_function() -> None:
    rows = [_Row("Sarajevo", 1000), _Row("Belgrade", 2000), _Row("Skopje", 1500)]
    result = filter_by_hub(rows, key=lambda r: r.hub, allowed_hubs=["Sarajevo", "Skopje"])
    assert result == [_Row("Sarajevo", 1000), _Row("Skopje", 1500)]


def test_tc_u_authz_4_filter_is_pure_does_not_mutate_inputs() -> None:
    """TC-U-AUTHZ-4: filter is pure — never mutates its inputs."""
    rows = [_Row("Sarajevo", 1), _Row("Belgrade", 2)]
    allowed = ["Sarajevo"]
    rows_copy = list(rows)
    allowed_copy = list(allowed)

    result = filter_by_hub(rows, key=lambda r: r.hub, allowed_hubs=allowed)

    assert rows == rows_copy
    assert allowed == allowed_copy
    assert result is not rows


def test_filter_by_hub_empty_scope_returns_new_list() -> None:
    """Defensive: callers shouldn't rely on reference identity with input."""
    rows = [_Row("Sarajevo", 1)]
    result = filter_by_hub(rows, key=lambda r: r.hub, allowed_hubs=[])
    assert result == rows
    assert result is not rows


# ---------------------------------------------------------------------------
# hub_scope_clause
# ---------------------------------------------------------------------------


def _col() -> Column[str]:
    """Build a bare ``Column`` outside any table — good enough for SQL compilation."""
    md = MetaData()
    tbl = Table("hires", md, Column("hub", String))
    return tbl.c.hub


def test_hub_scope_clause_empty_scope_is_tautology() -> None:
    clause = hub_scope_clause(_col(), [])
    compiled = str(clause.compile(compile_kwargs={"literal_binds": True}))
    assert compiled.strip().lower() == "true"


def test_hub_scope_clause_non_empty_renders_in_list() -> None:
    clause = hub_scope_clause(_col(), ["Sarajevo", "Skopje"])
    compiled = str(clause.compile(compile_kwargs={"literal_binds": True}))
    assert "hires.hub" in compiled
    assert "IN" in compiled.upper()
    assert "Sarajevo" in compiled
    assert "Skopje" in compiled


def test_hub_scope_clause_composes_with_other_clauses() -> None:
    col = _col()
    combined = and_(hub_scope_clause(col, ["Sarajevo"]), col != "Belgrade")
    assert isinstance(combined, BooleanClauseList)
