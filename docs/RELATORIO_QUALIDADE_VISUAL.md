# Relatório — Refinamento visual do VRChat Avatar Studio

**Versão do aplicativo:** 1.3.0  
**Data:** 17/11/2026

## Alterações realizadas

- A franja frontal foi refeita como mechas curvas em malha 3D, com perfil largo na raiz e pontas afiladas; foi removida a faixa frontal volumosa que dava aparência de capacete.
- O padrão de personagem agora é humanoide (orelhas humanas e sem cauda). Orelhas e caudas de criatura continuam selecionáveis e o preset Kawaii mantém essas opções.
- Os estilos Anime VRChat, Streetwear e Kawaii possuem prévias atualizadas em `examples/previews/`.
- O moletom mantém detalhes mais discretos; decorações que pareciam flutuar sobre a malha foram removidas.
- Versão do aplicativo atualizada para 1.3.0 e pacote `.unitypackage` regenerado.
- Documentação ampliada com o limite do gerador procedural e um fluxo recomendado para modelos de maior acabamento usando VRoid/XAvatar.

## Validação executada

- `python -m unittest discover -s tests -v`: **32 testes aprovados**.
- `python -m py_compile studio/*.py avatar_studio.py`: aprovado.
- `node --check studio/web/app.js`: aprovado.
- `node --check studio/web/viewer.js`: aprovado.
- As três prévias foram geradas e passaram por `selfcheck`.
- `VRChatAvatarStudio_Unity.unitypackage` foi regenerado.

## Limite importante

Esta versão melhora o aspecto e a organização do modelo procedural, mas **não transforma o gerador em um criador de avatares premium**. O corpo, cabelo e roupa ainda são construídos por geometria procedural e cores sólidas; não há cabelo esculpido com muitas camadas, UVs e texturas pintadas à mão, shaders toon autorais nem roupas com acabamento de catálogo.

O Studio ainda não importa `VRM`, `XAvatar`, `FBX` ou `GLB` como corpo-base skinned dentro do editor web. Para um personagem com aparência de VRChat de catálogo, a rota recomendada é criar/customizar a base no VRoid Studio e seguir o fluxo documentado no Unity com XAvatar/XWear Packager e o VRChat SDK. Ver `docs/QUALIDADE_VISUAL.md`.

A compilação e o Build & Publish em um Editor Unity real continuam pendentes, pois dependem da instalação local de Unity e do VRChat SDK.
