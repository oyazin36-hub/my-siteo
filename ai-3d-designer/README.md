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
| 2 | STEP4(3Dモデル生成・3Dビューア) | 未着手 |
| 3 | 3MF 出力・機構ルート(パラメトリック CAD) | 未着手 |
| 4 | STEP5〜6(フィラメント選定・AMS 配置) | 未着手 |

### 開発モード — 外部サービス無しで動く

Firebase も OpenAI キーも無い状態で、STEP1〜3 の流れを最後まで通せます。
各外部依存に開発用の実装を用意してあるためです。

| 依存 | 本番 | 開発 |
|---|---|---|
| 認証 | Firebase ID トークン | `insecure_dev` — トークンを uid として扱う |
| LLM / 画像生成 | OpenAI | `stub` — 固定の企画と単色画像を返す |
| 永続化 | Firestore | `memory` — プロセス内 |
| 画像保存 | Cloud Storage | `local` — ファイルに保存し `/media` で配信 |

**`insecure_dev` と `stub` は `APP_ENVIRONMENT=local` 以外では起動時にエラーになります。**
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

### Phase 1 に含まれないもの

- Firebase プロジェクトの作成(ユーザー側の作業。手順は `SETUP.md`)
- 3Dモデルの生成(Phase 2)
- 画像の添付アップロード — 現状は URL 指定のみ受け付ける
