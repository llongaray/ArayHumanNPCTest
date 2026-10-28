"""Ollama build contracts with a simulated HTTP client; no service startup."""
import copy
import json
from types import SimpleNamespace

import pytest

import character_build_handler as bh

WORLD = "Sandbox/build-tests"


@pytest.fixture
def data():
    def row(key, cost, *, free=False, grants=None, excludes=None):
        return {"id": key, "cost": cost, "free": free, "selectable": not free and cost != 0,
                "grants": grants or [], "excludes": excludes or [], "xp_boosts": {}}
    catalog = {"schema_version": 1, "world_id": WORLD, "captured_at_ms": 10000, "complete": True,
               "rules": {"free_points": 0, "negative_traits_penalty": 1},
               "professions": {"unemployed": row("unemployed", 8), "veteran": row("veteran", -8, grants=["fearless"])},
               "traits": {"strong": row("strong", 10, excludes=["weak"]), "weak": row("weak", -10, excludes=["strong"]),
                          "brave": row("brave", 4), "dextrous": row("dextrous", 2), "outdoorsman": row("outdoorsman", 2),
                          "fearless": row("fearless", 0, free=True, excludes=["coward"]),
                          "coward": row("coward", -2, excludes=["fearless"]), "smoker": row("smoker", -4)}}
    return {"kind": "character_build_request", "id": "build-1", "npc_id": "33333333-3333-4333-8333-333333333333",
            "world_id": WORLD, "session_id": "session-1", "issued_at_ms": 10000, "expires_at_ms": 30000,
            "context": {"schema_version": 1, "world_id": WORLD, "role": "Carpinteiro de apoio", "catalog": catalog,
                        "player_profile": {"profession": {"known": True, "value": "unemployed"},
                                           "traits": {"known": True, "items": ["brave"]},
                                           "skills": {"known": True, "items": [{"id": "Woodwork", "level": {"known": True, "value": 3},
                                               "xp": {"known": True, "value": 300}, "xp_boost": {"known": True, "value": 1}}]},
                                           "xp": {"total": {"known": True, "value": 300}, "level": {"known": True, "value": 0}},
                                           "points": {"known": False, "reason": "unavailable"}}}}


def proposal(traits=None, profession="unemployed"):
    return {"schema_version": 1, "profession_id": profession, "trait_ids": traits if traits is not None else ["brave", "dextrous", "outdoorsman"]}


class Client:
    def __init__(self, content=None, hook=None):
        self.content = json.dumps(proposal()) if content is None else content
        self.hook = hook
        self.calls = []

    def chat(self, model, messages, timeout, profile):
        self.calls.append((model, messages, timeout, profile))
        if self.hook:
            self.hook()
        return {"message": {"content": self.content}}


def test_valid_proposal_uses_selected_model_and_preserves_inputs(data):
    client = Client()
    state = SimpleNamespace(world_models={WORLD: "existing-selected-model"}, online=True,
                            models=["other", "existing-selected-model"], client=client)
    before = copy.deepcopy(data)
    result = bh.propose_for_world(data, state, lambda: 10000)
    assert result["ok"] and not result["executable"] and result["validation"]["balance"] == 0
    assert result["world_id"] == WORLD and result["npc_id"] == data["npc_id"]
    assert client.calls[0][0] == "existing-selected-model"
    assert client.calls[0][2] == 15 and client.calls[0][3]["temperature"] == 0
    assert client.calls[0][3]["num_predict"] >= 512 and client.calls[0][3]["format"] == bh.SCHEMA
    assert data == before and state.world_models == {WORLD: "existing-selected-model"}


@pytest.mark.parametrize("content,reason", [
    ('not JSON', None), ('{"schema_version":1', None),
    (json.dumps(proposal(["strong"])), "negative_balance"),
    (json.dumps(proposal(["strong", "weak"])), "incompatible_traits"),
    (json.dumps(proposal(["fearless"])), "trait_unavailable_or_duplicate"),
    (json.dumps(proposal(["missing"])), "trait_unavailable_or_duplicate"),
    (json.dumps(proposal(["brave", "brave"])), "trait_ids"),
    (json.dumps(proposal([], "invented")), "profession_unavailable"),
    (json.dumps({**proposal(), "cost": -999}), "proposal_schema"),
    (json.dumps({**proposal(), "skills": {"Strength": 10}}), "proposal_schema"),
    (json.dumps({**proposal(), "code": "os.execute('anything')"}), "proposal_schema"),
    ('{"schema_version":1,"schema_version":1,"profession_id":"unemployed","trait_ids":[]}', None),
    ('{"schema_version":NaN,"profession_id":"unemployed","trait_ids":[]}', None),
    (json.dumps({**proposal(), "schema_version": True}), "proposal_schema"),
])
def test_invalid_model_responses_never_become_executable(data, content, reason):
    result = bh.propose(data, Client(content), "selected", lambda: 10000)
    assert not result["ok"] and not result["executable"]
    if reason:
        assert result["error"] == reason


def test_positive_balance_is_valid_but_not_optimal(data):
    result = bh.propose(data, Client(json.dumps(proposal([]))), "selected", lambda: 10000)
    assert result["ok"] and result["validation"]["balance"] == 8
    assert result["validation"]["budget_status"] == "unspent_suboptimal"
    assert result["validation"]["strategic_quality"]["known"] is False
    assert result["validation"]["rewards"] == {"implemented": False}


def test_profession_grants_and_asymmetric_exclusions(data):
    result = bh.propose(data, Client(json.dumps(proposal(["weak", "coward"], "veteran"))), "selected", lambda: 10000)
    assert not result["ok"] and result["error"] == "incompatible_traits"


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(model="invented"), lambda d: d.update(npc_id="npc_1"),
    lambda d: d.update(expires_at_ms=10000), lambda d: d.update(expires_at_ms=50000),
    lambda d: d["context"]["catalog"].update(complete=False),
    lambda d: d["context"]["catalog"].update(world_id="other"),
    lambda d: d["context"]["catalog"].update(captured_at_ms=-30001),
    lambda d: d["context"]["catalog"]["rules"].update(negative_traits_penalty=0),
    lambda d: d["context"]["catalog"]["traits"]["brave"].update(cost=True),
    lambda d: d["context"]["player_profile"]["skills"]["items"][0].update(email="private"),
    lambda d: d["context"]["player_profile"]["profession"].update(value={"email": "private"}),
])
def test_invalid_request_is_rejected_before_http(data, mutation):
    mutation(data)
    client = Client()
    result = bh.propose(data, client, "selected", lambda: 10000)
    assert not result["ok"] and not client.calls


def test_timeout_expiry_and_missing_model(data):
    def timeout():
        raise TimeoutError()
    assert bh.propose(data, Client(hook=timeout), "selected", lambda: 10000)["error"] == "ollama_timeout"
    clock = [10000]
    expired = Client(hook=lambda: clock.__setitem__(0, 30000))
    assert bh.propose(data, expired, "selected", lambda: clock[0])["error"] == "expired"
    client = Client()
    assert bh.propose(data, client, None, lambda: 10000)["error"] == "model_unavailable"
    assert not client.calls


def test_player_metadata_is_not_sent_to_model(data):
    data["context"]["player_profile"].update(name="PERSONAL-NAME", email="PERSONAL-EMAIL", account_id="PRIVATE-ACCOUNT", position={"x": 1})
    client = Client()
    assert bh.propose(data, client, "selected", lambda: 10000)["ok"]
    sent = json.dumps(client.calls[0][1])
    for value in ("PERSONAL-NAME", "PERSONAL-EMAIL", "PRIVATE-ACCOUNT"):
        assert value not in sent


def test_two_npcs_do_not_share_builds_or_histories(data):
    other = copy.deepcopy(data)
    other.update(npc_id="44444444-4444-4444-8444-444444444444", id="build-2")
    a = bh.propose(data, Client(), "selected", lambda: 10000)
    b = bh.propose(other, Client(json.dumps(proposal([]))), "selected", lambda: 10000)
    assert a["npc_id"] != b["npc_id"] and a["validation"]["balance"] == 0 and b["validation"]["balance"] == 8
    assert "history" not in a and "history" not in b


def test_prompt_budget_and_unknown_values_are_explicit(data):
    client = Client()
    data["context"]["player_profile"]["skills"]["items"][0]["level"] = {"known": False}
    assert bh.propose(data, client, "selected", lambda: 10000)["ok"]
    prompt = json.loads(client.calls[0][1][1]["content"])
    assert prompt["player_profile"]["skills"][0][1] is None
    assert prompt["player_profile"]["skills_known"] is True
    assert "points" in prompt["player_profile"] and prompt["player_profile"]["points"] is None
    for row in data["context"]["catalog"]["traits"].values():
        row["xp_boosts"] = {("SyntheticSkillNameForBudget" + str(i)): 1 for i in range(128)}
    client = Client()
    result = bh.propose(data, client, "selected", lambda: 10000)
    assert not result["ok"] and result["error"] == "context_budget" and not client.calls
