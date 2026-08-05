# セットアップ手順(Phase 0)

Phase 0 のゴールは **アプリからサーバーへ到達でき、ログインが成立すること** の確認です。

**Firebase プロジェクトがなくても、この手順だけで動きます。** 開発用の認証モードを用意してあるので、
Firebase の作成は後回しにできます(手順は後半の「Firebase を有効化する」に記載)。

---

## 1. バックエンドを起動する

必要なもの: Python 3.11 以上

```bash
cd ai-3d-designer/server

python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt

cp .env.example .env      # 既定で APP_AUTH_MODE=insecure_dev になっている

.venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

別のターミナルで疎通を確認します。

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","version":"0.1.0","environment":"local","auth_mode":"insecure_dev"}

curl -H "Authorization: Bearer dev-user-1" http://127.0.0.1:8000/me
# {"uid":"dev-user-1","email":null,"is_anonymous":true}
```

API ドキュメントは http://127.0.0.1:8000/docs で見られます。

### STEP1〜3 を curl で通す

アプリを起動しなくても、コマンドラインだけで流れを確認できます。

```bash
API=http://127.0.0.1:8000
H="Authorization: Bearer dev-user-1"

# STEP1: アイデア入力
PID=$(curl -s -X POST $API/projects -H "$H" -H "Content-Type: application/json" \
  -d '{"text":"名刺入れをつくって。ボタンで取り出せて、30枚入って、ポケットに入るサイズ"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# STEP2: 企画生成 → 修正
curl -s -X POST $API/projects/$PID/proposal -H "$H" | python3 -m json.tool
curl -s -X POST $API/projects/$PID/proposal/revise -H "$H" \
  -H "Content-Type: application/json" -d '{"request":"もう少し薄くして"}' | python3 -m json.tool

# STEP3: 画像生成
curl -s -X POST $API/projects/$PID/images -H "$H" | python3 -m json.tool
```

> `APP_AI_MODE=stub` のままなら、企画は固定文面・画像は単色 PNG が返ります。
> 実際の生成を試すには次節の OpenAI 設定が必要です。

---

## 1-2. 実際に AI を使う(任意)

OpenAI の API キーを用意して `.env` を書き換えます。

```bash
APP_AI_MODE=openai
APP_OPENAI_API_KEY=sk-...
```

キーが未設定のまま `APP_AI_MODE=openai` にすると、**起動時にその旨のエラーで落ちます**
(実行してから失敗するのではなく、設定の時点で気付けるようにしてあります)。

課金は従量制です。1プロジェクトあたり企画生成1回 + 画像5枚が目安なので、
試行錯誤の回数がそのままコストになります。

テストと lint:

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
```

> `--host 0.0.0.0` にしているのは、実機やエミュレータからホスト PC に届くようにするためです。

---

## 2. アプリを起動する

必要なもの: Flutter SDK 3.27 以上(Dart 3.6 以上)

### 2-1. プラットフォーム定義を生成する

`android/` `ios/` は生成物なのでリポジトリに含めていません。最初に一度だけ生成します。

```bash
cd ai-3d-designer/app
flutter create . --project-name ai_3d_designer --platforms=android,ios
flutter pub get
```

> `--project-name` を指定しているので、既存の `lib/` と `pubspec.yaml` は上書きされません。

### 2-2. 起動する

接続先はビルド時に `--dart-define` で渡します。**実行環境によって指定する URL が違います。**

| 実行環境 | `API_BASE_URL` に指定する値 |
|---|---|
| Android エミュレータ | `http://10.0.2.2:8000` (既定値) |
| iOS シミュレータ | `http://127.0.0.1:8000` |
| 実機 | `http://<開発PCのLAN IP>:8000` |

```bash
# Android エミュレータ(既定値でよいので dart-define 不要)
flutter run

# iOS シミュレータ
flutter run --dart-define=API_BASE_URL=http://127.0.0.1:8000

# 実機(IP は各自の環境に読み替える)
flutter run --dart-define=API_BASE_URL=http://192.168.1.23:8000
```

### 2-3. 動作確認

アプリを起動すると自動で確認が走り、以下の2つに緑のチェックが付けば Phase 0 は完了です。

- **サーバー疎通** — version / environment / auth_mode が表示される
- **ログイン** — uid が表示される

アプリとサーバーの `AUTH_MODE` が食い違っている場合は、画面に警告が出ます。

テスト:

```bash
flutter analyze
flutter test
```

---

## 3. Firebase を有効化する(Phase 1 以降・任意)

Phase 0 の疎通確認だけなら不要です。実データを扱い始める前に実施してください。

### 3-1. Firebase プロジェクトを作る(ユーザー側の作業)

1. [Firebase コンソール](https://console.firebase.google.com/) でプロジェクトを作成
2. **Authentication** を有効化し、**匿名認証** をオンにする
3. **Firestore** と **Storage** を有効化する
4. サービスアカウントの秘密鍵 JSON をダウンロードする
   (プロジェクトの設定 → サービスアカウント → 新しい秘密鍵の生成)

### 3-2. サーバー側の設定

ダウンロードした JSON を `ai-3d-designer/server/serviceAccount.json` に置き、`.env` を書き換えます。

```bash
APP_AUTH_MODE=firebase
APP_FIREBASE_PROJECT_ID=your-project-id
APP_FIREBASE_CREDENTIALS_PATH=./serviceAccount.json
```

> `serviceAccount.json` と `.env` は `.gitignore` 済みです。**絶対にコミットしないでください。**
> Cloud Run にデプロイする際は `APP_FIREBASE_CREDENTIALS_PATH` を空にします
> (Application Default Credentials が使われます)。

### 3-3. アプリ側の設定

```bash
cd ai-3d-designer/app

# FlutterFire CLI で lib/firebase_options.dart を生成する
dart pub global activate flutterfire_cli
flutterfire configure
```

続いて 3 箇所を変更します。

1. `lib/services/firebase_auth_service.dart.template` を
   `lib/services/firebase_auth_service.dart` にリネーム
2. `pubspec.yaml` の `firebase_core` / `firebase_auth` のコメントを外して `flutter pub get`
3. `lib/main.dart` の `_buildAuthService` にある `AuthMode.firebase` の分岐を、
   `throw UnimplementedError(...)` から `FirebaseAuthService()` を返すよう差し替え

起動時に `--dart-define=AUTH_MODE=firebase` を指定すれば Firebase 認証で動きます。

---

## 補足: 開発用認証モードについて

`insecure_dev` は **トークンを検証せず、送られてきた文字列をそのまま uid として扱います。**
Firebase なしで開発を始められるようにするためのものです。

安全装置として、`APP_ENVIRONMENT` が `local` 以外のときにこのモードを指定すると
**サーバーが起動を拒否します**(実行時ではなく設定読み込みの時点で失敗します)。
本番環境に紛れ込むことはありません。
