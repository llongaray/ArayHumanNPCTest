"""Manipulador de conversação com Ollama."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

# Limites de segurança
MAX_MESSAGE_LENGTH = 2000
MAX_RESPONSE_LENGTH = 4000
MAX_HISTORY_MESSAGES = 6
CHAT_TIMEOUT = 30  # seconds

# Mesmo num_ctx nos dois perfis para nao recarregar o modelo ao trocar de uso.
CHAT_PROFILE = {
    "name": "chat",
    "keep_alive": "30m",
    "num_ctx": 8192,
    "num_predict": 160,
    "temperature": 0.7,
    "stream": False,
}

DECISION_PROFILE = {
    "name": "decision",
    "keep_alive": "30m",
    "num_ctx": 8192,
    "num_predict": 12,
    "temperature": 0,
    "stream": False,
}


class ChatHistory:
    """Gerencia histórico de conversa por sessão."""
    
    def __init__(self, max_messages: int = MAX_HISTORY_MESSAGES):
        self.max_messages = max_messages
        self.messages: list[dict[str, str]] = []
    
    def add_user(self, content: str) -> None:
        """Adiciona mensagem do usuário."""
        self.messages.append({"role": "user", "content": content})
        self._trim()
    
    def add_assistant(self, content: str) -> None:
        """Adiciona mensagem do assistente."""
        self.messages.append({"role": "assistant", "content": content})
        self._trim()
    
    def get_messages(self) -> list[dict[str, str]]:
        """Retorna todas as mensagens."""
        return self.messages.copy()
    
    def _trim(self) -> None:
        """Mantém apenas as últimas N mensagens."""
        if len(self.messages) > self.max_messages:
            # Sempre mantém pares user/assistant
            remove_count = len(self.messages) - self.max_messages
            # Remove pares completos
            if remove_count % 2 != 0:
                remove_count += 1
            self.messages = self.messages[remove_count:]
    
    def clear(self) -> None:
        """Limpa histórico."""
        self.messages.clear()


# Históricos por mundo e NPC
_histories: dict[str, ChatHistory] = {}


def get_history(world_id: str, npc_id: str) -> ChatHistory:
    """Obtém ou cria histórico para world+npc."""
    key = f"{world_id}:{npc_id}"
    if key not in _histories:
        _histories[key] = ChatHistory()
    return _histories[key]


def clear_history(world_id: str, npc_id: str) -> None:
    """Limpa histórico específico."""
    key = f"{world_id}:{npc_id}"
    if key in _histories:
        _histories[key].clear()


def load_persona(persona_path: Path) -> dict[str, Any]:
    """Carrega arquivo de personalidade."""
    if not persona_path.is_file():
        return {}
    try:
        return json.loads(persona_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"[ARAY] Erro ao carregar persona: {e}", flush=True)
        return {}


def build_system_prompt(persona: dict[str, Any], context: dict[str, Any]) -> str:
    """Constrói prompt de sistema com personalidade e contexto."""
    if not persona:
        from language_policy import PT_BR
        return PT_BR + " Você é um sobrevivente do apocalipse zumbi que está ajudando o jogador."
    
    from language_policy import PT_BR
    parts = [PT_BR]
    
    # Identidade básica
    if persona.get("name"):
        parts.append(f"Seu nome é {persona['name']}.")
    if persona.get("occupation"):
        parts.append(f"Sua profissão registrada é {persona['occupation']}.")
    if persona.get("age"):
        parts.append(f"Você tem {persona['age']} anos.")
    if persona.get("gender"):
        parts.append(f"Você é do gênero {persona['gender']}.")
    
    # Background
    if persona.get("background"):
        parts.append(f"\n{persona['background']}")
    
    # Personalidade
    if persona.get("personality"):
        parts.append(f"\nPersonalidade: {persona['personality']}")
    
    # Estilo de fala
    if persona.get("speaking_style"):
        parts.append(f"\n{persona['speaking_style']}")
    
    # Relacionamento
    if persona.get("relationship_to_player"):
        parts.append(f"\n{persona['relationship_to_player']}")
    
    # Contexto do jogo
    if context:
        parts.append("\n--- Contexto Atual ---")
        
        if context.get("time"):
            parts.append(f"Horário no jogo: {context['time']}")
        
        if context.get("location"):
            parts.append(f"Localização: {context['location']}")
        
        if context.get("npc_state"):
            parts.append(f"O que você está fazendo: {context['npc_state']}")
        
        if context.get("distance_to_player"):
            dist = context["distance_to_player"]
            if dist < 2:
                parts.append("Você está bem perto do jogador.")
            elif dist < 5:
                parts.append("Você está a alguns metros do jogador.")
            else:
                parts.append("Você está a certa distância do jogador.")
    
    # Regras de comportamento
    if persona.get("behavior_rules"):
        parts.append("\n--- Regras Importantes ---")
        for rule in persona["behavior_rules"]:
            parts.append(f"- {rule}")
    
    parts.append(PT_BR)
    return "\n".join(parts)


def validate_message(message: str) -> tuple[bool, str]:
    """Valida mensagem de entrada."""
    if not message or not message.strip():
        return False, "Mensagem vazia"
    
    if len(message) > MAX_MESSAGE_LENGTH:
        return False, f"Mensagem muito longa (máx {MAX_MESSAGE_LENGTH} caracteres)"
    
    return True, ""


def build_chat_messages(system_prompt: str, history: ChatHistory, user_message: str) -> list[dict[str, str]]:
    """Monta o prompt sem repetir a fala atual se ela ja entrou no historico."""
    messages = [{"role": "system", "content": system_prompt}]
    prior = history.get_messages()
    messages.extend(prior)
    if not prior or prior[-1].get("role") != "user" or prior[-1].get("content") != user_message:
        messages.append({"role": "user", "content": user_message})
    return messages


def chat_with_ollama(
    client: Any,
    model: str,
    system_prompt: str,
    history: ChatHistory,
    user_message: str,
    profile: dict[str, Any] | None = None,
) -> tuple[bool, str, str, dict]:
    """Envia conversa ao Ollama. Retorna sucesso, texto, erro e metricas nativas."""
    profile = profile or CHAT_PROFILE
    try:
        messages = build_chat_messages(system_prompt, history, user_message)
        from language_policy import chat_ptbr
        response = chat_ptbr(client, model, messages, timeout=CHAT_TIMEOUT, profile=profile)
        
        if not response or not response.get("message"):
            return False, "", "Resposta vazia do Ollama", {}
        
        reply = response["message"].get("content", "").strip()
        
        if not reply:
            return False, "", "Resposta vazia", {}
        
        # Limita tamanho da resposta
        if len(reply) > MAX_RESPONSE_LENGTH:
            reply = reply[:MAX_RESPONSE_LENGTH] + "..."

        metrics = {
            "load_duration": response.get("load_duration"),
            "prompt_eval_duration": response.get("prompt_eval_duration"),
            "eval_duration": response.get("eval_duration"),
            "prompt_eval_count": response.get("prompt_eval_count"),
            "eval_count": response.get("eval_count"),
            "total_duration": response.get("total_duration"),
        }
        return True, reply, "", metrics
    
    except Exception as e:
        return False, "", str(e), {}
