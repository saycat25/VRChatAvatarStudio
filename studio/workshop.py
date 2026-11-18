# -*- coding: utf-8 -*-
"""Biblioteca local de assets e integração opcional com a API Meshy.

Os arquivos originais nunca são alterados. Toda saída de IA é salva como um
novo asset derivado, com referência/hash do original e política de edição.
"""
from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
import threading
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_DIR = PROJECT_ROOT / "workspace"
ASSET_DIR = WORKSPACE_DIR / "assets"
ASSET_INDEX = WORKSPACE_DIR / "assets.json"
TASKS_FILE = WORKSPACE_DIR / "ai_tasks.json"
MAX_ASSET_BYTES = 25 * 1024 * 1024
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_MODEL_AI_BYTES = 25 * 1024 * 1024
MAX_GENERATED_BYTES = 120 * 1024 * 1024
MESHY_BASE = "https://api.meshy.ai"
MESHY_API_KEY = os.environ.get("MESHY_API_KEY", "").strip()
_STORE_LOCK = threading.RLock()

MODEL_EXTENSIONS = {".glb", ".gltf", ".fbx", ".obj", ".stl", ".vrm"}
AI_MODEL_EXTENSIONS = {".glb", ".gltf", ".fbx", ".obj", ".stl"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
CATEGORY_EXTENSIONS = {
    "base_model": MODEL_EXTENSIONS,
    "accessory": MODEL_EXTENSIONS,
    "reference": IMAGE_EXTENSIONS,
    "texture": IMAGE_EXTENSIONS,
}
CATEGORY_LABELS = {
    "base_model": "Modelo-base", "accessory": "Acessório", "reference": "Referência visual",
    "texture": "Textura", "generated": "Gerado por IA",
}


class WorkshopError(ValueError):
    pass


def configure_api_key(key: str | None = None) -> bool:
    """Define chave apenas em memória; não grava em arquivos nem devolve o segredo."""
    global MESHY_API_KEY
    value = (key if key is not None else os.environ.get("MESHY_API_KEY", "")).strip()
    if len(value) > 300:
        raise WorkshopError("A chave da API é inválida (comprimento excessivo).")
    MESHY_API_KEY = value
    return bool(MESHY_API_KEY)


def api_status() -> dict:
    return {"provider": "Meshy", "configured": bool(MESHY_API_KEY),
            "key_storage": "memória do servidor local; não é gravada no projeto"}


def _ensure_dirs() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path, fallback):
    try:
        with path.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
        return data if isinstance(data, type(fallback)) else fallback
    except (OSError, ValueError, TypeError):
        return fallback


def _write_json_atomic(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def _assets() -> list[dict]:
    _ensure_dirs()
    return _read_json(ASSET_INDEX, [])


def _tasks() -> list[dict]:
    _ensure_dirs()
    return _read_json(TASKS_FILE, [])


def _safe_display_name(filename: str) -> str:
    raw = Path(str(filename).replace("\\", "/")).name
    raw = re.sub(r"[\x00-\x1f\x7f]", "", raw).strip()
    return raw[:120] or "arquivo"


def _validate_file_signature(ext: str, data: bytes) -> None:
    if not data:
        raise WorkshopError("O arquivo está vazio.")
    if ext in (".png",) and not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise WorkshopError("O conteúdo não corresponde a um PNG válido.")
    if ext in (".jpg", ".jpeg") and not data.startswith(b"\xff\xd8\xff"):
        raise WorkshopError("O conteúdo não corresponde a um JPEG válido.")
    if ext == ".webp" and not (data[:4] == b"RIFF" and data[8:12] == b"WEBP"):
        raise WorkshopError("O conteúdo não corresponde a um WebP válido.")
    if ext in (".glb", ".vrm") and not data.startswith(b"glTF"):
        raise WorkshopError("O arquivo GLB/VRM não tem cabeçalho glTF válido.")
    if ext == ".gltf":
        try:
            parsed = json.loads(data.decode("utf-8-sig"))
        except (UnicodeDecodeError, ValueError):
            raise WorkshopError("O arquivo glTF não contém JSON válido.")
        if not isinstance(parsed, dict) or not isinstance(parsed.get("asset"), dict) or parsed["asset"].get("version") != "2.0":
            raise WorkshopError("O arquivo não declara glTF 2.0.")
    if ext == ".obj":
        sample = data[:200_000].decode("utf-8-sig", errors="ignore")
        if not re.search(r"(?m)^\s*v\s+[-+0-9.eE]+\s+[-+0-9.eE]+\s+[-+0-9.eE]+", sample):
            raise WorkshopError("O OBJ não contém vértices válidos no início do arquivo.")
    if ext == ".fbx":
        if not (data.startswith(b"Kaydara FBX Binary") or b"FBXHeaderExtension" in data[:100_000]):
            raise WorkshopError("O FBX não parece estar no formato binário ou ASCII esperado.")
    if ext == ".stl":
        is_binary = len(data) >= 84 and (84 + int.from_bytes(data[80:84], "little") * 50) <= len(data)
        is_ascii = data.lstrip().lower().startswith(b"solid") and b"facet" in data[:100_000].lower()
        if not (is_binary or is_ascii):
            raise WorkshopError("O STL não parece ser binário ou ASCII válido.")


def save_asset(filename: str, category: str, data: bytes, *, source_task: str | None = None,
               derived_from: str | None = None, policy: dict | None = None) -> dict:
    category = str(category or "").lower()
    name = _safe_display_name(filename)
    ext = Path(name).suffix.lower()
    if category not in CATEGORY_EXTENSIONS and category != "generated":
        raise WorkshopError("Categoria de arquivo desconhecida.")
    allowed = MODEL_EXTENSIONS if category == "generated" else CATEGORY_EXTENSIONS[category]
    if ext not in allowed:
        raise WorkshopError("Formato %s não permitido para %s." % (ext or "sem extensão", CATEGORY_LABELS.get(category, category)))
    limit = MAX_IMAGE_BYTES if ext in IMAGE_EXTENSIONS else MAX_ASSET_BYTES
    if len(data) > limit:
        raise WorkshopError("Arquivo excede o limite de %d MB." % (limit // (1024 * 1024)))
    _validate_file_signature(ext, data)
    asset_id = uuid.uuid4().hex
    digest = hashlib.sha256(data).hexdigest()
    stored_name = asset_id + ext
    _ensure_dirs()
    path = ASSET_DIR / stored_name
    temp = path.with_suffix(path.suffix + ".tmp")
    with _STORE_LOCK:
        temp.write_bytes(data)
        os.replace(temp, path)
        item = {
            "id": asset_id, "name": name, "category": category,
            "category_label": CATEGORY_LABELS.get(category, category), "extension": ext,
            "size": len(data), "sha256": digest, "stored_name": stored_name,
            "created_at": int(time.time()), "original": source_task is None,
        }
        if source_task:
            item["source_task"] = source_task
        if derived_from:
            item["derived_from"] = derived_from
        if policy:
            item["policy"] = policy
        items = _assets()
        items.append(item)
        _write_json_atomic(ASSET_INDEX, items)
    return public_asset(item)


def public_asset(item: dict) -> dict:
    return {k: v for k, v in item.items() if k != "stored_name"}


def list_assets() -> list[dict]:
    with _STORE_LOCK:
        return [public_asset(x) for x in _assets() if (ASSET_DIR / x.get("stored_name", "")).is_file()]


def get_asset(asset_id: str) -> tuple[dict, bytes]:
    if not re.fullmatch(r"[0-9a-f]{32}", str(asset_id or "")):
        raise WorkshopError("Identificador de arquivo inválido.")
    with _STORE_LOCK:
        item = next((x for x in _assets() if x.get("id") == asset_id), None)
        if not item:
            raise WorkshopError("Arquivo não encontrado na biblioteca.")
        path = ASSET_DIR / item["stored_name"]
        try:
            data = path.read_bytes()
        except OSError:
            raise WorkshopError("O arquivo armazenado não está disponível.")
    if hashlib.sha256(data).hexdigest() != item.get("sha256"):
        raise WorkshopError("A integridade do arquivo mudou; a IA não utilizará este arquivo.")
    return item, data


def asset_data_uri(asset_id: str, max_bytes: int) -> tuple[dict, str]:
    item, data = get_asset(asset_id)
    if len(data) > max_bytes:
        raise WorkshopError("O arquivo é grande demais para esta operação de IA (limite %d MB)." % (max_bytes // (1024 * 1024)))
    ext = item["extension"]
    if ext not in AI_MODEL_EXTENSIONS and ext not in IMAGE_EXTENSIONS:
        raise WorkshopError("Este formato é armazenado, mas não é aceito nesta operação da API.")
    mime = mimetypes.types_map.get(ext, "application/octet-stream")
    if ext in AI_MODEL_EXTENSIONS:
        mime = "application/octet-stream"
    return item, "data:%s;base64,%s" % (mime, base64.b64encode(data).decode("ascii"))


def _meshy_request(path: str, payload: dict | None = None, *, method: str | None = None, timeout: int = 120) -> dict:
    if not MESHY_API_KEY:
        raise WorkshopError("Configure a chave da API Meshy na aba IA & Modelos antes de gerar. A chave fica apenas na memória desta execução.")
    url = MESHY_BASE + path
    headers = {"Authorization": "Bearer " + MESHY_API_KEY, "Accept": "application/json"}
    body = None
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=body, headers=headers, method=method or ("POST" if body is not None else "GET"))
    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read(2 * 1024 * 1024)
            return json.loads(raw.decode("utf-8")) if raw else {}
    except HTTPError as exc:
        detail = exc.read(16_000).decode("utf-8", errors="replace")
        try:
            parsed = json.loads(detail)
            detail = parsed.get("message") or parsed.get("error") or detail
        except ValueError:
            pass
        raise WorkshopError("Meshy respondeu HTTP %d: %s" % (exc.code, str(detail)[:900]))
    except (URLError, TimeoutError, OSError) as exc:
        raise WorkshopError("Não foi possível conectar à API Meshy: %s" % exc)
    except (UnicodeDecodeError, ValueError) as exc:
        raise WorkshopError("Resposta inesperada da API Meshy: %s" % exc)


def _find_asset(asset_id: str) -> dict:
    if not asset_id:
        raise WorkshopError("Selecione ou envie o arquivo de modelo solicitado.")
    item, _ = get_asset(asset_id)
    return item


def _save_job(job: dict) -> None:
    with _STORE_LOCK:
        tasks = _tasks()
        tasks = [x for x in tasks if x.get("id") != job["id"]]
        tasks.insert(0, job)
        _write_json_atomic(TASKS_FILE, tasks[:100])


def list_jobs() -> list[dict]:
    with _STORE_LOCK:
        return [{k: v for k, v in x.items() if k != "remote_id"} for x in _tasks()]


def create_task(payload: dict) -> dict:
    mode = payload.get("mode")
    operation = payload.get("operation")
    prompt = str(payload.get("prompt", "")).strip()
    asset_kind = str(payload.get("asset_kind", "accessory"))
    if mode not in ("preserve", "personalize"):
        raise WorkshopError("Escolha o modo Preservar ou Personalizar.")
    if operation not in ("text_to_3d", "image_to_3d", "retexture_base", "remesh_base"):
        raise WorkshopError("Operação de IA desconhecida.")
    if not prompt and operation in ("text_to_3d", "retexture_base"):
        raise WorkshopError("Descreva o que deseja gerar ou como deseja retexturizar.")
    if len(prompt) > 620:
        raise WorkshopError("A descrição deve ter até 620 caracteres para reservar espaço às instruções técnicas da geração.")
    if asset_kind not in ("hair", "clothing", "accessory", "character"):
        raise WorkshopError("Tipo de peça desconhecido.")

    base_item = None
    reference_item = None
    remote_endpoint = ""
    request_payload: dict
    if operation == "text_to_3d":
        instructions = {
            "hair": "Create a standalone 3D hair asset only, no head or body, game-ready, clean geometry, UVs and PBR textures.",
            "clothing": "Create a standalone wearable clothing 3D asset only, no human body, game-ready, clean geometry, UVs and PBR textures.",
            "accessory": "Create a standalone 3D avatar accessory only, no human body, game-ready, clean geometry, UVs and PBR textures.",
            "character": "Create one complete stylized humanoid anime character, full body, neutral A-pose, game-ready, clean geometry, UVs and PBR textures.",
        }[asset_kind]
        final_prompt = prompt + ". " + instructions
        if len(final_prompt) > 800:
            final_prompt = prompt[:max(1, 798 - len(instructions))] + ". " + instructions
        request_payload = {"mode": "preview", "prompt": final_prompt, "ai_model": "meshy-7.1",
                           "should_remesh": True, "target_polycount": 80000 if asset_kind == "character" else 25000,
                           "target_formats": ["glb"]}
        if asset_kind == "character":
            request_payload["pose_mode"] = "a-pose"
        remote_endpoint = "/openapi/v2/text-to-3d"
        preview_note = "Prévia sem textura; use Refinar para gerar materiais e texturas."
    elif operation == "image_to_3d":
        reference_item, image_uri = asset_data_uri(str(payload.get("reference_asset_id", "")), MAX_IMAGE_BYTES)
        if reference_item["category"] not in ("reference", "texture"):
            raise WorkshopError("A entrada Imagem para 3D precisa ser uma imagem de referência.")
        instruction = {
            "hair": "Generate only a standalone 3D hairstyle/hair asset. Do not include the head or body.",
            "clothing": "Generate only a standalone wearable clothing asset. Do not include the human body.",
            "accessory": "Generate only the isolated 3D accessory shown in the reference.",
            "character": "Generate a complete stylized humanoid anime character, full body, neutral A-pose.",
        }[asset_kind]
        request_payload = {"image_url": image_uri, "ai_model": "meshy-7.1", "should_texture": True,
                           "enable_pbr": True, "should_remesh": True,
                           "target_polycount": 80000 if asset_kind == "character" else 25000,
                           "target_formats": ["glb"]}
        if asset_kind == "character":
            request_payload["pose_mode"] = "a-pose"
        remote_endpoint = "/openapi/v1/image-to-3d"
        preview_note = "Modelo criado a partir da imagem; compare com a referência antes de utilizar. " + instruction
    else:
        target_id = str(payload.get("target_asset_id") or payload.get("base_asset_id") or "")
        base_item, model_uri = asset_data_uri(target_id, MAX_MODEL_AI_BYTES)
        if base_item["category"] not in ("base_model", "accessory", "generated"):
            raise WorkshopError("Escolha um modelo 3D, não uma imagem/textura.")
        if mode == "preserve" and base_item["category"] == "base_model":
            raise WorkshopError("No modo Preservar, o modelo-base não pode ser retexturizado/remalhado. Selecione um acessório separado ou mude para Personalizar.")
        if base_item["extension"] not in AI_MODEL_EXTENSIONS:
            raise WorkshopError("A API de processamento não aceita este formato. Converta VRM para GLB/FBX/OBJ no Blender antes.")
        if operation == "retexture_base":
            request_payload = {"model_url": model_uri, "text_style_prompt": prompt[:780],
                               "enable_original_uv": True, "enable_pbr": True}
            ref_id = str(payload.get("reference_asset_id", ""))
            if ref_id:
                reference_item, image_uri = asset_data_uri(ref_id, MAX_IMAGE_BYTES)
                if reference_item["category"] not in ("reference", "texture"):
                    raise WorkshopError("Imagem de estilo precisa ser uma referência ou textura.")
                request_payload.pop("text_style_prompt", None)
                request_payload["image_style_url"] = image_uri
            remote_endpoint = "/openapi/v1/retexture"
            preview_note = "Nova versão retexturizada; a geometria da base não é intencionalmente editada."
        else:
            request_payload = {"model_url": model_uri, "target_formats": ["glb", "fbx"],
                               "topology": "triangle", "target_polycount": 50000}
            remote_endpoint = "/openapi/v1/remesh"
            preview_note = "Nova topologia/cópia do modelo; remesh não altera deliberadamente rosto ou proporções."

    # Custos/créditos do provedor são externos; nunca criar tarefa sem clique explícito do usuário.
    response = _meshy_request(remote_endpoint, request_payload)
    remote_id = str(response.get("result", ""))
    if not remote_id:
        raise WorkshopError("A API não retornou o identificador da tarefa.")
    route = ("text_to_3d" if operation == "text_to_3d" else
             "image_to_3d" if operation == "image_to_3d" else
             "retexture" if operation == "retexture_base" else "remesh")
    policy = ({"preserve": ["base_model", "face", "body", "skeleton"],
               "new_asset": True, "editable": ["hair", "clothing", "accessories"],
               "target_is_separate_accessory": bool(base_item and base_item["category"] in ("accessory", "generated"))}
              if mode == "preserve" else
              {"original_immutable": True, "editable_in_working_copy": ["face", "body", "hair", "clothing", "materials"],
               "skeleton_preserved_by_default": True, "requires_rig_retarget_for_skeleton_changes": True})
    job = {
        "id": uuid.uuid4().hex, "provider": "Meshy", "remote_id": remote_id, "route": route,
        "operation": operation, "mode": mode, "asset_kind": asset_kind,
        "prompt": prompt, "status": "PENDING", "progress": 0,
        "created_at": int(time.time()), "note": preview_note,
        "policy": policy,
    }
    if base_item:
        job["target_asset_id"] = base_item["id"]
        job["source_sha256"] = base_item["sha256"]
        job["source_name"] = base_item["name"]
    if reference_item:
        job["reference_asset_id"] = reference_item["id"]
    _save_job(job)
    return {k: v for k, v in job.items() if k not in ("remote_id",)}


def refine_text_task(preview_job_id: str) -> dict:
    with _STORE_LOCK:
        preview = next((x for x in _tasks() if x.get("id") == preview_job_id), None)
    if not preview or preview.get("route") != "text_to_3d" or preview.get("status") != "SUCCEEDED":
        raise WorkshopError("Somente uma prévia de Texto para 3D concluída pode ser refinada.")
    response = _meshy_request("/openapi/v2/text-to-3d", {
        "mode": "refine", "preview_task_id": preview["remote_id"],
        "enable_pbr": True, "target_formats": ["glb"], "texture_resolution": "4k"})
    remote_id = str(response.get("result", ""))
    if not remote_id:
        raise WorkshopError("A API não retornou o identificador da tarefa de refinamento.")
    job = {"id": uuid.uuid4().hex, "provider": "Meshy", "remote_id": remote_id,
           "route": "text_to_3d", "operation": "refine_text_3d", "mode": preview["mode"],
           "asset_kind": preview["asset_kind"], "prompt": preview.get("prompt", ""),
           "status": "PENDING", "progress": 0, "created_at": int(time.time()),
           "note": "Texturas PBR 4K geradas a partir da prévia.", "preview_job_id": preview_job_id,
           "policy": preview.get("policy", {})}
    _save_job(job)
    return {k: v for k, v in job.items() if k != "remote_id"}


def _download_model(url: str) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not (parsed.hostname or "").endswith(".meshy.ai"):
        raise WorkshopError("A URL de resultado não pertence a um domínio seguro do Meshy.")
    req = Request(url, headers={"User-Agent": "VRChatAvatarStudio/1.4"})
    try:
        with urlopen(req, timeout=180) as response:
            data = response.read(MAX_GENERATED_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise WorkshopError("Não foi possível baixar o modelo gerado: %s" % exc)
    if len(data) > MAX_GENERATED_BYTES:
        raise WorkshopError("O modelo gerado excede o limite local de 120 MB.")
    if not data.startswith(b"glTF"):
        raise WorkshopError("O resultado GLB baixado não tem cabeçalho válido.")
    return data


def poll_task(job_id: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{32}", str(job_id or "")):
        raise WorkshopError("Identificador de tarefa inválido.")
    with _STORE_LOCK:
        jobs = _tasks()
        job = next((x for x in jobs if x.get("id") == job_id), None)
    if not job:
        raise WorkshopError("Tarefa não encontrada.")
    endpoint = {"text_to_3d": "/openapi/v2/text-to-3d/", "image_to_3d": "/openapi/v1/image-to-3d/",
                "retexture": "/openapi/v1/retexture/", "remesh": "/openapi/v1/remesh/"}.get(job["route"])
    remote = _meshy_request(endpoint + job["remote_id"])
    job["status"] = str(remote.get("status", job.get("status", "PENDING"))).upper()
    job["progress"] = max(0, min(100, int(remote.get("progress") or 0)))
    if job["status"] == "SUCCEEDED" and not job.get("result_asset_id"):
        model_url = (remote.get("model_urls") or {}).get("glb")
        if model_url:
            try:
                data = _download_model(model_url)
                source_task = job["id"]
                derived = job.get("target_asset_id")
                name = "IA_%s_%s.glb" % (job.get("asset_kind", "modelo"), job["id"][:8])
                created = save_asset(name, "generated", data, source_task=source_task,
                                     derived_from=derived, policy=job.get("policy"))
                job["result_asset_id"] = created["id"]
                job["result_name"] = created["name"]
                job["result_sha256"] = created["sha256"]
            except WorkshopError as exc:
                job["download_error"] = str(exc)
    if job["status"] == "FAILED":
        error = remote.get("task_error") or {}
        job["error"] = error.get("message") or str(error) or "Falha informada pelo provedor."
    job["updated_at"] = int(time.time())
    _save_job(job)
    return {k: v for k, v in job.items() if k != "remote_id"}


def asset_download_path(asset_id: str) -> Path:
    item, _ = get_asset(asset_id)
    return ASSET_DIR / item["stored_name"]


def asset_private_record(asset_id: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{32}", str(asset_id or "")):
        raise WorkshopError("Identificador de arquivo inválido.")
    item = next((x for x in _assets() if x.get("id") == asset_id), None)
    if not item:
        raise WorkshopError("Arquivo não encontrado.")
    return item
