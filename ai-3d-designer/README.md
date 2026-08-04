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
| 1 | STEP1〜3(アイデア入力・AI企画提案・画像生成) | 未着手 |
| 2 | STEP4(3Dモデル生成・3Dビューア) | 未着手 |
| 3 | 3MF 出力・機構ルート(パラメトリック CAD) | 未着手 |
| 4 | STEP5〜6(フィラメント選定・AMS 配置) | 未着手 |

### Phase 0 で実装した範囲

- モノレポ構成(`app/` + `server/`)
- FastAPI バックエンド
  - `GET /health` — 認証不要の疎通確認
  - `GET /me` — 要認証。ログイン確認
  - Firebase ID トークン検証(差し替え可能な `TokenVerifier` として実装)
  - 開発用の `insecure_dev` 認証モード。**local 以外では起動を拒否する安全装置つき**
- Flutter アプリ骨格 — 起動時に疎通とログインを自動確認して結果を表示
- GitHub Actions CI — サーバーの lint / test、アプリの analyze / test

### Phase 0 に含まれないもの

- Firebase プロジェクトの作成(ユーザー側の作業。手順は `SETUP.md`)
- Firestore / Storage への読み書き(Phase 1)
- 外部 AI API の呼び出し(Phase 1 以降)
