import 'dart:async';

import 'package:flutter/material.dart';
import 'package:model_viewer_plus/model_viewer_plus.dart';

import '../app_scope.dart';
import '../models/project.dart';
import '../services/api_client.dart';
import '../widgets/revision_sheet.dart';

/// 画面5: 3Dモデル確認 (STEP4)。
///
/// 生成は数分かかるのでポーリングで進行状況を追う。
class ModelScreen extends StatefulWidget {
  const ModelScreen({super.key, required this.projectId, this.autoGenerate = false});

  final String projectId;
  final bool autoGenerate;

  @override
  State<ModelScreen> createState() => _ModelScreenState();
}

class _ModelScreenState extends State<ModelScreen> {
  static const _pollInterval = Duration(seconds: 3);

  Project? _project;
  Timer? _poller;
  bool _busy = false;
  String? _error;

  Model3D? get _model => _project?.model;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _start());
  }

  @override
  void dispose() {
    _poller?.cancel();
    super.dispose();
  }

  Future<void> _start() async {
    final api = AppScope.of(context).apiClient;
    setState(() {
      _busy = true;
      _error = null;
    });

    try {
      var project = await api.getProject(widget.projectId);
      if (widget.autoGenerate && project.model == null) {
        project = await api.generateModel(project.id);
      }
      if (!mounted) return;
      setState(() => _project = project);
      _syncPolling();
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// 生成中だけポーリングする。完了・失敗したら止める。
  void _syncPolling() {
    final inProgress = _model?.jobStatus.inProgress ?? false;
    if (inProgress && _poller == null) {
      _poller = Timer.periodic(_pollInterval, (_) => _refresh());
    } else if (!inProgress) {
      _poller?.cancel();
      _poller = null;
    }
  }

  Future<void> _refresh() async {
    final api = AppScope.of(context).apiClient;
    try {
      final project = await api.getProject(widget.projectId);
      if (!mounted) return;
      setState(() => _project = project);
      _syncPolling();
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _error = error.message);
      _poller?.cancel();
      _poller = null;
    }
  }

  Future<void> _revise() async {
    final request = await showRevisionSheet(
      context,
      title: '3Dモデルのどこを直しますか?',
      hint: '例: もっと丸みをつけて / 厚みを増やして',
    );
    if (request == null || !mounted) return;

    final api = AppScope.of(context).apiClient;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final project = await api.reviseModel(widget.projectId, request);
      if (!mounted) return;
      setState(() => _project = project);
      _syncPolling();
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final model = _model;

    return Scaffold(
      appBar: AppBar(title: const Text('3Dモデルの確認')),
      body: _busy && _project == null
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
              children: [
                if (_error != null) ...[
                  _Banner(
                    icon: Icons.error_outline,
                    color: Theme.of(context).colorScheme.errorContainer,
                    child: SelectableText(_error!),
                  ),
                  const SizedBox(height: 16),
                ],
                if (model == null)
                  const Text('まだ3Dモデルがありません')
                else ...[
                  if (model.jobStatus.inProgress)
                    _Generating(status: model.jobStatus)
                  else if (model.jobStatus == JobStatus.error)
                    _Banner(
                      icon: Icons.error_outline,
                      color: Theme.of(context).colorScheme.errorContainer,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text('3Dモデルの生成に失敗しました'),
                          if (model.error != null) ...[
                            const SizedBox(height: 8),
                            SelectableText(model.error!),
                          ],
                          const SizedBox(height: 12),
                          FilledButton(
                            onPressed: _start,
                            child: const Text('もう一度試す'),
                          ),
                        ],
                      ),
                    )
                  else ...[
                    _Viewer(previewUrl: model.previewUrl),
                    const SizedBox(height: 16),
                    _Specs(model: model),
                    if (model.warnings.isNotEmpty) ...[
                      const SizedBox(height: 12),
                      for (final warning in model.warnings) ...[
                        _Banner(
                          icon: Icons.warning_amber,
                          color: Colors.amber.withValues(alpha: 0.18),
                          child: Text(warning),
                        ),
                        const SizedBox(height: 8),
                      ],
                    ],
                    if (model.repairActions.isNotEmpty) ...[
                      const SizedBox(height: 4),
                      _RepairLog(actions: model.repairActions),
                    ],
                    const SizedBox(height: 24),
                    FilledButton.icon(
                      onPressed: model.printable
                          ? () => ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                  content: Text('印刷データ(3MF)の生成は Phase 3 で実装します'),
                                ),
                              )
                          : null,
                      icon: const Icon(Icons.print),
                      label: const Text('このモデルでOK — 印刷データへ'),
                    ),
                    if (!model.printable) ...[
                      const SizedBox(height: 4),
                      Text(
                        '印刷できない状態のため先に進めません。作り直してください。',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                    const SizedBox(height: 8),
                    OutlinedButton.icon(
                      onPressed: _busy ? null : _revise,
                      icon: const Icon(Icons.edit),
                      label: const Text('作り直す'),
                    ),
                  ],
                ],
              ],
            ),
    );
  }
}

class _Viewer extends StatelessWidget {
  const _Viewer({required this.previewUrl});

  final String? previewUrl;

  @override
  Widget build(BuildContext context) {
    if (previewUrl == null) {
      return const SizedBox.shrink();
    }
    final url = AppScope.of(context).apiClient.absoluteUrl(previewUrl!);

    return Card(
      clipBehavior: Clip.antiAlias,
      child: SizedBox(
        height: 340,
        // STL は表示できないので、同じメッシュから書き出した GLB を読む。
        child: ModelViewer(
          src: url,
          alt: '生成された3Dモデル',
          ar: false,
          autoRotate: true,
          cameraControls: true,
          disableZoom: false,
          backgroundColor: Theme.of(context).colorScheme.surfaceContainerHighest,
        ),
      ),
    );
  }
}

class _Generating extends StatelessWidget {
  const _Generating({required this.status});

  final JobStatus status;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 40, horizontal: 16),
        child: Column(
          children: [
            const CircularProgressIndicator(),
            const SizedBox(height: 20),
            Text(
              status == JobStatus.queued ? '順番待ちです' : '3Dモデルを生成しています',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            Text(
              '数分かかります。この画面を開いたままにしておくか、\n'
              '後でホームから開き直しても続きが見られます。',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}

class _Specs extends StatelessWidget {
  const _Specs({required this.model});

  final Model3D model;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  model.printable ? Icons.check_circle : Icons.cancel,
                  color: model.printable ? Colors.green : Theme.of(context).colorScheme.error,
                ),
                const SizedBox(width: 8),
                Text(
                  model.printable ? '印刷できる状態です' : '印刷できません',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ],
            ),
            const Divider(height: 24),
            if (model.sizeMm != null) _Row(label: '実寸', value: model.sizeMm!.label),
            _Row(label: '寸法の確からしさ', value: model.dimensionalAccuracy.label),
            _Row(label: '防水(閉じた立体)', value: model.watertight ? 'はい' : 'いいえ'),
            _Row(label: '面数', value: '${model.faceCount}'),
            if (model.volumeMm3 > 0)
              _Row(label: '体積', value: '${(model.volumeMm3 / 1000).toStringAsFixed(1)} cm³'),
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

class _RepairLog extends StatelessWidget {
  const _RepairLog({required this.actions});

  final List<String> actions;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('自動で行った修復', style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: 8),
            for (final action in actions) Text('・$action'),
          ],
        ),
      ),
    );
  }
}

class _Banner extends StatelessWidget {
  const _Banner({required this.icon, required this.color, required this.child});

  final IconData icon;
  final Color color;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(8)),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon),
          const SizedBox(width: 12),
          Expanded(child: child),
        ],
      ),
    );
  }
}
