#!/usr/bin/env python3
"""Small self-contained server for the Image Lab demo page."""

from __future__ import annotations

import base64
import io
import json
import math
import mimetypes
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from uuid import uuid4

try:
    from PIL import Image, ImageOps
except Exception:  # pragma: no cover - optional deployment dependency
    Image = None
    ImageOps = None


APP_ROOT = Path(os.getenv("IMAGE_LAB_ROOT", "/opt/image-lab"))
HTML_PATH = APP_ROOT / "image-lab.html"
OUTPUT_ROOT = APP_ROOT / "output"
HOST = os.getenv("IMAGE_LAB_HOST", "127.0.0.1")
PORT = int(os.getenv("IMAGE_LAB_PORT", "28081"))
BASE_URL = os.getenv("IMAGE_LAB_BASE_URL", "https://cdn.jucode.top/v1").rstrip("/")
API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
PROVIDER = os.getenv("IMAGE_LAB_PROVIDER", "vivgrid_primary")
IMAGE_MODEL = os.getenv("IMAGE_LAB_IMAGE_MODEL", "grok-imagine-image-lite")
RESPONSE_MODEL = os.getenv("IMAGE_LAB_RESPONSE_MODEL", "gpt-5.2")
REFERENCE_IMAGE_MAX_BYTES = int(os.getenv("IMAGE_LAB_REFERENCE_IMAGE_MAX_BYTES", str(700 * 1024)))

ASPECTS = {
    "16:9": (16, 9),
    "9:21": (9, 21),
    "9:16": (9, 16),
    "1:1": (1, 1),
    "4:3": (4, 3),
    "3:4": (3, 4),
    "3:2": (3, 2),
    "2:3": (2, 3),
    "21:9": (21, 9),
}


def json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def simplify_ratio(width: int, height: int) -> str:
    gcd = math.gcd(max(width, 1), max(height, 1))
    return f"{width // gcd}:{height // gcd}"


def dimensions(req: dict[str, Any]) -> dict[str, Any]:
    ratio_key = str(req.get("aspect_ratio") or "16:9").strip()
    if ratio_key not in ASPECTS:
        ratio_key = "16:9"
    ratio_w, ratio_h = ASPECTS[ratio_key]
    long_edge = max(int(req.get("long_edge") or 1536), 64)
    multiple = max(int(req.get("round_to_multiple") or 64), 1)
    if ratio_w >= ratio_h:
        width = long_edge
        height = max(round(long_edge * ratio_h / ratio_w), 1)
    else:
        height = long_edge
        width = max(round(long_edge * ratio_w / ratio_h), 1)
    width = max(int(math.ceil(width / multiple) * multiple), multiple)
    height = max(int(math.ceil(height / multiple) * multiple), multiple)
    return {"width": width, "height": height, "size": f"{width}x{height}", "aspect_ratio": simplify_ratio(width, height)}


def merged_prompt(prompt: str, negative: str) -> str:
    prompt = str(prompt or "").strip()
    negative = str(negative or "").strip()
    return f"{prompt}\n\nAvoid: {negative}" if negative else prompt


def pick_image_model(req: dict[str, Any]) -> str:
    return str(req.get("model") or IMAGE_MODEL).strip()


def pick_response_model(req: dict[str, Any]) -> str:
    return str(req.get("response_model") or RESPONSE_MODEL).strip()


def upstream_base_url(req: dict[str, Any]) -> str:
    return str(req.get("base_url_override") or BASE_URL).strip().rstrip("/")


def upstream_api_key(req: dict[str, Any]) -> str:
    return str(req.get("api_key_override") or API_KEY).strip()


def upstream_provider_name(req: dict[str, Any]) -> str:
    return str(req.get("provider") or PROVIDER).strip() or PROVIDER


def request_json(url: str, body: dict[str, Any], timeout: int) -> dict[str, Any]:
    api_key = str(body.pop("_api_key_override", "") or API_KEY).strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured on the image-lab server")
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "image-lab/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"HTTP {exc.code} from {url}: {detail or exc.reason}") from exc


def encode_multipart(fields: dict[str, Any], files: list[tuple[str, str, str, bytes]]) -> tuple[bytes, str]:
    boundary = f"----ImageLabBoundary{uuid4().hex}"
    lines: list[bytes] = []
    for name, value in fields.items():
        lines.append(f"--{boundary}".encode())
        lines.append(f'Content-Disposition: form-data; name="{name}"'.encode())
        lines.append(b"")
        lines.append(str(value).encode("utf-8"))
    for field_name, filename, content_type, content in files:
        lines.append(f"--{boundary}".encode())
        lines.append(f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"'.encode())
        lines.append(f"Content-Type: {content_type}".encode())
        lines.append(b"")
        lines.append(content)
    lines.append(f"--{boundary}--".encode())
    lines.append(b"")
    return b"\r\n".join(lines), f"multipart/form-data; boundary={boundary}"


def request_multipart(url: str, fields: dict[str, Any], files: list[tuple[str, str, str, bytes]], timeout: int) -> dict[str, Any]:
    api_key = str(fields.pop("_api_key_override", "") or API_KEY).strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured on the image-lab server")
    data, content_type = encode_multipart(fields, files)
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": content_type,
            "Accept": "application/json",
            "User-Agent": "image-lab/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"HTTP {exc.code} from {url}: {detail or exc.reason}") from exc


def load_input_image(item: dict[str, Any], index: int) -> tuple[str, str, bytes]:
    filename = str(item.get("filename") or f"input_{index + 1}.png")
    content_type = str(item.get("content_type") or "image/png")
    if item.get("data_url"):
        header, _, data = str(item["data_url"]).partition(",")
        match = re.match(r"data:([^;]+);base64", header)
        if match:
            content_type = match.group(1)
        return filename, content_type, base64.b64decode(data)
    if item.get("base64_data"):
        return filename, content_type, base64.b64decode(str(item["base64_data"]))
    if item.get("url"):
        with urllib.request.urlopen(str(item["url"]), timeout=120) as response:
            content_type = response.headers.get_content_type() or content_type
            return filename, content_type, response.read()
    raise ValueError("input image must provide data_url, base64_data, or url")


def normalize_reference_image(filename: str, content_type: str, payload: bytes) -> tuple[str, str, bytes]:
    if len(payload) <= REFERENCE_IMAGE_MAX_BYTES and content_type in {"image/jpeg", "image/jpg", "image/png", "image/webp"}:
        return filename, content_type, payload
    if Image is None or ImageOps is None:
        return filename, content_type, payload
    try:
        with Image.open(io.BytesIO(payload)) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            max_side = 1024 if len(payload) <= 2 * 1024 * 1024 else 768
            quality = 82
            best = payload
            for _ in range(8):
                candidate = image.copy()
                candidate.thumbnail((max_side, max_side))
                out = io.BytesIO()
                candidate.save(out, format="JPEG", quality=quality, optimize=True)
                best = out.getvalue()
                if len(best) <= REFERENCE_IMAGE_MAX_BYTES or max_side <= 512:
                    break
                max_side = max(512, int(max_side * 0.82))
                quality = max(62, quality - 8)
            stem = Path(filename).stem or "reference"
            return f"{stem}_server_ref.jpg", "image/jpeg", best
    except Exception:
        return filename, content_type, payload


def extract_images(payload: dict[str, Any]) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    for index, item in enumerate(payload.get("data") or []):
        if isinstance(item, dict) and item.get("b64_json"):
            images.append({"index": index, "b64_json": item["b64_json"], "output_format": payload.get("output_format") or "png"})
        elif isinstance(item, dict) and item.get("url"):
            images.append({"index": index, "url": item["url"], "output_format": payload.get("output_format") or "png"})
    for index, item in enumerate(payload.get("output") or []):
        if isinstance(item, dict) and item.get("type") == "image_generation_call" and item.get("result"):
            images.append({"index": index, "b64_json": item["result"], "output_format": item.get("output_format") or "png"})
    for index, item in enumerate(payload.get("images") or []):
        if isinstance(item, dict) and item.get("b64_json"):
            images.append({"index": index, "b64_json": item["b64_json"], "output_format": item.get("output_format") or "png"})
        elif isinstance(item, dict) and item.get("url"):
            images.append({"index": index, "url": item["url"], "output_format": item.get("output_format") or "png"})
    return images


def save_images(req: dict[str, Any], result: dict[str, Any]) -> list[dict[str, Any]]:
    if req.get("save") is False:
        return []
    target = OUTPUT_ROOT / datetime.now().strftime("%Y%m%d")
    target.mkdir(parents=True, exist_ok=True)
    saved: list[dict[str, Any]] = []
    prefix = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(req.get("file_name_prefix") or "image_lab"))[:80]
    for index, image in enumerate(result.get("images") or []):
        ext = str(image.get("output_format") or req.get("output_format") or "png").strip(".").lower() or "png"
        filename = f"{prefix}_{datetime.now().strftime('%H%M%S')}_{index + 1}.{ext}"
        path = target / filename
        if image.get("b64_json"):
            path.write_bytes(base64.b64decode(image["b64_json"]))
        elif image.get("url"):
            with urllib.request.urlopen(image["url"], timeout=180) as response:
                path.write_bytes(response.read())
        rel = path.relative_to(OUTPUT_ROOT).as_posix()
        saved.append(
            {
                "path": str(path),
                "asset_path": rel,
                "asset_url": f"/api/assets/{rel}",
                "download_url": f"/api/download/{rel}",
                "requested_size": result.get("size"),
                "actual_size": result.get("size"),
                "provider": result.get("provider"),
                "endpoint": result.get("endpoint"),
                "model": result.get("model"),
            }
        )
    return saved


def call_images_generations(req: dict[str, Any], dims: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": pick_image_model(req),
        "prompt": merged_prompt(req.get("prompt", ""), req.get("negative_prompt", "")),
        "size": dims["size"],
        "n": int(req.get("n") or 1),
        "response_format": req.get("response_format") or "b64_json",
        "_api_key_override": upstream_api_key(req),
    }
    for name in ("quality", "background", "output_format", "moderation", "seed", "user"):
        if req.get(name) not in (None, ""):
            body[name] = req[name]
    if req.get("negative_prompt"):
        body["negative_prompt"] = req["negative_prompt"]
    data = request_json(f"{upstream_base_url(req)}/images/generations", body, int(req.get("timeout_seconds") or 300))
    images = extract_images(data)
    if not images:
        raise RuntimeError(f"upstream returned no image payload; keys={list(data.keys())}")
    return {"success": True, "endpoint": "images_generations", "provider": upstream_provider_name(req), "model": body["model"], "images": images, "raw_response_keys": list(data.keys())}


def call_responses(req: dict[str, Any], dims: dict[str, Any]) -> dict[str, Any]:
    tool: dict[str, Any] = {"type": "image_generation", "model": pick_image_model(req), "size": dims["size"], "output_format": req.get("output_format") or "png"}
    if int(req.get("n") or 1) != 1:
        tool["n"] = int(req.get("n") or 1)
    for name in ("quality", "background", "moderation"):
        if req.get(name) not in (None, ""):
            tool[name] = req[name]
    body: dict[str, Any] = {
        "model": pick_response_model(req),
        "input": merged_prompt(req.get("prompt", ""), req.get("negative_prompt", "")),
        "tool_choice": {"type": "image_generation"},
        "tools": [tool],
        "_api_key_override": upstream_api_key(req),
    }
    if req.get("seed") not in (None, ""):
        body["seed"] = req["seed"]
    data = request_json(f"{upstream_base_url(req)}/responses", body, int(req.get("timeout_seconds") or 300))
    images = extract_images(data)
    if not images:
        raise RuntimeError(f"responses returned no image payload; keys={list(data.keys())}")
    return {"success": True, "endpoint": "responses", "provider": upstream_provider_name(req), "model": tool["model"], "response_model": body["model"], "images": images, "raw_response_keys": list(data.keys())}


def call_responses_with_reference_images(req: dict[str, Any], dims: dict[str, Any]) -> dict[str, Any]:
    sources = req.get("input_images") or []
    if not sources:
        return call_responses(req, dims)
    tool: dict[str, Any] = {"type": "image_generation", "model": pick_image_model(req), "size": dims["size"], "output_format": req.get("output_format") or "png"}
    if int(req.get("n") or 1) != 1:
        tool["n"] = int(req.get("n") or 1)
    for name in ("quality", "background", "moderation"):
        if req.get(name) not in (None, ""):
            tool[name] = req[name]

    content: list[dict[str, Any]] = [{"type": "input_text", "text": merged_prompt(req.get("prompt", ""), req.get("negative_prompt", ""))}]
    for index, item in enumerate(sources):
        filename, content_type, payload = load_input_image(item, index)
        filename, content_type, payload = normalize_reference_image(filename, content_type, payload)
        data_url = f"data:{content_type};base64,{base64.b64encode(payload).decode('ascii')}"
        content.append({"type": "input_image", "image_url": data_url})

    body: dict[str, Any] = {
        "model": pick_response_model(req),
        "input": [{"role": "user", "content": content}],
        "tool_choice": {"type": "image_generation"},
        "tools": [tool],
        "_api_key_override": upstream_api_key(req),
    }
    if req.get("seed") not in (None, ""):
        body["seed"] = req["seed"]
    data = request_json(f"{upstream_base_url(req)}/responses", body, int(req.get("timeout_seconds") or 300))
    images = extract_images(data)
    if not images:
        raise RuntimeError(f"responses reference-image path returned no image payload; keys={list(data.keys())}")
    return {
        "success": True,
        "endpoint": "responses_reference_images",
        "provider": upstream_provider_name(req),
        "model": tool["model"],
        "response_model": body["model"],
        "images": images,
        "raw_response_keys": list(data.keys()),
    }


def call_images_edits(req: dict[str, Any], dims: dict[str, Any]) -> dict[str, Any]:
    sources = req.get("input_images") or []
    if not sources:
        raise ValueError("input_images is required for image_to_image")
    fields: dict[str, Any] = {
        "model": pick_image_model(req),
        "prompt": merged_prompt(req.get("prompt", ""), req.get("negative_prompt", "")),
        "size": dims["size"],
        "n": str(int(req.get("n") or 1)),
        "_api_key_override": upstream_api_key(req),
    }
    for name in ("quality", "background", "output_format", "moderation", "user"):
        if req.get(name) not in (None, ""):
            fields[name] = str(req[name])
    if req.get("negative_prompt"):
        fields["negative_prompt"] = str(req["negative_prompt"])
    field_name = "image" if len(sources) == 1 else "image[]"
    files = [(field_name, *normalize_reference_image(*load_input_image(item, index))) for index, item in enumerate(sources)]
    if req.get("mask_image"):
        files.append(("mask", *normalize_reference_image(*load_input_image(req["mask_image"], len(sources)))))
    data = request_multipart(f"{upstream_base_url(req)}/images/edits", fields, files, int(req.get("timeout_seconds") or 300))
    images = extract_images(data)
    if not images:
        raise RuntimeError(f"image edit API returned no image payload; keys={list(data.keys())}")
    return {"success": True, "endpoint": "images_edits", "provider": upstream_provider_name(req), "model": fields["model"], "images": images, "raw_response_keys": list(data.keys())}


def generate(req: dict[str, Any]) -> dict[str, Any]:
    if not str(req.get("prompt") or "").strip():
        raise ValueError("prompt is required")
    dims = dimensions(req)
    endpoint = str(req.get("endpoint") or "auto").lower()
    mode = str(req.get("mode") or "auto").lower()
    errors: list[str] = []
    has_reference_images = bool(req.get("input_images")) or mode == "image_to_image"
    if has_reference_images:
        candidates = ["responses_reference_images", "images_edits"] if endpoint == "auto" else [endpoint]
    else:
        candidates = ["images_generations", "responses"] if endpoint == "auto" else [endpoint]
    for candidate in candidates:
        try:
            if candidate in ("images_edits", "edits", "image_edits"):
                result = call_images_edits(req, dims)
            elif candidate in ("responses_reference_images", "responses_with_images"):
                result = call_responses_with_reference_images(req, dims)
            elif candidate in ("images_generations", "images", "image"):
                result = call_images_generations(req, dims)
            elif candidate in ("responses", "response"):
                result = call_responses_with_reference_images(req, dims) if has_reference_images else call_responses(req, dims)
            else:
                raise ValueError(f"unsupported endpoint: {candidate}")
            result.update({"mode": "image_to_image" if has_reference_images else "text_to_image", **dims})
            result["saved_images"] = save_images(req, result)
            result["saved_image"] = result["saved_images"][0] if result["saved_images"] else None
            result["diagnostics"] = errors
            result["degraded_params"] = []
            return result
        except Exception as exc:  # keep fallback practical for demos
            errors.append(f"{candidate}: {exc}")
    raise RuntimeError("all generation endpoints failed; " + "; ".join(errors))


class Handler(BaseHTTPRequestHandler):
    server_version = "ImageLab/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store" if content_type.startswith("application/json") else "public, max-age=60")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status: int, payload: Any) -> None:
        self.send_bytes(status, json_bytes(payload), "application/json; charset=utf-8")

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/image-lab.html"):
            self.send_bytes(200, HTML_PATH.read_bytes(), "text/html; charset=utf-8")
            return
        if path == "/health":
            self.send_json(200, {"status": "healthy", "service": "image-lab"})
            return
        if path == "/api/images/presets/aspect-ratios":
            self.send_json(200, {"default": "16:9", "mobile_default": "9:21", "presets": [{"name": k, "ratio": list(v), "default_size": dimensions({"aspect_ratio": k})["size"]} for k, v in ASPECTS.items()]})
            return
        if path == "/api/images/capabilities":
            self.send_json(200, {"providers": [{"name": PROVIDER, "base_url": BASE_URL, "models": [IMAGE_MODEL], "available": bool(API_KEY)}], "parameter_support": {"prompt": "supported", "aspect_ratio": "supported", "negative_prompt": "best_effort", "seed": "best_effort", "input_images": "images_edits_with_responses_reference_fallback"}})
            return
        if path.startswith("/api/assets/") or path.startswith("/api/download/"):
            rel = path.split("/api/assets/", 1)[-1] if path.startswith("/api/assets/") else path.split("/api/download/", 1)[-1]
            file_path = (OUTPUT_ROOT / rel).resolve()
            if not str(file_path).startswith(str(OUTPUT_ROOT.resolve())) or not file_path.is_file():
                self.send_json(404, {"detail": "file not found"})
                return
            mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            self.send_bytes(200, file_path.read_bytes(), mime)
            return
        self.send_json(404, {"detail": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        try:
            if path in ("/api/images/generate", "/api/images/render"):
                self.send_json(200, generate(self.read_json()))
                return
            if path == "/api/images/batch-render":
                body = self.read_json()
                results = []
                success = 0
                failure = 0
                for index, req in enumerate(body.get("requests") or []):
                    try:
                        result = generate(req)
                        results.append({"index": index, "success": True, "result": result})
                        success += 1
                    except Exception as exc:
                        results.append({"index": index, "success": False, "error": {"message": str(exc)}})
                        failure += 1
                self.send_json(200, {"success": failure == 0, "success_count": success, "failure_count": failure, "results": results})
                return
            self.send_json(404, {"detail": "not found"})
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:2000]
            self.send_json(exc.code, {"detail": {"message": detail or f"HTTP {exc.code}"}})
        except Exception as exc:
            self.send_json(500, {"detail": {"message": str(exc)}})


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"image-lab listening on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
