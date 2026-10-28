#!/usr/bin/env python3
"""Testes para o sistema de chat."""

import json
import sys
from pathlib import Path

# Add ai directory to path
sys.path.insert(0, str(Path(__file__).parent))

from chat_handler import (
    ChatHistory,
    load_persona,
    build_system_prompt,
    validate_message,
    MAX_MESSAGE_LENGTH,
)


def test_chat_history():
    """Testa gerenciamento de histórico."""
    print("=== Teste: ChatHistory ===")
    
    history = ChatHistory(max_messages=4)
    
    # Adiciona mensagens
    history.add_user("Olá")
    history.add_assistant("Oi, tudo bem?")
    history.add_user("Sim")
    history.add_assistant("Ótimo!")
    
    messages = history.get_messages()
    assert len(messages) == 4, f"Esperado 4, obtido {len(messages)}"
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Olá"
    
    # Adiciona mais para testar limite
    history.add_user("Teste")
    history.add_assistant("Resposta")
    
    messages = history.get_messages()
    assert len(messages) == 4, f"Deve manter apenas 4, obtido {len(messages)}"
    # Deve ter removido as 2 primeiras
    assert messages[0]["content"] == "Sim", "Deve ter removido mensagens antigas"
    
    # Limpa
    history.clear()
    assert len(history.get_messages()) == 0
    
    print("✓ ChatHistory passou")


def test_load_persona():
    """Testa carregamento de personalidade."""
    print("\n=== Teste: load_persona ===")
    
    persona_path = Path(__file__).parent / "persona_default.json"
    persona = load_persona(persona_path)
    
    assert isinstance(persona, dict), "Persona deve ser dict"
    assert persona.get("name"), "Deve ter nome"
    assert persona.get("age"), "Deve ter idade"
    assert persona.get("personality"), "Deve ter personalidade"
    
    print(f"✓ Persona carregada: {persona.get('name')}, {persona.get('age')} anos")


def test_build_system_prompt():
    """Testa construção do prompt de sistema."""
    print("\n=== Teste: build_system_prompt ===")
    
    persona = {
        "name": "Carlos",
        "age": 35,
        "background": "Mecânico sobrevivente",
        "personality": "Pragmático e cauteloso",
    }
    
    context = {
        "time": "14:30, dia 9/7/1993",
        "location": "coordenadas 3394,10975",
        "npc_state": "seguindo você",
        "distance_to_player": 2.5,
    }
    
    prompt = build_system_prompt(persona, context)
    
    assert "Carlos" in prompt
    assert "35 anos" in prompt
    assert "Mecânico" in prompt
    assert "14:30" in prompt
    assert "seguindo você" in prompt
    
    print(f"✓ System prompt gerado ({len(prompt)} caracteres)")
    print(f"Exemplo: {prompt[:200]}...")


def test_validate_message():
    """Testa validação de mensagens."""
    print("\n=== Teste: validate_message ===")
    
    # Mensagem válida
    valid, error = validate_message("Olá, tudo bem?")
    assert valid, "Mensagem válida deve passar"
    
    # Mensagem vazia
    valid, error = validate_message("")
    assert not valid, "Mensagem vazia deve falhar"
    assert "vazia" in error.lower()
    
    # Mensagem muito longa
    long_message = "a" * (MAX_MESSAGE_LENGTH + 1)
    valid, error = validate_message(long_message)
    assert not valid, "Mensagem longa deve falhar"
    assert "longa" in error.lower()
    
    print("✓ Validação de mensagens passou")


def test_context_building():
    """Testa que contextos são incluídos corretamente."""
    print("\n=== Teste: Context Building ===")
    
    persona = {"name": "Test"}
    
    # Contexto vazio
    prompt1 = build_system_prompt(persona, {})
    assert "Test" in prompt1
    
    # Contexto com tempo
    prompt2 = build_system_prompt(persona, {"time": "10:00"})
    assert "10:00" in prompt2
    
    # Contexto com distância curta
    prompt3 = build_system_prompt(persona, {"distance_to_player": 1.5})
    assert "perto" in prompt3.lower()
    
    # Contexto com distância média
    prompt4 = build_system_prompt(persona, {"distance_to_player": 3.0})
    assert "metros" in prompt4.lower() or "alguns" in prompt4.lower()
    
    print("✓ Context building passou")


def test_history_trimming():
    """Testa que histórico mantém pares completos."""
    print("\n=== Teste: History Trimming ===")
    
    history = ChatHistory(max_messages=5)
    
    # Adiciona 3 pares (6 mensagens)
    for i in range(3):
        history.add_user(f"User {i}")
        history.add_assistant(f"Assistant {i}")
    
    messages = history.get_messages()
    # Deve ter removido 1 par completo para ficar em 4 (não 5)
    assert len(messages) == 4, f"Esperado 4 (2 pares), obtido {len(messages)}"
    assert messages[0]["content"] == "User 1", "Deve ter removido primeiro par"
    
    print("✓ History trimming passou")


def run_all_tests():
    """Executa todos os testes."""
    print("Executando testes do sistema de chat...\n")
    
    try:
        test_chat_history()
        test_load_persona()
        test_build_system_prompt()
        test_validate_message()
        test_context_building()
        test_history_trimming()
        
        print("\n=== TODOS OS TESTES PASSARAM ===")
        return 0
    except AssertionError as e:
        print(f"\n❌ FALHA: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
