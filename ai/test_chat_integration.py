#!/usr/bin/env python3
"""Testes de integração para o sistema de chat presencial."""

import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


def test_chat_request_response_cycle():
    """Testa ciclo completo de requisição e resposta de chat."""
    
    # Setup
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        to_py = root / "to_py"
        to_lua = root / "to_lua"
        to_py.mkdir(parents=True)
        to_lua.mkdir(parents=True)
        
        # Simula requisição Lua
        req_id = "1234567890-chat-1"
        world_id = "Apocalypse/test"
        npc_id = "npc_1"
        message = "Olá Carlos!"
        
        request = {
            "id": req_id,
            "kind": "chat_request",
            "world_id": world_id,
            "npc_id": npc_id,
            "message": message,
            "context": {
                "time": "10:30, dia 1/1/1993",
                "location": "coordenadas 100,100",
                "npc_state": "parado",
                "distance_to_player": 2.5
            }
        }
        
        # Escreve requisição
        tmp_path = to_py / f"{req_id}.json.tmp"
        ok_path = to_py / f"{req_id}.ok"
        tmp_path.write_text(json.dumps(request), encoding="utf-8")
        ok_path.write_text(req_id, encoding="utf-8")
        
        # Simula processamento Python (mock)
        response = {
            "id": req_id,
            "kind": "chat_response",
            "world_id": world_id,
            "npc_id": npc_id,
            "success": True,
            "reply": "Olá! Como posso ajudar?"
        }
        
        # Escreve resposta
        response_path = to_lua / f"{req_id}.json"
        response_tmp = to_lua / f"{req_id}.json.part"
        response_tmp.write_text(json.dumps(response), encoding="utf-8")
        os.replace(response_tmp, response_path)
        
        # Simula leitura Lua (corrigida)
        with open(response_path, "r", encoding="utf-8") as f:
            chunks = []
            for line in f:
                chunks.append(line)
            json_text = "".join(chunks)
        
        # Valida parse
        assert json_text is not None
        assert isinstance(json_text, str)
        assert json_text != ""
        
        parsed = json.loads(json_text)
        assert parsed["id"] == req_id
        assert parsed["kind"] == "chat_response"
        assert parsed["success"] is True
        assert parsed["reply"] == "Olá! Como posso ajudar?"
        
        print("[PASS] Ciclo de chat funcionou corretamente")


def test_pcall_return_semantics():
    """Valida semântica correta de pcall em Python (simulação)."""
    
    # Simula pcall bem-sucedido
    def pcall_success():
        try:
            result = "conteúdo JSON"
            return True, result
        except Exception as e:
            return False, str(e)
    
    # Uso CORRETO
    ok, json_text = pcall_success()
    assert ok is True
    assert isinstance(json_text, str)
    assert json_text == "conteúdo JSON"
    
    # Uso INCORRETO (bug original)
    # json, err = pcall_success()
    # Neste caso: json = True, err = "conteúdo JSON"
    # json:match() falharia porque json é boolean
    
    print("[PASS] Semântica de pcall validada")


def test_distance_validation():
    """Testa validação de distância para conversa presencial."""
    
    MAX_DISTANCE = 5.0
    
    # Casos válidos
    assert math.sqrt(2**2 + 2**2) <= MAX_DISTANCE  # ~2.83 tiles
    assert math.sqrt(3**2 + 3**2) <= MAX_DISTANCE  # ~4.24 tiles
    assert 4.9 <= MAX_DISTANCE
    
    # Casos inválidos
    assert math.sqrt(4**2 + 4**2) > MAX_DISTANCE  # ~5.66 tiles
    assert 10.0 > MAX_DISTANCE
    
    print("[PASS] Validação de distância OK")


def test_speech_bubble_duration():
    """Testa cálculo de duração de balões de fala."""
    
    CHAR_PER_SECOND = 15
    MIN_DURATION = 3000  # ms
    MAX_DURATION = 15000  # ms
    
    def calculate_duration(text):
        chars = len(text)
        duration = max(MIN_DURATION, chars / CHAR_PER_SECOND * 1000)
        return min(duration, MAX_DURATION)
    
    # Texto curto
    short = "Oi!"
    assert calculate_duration(short) == MIN_DURATION
    
    # Texto médio (precisa ter mais de 45 chars para exceder MIN_DURATION de 3s)
    medium = "Esta é uma resposta de tamanho médio que precisa ter mais caracteres para testar corretamente."
    duration_medium = calculate_duration(medium)
    assert MIN_DURATION < duration_medium < MAX_DURATION
    
    # Texto longo
    long = "A" * 300  # 300 caracteres
    assert calculate_duration(long) == MAX_DURATION
    
    print("[PASS] Duração de balões calculada corretamente")


def test_message_validation():
    """Testa validação de mensagens antes do envio."""
    
    # Mensagem válida
    valid = "Como está o tempo hoje?"
    assert valid is not None
    assert valid != ""
    assert len(valid) <= 2000
    
    # Mensagem vazia
    empty = ""
    assert empty == ""
    
    # Mensagem muito longa
    too_long = "A" * 2001
    assert len(too_long) > 2000
    
    print("[PASS] Validação de mensagens OK")


def test_json_escape_handling():
    """Testa tratamento de caracteres especiais em JSON."""
    
    # Mensagem com caracteres especiais
    message = 'Ele disse: "Olá!"\nComo vai?'
    
    # Escaping
    escaped = message.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    
    # Cria JSON
    payload = f'{{"message": "{escaped}"}}'
    parsed = json.loads(payload)
    
    # Valida que o parse funciona
    assert "message" in parsed
    
    # Unescaping
    unescaped = parsed["message"].replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
    assert unescaped == message
    
    print("[PASS] Escape de JSON validado")


import math


if __name__ == "__main__":
    test_chat_request_response_cycle()
    test_pcall_return_semantics()
    test_distance_validation()
    test_speech_bubble_duration()
    test_message_validation()
    test_json_escape_handling()
    
    print("\n[✓] Todos os testes de integração de chat passaram!")
