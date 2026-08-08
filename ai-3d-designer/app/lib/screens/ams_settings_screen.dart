import 'package:flutter/material.dart';

import '../app_scope.dart';
import '../models/project.dart';
import '../services/api_client.dart';

/// AMS の装填状態を登録する画面。
///
/// 「今なにが入っているか」はユーザーにしか分からないので登録してもらう。
/// 登録すると、印刷データ作成時に入れ替えの要否まで分かるようになる。
class AmsSettingsScreen extends StatefulWidget {
  const AmsSettingsScreen({super.key});

  @override
  State<AmsSettingsScreen> createState() => _AmsSettingsScreenState();
}

class _AmsSettingsScreenState extends State<AmsSettingsScreen> {
  static const _slotCount = 4;

  bool _loading = true;
  bool _saving = false;
  String? _error;
  String? _saved;

  List<Filament> _catalog = const [];
  bool _connected = false;

  /// スロット番号 → 選択中のフィラメント。未装填は null。
  final Map<int, ({String product, String color})?> _slots = {
    for (var i = 1; i <= _slotCount; i++) i: null,
  };

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  Future<void> _load() async {
    final api = AppScope.of(context).apiClient;
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final catalog = await api.listFilaments();
      final settings = await api.getSettings();
      if (!mounted) return;

      setState(() {
        // AMS を通せないものは選択肢に出さない。登録してもサーバーが弾く。
        _catalog = catalog.where((f) => f.amsCompatible).toList();
        _connected = settings.amsConnected;
        for (var i = 1; i <= _slotCount; i++) {
          _slots[i] = null;
        }
        for (final slot in settings.slots) {
          _slots[slot.slot] = (product: slot.product, color: slot.color);
        }
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _save() async {
    final api = AppScope.of(context).apiClient;
    setState(() {
      _saving = true;
      _error = null;
      _saved = null;
    });

    final slots = <LoadedSlot>[
      for (final entry in _slots.entries)
        if (entry.value != null)
          LoadedSlot(
            slot: entry.key,
            product: entry.value!.product,
            color: entry.value!.color,
          ),
    ];

    try {
      await api.updateAms(connected: _connected, slots: slots);
      if (!mounted) return;
      setState(() => _saved = '保存しました');
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('AMS の装填状態')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Text(
                  'AMS に今なにが入っているかを登録すると、印刷データを作るときに '
                  '「入れ替えが要るか」まで分かるようになります。',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                const SizedBox(height: 12),
                SwitchListTile(
                  value: _connected,
                  onChanged: (value) => setState(() => _connected = value),
                  title: const Text('AMS を使用する'),
                  contentPadding: EdgeInsets.zero,
                ),
                const Divider(),
                for (var slot = 1; slot <= _slotCount; slot++) ...[
                  _SlotEditor(
                    slot: slot,
                    catalog: _catalog,
                    selection: _slots[slot],
                    enabled: _connected,
                    onChanged: (value) => setState(() => _slots[slot] = value),
                  ),
                  const SizedBox(height: 8),
                ],
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
                if (_saved != null) ...[
                  const SizedBox(height: 12),
                  Text(_saved!, style: const TextStyle(color: Colors.green)),
                ],
                const SizedBox(height: 20),
                FilledButton.icon(
                  onPressed: _saving ? null : _save,
                  icon: const Icon(Icons.save),
                  label: Text(_saving ? '保存中…' : '保存する'),
                ),
              ],
            ),
    );
  }
}

typedef _Selection = ({String product, String color});

class _SlotEditor extends StatelessWidget {
  const _SlotEditor({
    required this.slot,
    required this.catalog,
    required this.selection,
    required this.enabled,
    required this.onChanged,
  });

  final int slot;
  final List<Filament> catalog;
  final _Selection? selection;
  final bool enabled;
  final ValueChanged<_Selection?> onChanged;

  @override
  Widget build(BuildContext context) {
    final filament = selection == null
        ? null
        : catalog.where((f) => f.product == selection!.product).firstOrNull;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text('Slot $slot', style: Theme.of(context).textTheme.titleMedium),
                const Spacer(),
                if (selection != null)
                  TextButton(
                    onPressed: enabled ? () => onChanged(null) : null,
                    child: const Text('空にする'),
                  ),
              ],
            ),
            const SizedBox(height: 8),
            DropdownButtonFormField<String>(
              initialValue: selection?.product,
              decoration: const InputDecoration(
                labelText: 'フィラメント',
                border: OutlineInputBorder(),
                isDense: true,
              ),
              items: [
                for (final item in catalog)
                  DropdownMenuItem(value: item.product, child: Text(item.product)),
              ],
              onChanged: enabled
                  ? (product) {
                      if (product == null) return;
                      final picked = catalog.firstWhere((f) => f.product == product);
                      // 製品を変えたら、その製品にある色へ寄せる。
                      onChanged((product: product, color: picked.colors.first));
                    }
                  : null,
            ),
            if (filament != null) ...[
              const SizedBox(height: 8),
              DropdownButtonFormField<String>(
                initialValue: selection?.color,
                decoration: const InputDecoration(
                  labelText: '色',
                  border: OutlineInputBorder(),
                  isDense: true,
                ),
                items: [
                  for (final color in filament.colors)
                    DropdownMenuItem(value: color, child: Text(color)),
                ],
                onChanged: enabled
                    ? (color) {
                        if (color == null) return;
                        onChanged((product: filament.product, color: color));
                      }
                    : null,
              ),
            ],
          ],
        ),
      ),
    );
  }
}
