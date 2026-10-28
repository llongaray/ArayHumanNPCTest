"""Conservative language check, one correction maximum, no model selection changes."""
import re
import time
import unicodedata

PT_BR = "Responda exclusivamente em português brasileiro (PT-BR), mesmo se o jogador escrever em outro idioma. Preserve nomes próprios, profissão, personalidade e fatos reais; não traduza nomes nem invente identidade."


def compare(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.casefold()) if unicodedata.category(c) != 'Mn')


def predominantly_english(text):
    words = re.findall(r"[a-z]+", compare(text))
    en = set('the and you your we our this that with have will would can cannot am is are was were not here there hello thanks please follow stay need help safe'.split())
    pt = set('eu voce voces nos meu minha seu sua estou esta estamos sou somos nao sim aqui ali obrigado obrigada ola com para uma um de do da e que seguir ajuda seguro segura preciso tenho'.split())
    e, p = sum(w in en for w in words), sum(w in pt for w in words)
    return (e >= 2 and e > p * 2) or (p == 0 and len(words)<=3 and any(w in {'hello','hi','thanks','goodbye','bye','please'} for w in words))


def chat_ptbr(client, model, messages, timeout, profile, clock=time.monotonic):
    deadline = clock() + timeout
    raw = client.chat(model, messages, timeout=timeout, profile=profile)
    reply = raw.get('message', {}).get('content') if isinstance(raw, dict) else None
    if not isinstance(reply, str) or not predominantly_english(reply):
        return raw
    if len(reply)>4000:
        raise ValueError('reply_budget')
    remaining = deadline - clock()
    if remaining <= .1:
        raise ValueError('language_correction_expired')
    correction = messages + [
        {'role': 'assistant', 'content': reply},
        {'role': 'user', 'content': PT_BR + ' Reescreva somente sua última resposta em PT-BR. Sem adicionar ações ou fatos.'},
    ]
    # Keep current question/context, discard older whole turns if the extra pass needs space.
    import json
    while len(json.dumps(correction, ensure_ascii=False).encode('utf-8')) > 40000 and len(correction) > 4:
        del correction[1:3]
    fixed = client.chat(model, correction, timeout=remaining, profile=profile)
    text = fixed.get('message', {}).get('content') if isinstance(fixed, dict) else None
    if clock()>=deadline:
        raise ValueError('language_correction_expired')
    if not isinstance(text, str) or not text.strip() or predominantly_english(text):
        raise ValueError('language_not_pt_br')
    print('[ARAY] event=language_correction result=accepted', flush=True)
    return fixed
