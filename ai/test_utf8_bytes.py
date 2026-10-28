#!/usr/bin/env python3
"""Prova os bytes de 'olá' e o reparo de UTF-8 lido como Latin-1."""


def repair_mojibake(text: str) -> tuple[str, bool]:
    raw = []
    suspicious = False
    for ch in text:
        code = ord(ch)
        if code > 255:
            return text, False
        raw.append(code)
        if 0xC2 <= code <= 0xF4:
            suspicious = True
    if not suspicious:
        return text, False
    try:
        repaired = bytes(raw).decode("utf-8")
    except UnicodeDecodeError:
        return text, False
    return repaired, repaired != text


def test_ola_utf8_bytes():
    raw = "olá".encode("utf-8")
    assert raw.hex(" ") == "6f 6c c3 a1"
    print("[PASS] olá UTF-8 = 6f 6c c3 a1")


def test_mojibake_repair():
    mojibake = "olá".encode("utf-8").decode("latin-1")
    assert [hex(ord(ch)) for ch in mojibake] == ["0x6f", "0x6c", "0xc3", "0xa1"]
    repaired, changed = repair_mojibake(mojibake)
    assert changed
    assert repaired == "olá"
    assert [hex(ord(ch)) for ch in repaired] == ["0x6f", "0x6c", "0xe1"]
    print("[PASS] C3 A1 reparado para U+00E1")


def test_already_unicode_is_left_alone():
    repaired, changed = repair_mojibake("olá")
    assert changed is False
    assert repaired == "olá"
    print("[PASS] Unicode correto nao e alterado")


def test_chunk_queue_order():
    active = []
    queue_log = []

    def show(text):
        if active:
            active[0]["queue"].append(text)
            return
        active.append({"text": text, "queue": []})

    def expire():
        bubble = active.pop()
        queue_log.append(bubble["text"])
        if bubble["queue"]:
            nxt = bubble["queue"].pop(0)
            active.append({"text": nxt, "queue": bubble["queue"]})

    show("um")
    show("dois")
    show("tres")
    while active:
        expire()
    assert queue_log == ["um", "dois", "tres"]
    print("[PASS] fila de trechos em ordem")


if __name__ == "__main__":
    test_ola_utf8_bytes()
    test_mojibake_repair()
    test_already_unicode_is_left_alone()
    test_chunk_queue_order()
    print("[OK] testes de bytes e fila passaram")
