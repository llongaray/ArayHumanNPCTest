#!/usr/bin/env python3
"""Perfis de inferencia e montagem do prompt, sem chamar o Ollama."""

from chat_handler import (
    CHAT_PROFILE,
    DECISION_PROFILE,
    ChatHistory,
    build_chat_messages,
)


def test_profiles_keep_model_warm_and_share_context():
    assert CHAT_PROFILE["keep_alive"] == "30m"
    assert DECISION_PROFILE["keep_alive"] == "30m"
    assert CHAT_PROFILE["num_ctx"] == DECISION_PROFILE["num_ctx"] == 8192
    assert CHAT_PROFILE["stream"] is False
    assert DECISION_PROFILE["stream"] is False
    assert DECISION_PROFILE["num_predict"] == 12
    assert DECISION_PROFILE["temperature"] == 0
    assert CHAT_PROFILE["num_predict"] > DECISION_PROFILE["num_predict"]
    print("[PASS] perfis chat e decision separados, mesmo contexto")


def test_user_message_is_not_duplicated():
    history = ChatHistory()
    history.add_user("Olá Carlos")
    messages = build_chat_messages("persona", history, "Olá Carlos")
    users = [item for item in messages if item["role"] == "user"]
    assert len(users) == 1
    assert users[0]["content"] == "Olá Carlos"
    assert messages[0]["role"] == "system"
    print("[PASS] fala atual nao e repetida no prompt")


def test_history_stays_short():
    history = ChatHistory()
    for index in range(8):
        history.add_user(f"u{index}")
        history.add_assistant(f"a{index}")
    assert len(history.get_messages()) <= 6
    print("[PASS] historico limitado a 6 mensagens")


if __name__ == "__main__":
    test_profiles_keep_model_warm_and_share_context()
    test_user_message_is_not_duplicated()
    test_history_stays_short()
    print("[OK] perfis de latencia passaram")
