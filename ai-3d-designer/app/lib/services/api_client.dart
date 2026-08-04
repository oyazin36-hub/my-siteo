import 'dart:convert';

import 'package:http/http.dart' as http;

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

  Future<Map<String, dynamic>> _get(
    String path, {
    required bool authenticated,
  }) async {
    final headers = <String, String>{'Accept': 'application/json'};

    if (authenticated) {
      final token = await _auth.idToken();
      if (token == null) {
        throw ApiException('サインインしていません');
      }
      headers['Authorization'] = 'Bearer $token';
    }

    final http.Response response;
    try {
      response = await _http.get(Uri.parse('$baseUrl$path'), headers: headers);
    } catch (error) {
      // 接続失敗はセットアップ時に最も多いので、原因の候補まで出す。
      throw ApiException(
        'サーバーに接続できません ($baseUrl$path)\n'
        'サーバーが起動しているか、API_BASE_URL が正しいか確認してください。\n'
        '詳細: $error',
      );
    }

    if (response.statusCode != 200) {
      throw ApiException(
        'HTTP ${response.statusCode}: ${utf8.decode(response.bodyBytes)}',
      );
    }

    return jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
  }
}
