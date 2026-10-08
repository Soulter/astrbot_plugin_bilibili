from __future__ import annotations

import asyncio
import base64
import os
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_LOGO_BYTES = 5 * 1024 * 1024
MAX_LOGO_PIXELS = 16 * 1024 * 1024
MAX_LOGO_DIMENSION = 2048
ALLOWED_LOGO_FORMATS = {"JPEG", "PNG", "WEBP"}
CUSTOM_LOGO_FILENAME = "custom_logo.png"


class LogoService:
    """管理渲染卡片使用的可选自定义头像。"""

    def __init__(self, default_path: str | Path, data_dir: str | Path) -> None:
        self.default_path = Path(default_path)
        self.data_dir = Path(data_dir)
        self.custom_path = self.data_dir / CUSTOM_LOGO_FILENAME
        self._mutation_lock = asyncio.Lock()

    def get_active_path(self) -> str:
        """返回当前生效的图片路径；自定义图片不存在时回退到默认资源。"""
        path = self.custom_path if self.custom_path.is_file() else self.default_path
        return str(path)

    def get_status(self) -> dict[str, Any]:
        """返回页面预览所需的状态，不暴露本地文件路径。"""
        path = Path(self.get_active_path())
        customized = path == self.custom_path and path.is_file()
        data_url = self._as_data_url(path) if path.is_file() else ""
        width, height = self._get_dimensions(path)
        return {
            "customized": customized,
            "filename": CUSTOM_LOGO_FILENAME if customized else path.name,
            "data_url": data_url,
            "width": width,
            "height": height,
            "size_bytes": path.stat().st_size if path.is_file() else 0,
        }

    async def save_upload(self, upload: Any) -> dict[str, Any]:
        """校验并将上传图片规范化保存为 PNG。"""
        if upload is None or not callable(getattr(upload, "save", None)):
            raise TypeError("请先选择一张图片。")
        content_length = getattr(upload, "content_length", None)
        if isinstance(content_length, int) and content_length > MAX_LOGO_BYTES:
            raise ValueError("图片不能超过 5 MB。")

        async with self._mutation_lock:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            upload_path = self.data_dir / f".{CUSTOM_LOGO_FILENAME}.upload"
            output_path = self.data_dir / f".{CUSTOM_LOGO_FILENAME}.tmp"
            try:
                await upload.save(upload_path)
                if not upload_path.is_file():
                    raise ValueError("上传图片为空。")
                if upload_path.stat().st_size > MAX_LOGO_BYTES:
                    raise ValueError("图片不能超过 5 MB。")
                self._convert_to_png(upload_path, output_path)
                if output_path.stat().st_size > MAX_LOGO_BYTES:
                    raise ValueError("处理后的图片不能超过 5 MB。")
                os.replace(output_path, self.custom_path)
            finally:
                upload_path.unlink(missing_ok=True)
                output_path.unlink(missing_ok=True)

        return self.get_status()

    async def reset(self) -> dict[str, Any]:
        """删除自定义图片并恢复默认头像。"""
        async with self._mutation_lock:
            self.custom_path.unlink(missing_ok=True)
        return self.get_status()

    @staticmethod
    def _convert_to_png(source_path: Path, output_path: Path) -> None:
        try:
            with Image.open(source_path) as image:
                image_format = (image.format or "").upper()
                if image_format not in ALLOWED_LOGO_FORMATS:
                    raise ValueError("仅支持 PNG、JPEG 或 WebP 图片。")
                if image.width <= 0 or image.height <= 0:
                    raise ValueError("图片尺寸无效。")
                if image.width * image.height > MAX_LOGO_PIXELS:
                    raise ValueError("图片像素数量过大，请上传尺寸更小的图片。")
                image.verify()

            with Image.open(source_path) as image:
                image = ImageOps.exif_transpose(image)
                image.thumbnail(
                    (MAX_LOGO_DIMENSION, MAX_LOGO_DIMENSION),
                    Image.Resampling.LANCZOS,
                )
                if image.mode not in {"RGB", "RGBA"}:
                    image = image.convert("RGBA")
                image.save(output_path, format="PNG", optimize=True)
        except Image.DecompressionBombError as exc:
            raise ValueError("图片像素数量过大，请上传尺寸更小的图片。") from exc
        except ValueError:
            raise
        except (OSError, UnidentifiedImageError) as exc:
            raise ValueError("无法识别图片文件，请上传有效的 PNG、JPEG 或 WebP 图片。") from exc

    @staticmethod
    def _as_data_url(path: Path) -> str:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    @staticmethod
    def _get_dimensions(path: Path) -> tuple[int, int]:
        if not path.is_file():
            return 0, 0
        try:
            with Image.open(path) as image:
                return image.width, image.height
        except (OSError, UnidentifiedImageError):
            return 0, 0
