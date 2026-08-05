import 'dart:convert';

import 'package:ai_3d_designer/models/project.dart';
import 'package:flutter_test/flutter_test.dart';

/// サーバーが実際に返す形。server/tests/test_design_flow.py と対で維持する。
const _projectJson = '''
{
  "id": "abc123",
  "owner_uid": "demo-user",
  "title": "スマートスライド名刺ケース",
  "status": "image_review",
  "route": "mechanism",
  "idea": {"text": "名刺入れをつくって", "image_urls": []},
  "proposal": {
    "product_name": "スマートスライド名刺ケース",
    "concept": "ボタンで名刺が持ち上がるケース",
    "size_mm": {"width": 96.0, "depth": 60.0, "height": 10.7},
    "capacity": "名刺30枚",
    "mechanism": "ボタン式スライド排出",
    "material": "Bambu PETG Basic",
    "print_time_est_min": 180,
    "features": ["窓付きフタ", "板バネ一体成形"],
    "revisions": [{"request": "もう少し薄くして", "applied_at": "2026-08-05T12:00:00Z"}]
  },
  "images": [
    {
      "kind": "exterior",
      "url": "/media/abc123/x.png",
      "prompt": "...",
      "created_at": "2026-08-05T12:00:00Z"
    }
  ],
  "image_revisions": [],
  "created_at": "2026-08-05T11:00:00Z",
  "updated_at": "2026-08-05T12:00:00Z"
}
''';

void main() {
  group('Project.fromJson', () {
    late Project project;

    setUp(() {
      project = Project.fromJson(jsonDecode(_projectJson) as Map<String, dynamic>);
    });

    test('状態とルートを解釈できる', () {
      expect(project.status, ProjectStatus.imageReview);
      expect(project.status.label, '画像の確認');
      expect(project.route, DesignRoute.mechanism);
    });

    test('企画を解釈できる', () {
      final proposal = project.proposal!;
      expect(proposal.productName, 'スマートスライド名刺ケース');
      expect(proposal.capacity, '名刺30枚');
      expect(proposal.features, hasLength(2));
      expect(proposal.revisions.single.request, 'もう少し薄くして');
    });

    test('画像を解釈できる', () {
      expect(project.images.single.kind, ImageKind.exterior);
      expect(project.images.single.url, '/media/abc123/x.png');
    });

    test('企画がまだ無いプロジェクトも読める', () {
      final raw = jsonDecode(_projectJson) as Map<String, dynamic>;
      raw['proposal'] = null;
      raw['route'] = null;
      raw['status'] = 'idea_input';

      final fresh = Project.fromJson(raw);
      expect(fresh.proposal, isNull);
      expect(fresh.route, isNull);
      expect(fresh.status, ProjectStatus.ideaInput);
    });
  });

  group('表示用の整形', () {
    test('寸法は不要な小数を出さない', () {
      const dimensions = Dimensions(width: 96, depth: 60, height: 10.7);
      expect(dimensions.label, '96 × 60 × 10.7 mm');
    });

    test('印刷時間を時間と分に分ける', () {
      Proposal build(int minutes) => Proposal(
            productName: 'x',
            concept: 'x',
            sizeMm: const Dimensions(width: 1, depth: 1, height: 1),
            material: 'x',
            printTimeEstMin: minutes,
            features: const [],
            revisions: const [],
          );

      expect(build(45).printTimeLabel, '約45分');
      expect(build(120).printTimeLabel, '約2時間');
      expect(build(195).printTimeLabel, '約3時間15分');
    });
  });

  group('未知の値', () {
    test('未知の status は例外にする', () {
      expect(() => ProjectStatus.parse('unknown'), throwsArgumentError);
    });
  });
}
