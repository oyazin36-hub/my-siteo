import 'package:flutter/material.dart';

import '../app_scope.dart';
import '../models/project.dart';
import '../services/api_client.dart';
import 'connection_screen.dart';
import 'idea_input_screen.dart';
import 'proposal_screen.dart';

/// 画面1: ホーム。
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  bool _loading = true;
  List<Project> _projects = const [];
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  Future<void> _load() async {
    final scope = AppScope.of(context);
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      // 過去作品の取得には認証が要るので、まずサインインを済ませる。
      await scope.authService.signIn();
      final projects = await scope.apiClient.listProjects();
      if (!mounted) return;
      setState(() => _projects = projects);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _startNew() async {
    final created = await Navigator.of(context).push<Project>(
      MaterialPageRoute(builder: (_) => const IdeaInputScreen()),
    );
    if (created != null && mounted) await _load();
  }

  Future<void> _open(Project project) async {
    await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => ProposalScreen(projectId: project.id)),
    );
    if (mounted) await _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('AI 3D Product Designer'),
        actions: [
          IconButton(
            icon: const Icon(Icons.settings),
            tooltip: '設定',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) {
                  final scope = AppScope.of(context);
                  return ConnectionScreen(
                    config: scope.config,
                    authService: scope.authService,
                    apiClient: scope.apiClient,
                  );
                },
              ),
            ),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _startNew,
        icon: const Icon(Icons.add),
        label: const Text('新規作成'),
      ),
      body: RefreshIndicator(onRefresh: _load, child: _body()),
    );
  }

  Widget _body() {
    if (_loading && _projects.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_error != null) {
      return ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            color: Theme.of(context).colorScheme.errorContainer,
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('読み込みに失敗しました'),
                  const SizedBox(height: 8),
                  SelectableText(_error!),
                  const SizedBox(height: 12),
                  FilledButton(onPressed: _load, child: const Text('再試行')),
                ],
              ),
            ),
          ),
        ],
      );
    }

    if (_projects.isEmpty) {
      return ListView(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 64),
        children: [
          Icon(
            Icons.view_in_ar_outlined,
            size: 72,
            color: Theme.of(context).colorScheme.outline,
          ),
          const SizedBox(height: 24),
          Text(
            'まだ作品がありません',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 8),
          Text(
            '「新規作成」から、作りたい物を言葉で説明してください。\n'
            'AIが企画を立てて、画像と3Dモデルにしていきます。',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      );
    }

    return ListView.separated(
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 88),
      itemCount: _projects.length,
      separatorBuilder: (_, __) => const SizedBox(height: 8),
      itemBuilder: (context, index) {
        final project = _projects[index];
        return Card(
          margin: EdgeInsets.zero,
          child: ListTile(
            title: Text(project.title),
            subtitle: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SizedBox(height: 4),
                Text(
                  project.ideaText,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                const SizedBox(height: 6),
                Wrap(
                  spacing: 6,
                  children: [
                    _Chip(label: project.status.label),
                    if (project.route != null) _Chip(label: project.route!.label),
                  ],
                ),
              ],
            ),
            isThreeLine: true,
            trailing: const Icon(Icons.chevron_right),
            onTap: () => _open(project),
          ),
        );
      },
    );
  }
}

class _Chip extends StatelessWidget {
  const _Chip({required this.label});
  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.secondaryContainer,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 11,
          color: Theme.of(context).colorScheme.onSecondaryContainer,
        ),
      ),
    );
  }
}
