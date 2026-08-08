"""出来上がったモデルの中に、収納物が実際に入る空間があるかを調べる.

寸法検証(services/cad.py)は外形の箱しか見ていない。企画の検算
(domain/feasibility.py)は数字しか見ていない。どちらも
「外形は正しいが中が詰まっている」モデルを通してしまう。ここは実際の
形状を見る最後の関門。

やり方は、Z 方向のレイ刺しによるソリッドのボクセル化。各 (x, y) の柱で
上向きの直線と三角形の交点 z を集め、昇順に並べて偶数〜奇数番の区間を
材料とみなす(even-odd 則)。閉じたメッシュなら交点は必ず偶数個になる。

scipy も rtree も使わない。この判定ひとつのために依存を増やしたくないため
(trimesh.contains は rtree を要求する)。

**この判定は必要条件でしかない。** 空間があることは分かるが、そこに約束した
機構が入っているかまでは分からない。通ったからといって設計が正しいとは
言えない。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: ボクセルの一辺 (mm)。0.4mm ノズルで印刷する物に対して 1mm あれば十分細かい。
DEFAULT_PITCH_MM = 1.0

#: 格子の上限。これを超えるならピッチを粗くする。判定に何秒もかけない。
MAX_VOXELS = 4_000_000

#: 交点が奇数個になった柱の割合がこれを超えたら、判定そのものを諦める。
#: メッシュが荒れていて even-odd 則が信用できない状態。
_MAX_ODD_COLUMN_RATIO = 0.02

#: 標本点をボクセルのどこに置くか(ピッチに対する比)。
#: 中央(0.5)だと設計寸法の面にちょうど乗るので、無理数を使ってずらす。
_SAMPLE_OFFSET = 1.0 / 3.0**0.5  # ≒ 0.5774


@dataclass(frozen=True)
class FitResult:
    """収納物が入るかの判定."""

    fits: bool | None
    """True=入る / False=入らない / None=判定できなかった."""

    reason: str
    pitch_mm: float

    @property
    def undetermined(self) -> bool:
        return self.fits is None


def _choose_pitch(extents: tuple[float, float, float], pitch: float) -> float:
    """格子が大きくなりすぎないようピッチを粗くする."""
    while True:
        cells = 1.0
        for length in extents:
            cells *= max(1.0, length / pitch)
        if cells <= MAX_VOXELS:
            return pitch
        pitch *= 2


def voxelize(mesh: object, pitch: float) -> tuple[np.ndarray, float]:
    """材料が詰まっているボクセルを True にした配列と、奇数柱の割合を返す."""
    import trimesh

    assert isinstance(mesh, trimesh.Trimesh)

    lo, hi = mesh.bounds
    # 標本点をピッチのちょうど半分に置くと、0.1mm 刻みで設計された面
    # (壁が 1.5mm、段が 0.5mm など)にそのまま乗ってしまう。
    # 面の上を走る直線は交点の数が不定になり、even-odd 則が崩れる。
    # 1/sqrt(3) は 10 進で有限桁にならないので、設計寸法とは決して一致しない。
    offset = pitch * _SAMPLE_OFFSET
    xs = np.arange(lo[0] + offset, hi[0], pitch)
    ys = np.arange(lo[1] + offset, hi[1], pitch)
    zs = np.arange(lo[2] + offset, hi[2], pitch)
    if xs.size == 0 or ys.size == 0 or zs.size == 0:
        return np.zeros((max(xs.size, 1), max(ys.size, 1), max(zs.size, 1)), bool), 0.0

    columns: list[np.ndarray] = []
    heights: list[np.ndarray] = []

    for tri in mesh.triangles:
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = tri
        area = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)
        if area == 0:
            continue  # Z に平行な面。上向きの直線とは交わらない。

        i0 = int(np.searchsorted(xs, min(ax, bx, cx)))
        i1 = int(np.searchsorted(xs, max(ax, bx, cx)))
        j0 = int(np.searchsorted(ys, min(ay, by, cy)))
        j1 = int(np.searchsorted(ys, max(ay, by, cy)))
        if i0 >= i1 or j0 >= j1:
            continue

        px = xs[i0:i1][:, None]
        py = ys[j0:j1][None, :]
        u = ((px - ax) * (cy - ay) - (cx - ax) * (py - ay)) / area
        v = ((bx - ax) * (py - ay) - (px - ax) * (by - ay)) / area
        # 辺ちょうどを踏んだ柱は数えない。両側の三角形で二重に数えてしまうため。
        hit = (u > 0) & (v > 0) & (u + v < 1)
        if not hit.any():
            continue

        z = az + u * (bz - az) + v * (cz - az)
        ii, jj = np.nonzero(hit)
        columns.append((i0 + ii) * ys.size + (j0 + jj))
        heights.append(z[ii, jj])

    solid = np.zeros((xs.size, ys.size, zs.size), dtype=bool)
    if not columns:
        return solid, 0.0

    column_index = np.concatenate(columns)
    hit_z = np.concatenate(heights)

    # 柱ごとにまとめ、その中で z の昇順に並べる。
    order = np.lexsort((hit_z, column_index))
    column_index = column_index[order]
    hit_z = hit_z[order]

    starts = np.flatnonzero(np.r_[True, column_index[1:] != column_index[:-1]])
    counts = np.diff(np.r_[starts, column_index.size])

    odd = 0
    flat = solid.reshape(-1, zs.size)
    for start, count, column in zip(starts, counts, column_index[starts], strict=True):
        if count % 2:
            # 閉じたメッシュでは起きない。起きた柱は信用せず飛ばす。
            odd += 1
            continue
        span = hit_z[start : start + count]
        for lo_z, hi_z in zip(span[0::2], span[1::2], strict=True):
            flat[column] |= (zs > lo_z) & (zs < hi_z)

    return solid, odd / max(1, starts.size)


def reachable_free(solid: np.ndarray) -> np.ndarray:
    """材料でなく、かつ外から届く空間を True にする.

    届かない空洞は数えない。中に入れられない空間は収納には使えないため。
    """
    # 外側を 1 層ぶん足して、そこを起点に広げる。
    # 端で np.roll が反対側に回り込むのを防ぐ意味もある。
    free = np.pad(~solid, 1, constant_values=True)
    reach = np.zeros_like(free)
    reach[0, :, :] = reach[-1, :, :] = True
    reach[:, 0, :] = reach[:, -1, :] = True
    reach[:, :, 0] = reach[:, :, -1] = True

    while True:
        grown = reach.copy()
        for axis in (0, 1, 2):
            grown |= np.roll(reach, 1, axis=axis)
            grown |= np.roll(reach, -1, axis=axis)
        grown &= free
        grown[0, :, :] = grown[-1, :, :] = True
        grown[:, 0, :] = grown[:, -1, :] = True
        grown[:, :, 0] = grown[:, :, -1] = True
        if np.array_equal(grown, reach):
            return reach[1:-1, 1:-1, 1:-1]
        reach = grown


def _has_empty_box(free: np.ndarray, counts: tuple[int, int, int]) -> bool:
    """指定した大きさの直方体が、まるごと空いている場所があるか."""
    occupied = (~free).astype(np.int32)
    if any(counts[k] > occupied.shape[k] for k in range(3)):
        return False

    # 3 次元の累積和。どの直方体についても O(1) で「材料が 0 個か」を見る。
    cumulative = occupied.cumsum(0).cumsum(1).cumsum(2)
    cumulative = np.pad(cumulative, ((1, 0), (1, 0), (1, 0)))

    nx, ny, nz = counts
    total = (
        cumulative[nx:, ny:, nz:]
        - cumulative[:-nx, ny:, nz:]
        - cumulative[nx:, :-ny, nz:]
        - cumulative[nx:, ny:, :-nz]
        + cumulative[:-nx, :-ny, nz:]
        + cumulative[:-nx, ny:, :-nz]
        + cumulative[nx:, :-ny, :-nz]
        - cumulative[:-nx, :-ny, :-nz]
    )
    return bool((total == 0).any())


def content_fits(
    mesh: object,
    box_mm: tuple[float, float, float],
    *,
    pitch_mm: float = DEFAULT_PITCH_MM,
) -> FitResult:
    """box_mm の収納物が入る空間がモデルの中にあるかを調べる.

    Z 軸まわりに 90 度回した向きも試す。ケースの縦横は設計次第のため。
    """
    import trimesh

    assert isinstance(mesh, trimesh.Trimesh)

    if not mesh.is_watertight:
        # 閉じていないと内外を決められない。even-odd 則が成り立たない。
        return FitResult(None, "メッシュが閉じていないため判定できません", pitch_mm)

    extents = tuple(float(v) for v in mesh.extents)
    pitch = _choose_pitch(extents, pitch_mm)  # type: ignore[arg-type]

    solid, odd_ratio = voxelize(mesh, pitch)
    if odd_ratio > _MAX_ODD_COLUMN_RATIO:
        return FitResult(
            None,
            f"メッシュが荒れているため判定できません(交点が奇数の柱 {odd_ratio:.1%})",
            pitch,
        )

    free = reachable_free(solid)

    for width, depth in ((box_mm[0], box_mm[1]), (box_mm[1], box_mm[0])):
        counts = (
            int(np.ceil(width / pitch)),
            int(np.ceil(depth / pitch)),
            int(np.ceil(box_mm[2] / pitch)),
        )
        if _has_empty_box(free, counts):
            return FitResult(
                True,
                f"{box_mm[0]:.0f} x {box_mm[1]:.0f} x {box_mm[2]:.1f}mm の空間があります",
                pitch,
            )

    return FitResult(
        False,
        f"{box_mm[0]:.0f} x {box_mm[1]:.0f} x {box_mm[2]:.1f}mm の"
        f"収納物が入る空間が内部にありません",
        pitch,
    )


__all__ = ["DEFAULT_PITCH_MM", "FitResult", "content_fits", "reachable_free", "voxelize"]
