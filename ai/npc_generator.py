"""Gera a identidade de um ajudante. O UUID nao vem do modelo."""

from __future__ import annotations

import json
from typing import Any, Callable

IDENTITY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "first_name": {"type": "string"},
        "last_name": {"type": "string"},
        "sex": {"type": "string", "enum": ["male", "female"]},
        "age": {"type": "integer"},
        "occupation": {"type": "string"},
        "description": {"type": "string"},
        "lore": {"type": "string"},
        "personality": {
            "type": "object",
            "properties": {
                "temperament": {"type": "string"},
                "sociability": {"type": "string"},
                "courage": {"type": "string"},
            },
            "required": ["temperament", "sociability", "courage"],
        },
        "speech": {"type": "string"},
        "skills": {"type": "array", "items": {"type": "string"}},
        "fears": {"type": "string"},
        "motivations": {"type": "string"},
    },
    "required": [
        "first_name", "last_name", "sex", "age", "occupation",
        "description", "lore", "personality", "speech", "skills",
        "fears", "motivations",
    ],
}

_PROMPT = (
    "Crie um sobrevivente adulto original para o universo de Project Zomboid. "
    "Gere nome, sobrenome, sexo, idade, profissao anterior, descricao fisica, "
    "historia pessoal, personalidade, maneira de falar, medos e motivacoes. "
    "A identidade deve ser realista e distinta das identidades ja existentes. "
    "Nao use personagens famosos, nao repita nomes fornecidos na lista de exclusao "
    "e nao invente acontecimentos confirmados do mundo atual. "
    "Habilidades sao apenas narrativa, nao itens nem vantagens de jogo. "
    "Responda exclusivamente com JSON valido, obedecendo ao esquema fornecido."
)


def _object_text(raw: str) -> str:
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("json")
    return raw[start:end + 1]


def validate_identity(data: dict[str, Any], excluded: set[str]) -> dict[str, Any]:
    from persistence import _NAME, normalize_full_name

    if not isinstance(data, dict):
        raise ValueError("json")
    name = str(data.get("first_name") or "").strip()
    surname = str(data.get("last_name") or "").strip()
    if not _NAME.match(name) or not _NAME.match(surname):
        raise ValueError("nome")
    key = normalize_full_name(name, surname)
    if key in excluded:
        raise ValueError("nome repetido")
    sex = data.get("sex")
    if sex not in ("male", "female"):
        raise ValueError("sex")
    age = data.get("age")
    if isinstance(age, float) and age.is_integer():
        age = int(age)
    if not isinstance(age, int) or age < 18 or age > 80:
        raise ValueError("age")
    occupation = str(data.get("occupation") or "").strip()
    description = str(data.get("description") or "").strip()
    lore = str(data.get("lore") or "").strip()
    speech = str(data.get("speech") or "").strip()
    fears = str(data.get("fears") or "").strip()
    motivations = str(data.get("motivations") or "").strip()
    if not occupation or not description or not lore or not speech or not fears or not motivations:
        raise ValueError("texto")
    personality = data.get("personality")
    if not isinstance(personality, dict):
        raise ValueError("personality")
    traits = {}
    for field in ("temperament", "sociability", "courage"):
        value = str(personality.get(field) or "").strip()
        if not value or len(value) > 40:
            raise ValueError("personality")
        traits[field] = value
    skills_raw = data.get("skills")
    if not isinstance(skills_raw, list) or not skills_raw:
        raise ValueError("skills")
    skills = [str(item).strip() for item in skills_raw[:8] if str(item).strip()]
    if not skills:
        raise ValueError("skills")
    return {
        "first_name": name,
        "last_name": surname,
        "sex": sex,
        "age": age,
        "occupation": occupation[:60],
        "description": description[:500],
        "lore": lore[:2000],
        "personality": traits,
        "speech": speech[:300],
        "skills": skills,
        "fears": fears[:300],
        "motivations": motivations[:300],
    }


def generate_identity(excluded: list[str], complete: Callable[[str, dict[str, Any]], str]) -> dict[str, Any]:
    blocked = {item.casefold() for item in excluded}
    prompt = _PROMPT + " Nomes proibidos: " + ", ".join(sorted(blocked) or ["nenhum"]) + "."
    last_error = "geracao"
    for _ in range(2):
        try:
            raw = complete(prompt, IDENTITY_SCHEMA)
            parsed = json.loads(_object_text(raw))
            return validate_identity(parsed, blocked)
        except (ValueError, json.JSONDecodeError, TypeError) as exc:
            last_error = str(exc) or "geracao"
            prompt += " A tentativa anterior foi invalida. Gere outro nome e outro JSON."
    raise ValueError(last_error)
