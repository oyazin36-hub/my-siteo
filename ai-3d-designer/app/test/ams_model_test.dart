import 'dart:convert';

import 'package:ai_3d_designer/models/project.dart';
import 'package:flutter_test/flutter_test.dart';

/// サーバーが実際に返す形。server/tests/test_materials.py と対で維持する。
///
/// AMS 未登録のケース: 全パーツが「要装填」で、提案スロットが付く。
/// 本体と板バネは同じフィラメントなので 1 スロットを共有する。
const _printDataJson = '''
{
  "url": "/media/abc123/p.3mf",
  "material": "Bambu PETG Basic",
  "print_time_min": 195,
  "filament_grams": 10.5,
  "estimated": true,
  "estimate_source": "体積からの概算",
  "ams_plan": {
    "assignments": [
      {
        "slot": 1,
        "part": "本体",
        "product": "Bambu PETG Basic",
        "color": "Black",
        "grams": 9.1,
        "reason": "繰り返し曲げに耐える強度が要るため",
        "needs_loading": true,
        "external_spool": false
      },
      {
        "slot": 1,
        "part": "板バネ",
        "product": "Bambu PETG Basic",
        "color": "Black",
        "grams": 0.6,
        "reason": "本体と同じ材料でまとめられるため",
        "needs_loading": true,
        "external_spool": false
      },
      {
        "slot": 2,
        "part": "ボタン",
        "product": "Bambu PLA Basic",
        "color": "Orange",
        "grams": 0.6,
        "reason": "見分けやすい色が要るため",
        "needs_loading": true,
        "external_spool": false
      }
    ],
    "warnings": ["AMS の装填状態が未登録です"]
  },
  "warnings": [],
  "created_at": "2026-08-05T13:00:00Z"
}
''';

/// GET /me/settings のレスポンス。AMS の入れ子に注意。
const _settingsJson = '''
{
  "uid": "demo-user",
  "ams": {
    "connected": true,
    "slots": [
      {"slot": 1, "product": "Bambu PLA Basic", "color": "White"},
      {"slot": 2, "product": "Bambu PETG Basic", "color": "Black"}
    ]
  },
  "printer_model": "P2S"
}
''';

const _filamentJson = '''
{
  "product": "Bambu TPU for AMS",
  "material": "TPU",
  "colors": ["Black", "White"],
  "ams_compatible": false,
  "notes": "柔らかいので外部スプールから給送する"
}
''';

void main() {
  group('AmsPlan.fromJson', () {
    late PrintData printData;
    late AmsPlan plan;

    setUp(() {
      printData =
          PrintData.fromJson(jsonDecode(_printDataJson) as Map<String, dynamic>);
      plan = printData.amsPlan!;
    });

    test('印刷データに AMS 計画がぶら下がる', () {
      expect(printData.amsPlan, isNotNull);
      expect(plan.assignments, hasLength(3));
      expect(plan.warnings.single, contains('未登録'));
    });

    test('パーツ別のフィラメントと理由を解釈できる', () {
      final body = plan.assignments.first;
      expect(body.part, '本体');
      expect(body.product, 'Bambu PETG Basic');
      expect(body.color, 'Black');
      expect(body.grams, closeTo(9.1, 0.001));
      expect(body.reason, isNotEmpty);
    });

    test('同じフィラメントのパーツは同じスロットを指す', () {
      // スロットを無駄遣いしないことが STEP6 の要点なので、ここで固定しておく。
      final petg = plan.assignments.where((a) => a.product == 'Bambu PETG Basic');
      expect(petg.map((a) => a.slot).toSet(), {1});
    });

    test('装填が要るかを計画全体で判定できる', () {
      expect(plan.requiresLoading, isTrue);
    });

    test('装填済みなら要装填にならない', () {
      final raw = jsonDecode(_printDataJson) as Map<String, dynamic>;
      final assignments =
          (raw['ams_plan'] as Map<String, dynamic>)['assignments'] as List<dynamic>;
      for (final a in assignments) {
        (a as Map<String, dynamic>)['needs_loading'] = false;
      }
      expect(PrintData.fromJson(raw).amsPlan!.requiresLoading, isFalse);
    });
  });

  group('SlotAssignment.slotLabel', () {
    SlotAssignment build({
      int? slot,
      bool needsLoading = false,
      bool externalSpool = false,
    }) =>
        SlotAssignment(
          slot: slot,
          part: 'x',
          product: 'x',
          color: 'x',
          grams: 1,
          reason: 'x',
          needsLoading: needsLoading,
          externalSpool: externalSpool,
        );

    test('スロット番号があれば Slot N', () {
      expect(build(slot: 3).slotLabel, 'Slot 3');
    });

    test('AMS を通せない材料は外部スプールと表示する', () {
      // 番号が付いていても外部スプールが優先される。
      expect(build(slot: 1, externalSpool: true).slotLabel, '外部スプール');
    });

    test('割り当て先が無い場合は空きなしと表示する', () {
      expect(build().slotLabel, '空きなし');
    });
  });

  group('UserSettings.fromJson', () {
    test('AMS の装填状態を解釈できる', () {
      final settings =
          UserSettings.fromJson(jsonDecode(_settingsJson) as Map<String, dynamic>);
      expect(settings.amsConnected, isTrue);
      expect(settings.printerModel, 'P2S');
      expect(settings.slots, hasLength(2));
      expect(settings.slots.last.slot, 2);
      expect(settings.slots.last.product, 'Bambu PETG Basic');
    });

    test('未登録ユーザーでも読める', () {
      final settings = UserSettings.fromJson({
        'uid': 'demo-user',
        'ams': {'connected': false, 'slots': <dynamic>[]},
        'printer_model': 'P2S',
      });
      expect(settings.amsConnected, isFalse);
      expect(settings.slots, isEmpty);
    });

    test('登録用の JSON はサーバーのキー名に揃っている', () {
      const slot = LoadedSlot(slot: 1, product: 'Bambu PLA Basic', color: 'White');
      expect(slot.toJson(), {
        'slot': 1,
        'product': 'Bambu PLA Basic',
        'color': 'White',
      });
    });
  });

  group('Filament.fromJson', () {
    test('AMS 非対応のフィラメントを見分けられる', () {
      // AMS 設定画面はこのフラグで選択肢を絞る。
      final filament =
          Filament.fromJson(jsonDecode(_filamentJson) as Map<String, dynamic>);
      expect(filament.product, 'Bambu TPU for AMS');
      expect(filament.material, 'TPU');
      expect(filament.amsCompatible, isFalse);
      expect(filament.colors, contains('Black'));
    });
  });
}
