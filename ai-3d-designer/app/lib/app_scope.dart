import 'package:flutter/widgets.dart';

import 'config.dart';
import 'services/api_client.dart';
import 'services/auth_service.dart';

/// アプリ全体で共有する依存。画面ツリーを跨いで受け渡す。
class AppScope extends InheritedWidget {
  const AppScope({
    super.key,
    required this.config,
    required this.authService,
    required this.apiClient,
    required super.child,
  });

  final AppConfig config;
  final AuthService authService;
  final ApiClient apiClient;

  static AppScope of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<AppScope>();
    assert(scope != null, 'AppScope が見つかりません');
    return scope!;
  }

  @override
  bool updateShouldNotify(AppScope oldWidget) =>
      apiClient != oldWidget.apiClient || config != oldWidget.config;
}
