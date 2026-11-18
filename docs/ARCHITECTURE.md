# Arquitetura técnica

## Componentes

- `avatar_studio.py`: ponto de entrada CLI e servidor.
- `studio/builder.py`: normalização das opções, construção procedural, esqueleto, malhas, métricas e ranking heurístico.
- `studio/geometry.py`: primitivas e operações vetoriais usadas pelo gerador.
- `studio/parts.py`: sanitização de acessórios, biblioteca de templates e importação OBJ.
- `studio/export.py`: JSON do importador Unity, GLB/glTF, PNG da paleta, miniatura, manifesto e publicação transacional do pacote.
- `studio/server.py`: API HTTP local, validação de requisições e entrega da interface.
- `studio/web/`: HTML, CSS, JavaScript do editor e visualizador WebGL.
- `Unity/Assets/VRChatAvatarStudio/Editor/`: importador JSON/PNG, criação do Humanoid, configuração de Descriptor/FX/menus/PhysBones e estimativa de desempenho.
- `tests/test_studio.py`: testes Python e verificações estáticas de regressão para as fontes C#.

## Fluxo de geração

1. O navegador envia as opções normalizadas para `/api/model`.
2. `builder.py` produz esqueleto, malhas, blendshapes, paleta e estatísticas.
3. `server.py` envia os dados binários ao visualizador; `viewer.js` apresenta o preview WebGL.
4. Para exportar, `export.py` gera o JSON do Unity, PNG, GLB, preset e manifesto em staging.
5. Depois de validar os artefatos, a pasta final é substituída por rename; a pasta anterior só é removida após o commit.
6. No Unity, `VASImporter` valida JSON/PNG, cria assets e objetos, constrói o Humanoid e restaura o backup em caso de falha.
7. `VASVRChatSetup` configura componentes e assets do SDK por reflexão e `SerializedObject`. O SDK Control Panel permanece a validação oficial.

## Limites conhecidos

- O formato de avatar atual é a versão 1; ainda não há migração automática de versões.
- O importador OBJ ignora MTL, textura, UV e normais originais; usa triangulação em leque.
- O ranking é uma estimativa parcial e não substitui o SDK.
- C# não foi compilado nem validado em um Unity real neste ciclo.
