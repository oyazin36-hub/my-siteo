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
    "revisions": [{"request": "もう少し薄くして", "applied_at": "2026-08-05T12:00:00Z"}],
    "warnings": []
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
  "model": {
    "job_id": "stub-job-1",
    "job_status": "done",
    "error": null,
    "url": "/media/abc123/m.stl",
    "preview_url": "/media/abc123/m.glb",
    "format": "stl",
    "gen_source": "tripo",
    "dimensional_accuracy": "approximate",
    "watertight": true,
    "printable": true,
    "face_count": 12,
    "size_mm": {"width": 96.0, "depth": 72.0, "height": 48.0},
    "volume_mm3": 331776.0,
    "repair_actions": ["穴を塞いだ"],
    "warnings": ["実寸が企画値と食い違っています"],
    "revisions": []
  },
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
      // 成立性の検算結果。この企画には問題がない。
      expect(proposal.warnings, isEmpty);
    });

    test('成立しない企画の警告を解釈できる', () {
      final raw = jsonDecode(_projectJson) as Map<String, dynamic>;
      (raw['proposal'] as Map<String, dynamic>)['warnings'] = [
        '高さが足りません。名刺30枚(6.9mm)と機構(2.5mm)で 9.4mm 要りますが、'
            '内寸高さは 8.3mm です。高さを 11.8mm 以上にするか、25枚に減らしてください。',
      ];
      expect(Project.fromJson(raw).proposal!.warnings, hasLength(1));
    });

    test('warnings が無い古い応答も読める', () {
      final raw = jsonDecode(_projectJson) as Map<String, dynamic>;
      (raw['proposal'] as Map<String, dynamic>).remove('warnings');
      expect(Project.fromJson(raw).proposal!.warnings, isEmpty);
    });

    test('3Dモデルを解釈できる', () {
      final model = project.model!;
      expect(model.jobStatus, JobStatus.done);
      expect(model.jobStatus.inProgress, isFalse);
      expect(model.printable, isTrue);
      expect(model.watertight, isTrue);
      // 印刷用 STL と表示用 GLB は別物であること。
      expect(model.url, endsWith('.stl'));
      expect(model.previewUrl, endsWith('.glb'));
      expect(model.dimensionalAccuracy, DimensionalAccuracy.approximate);
      expect(model.warnings, hasLength(1));
    });

    test('生成中は進行中と判定される', () {
      for (final status in [JobStatus.queued, JobStatus.running]) {
        expect(status.inProgress, isTrue, reason: status.wire);
      }
      for (final status in [JobStatus.done, JobStatus.error]) {
        expect(status.inProgress, isFalse, reason: status.wire);
      }
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
      raw['model'] = null;

      final fresh = Project.fromJson(raw);
      expect(fresh.proposal, isNull);
      expect(fresh.route, isNull);
      expect(fresh.model, isNull);
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
