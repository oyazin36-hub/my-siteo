import 'package:flutter/material.dart';

import 'app_scope.dart';
import 'config.dart';
import 'screens/home_screen.dart';
import 'services/api_client.dart';
import 'services/auth_service.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();

  final config = AppConfig.fromEnvironment();
  final authService = _buildAuthService(config);
  final apiClient = ApiClient(baseUrl: config.apiBaseUrl, authService: authService);

  runApp(
    App(config: config, authService: authService, apiClient: apiClient),
  );
}

AuthService _buildAuthService(AppConfig config) {
  return switch (config.authMode) {
    AuthMode.insecureDev => DevAuthService(),
    // Firebase プロジェクト作成後、SETUP.md の手順で
    // FirebaseAuthService を有効化してここを差し替える。
    AuthMode.firebase => throw UnimplementedError(
        'AUTH_MODE=firebase はまだ有効化されていません。\n'
        'SETUP.md の「Firebase を有効化する」の手順を実施してください。\n'
        '今すぐ動かすには --dart-define=AUTH_MODE=insecure_dev を指定してください。',
      ),
  };
}

class App extends StatelessWidget {
  const App({
    super.key,
    required this.config,
    required this.authService,
    required this.apiClient,
  });

  final AppConfig config;
  final AuthService authService;
  final ApiClient apiClient;

  @override
  Widget build(BuildContext context) {
    return AppScope(
      config: config,
      authService: authService,
      apiClient: apiClient,
      child: MaterialApp(
        title: 'AI 3D Product Designer',
        theme: ThemeData(
          colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF0C9D58)),
          useMaterial3: true,
        ),
        home: const HomeScreen(),
      ),
    );
  }
}
