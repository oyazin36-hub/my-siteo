import 'package:flutter/material.dart';

import '../app_scope.dart';
import '../models/project.dart';
import '../services/api_client.dart';
import '../widgets/revision_sheet.dart';

/// 画面4: 画像確認 (STEP3)。OK なら次は3Dモデル生成 (Phase 2)。
class ImagesScreen extends StatefulWidget {
  const ImagesScreen({super.key, required this.projectId});

  final String projectId;

  @override
  State<ImagesScreen> createState() => _ImagesScreenState();
}

class _ImagesScreenState extends State<ImagesScreen> {
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
    await _run('読み込み中…', () => api.getProject(widget.projectId));
  }

  Future<void> _revise() async {
    final request = await showRevisionSheet(
      context,
      title: '画像のどこを直しますか?',
      hint: '例: もっと明るい色で / 木目調にして / 角を丸くして',
    );
    if (request == null || !mounted) return;

    final api = AppScope.of(context).apiClient;
    await _run(
      'AIが画像を作り直しています…',
      () => api.reviseImages(widget.projectId, request),
    );
  }

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

    return Scaffold(
      appBar: AppBar(title: const Text('画像の確認')),
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
                      child: SelectableText(_error!),
                    ),
                  ),
                  const SizedBox(height: 16),
                ],
                if (project != null) ...[
                  Text(
                    project.title,
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'AIが生成したイメージです。次の工程でこれを元に3Dモデルを作ります。',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  const SizedBox(height: 16),
                  for (final image in project.images) ...[
                    _ImageCard(image: image),
                    const SizedBox(height: 12),
                  ],
                  if (project.imageRevisions.isNotEmpty) ...[
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              '修正の履歴',
                              style: Theme.of(context).textTheme.titleSmall,
                            ),
                            const SizedBox(height: 8),
                            for (var i = 0; i < project.imageRevisions.length; i++)
                              Text('${i + 1}. ${project.imageRevisions[i].request}'),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                  ],
                  if (_busy)
                    Center(
                      child: Column(
                        children: [
                          const CircularProgressIndicator(),
                          const SizedBox(height: 12),
                          Text(
                            _busyLabel,
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ],
                      ),
                    )
                  else ...[
                    FilledButton.icon(
                      // Phase 2 で3Dモデル生成に繋ぐ。今は未実装であることを明示する。
                      onPressed: () => ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          content: Text('3Dモデル生成は Phase 2 で実装します'),
                        ),
                      ),
                      icon: const Icon(Icons.view_in_ar),
                      label: const Text('この画像でOK — 3Dモデルへ'),
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

class _ImageCard extends StatelessWidget {
  const _ImageCard({required this.image});

  final GeneratedImage image;

  @override
  Widget build(BuildContext context) {
    final api = AppScope.of(context).apiClient;

    return Card(
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          AspectRatio(
            aspectRatio: 1,
            child: Image.network(
              api.absoluteUrl(image.url),
              fit: BoxFit.cover,
              loadingBuilder: (context, child, progress) => progress == null
                  ? child
                  : const Center(child: CircularProgressIndicator()),
              errorBuilder: (context, error, stack) => ColoredBox(
                color: Theme.of(context).colorScheme.surfaceContainerHighest,
                child: const Center(child: Icon(Icons.broken_image_outlined)),
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(12),
            child: Text(
              image.kind.label,
              style: Theme.of(context).textTheme.titleSmall,
            ),
          ),
        ],
      ),
    );
  }
}
