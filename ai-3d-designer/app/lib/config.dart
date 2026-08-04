/// アプリ設定。値は `--dart-define` でビルド時に渡す。
///
/// 例:
///   flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000 \
///               --dart-define=AUTH_MODE=insecure_dev
library;

/// 認証方式。サーバー側の `APP_AUTH_MODE` と必ず一致させる。
enum AuthMode {
  /// Firebase 匿名認証で ID トークンを取得する(本番)。
  firebase,

  /// 端末ローカルの uid をそのままトークンとして送る。
  /// Firebase プロジェクト未作成でも疎通確認ができるようにするためのローカル専用モード。
  insecureDev;

  static AuthMode parse(String raw) {
    return switch (raw) {
      'firebase' => AuthMode.firebase,
      'insecure_dev' => AuthMode.insecureDev,
      _ => throw ArgumentError(
          'AUTH_MODE は firebase か insecure_dev のいずれかである必要があります (受け取った値: "$raw")',
        ),
    };
  }
}

class AppConfig {
  const AppConfig({required this.apiBaseUrl, required this.authMode});

  final String apiBaseUrl;
  final AuthMode authMode;

  /// Android エミュレータからホストの localhost を指すのは 10.0.2.2。
  /// iOS シミュレータと Web は localhost のままでよい。
  static const _defaultBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  static const _defaultAuthMode = String.fromEnvironment(
    'AUTH_MODE',
    defaultValue: 'insecure_dev',
  );

  factory AppConfig.fromEnvironment() => AppConfig(
        apiBaseUrl: _defaultBaseUrl,
        authMode: AuthMode.parse(_defaultAuthMode),
      );
}
