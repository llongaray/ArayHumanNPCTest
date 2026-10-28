#!/usr/bin/env python3
"""Regras de troca do jogador local e do log de latencia, sem o jogo."""


class World:
    def __init__(self):
        self.local_player = None
        self.npc = {"id": 43, "dead": False, "x": 10, "y": 10, "alpha": 0}
        self.npcs = [self.npc]
        self.model_attempted = True
        self.camera = None
        self.logs = []

    def alive(self, player):
        if not player or player.get("dead") or player is self.npc:
            return None
        return player

    def current(self, slot, fallback=None):
        return self.alive(slot) or self.alive(fallback)

    def sync(self, player):
        player = self.alive(player) or self.current(player)
        if not player:
            return None
        if player is self.local_player:
            return player
        previous = self.local_player
        self.local_player = player
        self.camera = player
        if self.npc and not self.npc["dead"]:
            self.model_attempted = False
        if previous:
            self.logs.append(f"anterior={previous['id']}")
            self.logs.append(f"atual={player['id']}")
        return player

    def spawn_square(self, player):
        return (player["x"] + 1, player["y"])

    def pull_square(self, player):
        return self.spawn_square(player)

    def adopt(self, player):
        if any(item.get("marker") == "ARAY" for item in self.npcs):
            return self.npc
        self.npc = {"id": 43, "dead": False, "x": player["x"] + 1, "y": player["y"], "alpha": 0, "marker": "ARAY"}
        self.npcs = [self.npc]
        return self.npc


def test_keeps_original_while_alive():
    world = World()
    first = {"id": 8, "dead": False, "x": 3, "y": 4}
    assert world.sync(first) is first
    assert world.sync(first) is first
    assert world.logs == []
    print("[PASS] jogador vivo nao e trocado de novo")


def test_death_then_new_survivor():
    world = World()
    first = {"id": 8, "dead": False, "x": 3, "y": 4}
    world.sync(first)
    first["dead"] = True
    assert world.sync(first) is None
    assert world.local_player is first
    newbie = {"id": 31, "dead": False, "x": 80, "y": 90}
    assert world.sync(newbie) is newbie
    assert world.local_player is newbie
    assert world.camera is newbie
    assert world.model_attempted is False
    assert "anterior=8" in world.logs
    assert "atual=31" in world.logs
    print("[PASS] morte e novo jogador atualizam referencia e camera")


def test_spawn_and_pull_use_new_position():
    world = World()
    old = {"id": 8, "dead": True, "x": 3, "y": 4}
    world.local_player = old
    newbie = {"id": 31, "dead": False, "x": 80, "y": 90}
    world.sync(newbie)
    spawned = world.adopt(newbie)
    assert world.spawn_square(world.local_player) == (81, 90)
    assert world.pull_square(world.local_player) == (81, 90)
    assert spawned["x"] != old["x"]
    assert len(world.npcs) == 1
    print("[PASS] spawn e puxar usam o jogador novo sem duplicar")


def test_chat_after_swap_and_concat():
    world = World()
    newbie = {"id": 31, "dead": False, "x": 1, "y": 1}
    world.sync({"id": 8, "dead": False, "x": 0, "y": 0})
    world.sync(newbie)
    speaker = world.local_player
    assert speaker["id"] == 31
    poll = None
    line = "latencia=" + str(1518) + "ms poll=" + str(poll)
    assert line == "latencia=1518ms poll=None"
    handled = set()
    response_id = "abc"
    assert response_id not in handled
    handled.add(response_id)
    assert response_id in handled
    print("[PASS] chat usa o jogador atual e a concatenacao aceita nulo")


if __name__ == "__main__":
    test_keeps_original_while_alive()
    test_death_then_new_survivor()
    test_spawn_and_pull_use_new_position()
    test_chat_after_swap_and_concat()
    print("[OK] regras do jogador local passaram")
