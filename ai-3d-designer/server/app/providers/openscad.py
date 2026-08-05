"""OpenSCAD の実行.

**LLM が生成したコードをサーバー上で実行する**ため、ここは信頼境界そのものになる。
OpenSCAD は描画用の DSL だが、ファイルを読み書きできる命令を持つので、
そのまま渡すと任意ファイルの読み出しに使われうる。実行前に必ず検査する。
"""

from __future__ import annotations

import asyncio
import re
import shutil
import tempfile
from pathlib import Path

#: ファイルシステムに触れる命令。LLM の出力に含まれていたら実行しない。
#: 正当な設計コードがこれらを必要とすることはない。
_FORBIDDEN_DIRECTIVES = (
    "include",
    "use",
    "import",
    "surface",
    "dxf_",  # dxf_cross / dxf_dim
)

#: 上の語が識別子の一部ではなく命令として現れているかを見る。
#: 例: `include <foo>` は禁止だが、変数名 `use_lid` は許す。
_DIRECTIVE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(" + "|".join(_FORBIDDEN_DIRECTIVES) + r")(?![A-Za-z0-9_])",
    re.IGNORECASE,
)

_MAX_SOURCE_BYTES = 100_000


class OpenScadError(Exception):
    """コードが不正、またはレンダリングに失敗した."""


class UnsafeScadError(OpenScadError):
    """危険な命令を含むため実行を拒否した."""


def assert_safe(source: str) -> None:
    """実行してよいコードかを検査する。危険なら UnsafeScadError."""
    if len(source.encode("utf-8")) > _MAX_SOURCE_BYTES:
        raise UnsafeScadError("コードが大きすぎます")

    found = _DIRECTIVE_PATTERN.search(_strip_comments(source))
    if found is not None:
        raise UnsafeScadError(f"ファイル操作を伴う命令は使用できません: {found.group(1)}")


def _strip_comments(source: str) -> str:
    """コメント内の語で誤検出しないよう先に落とす."""
    without_block = re.sub(r"/\*.*?\*/", " ", source, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", " ", without_block)


class OpenScadRenderer:
    """OpenSCAD の CLI を叩いて STL を得る.

    実行は一時ディレクトリの中だけで行い、終わったら消す。
    """

    def __init__(self, binary: str = "openscad", timeout_seconds: float = 120.0) -> None:
        self._binary = binary
        self._timeout = timeout_seconds

    @property
    def available(self) -> bool:
        return shutil.which(self._binary) is not None

    async def render_stl(self, source: str) -> bytes:
        assert_safe(source)

        if not self.available:
            raise OpenScadError(
                f"OpenSCAD が見つかりません ({self._binary})。"
                "インストールするか APP_CAD_MODE=stub を指定してください"
            )

        with tempfile.TemporaryDirectory(prefix="scad-") as workdir:
            directory = Path(workdir)
            scad_path = directory / "model.scad"
            stl_path = directory / "model.stl"
            scad_path.write_text(source, encoding="utf-8")

            process = await asyncio.create_subprocess_exec(
                self._binary,
                "-o",
                str(stl_path),
                str(scad_path),
                cwd=workdir,  # 相対パスの解決先を一時ディレクトリに閉じる
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                _, stderr = await asyncio.wait_for(process.communicate(), timeout=self._timeout)
            except TimeoutError:
                process.kill()
                await process.wait()
                raise OpenScadError(
                    f"レンダリングが {int(self._timeout)} 秒以内に終わりませんでした"
                ) from None

            if process.returncode != 0:
                raise OpenScadError(_describe_failure(stderr))
            if not stl_path.exists() or stl_path.stat().st_size == 0:
                raise OpenScadError("STL が生成されませんでした(形状が空の可能性があります)")

            return stl_path.read_bytes()


def _describe_failure(stderr: bytes) -> str:
    """OpenSCAD の出力から、原因が分かる行だけを拾う."""
    text = stderr.decode("utf-8", errors="replace")
    interesting = [
        line.strip()
        for line in text.splitlines()
        if line.startswith(("ERROR:", "WARNING:", "Parser error", "Compile error"))
    ]
    if interesting:
        return "OpenSCAD エラー: " + " / ".join(interesting[:5])
    return f"OpenSCAD の実行に失敗しました (終了コード): {text.strip()[:300]}"
