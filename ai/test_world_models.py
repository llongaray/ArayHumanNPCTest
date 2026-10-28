#!/usr/bin/env python3
"""Teste isolado para o sistema de modelos por mundo."""

from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).parent))
from world_models import load_world_models, get_model_for_world, set_model_for_world

def main():
    root = Path.home() / "Zomboid" / "Lua" / "ArayHumanNPCTest"
    root.mkdir(parents=True, exist_ok=True)
    
    print("=== Teste: world_models.py ===\n")
    
    # Carregar estado
    print("1. Carregando seleções existentes...")
    world_models = load_world_models(root)
    print(f"   Mundos salvos: {len(world_models)}")
    for world_id, model in world_models.items():
        print(f"   - {world_id}: {model}")
    print()
    
    # Simular modelos disponíveis
    available_models = [
        "hf.co/PatrickPat/remnants-llm-v5-GGUF:Q4_K_M",
        "llama3.2:latest",
        "mistral:latest",
    ]
    
    print("2. Modelos disponíveis no Ollama:")
    for i, model in enumerate(available_models, 1):
        print(f"   {i}. {model}")
    print()
    
    # Testar mundo sandbox/Riverside
    world_id = "sandbox/Riverside"
    print(f"3. Verificando modelo salvo para '{world_id}'...")
    saved_model = get_model_for_world(world_models, world_id, available_models)
    if saved_model:
        print(f"   ✓ Modelo salvo e disponível: {saved_model}")
    else:
        print(f"   ✗ Nenhum modelo salvo ou modelo não está mais disponível")
    print()
    
    # Testar seleção
    print("4. Selecionando modelo 'llama3.2:latest' para o mundo...")
    set_model_for_world(root, world_models, world_id, "llama3.2:latest")
    print(f"   ✓ Seleção salva em: {root / 'world_models.json'}")
    print()
    
    # Recarregar e verificar
    print("5. Recarregando para verificar persistência...")
    world_models = load_world_models(root)
    saved_model = get_model_for_world(world_models, world_id, available_models)
    print(f"   Modelo para '{world_id}': {saved_model}")
    print()
    
    # Testar outro mundo
    world_id2 = "survival/Muldraugh"
    print(f"6. Testando mundo diferente: '{world_id2}'...")
    saved_model2 = get_model_for_world(world_models, world_id2, available_models)
    if saved_model2:
        print(f"   Modelo salvo: {saved_model2}")
    else:
        print(f"   Nenhum modelo salvo para este mundo")
        print("   Selecionando 'mistral:latest'...")
        set_model_for_world(root, world_models, world_id2, "mistral:latest")
        world_models = load_world_models(root)
    print()
    
    # Mostrar JSON final
    print("7. Conteúdo final de world_models.json:")
    json_path = root / "world_models.json"
    if json_path.exists():
        data = json.loads(json_path.read_text(encoding="utf-8"))
        print(f"   {json.dumps(data, indent=2)}")
    print()
    
    print("=== Teste concluído com sucesso ===")

if __name__ == "__main__":
    main()
