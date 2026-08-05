# AI 3D Product Designer

作りたい物を日本語で説明すると、**Bambu Lab P2S で印刷できる 3MF ファイル**になるアプリ。
CAD の知識は不要。

設計の全体像(アーキテクチャ・API 一覧・ロードマップ・データ構造)は
[`docs/ai-3d-product-designer/DESIGN.md`](../docs/ai-3d-product-designer/DESIGN.md) を参照。

セットアップと起動手順は [`SETUP.md`](./SETUP.md)。

## 構成

```
ai-3d-designer/
├── app/       Flutter アプリ (iOS / Android)
│   ├── lib/
│   │   ├── config.dart          設定 (--dart-define で注入)
│   │   ├── main.dart
│   │   ├── screens/             画面
│   │   └── services/            認証・API クライアント
│   └── test/
└── server/    FastAPI バックエンド
    ├── app/
    │   ├── api/routes.py        エンドポイント
    │   ├── core/auth.py         Firebase ID トークン検証
    │   ├── core/config.py       設定
    │   └── models/schemas.py    リクエスト/レスポンス
    └── tests/
```

## 進捗

| Phase | 内容 | 状態 |
|---|---|---|
| 0 | 基盤構築(疎通・認証・CI) | **完了** |
| 1 | STEP1〜3(アイデア入力・AI企画提案・画像生成) | **完了** |
| 2 | STEP4(3Dモデル生成・3Dビューア) | **完了** |
| 3 | 3MF 出力・機構ルート(パラメトリック CAD) | **完了** |
| 4 | STEP5〜6(フィラメント選定・AMS 配置) | 未着手 |

### 開発モード — 外部サービス無しで動く

Firebase も OpenAI キーも無い状態で、STEP1〜3 の流れを最後まで通せます。
各外部依存に開発用の実装を用意してあるためです。

| 依存 | 本番 | 開発 |
|---|---|---|
| 認証 | Firebase ID トークン | `insecure_dev` — トークンを uid として扱う |
| LLM / 画像生成 | OpenAI | `stub` — 固定の企画と単色画像を返す |
| 3Dモデル生成(装飾) | Tripo3D | `stub` — 単純な箱を返す |
| CADコード生成(機構) | Claude | `stub` — 企画寸法どおりのケース形状 |
| 印刷時間の見積り | Bambu Studio CLI | `heuristic` — 体積からの概算 |
| 永続化 | Firestore | `memory` — プロセス内 |
| ファイル保存 | Cloud Storage | `local` — ファイルに保存し `/media` で配信 |

**`insecure_dev` と各 `stub` は `APP_ENVIRONMENT=local` 以外では起動時にエラーになります。**
実行時ではなく設定読み込みの時点で落ちるので、本番に紛れ込むことはありません。

### Phase 1 で実装した範囲

- **STEP1** `POST /projects` — アイデア(文章 + 画像 URL)を登録
- **STEP2** `POST /projects/{id}/proposal` — 企画を生成
  - 装飾ルート / 機構ルートの自動判定(DESIGN.md §0 の 2 ルート方式)
  - `POST /projects/{id}/proposal/revise` — 修正指示を反映。履歴は企画が差し替わっても残る
- **STEP3** `POST /projects/{id}/images` — 外観・使用シーン・分解図・内部構造・寸法の5枚を生成
  - `POST /projects/{id}/images/revise` — 修正指示を反映して作り直す
  - 3D化を見据え「単一オブジェクト・背景なし」をプロンプトで固定
  - 生成 API が返す期限付き URL は使わず、必ず自前で保存してから配信する
- 所有者以外には **404 を返す**(403 だと存在が漏れるため)
- Flutter 画面1〜4(ホーム / アイデア入力 / 企画確認 / 画像確認)

### Phase 2 で実装した範囲

- **STEP4** `POST /projects/{id}/model` — 画像から3Dモデルを生成(非同期・202)
  - 生成は数分かかるため受け付けだけ行い、進行状況は `model.job_status` で追う
  - `POST /projects/{id}/model/revise` — 作り直し
- **メッシュ処理** — 生成物を印刷可能な状態に整える
  - GLB/OBJ → STL の正規化(Tripo3D は glTF を返すため必須の経路)
  - 穴埋め・面の向き揃え・法線反転の修復
  - 造形範囲(256mm)超過と防水性の検証。**修復しても穴が残る場合は
    `printable=false` にして先へ進ませない**
  - 底面を Z=0 に載せる
- **印刷用と表示用を分けて保存** — スライサは STL、3Dビューアは GLB を要求するため
- **画像アップロード** `POST /projects/uploads` — Phase 1 の積み残しを解消
- Flutter 画面5(3Dビューア。回転・拡大・寸法表示、生成中のポーリング)

### 寸法の扱いについて(重要)

**ルートによって寸法の保証が違います。**

| ルート | 経路 | 寸法 |
|---|---|---|
| 装飾(置物・フィギュア) | 画像 → 3D生成API | **保証しない** (`approximate`) |
| 機構(ケース・スタンド) | 企画 → CADコード → 検証 | **保証する** (`guaranteed`) |

装飾ルートは画像から起こすため、等比拡縮で企画の寸法に寄せても各辺は一致しません
(縦横比が元画像由来のため)。ズレた場合は必ず警告を出します。
黙って別寸法の物を渡さないためです。

機構ルートは実寸を計測して企画値と照合し、**一致したものだけを合格**にします。

### Phase 3 で実装した範囲

**機構ルート(寸法保証)** — ここが Phase 3 の本丸。

```
企画 → Claude が OpenSCAD コードを生成 → レンダリング → 実寸を計測
     → 企画値と ±0.1mm 以内で一致するか検証
        一致 → 合格 (dimensional_accuracy = guaranteed)
        不一致 → ずれの実測値を添えて作り直し(最大3回)
        3回で合わなければ **失敗として返す**(合わないまま合格にしない)
```

- 装飾ルートは従来どおり画像経路。寸法は `approximate` のまま
- 生成された OpenSCAD コードはプロジェクトに保存し、アプリから確認できる

**OpenSCAD 実行のサンドボックス** — LLM が書いたコードをサーバーで実行するため、
`include` / `use` / `import` / `surface` を含むコードは実行前に拒否する。
実行は一時ディレクトリ内に閉じ、タイムアウトを設ける。

**3MF 出力** `POST /projects/{id}/print`
- `unit="millimeter"` と実寸座標を持つ、仕様に沿った 3MF
- 商品名・概要をメタデータに埋める
- **プリンタ/フィラメントのプリセットは埋め込まない** — Bambu 独自の
  `project_settings.config` は仕様が非公開で、推測で書くとファイルごと弾かれうる。
  開いた側で選ぶ運用にして、推奨値はアプリに表示する

**印刷時間・使用量の見積り** — 体積からの概算(既定)と Bambu Studio CLI 実測の 2 実装。
概算のときは必ずその旨を伝える。

### Phase 3 に含まれないもの

- Firebase プロジェクトの作成(ユーザー側の作業。手順は `SETUP.md`)
- フィラメントの自動選定と AMS スロット配置(Phase 4)
- ジョブの永続化 — 現状はプロセス内のバックグラウンドタスクなので、
  サーバー再起動中の生成は失われる(設計書どおり Cloud Tasks 化は後続)

### 未検証の箇所

- **Bambu Studio CLI**: この環境では Docker デーモンが使えず未検証。
  `docker/bambu-studio.Dockerfile` は用意してあるが、初回は手元でビルドして
  動作確認してから使うこと。既定は概算モードなので、無くてもアプリは動く
- **Tripo3D / OpenAI / Claude の実接続**: API キーが無いため未検証
