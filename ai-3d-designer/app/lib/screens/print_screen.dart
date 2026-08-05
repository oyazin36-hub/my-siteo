import 'package:flutter/material.dart';

import '../app_scope.dart';
import '../models/project.dart';
import '../services/api_client.dart';

/// 画面6: 印刷設定 (STEP5-6)。
///
/// ここがゴール。3MF をダウンロードして Bambu Studio で開く。
class PrintScreen extends StatefulWidget {
  const PrintScreen({super.key, required this.projectId, this.autoBuild = false});

  final String projectId;
  final bool autoBuild;

  @override
  State<PrintScreen> createState() => _PrintScreenState();
}

class _PrintScreenState extends State<PrintScreen> {
  Project? _project;
  bool _busy = false;
  String? _error;

  PrintData? get _printData => _project?.printData;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  Future<void> _load() async {
    final api = AppScope.of(context).apiClient;
    setState(() {
      _busy = true;
      _error = null;
    });

    try {
      var project = await api.getProject(widget.projectId);
      if (widget.autoBuild && project.printData == null) {
        project = await api.buildPrintData(project.id);
      }
      if (!mounted) return;
      setState(() => _project = project);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final project = _project;
    final printData = _printData;

    return Scaffold(
      appBar: AppBar(title: const Text('印刷データ')),
      body: _busy && project == null
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
              children: [
                if (_error != null) ...[
                  Card(
                    color: Theme.of(context).colorScheme.errorContainer,
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          SelectableText(_error!),
                          const SizedBox(height: 12),
                          FilledButton(onPressed: _load, child: const Text('再試行')),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                ],
                if (printData != null) ...[
                  _ReadyBanner(title: project!.title),
                  const SizedBox(height: 16),
                  _Specs(printData: printData, model: project.model),
                  const SizedBox(height: 16),
                  for (final warning in printData.warnings) ...[
                    _WarningTile(message: warning),
                    const SizedBox(height: 8),
                  ],
                  const SizedBox(height: 16),
                  _DownloadCard(url: printData.url),
                ],
              ],
            ),
    );
  }
}

class _ReadyBanner extends StatelessWidget {
  const _ReadyBanner({required this.title});
  final String title;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Theme.of(context).colorScheme.primaryContainer,
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          children: [
            Icon(
              Icons.check_circle,
              size: 44,
              color: Theme.of(context).colorScheme.onPrimaryContainer,
            ),
            const SizedBox(height: 12),
            Text(
              '印刷データができました',
              style: Theme.of(context).textTheme.titleLarge?.copyWith(
                    color: Theme.of(context).colorScheme.onPrimaryContainer,
                  ),
            ),
            const SizedBox(height: 4),
            Text(
              title,
              textAlign: TextAlign.center,
              style: TextStyle(color: Theme.of(context).colorScheme.onPrimaryContainer),
            ),
          ],
        ),
      ),
    );
  }
}

class _Specs extends StatelessWidget {
  const _Specs({required this.printData, this.model});

  final PrintData printData;
  final Model3D? model;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('印刷の条件', style: Theme.of(context).textTheme.titleMedium),
            const Divider(height: 24),
            _Row(label: 'フィラメント', value: printData.material),
            _Row(
              label: '印刷時間',
              value: printData.estimated
                  ? '${printData.printTimeLabel}(概算)'
                  : printData.printTimeLabel,
            ),
            _Row(
              label: '使用量',
              value: '${printData.filamentGrams.toStringAsFixed(1)} g'
                  '${printData.estimated ? "(概算)" : ""}',
            ),
            if (model?.sizeMm != null) _Row(label: '外形', value: model!.sizeMm!.label),
            if (model != null)
              _Row(label: '寸法の確からしさ', value: model!.dimensionalAccuracy.label),
            _Row(label: '算出方法', value: printData.estimateSource),
          ],
        ),
      ),
    );
  }
}

class _Row extends StatelessWidget {
  const _Row({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 130,
            child: Text(label, style: Theme.of(context).textTheme.bodySmall),
          ),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }
}

class _WarningTile extends StatelessWidget {
  const _WarningTile({required this.message});
  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.amber.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.info_outline),
          const SizedBox(width: 12),
          Expanded(child: Text(message)),
        ],
      ),
    );
  }
}

class _DownloadCard extends StatelessWidget {
  const _DownloadCard({required this.url});
  final String? url;

  @override
  Widget build(BuildContext context) {
    if (url == null) return const SizedBox.shrink();
    final absolute = AppScope.of(context).apiClient.absoluteUrl(url!);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('次にすること', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            const Text(
              '1. 下の 3MF をダウンロードする\n'
              '2. Bambu Studio で開く\n'
              '3. プリンタ(P2S)とフィラメントを選ぶ\n'
              '4. 造形の向きとサポート材を確認してスライスする',
            ),
            const SizedBox(height: 16),
            SelectableText(
              absolute,
              style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
            ),
            const SizedBox(height: 4),
            Text(
              'この URL をブラウザで開くと 3MF がダウンロードできます。',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}
