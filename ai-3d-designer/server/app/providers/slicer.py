"""印刷時間とフィラメント使用量の見積り.

正確な値はスライサにかけないと出ないが、スライサ本体(Bambu Studio)は
GUI 依存が重く、どの環境でも動くとは限らない。そこで 2 実装を用意する:

- BambuStudioCliSlicer: 実測。Docker で動かす前提(Dockerfile 同梱)
- HeuristicSlicer:      メッシュの体積からの概算。どこでも動く

概算であることは呼び出し側に必ず伝わるようにする(estimated フラグ)。
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

#: フィラメント密度 (g/cm3)。Bambu Lab 純正の公称値。
FILAMENT_DENSITY = {
    "PLA": 1.24,
    "PETG": 1.27,
    "ABS": 1.04,
    "TPU": 1.21,
    "ASA": 1.07,
}
_DEFAULT_DENSITY = 1.24

#: 既定の充填率。Bambu Studio の標準プロファイルに合わせる。
_DEFAULT_INFILL = 0.15

#: 外殻が占める体積の割合の目安。小物では無視できない大きさになる。
_SHELL_FRACTION = 0.35

#: 0.4mm ノズル・0.2mm 積層でのおおよその吐出速度 (mm3/秒)。
_FLOW_RATE_MM3_PER_SEC = 8.0


@dataclass(frozen=True)
class PrintEstimate:
    print_time_min: int
    filament_grams: float
    estimated: bool
    """True なら概算。スライサ実測ではない。"""

    source: str


class SlicerError(Exception):
    pass


class Slicer(Protocol):
    async def estimate(
        self, *, model_bytes: bytes, material: str, filename: str = "model.3mf"
    ) -> PrintEstimate: ...


def _density_for(material: str) -> float:
    upper = material.upper()
    for name, density in FILAMENT_DENSITY.items():
        if name in upper:
            return density
    return _DEFAULT_DENSITY


class HeuristicSlicer:
    """メッシュの体積からの概算。スライサが無い環境でも必ず値を返す.

    外殻ぶんと充填ぶんを足して materialize される体積を求め、
    密度から重量を、吐出速度から時間を出す。誤差は大きいが、
    桁が合っていれば「どれくらいかかるか」の判断には足りる。
    """

    def __init__(self, infill: float = _DEFAULT_INFILL) -> None:
        self._infill = infill

    async def estimate(
        self, *, model_bytes: bytes, material: str, filename: str = "model.3mf"
    ) -> PrintEstimate:
        import trimesh

        suffix = Path(filename).suffix.lstrip(".") or "3mf"
        try:
            mesh = trimesh.load(
                trimesh.util.wrap_as_stream(model_bytes), file_type=suffix, force="mesh"
            )
        except Exception as exc:
            raise SlicerError(f"見積り用にメッシュを読めませんでした: {exc}") from exc

        if not mesh.is_watertight:
            raise SlicerError("閉じていないメッシュは体積が求まらないため見積れません")

        volume_mm3 = float(mesh.volume)
        material_mm3 = volume_mm3 * (_SHELL_FRACTION + (1 - _SHELL_FRACTION) * self._infill)

        grams = material_mm3 / 1000.0 * _density_for(material)
        minutes = max(1, round(material_mm3 / _FLOW_RATE_MM3_PER_SEC / 60))

        return PrintEstimate(
            print_time_min=minutes,
            filament_grams=round(grams, 1),
            estimated=True,
            source="体積からの概算",
        )


class BambuStudioCliSlicer:
    """Bambu Studio の CLI で実測する.

    バイナリは GUI ライブラリに依存するため、同梱の Dockerfile
    (docker/bambu-studio.Dockerfile)で動かすことを想定している。
    """

    def __init__(self, binary: str, timeout_seconds: float = 600.0) -> None:
        self._binary = binary
        self._timeout = timeout_seconds

    @property
    def available(self) -> bool:
        return shutil.which(self._binary) is not None or Path(self._binary).exists()

    async def estimate(
        self, *, model_bytes: bytes, material: str, filename: str = "model.3mf"
    ) -> PrintEstimate:
        if not self.available:
            raise SlicerError(f"Bambu Studio が見つかりません: {self._binary}")

        with tempfile.TemporaryDirectory(prefix="slice-") as workdir:
            directory = Path(workdir)
            source = directory / filename
            source.write_bytes(model_bytes)

            process = await asyncio.create_subprocess_exec(
                self._binary,
                "--slice",
                "0",
                "--export-3mf",
                str(directory / "sliced.3mf"),
                str(source),
                cwd=workdir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=self._timeout
                )
            except TimeoutError:
                process.kill()
                await process.wait()
                raise SlicerError("スライスが時間内に終わりませんでした") from None

            if process.returncode != 0:
                raise SlicerError(
                    f"スライスに失敗しました: {stderr.decode('utf-8', 'replace')[:300]}"
                )

            return _parse_cli_output(stdout.decode("utf-8", "replace"))


def _parse_cli_output(stdout: str) -> PrintEstimate:
    """CLI の出力から時間と使用量を拾う.

    出力形式はバージョンで変わりうるので、複数の書式を試して
    どれにも当たらなければ失敗として扱う(黙って0を返さない)。
    """
    minutes: int | None = None
    grams: float | None = None

    if (found := re.search(r'"?estimated_?printing_?time"?\D+(\d+)', stdout, re.I)) is not None:
        minutes = round(int(found.group(1)) / 60)
    elif (found := re.search(r"(\d+)h\s*(\d+)m", stdout)) is not None:
        minutes = int(found.group(1)) * 60 + int(found.group(2))

    if (found := re.search(r'"?filament_?used_?g"?\D+([\d.]+)', stdout, re.I)) is not None:
        grams = float(found.group(1))

    if minutes is None or grams is None:
        raise SlicerError(
            "スライサの出力から印刷時間・使用量を読み取れませんでした。"
            "Bambu Studio のバージョンによる出力形式の違いの可能性があります"
        )

    return PrintEstimate(
        print_time_min=minutes,
        filament_grams=round(grams, 1),
        estimated=False,
        source="Bambu Studio によるスライス実測",
    )


def parse_estimate_json(payload: str) -> PrintEstimate:
    """将来 CLI が JSON を吐く場合の入口。現状は未使用."""
    data = json.loads(payload)
    return PrintEstimate(
        print_time_min=int(data["print_time_min"]),
        filament_grams=float(data["filament_grams"]),
        estimated=False,
        source="Bambu Studio によるスライス実測",
    )
