"""Tripo3D の実接続を確認する.

アプリのプロバイダ(app/providers/mesh3d.py)をそのまま使うので、
SDK ではなく **自前のバインディング** を検証できる。

    export APP_TRIPO_API_KEY=tsk_...
    .venv/bin/python scripts/check_tripo.py            # 残高だけ見る(無料)
    .venv/bin/python scripts/check_tripo.py --generate 画像.png   # 実際に生成する(有料)

キーは環境変数からしか読まない。引数にも出力にも出さない。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.providers.mesh3d import (  # noqa: E402
    GenerationRequest,
    Mesh3DError,
    TripoMeshProvider,
)
from app.services import meshproc  # noqa: E402

_MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


async def check_balance(provider: TripoMeshProvider) -> bool:
    """認証だけ確かめる。クレジットは減らない."""
    try:
        balance = await provider._client.get_balance()  # type: ignore[attr-defined]
    except Exception as exc:
        print(f"認証   NG  {type(exc).__name__}: {exc}")
        return False

    print(f"認証   OK  残高 {balance.balance}  (凍結中 {balance.frozen})")
    return True


async def generate(provider: TripoMeshProvider, image_path: Path, out_dir: Path) -> None:
    """画像から 3D モデルを作り、アプリのメッシュ処理まで通す."""
    media_type = _MEDIA_TYPES.get(image_path.suffix.lower(), "image/png")
    request = GenerationRequest(
        image=image_path.read_bytes(), image_media_type=media_type, with_texture=False
    )

    print(f"\n投入   {image_path.name} ({len(request.image):,} バイト, {media_type})")
    started = time.time()
    job_id = await provider.submit(request)
    print(f"       job_id = {job_id}")

    last = ""
    while True:
        state = await provider.poll(job_id)
        if state != last:
            print(f"       {int(time.time() - started):4d}秒  {state}")
            last = state
        if state == "done":
            break
        if time.time() - started > 900:
            raise Mesh3DError("15分以内に完了しませんでした")
        await asyncio.sleep(5)

    artifact = await provider.fetch(job_id)
    print(f"取得   {len(artifact.data):,} バイト  形式={artifact.format}")

    processed = meshproc.process(artifact)
    report = processed.report
    size = report.size_mm
    print(
        f"処理   面数={report.face_count}  防水={report.watertight}  "
        f"印刷可={report.printable}\n"
        f"       素の寸法 {size[0]:.1f} x {size[1]:.1f} x {size[2]:.1f} mm"
    )
    for action in report.repair_actions:
        print(f"       修復  {action}")
    for warning in report.warnings:
        print(f"       ! {warning}")

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "tripo.stl").write_bytes(processed.stl)
    (out_dir / "tripo.glb").write_bytes(processed.glb)
    (out_dir / "tripo_raw").with_suffix(f".{artifact.format}").write_bytes(artifact.data)
    print(f"保存   {out_dir}/tripo.stl / tripo.glb / tripo_raw.{artifact.format}")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Tripo3D の実接続確認")
    parser.add_argument(
        "--generate",
        metavar="画像",
        type=Path,
        help="この画像から実際に3Dモデルを作る(クレジットを消費します)",
    )
    parser.add_argument("--out", type=Path, default=Path("var/tripo"), help="出力先")
    parser.add_argument("--model-version", default=None, help="例 v3.1-20260211")
    args = parser.parse_args()

    api_key = os.environ.get("APP_TRIPO_API_KEY")
    if not api_key:
        print("APP_TRIPO_API_KEY が設定されていません。", file=sys.stderr)
        print("  export APP_TRIPO_API_KEY=tsk_...", file=sys.stderr)
        return 2

    provider = TripoMeshProvider(api_key=api_key, model_version=args.model_version)
    try:
        if not await check_balance(provider):
            return 1
        if args.generate:
            if not args.generate.exists():
                print(f"画像が見つかりません: {args.generate}", file=sys.stderr)
                return 2
            await generate(provider, args.generate, args.out)
        else:
            print("\n(生成はしていません。--generate 画像.png で実際に作れます)")
    except Mesh3DError as exc:
        print(f"\n失敗   {exc}", file=sys.stderr)
        return 1
    finally:
        await provider.aclose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
