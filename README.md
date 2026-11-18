# VRChat Avatar Studio

**Versão:** 1.4.0 · **Formato de avatar:** `vrc-avatar-studio` v1 · **Pacote Unity:** 1.1.0

[Português](#português) · [English](#english)

---

## Português

O **VRChat Avatar Studio** é uma ferramenta local, feita em Python, para criar avatares estilizados para VRChat, editar acessórios e exportar os dados para um projeto Unity. A versão 1.4.0 adiciona o **AI Avatar Workshop**, uma biblioteca local de modelos e uma integração opcional com a API Meshy.

> **Estado do repositório:** documentação pública da versão 1.4.0. A integração Unity/VRChat descrita abaixo ainda requer compilação e validação num projeto real com Unity e VRChat SDK Avatars.

### O que o programa faz

- Gera um avatar procedural com corpo, rosto, cabelo, roupas, esqueleto, expressões e visemas.
- Permite criar acessórios com primitivas, usar modelos da biblioteca e importar OBJ.
- Oferece edição de posição, rotação, escala, cor, espelhamento, grupos, ocultação e bloqueio de peças.
- Inclui histórico de desfazer/refazer, recuperação automática local, presets, paletas e temas.
- Exporta um pacote com JSON de avatar, GLB, PNG, preset e manifesto com hashes SHA-256.
- Fornece uma ferramenta de Editor para importar o pacote no Unity e configurar elementos do avatar.
- A aba **IA & Modelos** mantém uma biblioteca local e conecta-se opcionalmente à Meshy.

### AI Avatar Workshop 1.4.0

A interface oferece dois modos persistidos localmente no navegador:

**Preservar meu modelo**
- Mantém base, rosto, corpo e esqueleto originais.
- Gera cabelos, roupas, calçados e acessórios como assets separados, por texto ou imagem.
- Bloqueia retexturização/remesh da base.
- Permite processar um acessório separado sem tocar no modelo-base.
- Cada resultado é salvo como arquivo novo.

**Personalizar meu modelo**
- Cria uma cópia de trabalho derivada do modelo-base.
- Usa Meshy Retexture para gerar materiais/texturas e Meshy Remesh para reconstruir topologia/contagem de faces.
- Salva cada saída como novo GLB associado ao SHA-256 da origem.
- Não remodela automaticamente nariz, olhos, mandíbula, proporções corporais ou esqueleto.

### Fluxo de trabalho

1. Inicie o Studio e abra a interface no navegador.
2. Crie um avatar procedural ou carregue um modelo na biblioteca local.
3. Escolha Preservar ou Personalizar, conforme a operação desejada.
4. Se usar Meshy, conecte a API key, selecione modelo/asset e operação, revise o aviso de compartilhamento e créditos e confirme a tarefa.
5. Revise os resultados no Blender ou Unity.
6. Exporte o pacote e importe-o num projeto Unity preparado com VRChat SDK Avatars.

### Requisitos e execução

- Python 3.8 ou superior.
- Não são necessárias dependências Python de terceiros para o gerador local.
- Windows: execute `Iniciar.bat`.
- Linux/macOS: execute `./iniciar.sh`.
- Alternativa: `python avatar_studio.py`.
- Interface local: `http://127.0.0.1:8765`.

Comandos úteis:

```bash
python avatar_studio.py --version
python avatar_studio.py --list-templates
python avatar_studio.py --random --seed 5 --add halo --add wings_angel --name MeuAvatar
python avatar_studio.py --preset meu.preset.json --out saida
python -m unittest discover -s tests -v
```

### Meshy: configuração e custos

1. Obtenha uma API key na plataforma de desenvolvedor Meshy.
2. Inicie o Studio e abra **IA & Modelos**.
3. Cole a chave em **Conectar IA (Meshy)** e clique em **Conectar**.
4. Escolha a operação e o arquivo/referência.
5. Leia e confirme o aviso antes de criar uma tarefa.

A chave fica apenas numa variável do processo Python em memória; não é gravada no navegador, presets, exports ou disco. Também é possível definir `MESHY_API_KEY` no ambiente antes de iniciar. Ao reiniciar, conecte novamente se não tiver usado a variável de ambiente.

**Atenção:** tarefas Meshy podem consumir créditos e enviar ao provedor os arquivos e descrições escolhidos. Não envie conteúdo confidencial ou sem os direitos necessários. O uso da API pode exigir um plano pago/créditos na Meshy; isso é independente deste projeto.

### Formatos e limites

| Conteúdo | Formatos | Limite local |
|---|---|---:|
| Modelo-base e acessórios | GLB, glTF, FBX, OBJ, STL, VRM | 25 MB |
| Imagens e texturas | PNG, JPG, JPEG, WebP | 20 MB |

GLB autocontido é preferido. Arquivos glTF podem depender de buffers e texturas externos. VRM é armazenado como original, mas deve ser convertido para GLB/FBX/OBJ antes das operações Meshy usadas pelo Workshop.

Os arquivos de usuário ficam em `workspace/`, ignorada pelo Git. Essa pasta não deve ser distribuída.

### Integração Unity/VRChat

O pacote Unity está em `VRChatAvatarStudio_Unity.unitypackage`; alternativamente, copie `Unity/Assets/VRChatAvatarStudio` para `Assets` num projeto Unity compatível. A ferramenta de Editor valida o JSON/PNG, cria malhas e ossos, configura Humanoid e tenta configurar Descriptor, visemas, olhos, PhysBones, FX, parâmetros e menus.

O fluxo esperado é: importar no Unity → revisar a configuração → abrir VRChat SDK Control Panel → login → Build & Publish.

**Validação pendente:** o código C# não foi compilado/executado num Editor Unity neste ciclo. Importação real, compatibilidade do SDK, Humanoid, Descriptor, FX, menus, PhysBones, visemas e Build & Publish precisam ser testados num projeto criado pelo VRChat Creator Companion. O ranking local é apenas uma estimativa heurística; o valor oficial é o do SDK Control Panel.

### Limitações conhecidas

- O Studio não carrega arbitrariamente modelos GLB/FBX enviados no visualizador 3D atual.
- A IA não encaixa automaticamente roupas/acessórios em qualquer armature nem executa weight transfer/skin binding genérico.
- Retexture altera superfície; Remesh altera topologia. Nenhuma das operações faz edição semântica seletiva de rosto/corpo.
- A geração por imagem não garante reconstrução fiel de todos os ângulos.
- OBJ não importa MTL, imagens, UVs ou normais originais; polígonos côncavos podem exigir pré-triangulação.
- O modo procedural tem estilo próprio e não substitui um modelo premium feito por artista.
- Os resultados devem ser revisados no Blender/Unity e validados no VRChat SDK antes de publicar.

### Segurança e privacidade

- Uploads recebem identificadores internos aleatórios.
- Extensões e assinaturas são verificadas; uploads recebem SHA-256, revalidado antes do uso.
- Caminhos persistidos não são aceitos diretamente da interface.
- O arquivo-base não é substituído por respostas da IA.
- A chave Meshy fica na memória do servidor local.
- Downloads de resultado exigem HTTPS e domínio `*.meshy.ai`.
- Operações que podem consumir créditos exigem confirmação explícita.
- Não versionar `workspace/`, chaves, tokens, modelos privados ou dados pessoais.

### Testes

A suíte foi executada no pacote recebido: **43 testes passaram** com `python -m unittest discover -s tests -v`. Isso valida os testes Python e verificações estáticas incluídas; não substitui a compilação Unity, testes em Blender ou Build & Publish real.

### Documentação

- [AI Avatar Workshop](docs/AI_AVATAR_WORKSHOP.md)
- [Arquitetura](docs/ARCHITECTURE.md)
- [Status da implementação](docs/IMPLEMENTATION_STATUS.md)
- [Qualidade visual](docs/QUALIDADE_VISUAL.md)
- [Changelog](CHANGELOG.md)

### Licença

Este repositório está público, mas ainda não declara uma licença de código aberto. A visibilidade pública no GitHub, por si só, não concede permissão geral para redistribuir, modificar ou comercializar o código. A licença deve ser escolhida pelo mantenedor.

---

## English

**VRChat Avatar Studio** is a local Python application for procedural, stylized VRChat avatar creation, accessory editing and Unity export. Version 1.4.0 adds the **AI Avatar Workshop**, a local asset library and optional Meshy API integration.

### Main features

- Procedural avatar generation: body, face, hair, clothes, skeleton, expressions and visemes.
- Accessory creation from primitives and templates, plus OBJ import.
- Part transforms, colors, mirroring, groups, visibility and edit locking.
- Undo/redo, local autosave, presets, palettes and themes.
- Export package containing avatar JSON, GLB, PNG, preset and SHA-256 manifest.
- Unity Editor importer/setup utilities.
- Optional Meshy-powered text-to-3D, image-to-3D, retexture and remesh workflows.

### AI modes

- **Preserve my model:** keeps the base model, face, body and skeleton unchanged. AI-generated hair, clothes, shoes and accessories are saved as separate assets. Retexture/remesh of the base model is blocked.
- **Customize my model:** performs retexture/remesh on a working copy. Outputs are new GLB files linked to the source SHA-256; the original is not overwritten.

Neither mode automatically performs generic garment skinning, weight transfer, rig retargeting or semantic face/body reshaping.

### Run locally

- Python 3.8+; no third-party Python packages are required by the local procedural generator.
- Windows: run `Iniciar.bat`.
- Linux/macOS: run `./iniciar.sh`.
- Or run `python avatar_studio.py`.
- Open `http://127.0.0.1:8765`.

Run tests with:

```bash
python -m unittest discover -s tests -v
```

### Meshy API and privacy

A Meshy API key is held only in the Python server process memory, or can be supplied through `MESHY_API_KEY`. AI tasks may consume provider credits and upload the selected model/reference and prompt to Meshy. Review the confirmation prompt and do not upload confidential or unauthorized content.

### Unity / VRChat status

The Unity Editor integration is included, but it has **not been compiled or exercised in a real Unity + VRChat SDK project in this validation cycle**. Import, Humanoid setup, Descriptor, FX, menus, PhysBones, visemes and Build & Publish must be verified with the target Unity and VRChat SDK versions. The local performance rank is heuristic, not the official SDK rank.

### License

The repository is public but currently has no open-source license. Public visibility alone does not grant general rights to reuse, modify, redistribute or sell the code. The maintainer must select a license.

