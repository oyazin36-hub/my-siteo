import 'dart:math';

/// 認証の抽象。Firebase 実装への差し替えはこのインターフェースの背後で完結する。
abstract class AuthService {
  /// サインインして uid を返す。
  Future<String> signIn();

  /// バックエンドへ `Authorization: Bearer <token>` として送る値を返す。
  /// 未サインインなら null。
  Future<String?> idToken();

  /// 現在の uid。未サインインなら null。
  String? get currentUid;
}

/// Firebase を使わないローカル開発用の実装。
///
/// uid をそのままトークンとして送る。サーバー側の `insecure_dev` モードと対になっており、
/// サーバー側は環境が local 以外だと起動を拒否するので、本番へ漏れることはない。
class DevAuthService implements AuthService {
  DevAuthService({String? fixedUid}) : _fixedUid = fixedUid;

  final String? _fixedUid;
  String? _uid;

  @override
  String? get currentUid => _uid;

  @override
  Future<String> signIn() async {
    _uid = _fixedUid ?? 'dev-${Random().nextInt(1 << 32).toRadixString(16)}';
    return _uid!;
  }

  @override
  Future<String?> idToken() async => _uid;
}
