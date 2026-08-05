import 'package:flutter/material.dart';

import '../config.dart';
import '../services/api_client.dart';
import '../services/auth_service.dart';

/// 接続診断画面。サーバー疎通とログインが成立しているかを確認する。
/// ホームの設定から開く。
class ConnectionScreen extends StatefulWidget {
  const ConnectionScreen({
    super.key,
    required this.config,
    required this.authService,
    required this.apiClient,
  });

  final AppConfig config;
  final AuthService authService;
  final ApiClient apiClient;

  @override
  State<ConnectionScreen> createState() => _ConnectionScreenState();
}

class _ConnectionScreenState extends State<ConnectionScreen> {
  bool _running = false;
  HealthInfo? _health;
  UserInfo? _user;
  String? _error;

  @override
  void initState() {
    super.initState();
    _runConnectionCheck();
  }

  Future<void> _runConnectionCheck() async {
    setState(() {
      _running = true;
      _error = null;
      _health = null;
      _user = null;
    });

    try {
      final health = await widget.apiClient.health();
      if (!mounted) return;
      setState(() => _health = health);

      await widget.authService.signIn();
      final user = await widget.apiClient.me();
      if (!mounted) return;
      setState(() => _user = user);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _running = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('接続診断')),
      body: RefreshIndicator(
        onRefresh: _runConnectionCheck,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text('接続診断', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 4),
            Text(
              'アプリからサーバーへ到達でき、ログインが成立していることを確認します。',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 20),
            _StatusCard(
              title: 'サーバー疎通',
              subtitle: widget.config.apiBaseUrl,
              done: _health != null,
              running: _running && _health == null,
              details: _health == null
                  ? null
                  : {
                      'status': _health!.status,
                      'version': _health!.version,
                      'environment': _health!.environment,
                      'auth_mode': _health!.authMode,
                    },
            ),
            const SizedBox(height: 12),
            _StatusCard(
              title: 'ログイン',
              subtitle: switch (widget.config.authMode) {
                AuthMode.firebase => 'Firebase 匿名認証',
                AuthMode.insecureDev => 'ローカル開発モード(Firebase 不要)',
              },
              done: _user != null,
              running: _running && _health != null && _user == null,
              details: _user == null
                  ? null
                  : {
                      'uid': _user!.uid,
                      'is_anonymous': '${_user!.isAnonymous}',
                    },
            ),
            if (_health != null &&
                _health!.authMode != _serverAuthModeName(widget.config.authMode)) ...[
              const SizedBox(height: 12),
              _WarningBanner(
                message: 'アプリは "${_serverAuthModeName(widget.config.authMode)}"、'
                    'サーバーは "${_health!.authMode}" で動いています。'
                    '両者の AUTH_MODE を一致させてください。',
              ),
            ],
            if (_error != null) ...[
              const SizedBox(height: 12),
              _ErrorCard(message: _error!),
            ],
            const SizedBox(height: 20),
            FilledButton.icon(
              onPressed: _running ? null : _runConnectionCheck,
              icon: const Icon(Icons.refresh),
              label: const Text('もう一度確認する'),
            ),
          ],
        ),
      ),
    );
  }

  static String _serverAuthModeName(AuthMode mode) => switch (mode) {
        AuthMode.firebase => 'firebase',
        AuthMode.insecureDev => 'insecure_dev',
      };
}

class _StatusCard extends StatelessWidget {
  const _StatusCard({
    required this.title,
    required this.subtitle,
    required this.done,
    required this.running,
    this.details,
  });

  final String title;
  final String subtitle;
  final bool done;
  final bool running;
  final Map<String, String>? details;

  @override
  Widget build(BuildContext context) {
    final Widget leading;
    if (running) {
      leading = const SizedBox(
        width: 24,
        height: 24,
        child: CircularProgressIndicator(strokeWidth: 2),
      );
    } else if (done) {
      leading = const Icon(Icons.check_circle, color: Colors.green);
    } else {
      leading = const Icon(Icons.radio_button_unchecked, color: Colors.grey);
    }

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                leading,
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(title, style: Theme.of(context).textTheme.titleMedium),
                      Text(subtitle, style: Theme.of(context).textTheme.bodySmall),
                    ],
                  ),
                ),
              ],
            ),
            if (details != null) ...[
              const Divider(height: 24),
              for (final entry in details!.entries)
                Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      SizedBox(
                        width: 110,
                        child: Text(
                          entry.key,
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ),
                      Expanded(
                        child: Text(
                          entry.value,
                          style: const TextStyle(fontFamily: 'monospace'),
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }
}

class _WarningBanner extends StatelessWidget {
  const _WarningBanner({required this.message});
  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.amber.withValues(alpha: 0.15),
        border: Border.all(color: Colors.amber),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.warning_amber, color: Colors.amber),
          const SizedBox(width: 12),
          Expanded(child: Text(message)),
        ],
      ),
    );
  }
}

class _ErrorCard extends StatelessWidget {
  const _ErrorCard({required this.message});
  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.errorContainer,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.error_outline, color: Theme.of(context).colorScheme.onErrorContainer),
          const SizedBox(width: 12),
          Expanded(
            child: SelectableText(
              message,
              style: TextStyle(color: Theme.of(context).colorScheme.onErrorContainer),
            ),
          ),
        ],
      ),
    );
  }
}
