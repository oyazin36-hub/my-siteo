/// サーバーのドメインモデルに対応する型。
/// 対応する定義は server/app/domain/models.py。
library;

enum ProjectStatus {
  ideaInput('idea_input', 'アイデア入力'),
  proposing('proposing', '企画を作成中'),
  proposalReview('proposal_review', '企画の確認'),
  imageGenerating('image_generating', '画像を生成中'),
  imageReview('image_review', '画像の確認'),
  modelGenerating('model_generating', '3Dモデルを生成中'),
  modelReview('model_review', '3Dモデルの確認'),
  slicing('slicing', '印刷データを作成中'),
  printReady('print_ready', '印刷データ完成');

  const ProjectStatus(this.wire, this.label);

  final String wire;
  final String label;

  static ProjectStatus parse(String raw) => values.firstWhere(
        (status) => status.wire == raw,
        orElse: () => throw ArgumentError('未知の status: $raw'),
      );
}

enum DesignRoute {
  decorative('decorative', '装飾ルート'),
  mechanism('mechanism', '機構ルート');

  const DesignRoute(this.wire, this.label);

  final String wire;
  final String label;

  static DesignRoute? parse(String? raw) {
    if (raw == null) return null;
    return values.firstWhere(
      (route) => route.wire == raw,
      orElse: () => throw ArgumentError('未知の route: $raw'),
    );
  }
}

enum ImageKind {
  exterior('exterior', '外観'),
  scene('scene', '使用シーン'),
  exploded('exploded', '分解図'),
  internal('internal', '内部構造'),
  dimensions('dimensions', '寸法');

  const ImageKind(this.wire, this.label);

  final String wire;
  final String label;

  static ImageKind parse(String raw) => values.firstWhere(
        (kind) => kind.wire == raw,
        orElse: () => throw ArgumentError('未知の kind: $raw'),
      );
}

class Dimensions {
  const Dimensions({required this.width, required this.depth, required this.height});

  final double width;
  final double depth;
  final double height;

  factory Dimensions.fromJson(Map<String, dynamic> json) => Dimensions(
        width: (json['width'] as num).toDouble(),
        depth: (json['depth'] as num).toDouble(),
        height: (json['height'] as num).toDouble(),
      );

  String get label => '${_fmt(width)} × ${_fmt(depth)} × ${_fmt(height)} mm';

  static String _fmt(double value) =>
      value == value.roundToDouble() ? value.toStringAsFixed(0) : value.toStringAsFixed(1);
}

class Revision {
  const Revision({required this.request, required this.appliedAt});

  final String request;
  final DateTime appliedAt;

  factory Revision.fromJson(Map<String, dynamic> json) => Revision(
        request: json['request'] as String,
        appliedAt: DateTime.parse(json['applied_at'] as String),
      );
}

class Proposal {
  const Proposal({
    required this.productName,
    required this.concept,
    required this.sizeMm,
    this.capacity,
    this.mechanism,
    required this.material,
    required this.printTimeEstMin,
    required this.features,
    required this.revisions,
  });

  final String productName;
  final String concept;
  final Dimensions sizeMm;
  final String? capacity;
  final String? mechanism;
  final String material;
  final int printTimeEstMin;
  final List<String> features;
  final List<Revision> revisions;

  factory Proposal.fromJson(Map<String, dynamic> json) => Proposal(
        productName: json['product_name'] as String,
        concept: json['concept'] as String,
        sizeMm: Dimensions.fromJson(json['size_mm'] as Map<String, dynamic>),
        capacity: json['capacity'] as String?,
        mechanism: json['mechanism'] as String?,
        material: json['material'] as String,
        printTimeEstMin: json['print_time_est_min'] as int,
        features: (json['features'] as List<dynamic>).cast<String>(),
        revisions: (json['revisions'] as List<dynamic>)
            .map((e) => Revision.fromJson(e as Map<String, dynamic>))
            .toList(),
      );

  String get printTimeLabel {
    final hours = printTimeEstMin ~/ 60;
    final minutes = printTimeEstMin % 60;
    if (hours == 0) return '約$minutes分';
    if (minutes == 0) return '約$hours時間';
    return '約$hours時間$minutes分';
  }
}

class GeneratedImage {
  const GeneratedImage({required this.kind, required this.url, required this.prompt});

  final ImageKind kind;
  final String url;
  final String prompt;

  factory GeneratedImage.fromJson(Map<String, dynamic> json) => GeneratedImage(
        kind: ImageKind.parse(json['kind'] as String),
        url: json['url'] as String,
        prompt: json['prompt'] as String,
      );
}

enum JobStatus {
  queued('queued', '順番待ち'),
  running('running', '生成中'),
  done('done', '完了'),
  error('error', '失敗');

  const JobStatus(this.wire, this.label);

  final String wire;
  final String label;

  bool get inProgress => this == queued || this == running;

  static JobStatus parse(String raw) => values.firstWhere(
        (status) => status.wire == raw,
        orElse: () => throw ArgumentError('未知の job_status: $raw'),
      );
}

enum DimensionalAccuracy {
  approximate('approximate', '寸法は目安'),
  guaranteed('guaranteed', '寸法保証あり');

  const DimensionalAccuracy(this.wire, this.label);

  final String wire;
  final String label;

  static DimensionalAccuracy parse(String raw) => values.firstWhere(
        (value) => value.wire == raw,
        orElse: () => throw ArgumentError('未知の dimensional_accuracy: $raw'),
      );
}

class Model3D {
  const Model3D({
    required this.jobStatus,
    this.error,
    this.url,
    this.previewUrl,
    required this.watertight,
    required this.printable,
    required this.faceCount,
    this.sizeMm,
    required this.volumeMm3,
    required this.dimensionalAccuracy,
    required this.repairActions,
    required this.warnings,
    required this.revisions,
    this.sourceCode,
    required this.attempts,
  });

  final JobStatus jobStatus;
  final String? error;

  /// 印刷用 STL。スライサに渡すのはこちら。
  final String? url;

  /// 表示用 GLB。3Dビューアが読むのはこちら。
  final String? previewUrl;

  final bool watertight;
  final bool printable;
  final int faceCount;
  final Dimensions? sizeMm;
  final double volumeMm3;
  final DimensionalAccuracy dimensionalAccuracy;
  final List<String> repairActions;
  final List<String> warnings;
  final List<Revision> revisions;

  /// 機構ルートで生成された OpenSCAD コード。寸法を後から追える。
  final String? sourceCode;

  /// 機構ルートで寸法が合うまでに要した試行回数。
  final int attempts;

  factory Model3D.fromJson(Map<String, dynamic> json) => Model3D(
        jobStatus: JobStatus.parse(json['job_status'] as String),
        error: json['error'] as String?,
        url: json['url'] as String?,
        previewUrl: json['preview_url'] as String?,
        watertight: json['watertight'] as bool,
        printable: json['printable'] as bool,
        faceCount: json['face_count'] as int,
        sizeMm: json['size_mm'] == null
            ? null
            : Dimensions.fromJson(json['size_mm'] as Map<String, dynamic>),
        volumeMm3: (json['volume_mm3'] as num).toDouble(),
        dimensionalAccuracy:
            DimensionalAccuracy.parse(json['dimensional_accuracy'] as String),
        repairActions: (json['repair_actions'] as List<dynamic>).cast<String>(),
        warnings: (json['warnings'] as List<dynamic>).cast<String>(),
        revisions: (json['revisions'] as List<dynamic>)
            .map((e) => Revision.fromJson(e as Map<String, dynamic>))
            .toList(),
        sourceCode: json['source_code'] as String?,
        attempts: json['attempts'] as int? ?? 0,
      );
}

class PrintData {
  const PrintData({
    this.url,
    required this.material,
    required this.printTimeMin,
    required this.filamentGrams,
    required this.estimated,
    required this.estimateSource,
    required this.warnings,
  });

  /// Bambu Studio で開ける 3MF。
  final String? url;

  final String material;
  final int printTimeMin;
  final double filamentGrams;

  /// true なら概算。スライサ実測ではない。
  final bool estimated;

  final String estimateSource;
  final List<String> warnings;

  factory PrintData.fromJson(Map<String, dynamic> json) => PrintData(
        url: json['url'] as String?,
        material: json['material'] as String,
        printTimeMin: json['print_time_min'] as int,
        filamentGrams: (json['filament_grams'] as num).toDouble(),
        estimated: json['estimated'] as bool,
        estimateSource: json['estimate_source'] as String,
        warnings: (json['warnings'] as List<dynamic>).cast<String>(),
      );

  String get printTimeLabel {
    final hours = printTimeMin ~/ 60;
    final minutes = printTimeMin % 60;
    if (hours == 0) return '約$minutes分';
    if (minutes == 0) return '約$hours時間';
    return '約$hours時間$minutes分';
  }
}

class Project {
  const Project({
    required this.id,
    required this.title,
    required this.status,
    this.route,
    required this.ideaText,
    this.proposal,
    required this.images,
    required this.imageRevisions,
    this.model,
    this.printData,
    required this.updatedAt,
  });

  final String id;
  final String title;
  final ProjectStatus status;
  final DesignRoute? route;
  final String ideaText;
  final Proposal? proposal;
  final List<GeneratedImage> images;
  final List<Revision> imageRevisions;
  final Model3D? model;
  final PrintData? printData;
  final DateTime updatedAt;

  factory Project.fromJson(Map<String, dynamic> json) => Project(
        id: json['id'] as String,
        title: json['title'] as String,
        status: ProjectStatus.parse(json['status'] as String),
        route: DesignRoute.parse(json['route'] as String?),
        ideaText: (json['idea'] as Map<String, dynamic>)['text'] as String,
        proposal: json['proposal'] == null
            ? null
            : Proposal.fromJson(json['proposal'] as Map<String, dynamic>),
        images: (json['images'] as List<dynamic>)
            .map((e) => GeneratedImage.fromJson(e as Map<String, dynamic>))
            .toList(),
        imageRevisions: (json['image_revisions'] as List<dynamic>)
            .map((e) => Revision.fromJson(e as Map<String, dynamic>))
            .toList(),
        model: json['model'] == null
            ? null
            : Model3D.fromJson(json['model'] as Map<String, dynamic>),
        printData: json['print_data'] == null
            ? null
            : PrintData.fromJson(json['print_data'] as Map<String, dynamic>),
        updatedAt: DateTime.parse(json['updated_at'] as String),
      );
}
