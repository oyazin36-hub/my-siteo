import 'package:flutter/material.dart';

import '../app_scope.dart';
import '../models/project.dart';
import '../services/api_client.dart';
import '../widgets/revision_sheet.dart';
import 'images_screen.dart';

/// 画面3: AI企画確認 (STEP2)。OK なら画像生成へ、修正なら企画を作り直す。
class ProposalScreen extends StatefulWidget {
  const ProposalScreen({
    super.key,
    required this.projectId,
    this.autoGenerate = false,
  });

  final String projectId;

  /// アイデア入力から来た場合、開いた直後に企画生成を始める。
  final bool autoGenerate;

  @override
  State<ProposalScreen> createState() => _ProposalScreenState();
}

class _ProposalScreenState extends State<ProposalScreen> {
  Project? _project;
  bool _busy = false;
  String _busyLabel = '';
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  Future<void> _load() async {
    final api = AppScope.of(context).apiClient;
    await _run('読み込み中…', () async {
      var project = await api.getProject(widget.projectId);
      if (widget.autoGenerate && project.proposal == null) {
        setState(() => _busyLabel = 'AIが企画を考えています…');
        project = await api.generateProposal(project.id);
      }
      return project;
    });
  }

  Future<void> _regenerate() async {
    final api = AppScope.of(context).apiClient;
    await _run(
      'AIが企画を考えています…',
      () => api.generateProposal(widget.projectId),
    );
  }

  Future<void> _revise() async {
    final request = await showRevisionSheet(
      context,
      title: 'どこを直しますか?',
      hint: '例: もう少し薄くして / 50枚入るようにして / 素材をPLAに',
    );
    if (request == null || !mounted) return;

    final api = AppScope.of(context).apiClient;
    await _run(
      '修正を反映しています…',
      () => api.reviseProposal(widget.projectId, request),
    );
  }

  Future<void> _approve() async {
    final api = AppScope.of(context).apiClient;
    final navigator = Navigator.of(context);

    final ok = await _run(
      'AIが画像を作っています…',
      () => api.generateImages(widget.projectId),
    );
    if (!ok || !mounted) return;

    await navigator.push(
      MaterialPageRoute(builder: (_) => ImagesScreen(projectId: widget.projectId)),
    );
    if (mounted) await _load();
  }

  /// 共通の実行ラッパ。成功なら true。
  Future<bool> _run(String label, Future<Project> Function() action) async {
    setState(() {
      _busy = true;
      _busyLabel = label;
      _error = null;
    });
    try {
      final project = await action();
      if (!mounted) return true;
      setState(() => _project = project);
      return true;
    } on ApiException catch (error) {
      if (!mounted) return false;
      setState(() => _error = error.message);
      return false;
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final project = _project;
    final proposal = project?.proposal;

    return Scaffold(
      appBar: AppBar(title: const Text('企画の確認')),
      body: _busy && project == null
          ? _Busy(label: _busyLabel)
          : ListView(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
              children: [
                if (_error != null) ...[
                  _ErrorCard(message: _error!, onRetry: _load),
                  const SizedBox(height: 16),
                ],
                if (project != null && proposal == null && !_busy) ...[
                  Text('まだ企画がありません', style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 12),
                  FilledButton.icon(
                    onPressed: _regenerate,
                    icon: const Icon(Icons.auto_awesome),
                    label: const Text('AIに企画してもらう'),
                  ),
                ],
                if (proposal != null) ...[
                  if (proposal.warnings.isNotEmpty) ...[
                    _FeasibilityCard(warnings: proposal.warnings),
                    const SizedBox(height: 12),
                  ],
                  _ProposalCard(proposal: proposal, route: project!.route),
                  if (proposal.revisions.isNotEmpty) ...[
                    const SizedBox(height: 12),
                    _RevisionHistory(revisions: proposal.revisions),
                  ],
                  const SizedBox(height: 24),
                  if (_busy)
                    _Busy(label: _busyLabel)
                  else ...[
                    FilledButton.icon(
                      onPressed: _approve,
                      icon: const Icon(Icons.check),
                      label: const Text('この案でOK — 画像を作る'),
                    ),
                    const SizedBox(height: 8),
                    OutlinedButton.icon(
                      onPressed: _revise,
                      icon: const Icon(Icons.edit),
                      label: const Text('修正を指示する'),
                    ),
                  ],
                ],
              ],
            ),
    );
  }
}

/// 企画が物理的に成立しない点を、案そのものより先に見せる。
///
/// ここを見落としたまま進むと、外形は指定どおりなのに機構が入っていない
/// モデルが出来てしまう。承認ボタンより前に置くのはそのため。
class _FeasibilityCard extends StatelessWidget {
  const _FeasibilityCard({required this.warnings});

  final List<String> warnings;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      color: scheme.errorContainer,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.warning_amber_rounded, color: scheme.onErrorContainer),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'この寸法では作れません',
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          color: scheme.onErrorContainer,
                        ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            for (final warning in warnings)
              Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Text(
                  warning,
                  style: TextStyle(color: scheme.onErrorContainer),
                ),
              ),
            const SizedBox(height: 4),
            Text(
              'このまま進めると、外形は指定どおりでも中身が入らないものが出来ます。'
              '「修正を指示する」から寸法か収納数を変えてください。',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: scheme.onErrorContainer,
                  ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ProposalCard extends StatelessWidget {
  const _ProposalCard({required this.proposal, this.route});

  final Proposal proposal;
  final DesignRoute? route;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(proposal.productName, style: Theme.of(context).textTheme.headlineSmall),
            const SizedBox(height: 8),
            Text(proposal.concept),
            const Divider(height: 28),
            _Row(label: 'サイズ', value: proposal.sizeMm.label),
            if (proposal.capacity != null) _Row(label: '収納', value: proposal.capacity!),
            if (proposal.mechanism != null) _Row(label: '機構', value: proposal.mechanism!),
            _Row(label: '素材', value: proposal.material),
            _Row(label: '印刷時間', value: proposal.printTimeLabel),
            if (route != null) _Row(label: '生成方式', value: route!.label),
            if (proposal.features.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text('設計の要点', style: Theme.of(context).textTheme.titleSmall),
              const SizedBox(height: 6),
              for (final feature in proposal.features)
                Padding(
                  padding: const EdgeInsets.only(bottom: 2),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('・'),
                      Expanded(child: Text(feature)),
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
            width: 76,
            child: Text(label, style: Theme.of(context).textTheme.bodySmall),
          ),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }
}

class _RevisionHistory extends StatelessWidget {
  const _RevisionHistory({required this.revisions});

  final List<Revision> revisions;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('修正の履歴', style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: 8),
            for (var i = 0; i < revisions.length; i++)
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Text('${i + 1}. ${revisions[i].request}'),
              ),
          ],
        ),
      ),
    );
  }
}

class _Busy extends StatelessWidget {
  const _Busy({required this.label});
  final String label;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 48),
      child: Column(
        children: [
          const CircularProgressIndicator(),
          const SizedBox(height: 16),
          Text(label, style: Theme.of(context).textTheme.bodySmall),
        ],
      ),
    );
  }
}

class _ErrorCard extends StatelessWidget {
  const _ErrorCard({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Theme.of(context).colorScheme.errorContainer,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SelectableText(message),
            const SizedBox(height: 12),
            FilledButton(onPressed: onRetry, child: const Text('再試行')),
          ],
        ),
      ),
    );
  }
}
