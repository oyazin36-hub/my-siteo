import 'package:flutter/material.dart';

import '../app_scope.dart';
import '../models/project.dart';
import '../services/api_client.dart';
import 'proposal_screen.dart';

/// 画面2: アイデア入力 (STEP1)。
class IdeaInputScreen extends StatefulWidget {
  const IdeaInputScreen({super.key});

  @override
  State<IdeaInputScreen> createState() => _IdeaInputScreenState();
}

class _IdeaInputScreenState extends State<IdeaInputScreen> {
  final _controller = TextEditingController();
  bool _submitting = false;
  String? _error;

  static const _example = '名刺入れをつくって。\n'
      '普段見えてるのは名刺の面。\n'
      'ボタンを押したら名刺が取り出しやすいように取り出せる。\n'
      '名刺は30枚くらい入ればいい。\n'
      'ポケットに収納しやすい大きさで作ってね';

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final text = _controller.text.trim();
    if (text.isEmpty) return;

    final scope = AppScope.of(context);
    final navigator = Navigator.of(context);
    setState(() {
      _submitting = true;
      _error = null;
    });

    try {
      final project = await scope.apiClient.createProject(text);
      if (!mounted) return;
      // 作成した直後に企画確認へ進む。ホームには結果を返す。
      await navigator.pushReplacement<void, Project>(
        MaterialPageRoute(
          builder: (_) => ProposalScreen(projectId: project.id, autoGenerate: true),
        ),
        result: project,
      );
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.message;
        _submitting = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('作りたい物を説明する')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(
            'どんな物を作りたいか、普段の言葉で書いてください。',
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          const SizedBox(height: 4),
          Text(
            'サイズ・収納数・使い方など、条件があれば一緒に書くほど精度が上がります。',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _controller,
            maxLines: 10,
            minLines: 6,
            maxLength: 4000,
            enabled: !_submitting,
            decoration: const InputDecoration(
              border: OutlineInputBorder(),
              hintText: '例: スマホスタンドをつくって。角度が変えられて、充電しながら使えるように',
            ),
          ),
          TextButton.icon(
            onPressed: _submitting
                ? null
                : () => setState(() => _controller.text = _example),
            icon: const Icon(Icons.lightbulb_outline, size: 18),
            label: const Text('書き方の例を入れる'),
          ),
          if (_error != null) ...[
            const SizedBox(height: 12),
            Card(
              color: Theme.of(context).colorScheme.errorContainer,
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: SelectableText(_error!),
              ),
            ),
          ],
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: _submitting ? null : _submit,
            icon: _submitting
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.auto_awesome),
            label: Text(_submitting ? '送信中…' : 'AIに企画してもらう'),
          ),
        ],
      ),
    );
  }
}
