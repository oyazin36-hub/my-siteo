import 'dart:convert';

import 'package:ai_3d_designer/config.dart';
import 'package:ai_3d_designer/services/api_client.dart';
import 'package:ai_3d_designer/services/auth_service.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  group('AuthMode.parse', () {
    test('サーバーが返す文字列表現を解釈できる', () {
      expect(AuthMode.parse('firebase'), AuthMode.firebase);
      expect(AuthMode.parse('insecure_dev'), AuthMode.insecureDev);
    });

    test('未知の値は例外にする', () {
      expect(() => AuthMode.parse('nope'), throwsArgumentError);
    });
  });

  group('ApiClient', () {
    test('health は認証ヘッダを付けずに呼ぶ', () async {
      String? sentAuthHeader;
      final client = ApiClient(
        baseUrl: 'http://test.local',
        authService: DevAuthService(fixedUid: 'dev-1'),
        httpClient: MockClient((request) async {
          sentAuthHeader = request.headers['Authorization'];
          return http.Response(
            jsonEncode({
              'status': 'ok',
              'version': '0.1.0',
              'environment': 'local',
              'auth_mode': 'insecure_dev',
            }),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          );
        }),
      );

      final health = await client.health();

      expect(sentAuthHeader, isNull);
      expect(health.status, 'ok');
      expect(health.authMode, 'insecure_dev');
    });

    test('me はサインイン後のトークンを Bearer で送る', () async {
      String? sentAuthHeader;
      final auth = DevAuthService(fixedUid: 'dev-1');
      final client = ApiClient(
        baseUrl: 'http://test.local',
        authService: auth,
        httpClient: MockClient((request) async {
          sentAuthHeader = request.headers['Authorization'];
          return http.Response(
            jsonEncode({'uid': 'dev-1', 'email': null, 'is_anonymous': true}),
            200,
            headers: {'content-type': 'application/json; charset=utf-8'},
          );
        }),
      );

      await auth.signIn();
      final user = await client.me();

      expect(sentAuthHeader, 'Bearer dev-1');
      expect(user.uid, 'dev-1');
      expect(user.isAnonymous, isTrue);
    });

    test('未サインインで me を呼ぶと ApiException', () async {
      final client = ApiClient(
        baseUrl: 'http://test.local',
        authService: DevAuthService(),
        httpClient: MockClient((_) async => http.Response('{}', 200)),
      );

      expect(() => client.me(), throwsA(isA<ApiException>()));
    });

    test('接続失敗は原因の候補を含むメッセージにする', () async {
      final client = ApiClient(
        baseUrl: 'http://test.local',
        authService: DevAuthService(),
        httpClient: MockClient((_) async => throw const SocketExceptionStub()),
      );

      expect(
        () => client.health(),
        throwsA(
          isA<ApiException>().having(
            (e) => e.message,
            'message',
            contains('API_BASE_URL'),
          ),
        ),
      );
    });
  });
}

class SocketExceptionStub implements Exception {
  const SocketExceptionStub();
  @override
  String toString() => 'Connection refused';
}
