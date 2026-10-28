#!/usr/bin/env python3
"""Fase 2: integração com Ollama."""

from __future__ import annotations

import atexit
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

# Add ai directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from world_models import load_world_models, get_model_for_world, set_model_for_world
from persistence import PersistenceStore, handle_persist
from appearance_store import handle as handle_appearance
from conversation_handler import ChatDispatcher, validate_routing
from decision_handler import DecisionDispatcher, DecisionError, envelope, strict_json, MAX_REQUEST_BYTES
from chat_handler import (
    CHAT_PROFILE,
    get_history,
    load_persona,
    build_system_prompt,
    validate_message,
    chat_with_ollama,
)

try:
    import requests
except ImportError:
    requests = None  # type: ignore

SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")
SLEEP_S = 0.05
REQUEST_TIMEOUT = 5

ROOT = Path(os.environ.get(
    "ARAY_BRIDGE_DIR",
    str(Path.home() / "Zomboid" / "Lua" / "ArayHumanNPCTest"),
))
TO_PY = ROOT / "to_py"
TO_LUA = ROOT / "to_lua"
CONFIG_PATH = ROOT / "config" / "ollama_config.json"
PID_FILE = Path(__file__).parent / "service.pid"
PERSONA_PATH = Path(__file__).parent / "persona_default.json"


def write_pid() -> None:
    """Write PID file for launcher to track this process."""
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    print(f"[ARAY] servico PID={os.getpid()} gravado em {PID_FILE}", flush=True)


def cleanup_pid() -> None:
    """Remove PID file on exit."""
    PID_FILE.unlink(missing_ok=True)
    print("[ARAY] servico PID removido", flush=True)


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def load_config() -> dict[str, Any]:
    """Load config, creating default if needed."""
    if not CONFIG_PATH.is_file():
        default = {
            "ollama_url": "http://127.0.0.1:11434",
            "selected_model": None,
            "update_interval_seconds": 30,
        }
        atomic_write(CONFIG_PATH, json.dumps(default, indent=2))
        return default
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "ollama_url": "http://127.0.0.1:11434",
            "selected_model": None,
            "update_interval_seconds": 30,
        }


def save_config(config: dict[str, Any]) -> None:
    atomic_write(CONFIG_PATH, json.dumps(config, indent=2))


class OllamaClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session() if requests else None
        self.last_error = None

    def get_version(self) -> str | None:
        self.last_error=None
        if not self.session:
            self.last_error="requests_unavailable"
            return None
        try:
            resp = self.session.get(
                f"{self.base_url}/api/version",
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                if not data.get("version"): self.last_error="version_missing"
                return data.get("version")
            self.last_error=f"http_status_{resp.status_code}"
        except Exception as exc:
            self.last_error=type(exc).__name__
        return None

    def list_models(self) -> list[str]:
        if not self.session:
            return []
        try:
            resp = self.session.get(
                f"{self.base_url}/api/tags",
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                models = data.get("models", [])
                return [m.get("name", "") for m in models if m.get("name")]
        except Exception:
            pass
        return []
    
    def chat(self, model: str, messages: list[dict[str, str]], timeout: int = 30, profile: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Envia requisição de chat ao Ollama."""
        if not self.session:
            return None
        profile = profile or {}
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": bool(profile.get("stream", False)),
            "keep_alive": profile.get("keep_alive", "30m"),
            "options": {
                "num_ctx": profile.get("num_ctx", 8192),
                "num_predict": profile.get("num_predict", 160),
                "temperature": profile.get("temperature", 0.7),
            },
        }
        if profile.get("format") is not None:
            body["format"] = profile["format"]
        try:
            resp = self.session.post(
                f"{self.base_url}/api/chat",
                json=body,
                timeout=timeout,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            self.last_error=type(e).__name__
            print(f"[ARAY] event=ollama_http_failure reason={self.last_error}", flush=True)
        return None


def validate_ping(data: object) -> str | None:
    if not isinstance(data, dict):
        return "nao objeto"
    kind = data.get("kind")
    req_id = data.get("id")
    world_id = data.get("world_id")
    if kind != "ping":
        return "kind"
    if not isinstance(req_id, str) or not SAFE_ID.match(req_id):
        return "id"
    if not isinstance(world_id, str) or not world_id or ".." in world_id:
        return "world_id"
    if data.get("action") is not None:
        return "action"
    return None


def validate_chat_request(data: object) -> str | None:
    """Valida requisição de chat."""
    if not isinstance(data, dict):
        return "nao objeto"
    kind = data.get("kind")
    req_id = data.get("id")
    world_id = data.get("world_id")
    npc_id = data.get("npc_id")
    message = data.get("message")
    
    if kind != "chat_request":
        return "kind"
    if not isinstance(req_id, str) or not SAFE_ID.match(req_id):
        return "id"
    if not isinstance(world_id, str) or not world_id or ".." in world_id:
        return "world_id"
    if not isinstance(npc_id, str) or not npc_id:
        return "npc_id"
    try:
        import uuid
        if str(uuid.UUID(npc_id))!=npc_id: return "npc_id"
    except ValueError:
        return "npc_id"
    if not isinstance(message, str):
        return "message"
    try:
        validate_routing(data)
    except (ValueError,TypeError,KeyError):
        return "recipient_required"
    
    return None


def seen_path() -> Path:
    return ROOT / "seen_ids.txt"


def already_seen(req_id: str) -> bool:
    path = seen_path()
    if not path.is_file():
        return False
    return req_id in path.read_text(encoding="utf-8").splitlines()


def remember(req_id: str) -> None:
    path = seen_path()
    lines = []
    if path.is_file():
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    lines.append(req_id)
    atomic_write(path, "\n".join(lines[-32:]) + "\n")


class OllamaState:
    def __init__(self, client: OllamaClient, config: dict[str, Any]):
        self.client = client
        self.config = config
        self.version: str | None = None
        self.models: list[str] = []
        self.online = False
        self.last_update = 0.0
        self.world_models = load_world_models(ROOT)
        self.current_world_id: str | None = None
        self.offline_reported=False

    def update(self, force: bool = False) -> None:
        now = time.time()
        interval = self.config.get("update_interval_seconds", 30)
        if not force and (now - self.last_update) < interval:
            return
        
        self.last_update = now
        self.version = self.client.get_version()
        self.online = self.version is not None
        
        if self.online:
            self.offline_reported=False
            self.models = self.client.list_models()
            if self.models:
                print(f"[ARAY] ollama online version={self.version} models={len(self.models)}", flush=True)
            else:
                print(f"[ARAY] ollama online version={self.version} models=0", flush=True)
        else:
            self.models = []
            if not self.offline_reported:
                print(f"[ARAY] event=ollama_offline reason={getattr(self.client,'last_error',None) or 'version_unavailable'}", flush=True)
                self.offline_reported=True


def reply(req_id: str, ollama_state: OllamaState, world_id: str | None = None) -> None:
    # Determine which model to report based on world
    selected = None
    if world_id and ollama_state.online:
        selected = get_model_for_world(ollama_state.world_models, world_id, ollama_state.models)
    
    payload = {
        "id": req_id,
        "kind": "pong",
        "ok": True,
        "service": "aray-ollama",
        "ollama": {
            "online": ollama_state.online,
            "version": ollama_state.version,
            "models": ollama_state.models,
            "selected_model": selected,
        }
    }
    atomic_write(TO_LUA / f"{req_id}.json", json.dumps(payload, separators=(",", ":")))
    print(f"[ARAY] ponte pong id={req_id}", flush=True)


def ns_to_ms(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "n/a"
    return f"{value / 1_000_000:.1f}"


def decision_dispatcher(state: OllamaState) -> DecisionDispatcher:
    dispatcher = getattr(state, "decision_dispatcher", None)
    if dispatcher is None:
        # Reuse the HTTP client implementation, but never share its Session across threads.
        base_url = state.client.base_url
        dispatcher = DecisionDispatcher(
            ROOT / "persistence" / "aray.sqlite", lambda: OllamaClient(base_url))
        state.decision_dispatcher = dispatcher
    return dispatcher


def poll_decisions(state: OllamaState) -> None:
    dispatcher = getattr(state, "decision_dispatcher", None)
    if dispatcher is not None:
        for result in dispatcher.poll():
            path = TO_LUA / f"{result['id']}.json"
            if not path.exists():
                atomic_write(path, json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":")))


def dispatch_decision(req_id: str, data: dict, state: OllamaState, raw: str) -> None:
    output = TO_LUA / f"{req_id}.json"
    if output.exists():
        return  # Replay, including after service restart, cannot replace an earlier reply.
    try:
        if len(raw.encode("utf-8")) > MAX_REQUEST_BYTES:
            raise DecisionError("request_size")
        data = strict_json(raw)
        if data.get("id") != req_id:
            raise DecisionError("request_id_mismatch")
        world = data.get("world_id")
        model = get_model_for_world(state.world_models, world, state.models) if state.online and isinstance(world, str) else None
        result = decision_dispatcher(state).submit(data, model)
    except DecisionError as exc:
        # Do not reflect invalid numeric values or untrusted objects into the envelope.
        result = envelope({"id": req_id}, str(exc))
    if result is not None:
        atomic_write(output, json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":")))


def handle_chat_request(req_id: str, data: dict[str, Any], ollama_state: OllamaState, mailbox_wait_ms: float = -1) -> None:
    """Processa requisição de chat."""
    import time
    t_start = time.perf_counter()
    
    world_id = data["world_id"]
    npc_id = data["npc_id"]
    message = data["message"]
    context = data.get("context", {})
    
    # Valida mensagem
    valid, error = validate_message(message)
    if not valid:
        payload = {
            "id": req_id,
            "kind": "chat_response",
            "world_id": world_id,
            "npc_id": npc_id,
            "success": False,
            "error": error,
        }
        atomic_write(TO_LUA / f"{req_id}.json", json.dumps(payload, separators=(",", ":")))
        print(f"[ARAY] chat validacao falhou id={req_id} error={error}", flush=True)
        return
    
    # Verifica se Ollama está online
    if not ollama_state.online:
        payload = {
            "id": req_id,
            "kind": "chat_response",
            "world_id": world_id,
            "npc_id": npc_id,
            "success": False,
            "error": "Ollama offline",
        }
        atomic_write(TO_LUA / f"{req_id}.json", json.dumps(payload, separators=(",", ":")))
        print(f"[ARAY] chat ollama offline id={req_id}", flush=True)
        return
    
    # Obtém modelo selecionado para o mundo
    model = get_model_for_world(ollama_state.world_models, world_id, ollama_state.models)
    if not model:
        payload = {
            "id": req_id,
            "kind": "chat_response",
            "world_id": world_id,
            "npc_id": npc_id,
            "success": False,
            "error": "Nenhum modelo selecionado",
        }
        atomic_write(TO_LUA / f"{req_id}.json", json.dumps(payload, separators=(",", ":")))
        print(f"[ARAY] chat sem modelo id={req_id}", flush=True)
        return
    
    t_after_validation = time.perf_counter()
    
    # Carrega persona e, se o NPC tiver identidade propria, usa essa identidade.
    persona = load_persona(PERSONA_PATH)
    persona = _persona_for_npc(world_id, npc_id, persona)
    
    # Monta system prompt
    system_prompt = build_system_prompt(persona, context)
    
    # Obtém histórico
    history = get_history(world_id, npc_id)
    
    # Adiciona mensagem do usuário ao histórico
    history.add_user(message)
    
    t_before_ollama = time.perf_counter()
    
    # Chama Ollama
    success, reply_text, error, metrics = chat_with_ollama(
        ollama_state.client,
        model,
        system_prompt,
        history,
        message,
        CHAT_PROFILE,
    )
    
    t_after_ollama = time.perf_counter()
    
    if success:
        # Adiciona resposta ao histórico
        history.add_assistant(reply_text)
        
        payload = {
            "id": req_id,
            "kind": "chat_response",
            "world_id": world_id,
            "npc_id": npc_id,
            "success": True,
            "reply": reply_text,
        }
        # Força ensure_ascii=False para manter UTF-8 literal, não \uXXXX
        t_before_write = time.perf_counter()
        json_text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        atomic_write(TO_LUA / f"{req_id}.json", json_text)
        t_end = time.perf_counter()
        
        validation_ms = (t_after_validation - t_start) * 1000
        prep_ms = (t_before_ollama - t_after_validation) * 1000
        ollama_ms = (t_after_ollama - t_before_ollama) * 1000
        write_ms = (t_end - t_before_write) * 1000
        total_ms = (t_end - t_start) * 1000
        raw = reply_text.encode("utf-8")
        
        print(f"[ARAY] chat sucesso id={req_id} model={model} len={len(reply_text)}", flush=True)
        print(
            f"[ARAY] latencia id={req_id} mailbox={mailbox_wait_ms:.1f}ms"
            f" validacao={validation_ms:.1f}ms prep={prep_ms:.1f}ms"
            f" ollama={ollama_ms:.1f}ms write={write_ms:.1f}ms total_py={total_ms:.1f}ms"
            f" perfil={CHAT_PROFILE['name']} predict={CHAT_PROFILE['num_predict']}",
            flush=True,
        )
        print(
            "[ARAY] ollama nativo id="
            f"{req_id} load={ns_to_ms(metrics.get('load_duration'))}ms"
            f" prompt_eval={ns_to_ms(metrics.get('prompt_eval_duration'))}ms"
            f" eval={ns_to_ms(metrics.get('eval_duration'))}ms"
            f" total={ns_to_ms(metrics.get('total_duration'))}ms"
            f" prompt_tokens={metrics.get('prompt_eval_count')}"
            f" eval_tokens={metrics.get('eval_count')}",
            flush=True,
        )
        # Conversation content is deliberately excluded from diagnostics.
    else:
        payload = {
            "id": req_id,
            "kind": "chat_response",
            "world_id": world_id,
            "npc_id": npc_id,
            "success": False,
            "error": error,
        }
        json_text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        atomic_write(TO_LUA / f"{req_id}.json", json_text)
        print(f"[ARAY] chat falhou id={req_id} error={error}", flush=True)


def _persona_for_npc(world_id: str, npc_id: str, persona: dict[str, Any]) -> dict[str, Any]:
    try:
        store = PersistenceStore(ROOT / "persistence" / "aray.sqlite")
        try:
            npc = store.get_by_id(world_id, npc_id)
        finally:
            store.close()
    except Exception:
        return persona
    if not npc or not npc.get("lore"):
        return persona
    merged = dict(persona)
    merged["name"] = f"{npc['name']} {npc['surname']}".strip()
    merged["age"] = npc.get("age")
    merged["gender"] = "masculino" if npc.get("sex") == "male" else "feminino"
    text = str(npc.get("lore") or "")
    if npc.get("description"):
        text += "\n" + str(npc["description"])
    if npc.get("fears"):
        text += "\nMedos: " + str(npc["fears"])
    if npc.get("motivations"):
        text += "\nMotivacoes: " + str(npc["motivations"])
    merged["background"] = text
    traits = npc.get("personality") if isinstance(npc.get("personality"), dict) else {}
    if traits:
        merged["personality"] = ", ".join(f"{key}: {value}" for key, value in traits.items())
    if npc.get("speech_style"):
        merged["speaking_style"] = npc["speech_style"]
    rules = list(merged.get("behavior_rules") or [])
    rules.append("Nao afirme itens, armas ou vantagens de jogo que o contexto atual nao confirmou.")
    merged["behavior_rules"] = rules
    return merged


def _with_generated_identity(store: PersistenceStore, data: dict[str, Any], ollama_state: OllamaState) -> dict[str, Any]:
    import npc_generator
    from persistence import validate_world_id

    world_id = str(data.get("world_id") or "")
    if validate_world_id(world_id):
        raise ValueError("world_id")
    if not ollama_state or not ollama_state.online or not ollama_state.client:
        raise ValueError("ollama_offline")
    model = get_model_for_world(ollama_state.world_models, world_id, ollama_state.models)
    remnants = "hf.co/PatrickPat/remnants-llm-v5-GGUF:Q4_K_M"
    if not model and remnants in ollama_state.models:
        model = remnants
    if not model:
        raise ValueError("modelo")

    def complete(prompt: str, schema: dict[str, Any]) -> str:
        messages = [{"role": "user", "content": prompt}]
        profile = dict(CHAT_PROFILE)
        profile["num_predict"] = 500
        profile["temperature"] = 0.8
        profile["format"] = schema
        response = ollama_state.client.chat(model, messages, timeout=60, profile=profile)
        content = ""
        if response and response.get("message"):
            content = str(response["message"].get("content") or "")
        if not content.strip():
            profile["format"] = "json"
            response = ollama_state.client.chat(model, messages, timeout=60, profile=profile)
            if response and response.get("message"):
                content = str(response["message"].get("content") or "")
        if not content.strip():
            raise ValueError("ollama")
        return content

    identity = npc_generator.generate_identity(store.name_keys(world_id), complete)
    copied = dict(data)
    copied["identity"] = identity
    return copied


def take_request(ok_path: Path, ollama_state: OllamaState) -> None:
    req_id = ok_path.stem
    tmp_path = TO_PY / f"{req_id}.json.tmp"
    if not SAFE_ID.match(req_id):
        print(f"[ARAY] ponte pedido recusado id", flush=True)
        ok_path.unlink(missing_ok=True)
        return
    if not tmp_path.is_file():
        print(f"[ARAY] ponte pedido recusado tmp id={req_id}", flush=True)
        ok_path.unlink(missing_ok=True)
        return
    try:
        if tmp_path.stat().st_size>MAX_REQUEST_BYTES: raise ValueError("request_budget")
        raw = tmp_path.read_text(encoding="utf-8")
        data = strict_json(raw)
    except (OSError, ValueError, RecursionError):
        print(f"[ARAY] ponte pedido recusado json id={req_id}", flush=True)
        tmp_path.unlink(missing_ok=True)
        ok_path.unlink(missing_ok=True)
        return
    
    if not isinstance(data, dict):
        tmp_path.unlink(missing_ok=True)
        ok_path.unlink(missing_ok=True)
        return
    world_id = data.get("world_id")
    kind = data.get("kind")
    mailbox_wait_ms = -1.0
    try:
        mailbox_wait_ms = max(0.0, (time.time() - ok_path.stat().st_mtime) * 1000.0)
    except OSError:
        mailbox_wait_ms = -1.0
    
    # Limpa arquivos temporários
    tmp_path.unlink(missing_ok=True)
    ok_path.unlink(missing_ok=True)

    if kind == "appearance_request":
        result=handle_appearance(ROOT,data)
        atomic_write(TO_LUA / f"{req_id}.json",json.dumps(result,ensure_ascii=True,separators=(",", ":")))
        return
    if kind == "decision_request":
        dispatch_decision(req_id, data, ollama_state, raw)
        return
    
    # Check for model selection request
    if data.get("set_model") and world_id:
        model_name = data.get("set_model")
        if model_name in ollama_state.models:
            set_model_for_world(ROOT, ollama_state.world_models, world_id, model_name)
            print(f"[ARAY] modelo selecionado world={world_id} model={model_name}", flush=True)
        else:
            print(f"[ARAY] modelo invalido model={model_name}", flush=True)
    
    if kind == "persist":
        print(f"[ARAY-PERSIST] request received id={req_id} op={data.get('op')}", flush=True)
        if already_seen(req_id):
            print(f"[ARAY] persist pedido antigo id={req_id}", flush=True)
            return
        remember(req_id)
        if not isinstance(data, dict):
            return
        print("[ARAY-PERSIST] database operation started", flush=True)
        store = PersistenceStore(ROOT / "persistence" / "aray.sqlite")
        try:
            try:
                if data.get("op") == "create_npc" and not isinstance(data.get("identity"), dict):
                    data = _with_generated_identity(store, data, ollama_state)
                result = handle_persist(store, data)
            except Exception as exc:
                result = {
                    "ok": False,
                    "op": data.get("op"),
                    "error": str(exc)[:180] or "geracao",
                    "message": str(exc)[:180] or "geracao",
                }
        finally:
            store.close()
        print("[ARAY-PERSIST] database operation completed", flush=True)
        result["id"] = req_id
        result["kind"] = "persist_result"
        atomic_write(TO_LUA / f"{req_id}.json", json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        print(f"[ARAY-PERSIST] response written id={req_id} success={str(bool(result.get('ok'))).lower()}", flush=True)
        return

    # Rota por tipo de requisição
    if kind == "chat_request":
        if data.get("protocol_version")==2:
            dispatcher=getattr(ollama_state,"conversation_dispatcher",None)
            if dispatcher is None:
                def factory():
                    return OllamaClient(ollama_state.client.base_url) if isinstance(ollama_state.client,OllamaClient) else ollama_state.client
                dispatcher=ChatDispatcher(ROOT / "persistence" / "aray.sqlite",factory)
                ollama_state.conversation_dispatcher=dispatcher
            # Saved selection is not erased by a stale offline probe. HTTP failures remain explicit.
            model=ollama_state.world_models.get(world_id)
            result=dispatcher.submit(data,model)
            if result: atomic_write(TO_LUA / f"{req_id}.json",json.dumps(result,ensure_ascii=True,separators=(",", ":")))
            return
        reason = validate_chat_request(data)
        if reason:
            print(f"[ARAY] chat_request invalido {reason} id={req_id}", flush=True)
            return
        if already_seen(req_id):
            print(f"[ARAY] chat_request antigo id={req_id}", flush=True)
            return
        remember(req_id)
        handle_chat_request(req_id, data, ollama_state, mailbox_wait_ms)
    else:
        # Ping request
        reason = validate_ping(data)
        if reason:
            print(f"[ARAY] ponte pedido recusado {reason} id={req_id}", flush=True)
            return
        if already_seen(req_id):
            print(f"[ARAY] ponte pedido antigo id={req_id}", flush=True)
            return
        remember(req_id)
        print(f"[ARAY] ponte ping id={req_id} world_id={world_id}", flush=True)
        
        ollama_state.update(force=False)
        reply(req_id, ollama_state, world_id)


def process_mailbox_once(ollama_state: OllamaState) -> None:
    """Dispatch legacy control/chat before accepting background decisions in this batch."""
    def priority(path: Path) -> tuple[int, str]:
        try:
            request_path = TO_PY / f"{path.stem}.json.tmp"
            if request_path.stat().st_size <= MAX_REQUEST_BYTES:
                data = json.loads(request_path.read_text(encoding="utf-8"))
                kind = data.get("kind") if isinstance(data, dict) else None
                return (2 if kind == "decision_request" else 1 if kind == "chat_request" else 0, path.name)
        except (OSError, ValueError, RecursionError):
            pass
        return (0, path.name)

    for ok_path in sorted(TO_PY.glob("*.ok"), key=priority):
        take_request(ok_path, ollama_state)
    poll_decisions(ollama_state)
    dispatcher=getattr(ollama_state,"conversation_dispatcher",None)
    if dispatcher:
        for result in dispatcher.poll():
            atomic_write(TO_LUA / f"{result['id']}.json",json.dumps(result,ensure_ascii=True,separators=(",", ":")))


def main() -> None:
    # Write PID for launcher tracking
    write_pid()
    atexit.register(cleanup_pid)
    
    if not requests:
        print("[ARAY] ERRO: requests nao instalado. Execute: pip install requests", flush=True)
        return
    
    TO_PY.mkdir(parents=True, exist_ok=True)
    TO_LUA.mkdir(parents=True, exist_ok=True)
    
    config = load_config()
    client = OllamaClient(config.get("ollama_url", "http://127.0.0.1:11434"))
    ollama_state = OllamaState(client, config)
    
    # Initial Ollama check
    ollama_state.update(force=True)
    
    print(f"[ARAY] servico ollama iniciado dir={ROOT}", flush=True)
    print(f"[ARAY] ollama url={config.get('ollama_url')}", flush=True)
    
    try:
        while True:
            process_mailbox_once(ollama_state)
            time.sleep(SLEEP_S)
    finally:
        dispatcher = getattr(ollama_state, "decision_dispatcher", None)
        if dispatcher is not None:
            dispatcher.close()


if __name__ == "__main__":
    main()
