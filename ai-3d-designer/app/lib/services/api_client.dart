import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/project.dart';
import 'auth_service.dart';

class ApiException implements Exception {
  ApiException(this.message);
  final String message;
  @override
  String toString() => message;
}

class HealthInfo {
  const HealthInfo({
    required this.status,
    required this.version,
    required this.environment,
    required this.authMode,
  });

  final String status;
  final String version;
  final String environment;
  final String authMode;

  factory HealthInfo.fromJson(Map<String, dynamic> json) => HealthInfo(
        status: json['status'] as String,
        version: json['version'] as String,
        environment: json['environment'] as String,
        authMode: json['auth_mode'] as String,
      );
}

class UserInfo {
  const UserInfo({required this.uid, this.email, required this.isAnonymous});

  final String uid;
  final String? email;
  final bool isAnonymous;

  factory UserInfo.fromJson(Map<String, dynamic> json) => UserInfo(
        uid: json['uid'] as String,
        email: json['email'] as String?,
        isAnonymous: json['is_anonymous'] as bool,
      );
}

class ApiClient {
  ApiClient({
    required this.baseUrl,
    required AuthService authService,
    http.Client? httpClient,
  })  : _auth = authService,
        _http = httpClient ?? http.Client();

  final String baseUrl;
  final AuthService _auth;
  final http.Client _http;

  /// 認証不要。サーバーへ到達できるかの確認。
  Future<HealthInfo> health() async {
    final response = await _get('/health', authenticated: false);
    return HealthInfo.fromJson(response);
  }

  /// 要認証。ログインが成立しているかの確認。
  Future<UserInfo> me() async {
    final response = await _get('/me', authenticated: true);
    return UserInfo.fromJson(response);
  }

  // --- プロジェクト (STEP1〜3) ---

  /// 画像 URL はサーバー相対で返るので、表示用に絶対 URL へ直す。
  String absoluteUrl(String path) =>
      path.startsWith('http') ? path : '$baseUrl$path';

  Future<List<Project>> listProjects() async {
    final response = await _send('GET', '/projects');
    return (jsonDecode(utf8.decode(response.bodyBytes)) as List<dynamic>)
        .map((e) => Project.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<Project> getProject(String id) => _project('GET', '/projects/$id');

  /// STEP1: アイデアを登録する。
  Future<Project> createProject(String text, {List<String> imageUrls = const []}) =>
      _project('POST', '/projects', body: {'text': text, 'image_urls': imageUrls});

  /// STEP2: 企画を生成する。
  Future<Project> generateProposal(String id) =>
      _project('POST', '/projects/$id/proposal');

  /// STEP2: 修正指示を反映する。
  Future<Project> reviseProposal(String id, String request) =>
      _project('POST', '/projects/$id/proposal/revise', body: {'request': request});

  /// STEP3: 企画を承認して画像を生成する。
  Future<Project> generateImages(String id) =>
      _project('POST', '/projects/$id/images');

  /// STEP3: 修正指示を反映して画像を作り直す。
  Future<Project> reviseImages(String id, String request) =>
      _project('POST', '/projects/$id/images/revise', body: {'request': request});

  Future<Project> _project(
    String method,
    String path, {
    Map<String, dynamic>? body,
  }) async {
    final response = await _send(method, path, body: body);
    return Project.fromJson(
      jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>,
    );
  }

  Future<Map<String, dynamic>> _get(
    String path, {
    required bool authenticated,
  }) async {
    final response = await _send('GET', path, authenticated: authenticated);
    return jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
  }

  Future<http.Response> _send(
    String method,
    String path, {
    Map<String, dynamic>? body,
    bool authenticated = true,
  }) async {
    final headers = <String, String>{'Accept': 'application/json'};

    if (authenticated) {
      final token = await _auth.idToken();
      if (token == null) {
        throw ApiException('サインインしていません');
      }
      headers['Authorization'] = 'Bearer $token';
    }
    if (body != null) {
      headers['Content-Type'] = 'application/json';
    }

    final uri = Uri.parse('$baseUrl$path');
    final encoded = body == null ? null : jsonEncode(body);

    final http.Response response;
    try {
      response = switch (method) {
        'GET' => await _http.get(uri, headers: headers),
        'POST' => await _http.post(uri, headers: headers, body: encoded),
        _ => throw ArgumentError('未対応のメソッド: $method'),
      };
    } catch (error) {
      if (error is ArgumentError) rethrow;
      // 接続失敗はセットアップ時に最も多いので、原因の候補まで出す。
      throw ApiException(
        'サーバーに接続できません ($baseUrl$path)\n'
        'サーバーが起動しているか、API_BASE_URL が正しいか確認してください。\n'
        '詳細: $error',
      );
    }

    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw ApiException(_describeError(response));
    }
    return response;
  }

  /// FastAPI は {"detail": "..."} でエラーを返すので、そこだけ取り出して読みやすくする。
  static String _describeError(http.Response response) {
    final raw = utf8.decode(response.bodyBytes);
    try {
      final decoded = jsonDecode(raw);
      if (decoded is Map<String, dynamic> && decoded['detail'] != null) {
        return '${decoded['detail']}';
      }
    } catch (_) {
      // JSON でなければそのまま出す。
    }
    return 'HTTP ${response.statusCode}: $raw';
  }
}
