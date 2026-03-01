import base64
from django.http import HttpResponse
from django.conf import settings


class BasicAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Basic認証が有効な場合のみチェック
        if not getattr(settings, 'BASIC_AUTH_ENABLED', False):
            return self.get_response(request)

        # 静的ファイル、メディアファイル、ヘルスチェック、アイコン類は認証をスキップ
        skip_paths = ('/static/', '/media/', '/health/', '/favicon.ico', '/apple-touch-icon')
        if any(request.path.startswith(p) for p in skip_paths):
            return self.get_response(request)

        # セッションに認証済みフラグがあればスキップ
        session_verified = request.session.get('basic_auth_verified', False)

        if session_verified:
            response = self.get_response(request)
            request.session.modified = True  # セッションの更新を明示
            return response

        # 認証ヘッダーを確認
        if 'HTTP_AUTHORIZATION' in request.META:
            auth = request.META['HTTP_AUTHORIZATION'].split()
            if len(auth) == 2 and auth[0].lower() == 'basic':
                try:
                    username, password = base64.b64decode(auth[1]).decode('utf-8').split(':', 1)
                    if (username == settings.BASIC_AUTH_USERNAME and
                        password == settings.BASIC_AUTH_PASSWORD):
                        # 認証成功をセッションに保存
                        request.session['basic_auth_verified'] = True
                        request.session.modified = True  # セッションの更新を明示
                        response = self.get_response(request)
                        return response
                except Exception:
                    pass

        # 認証失敗時は401を返す
        response = HttpResponse('Unauthorized', status=401)
        response['WWW-Authenticate'] = 'Basic realm="Login Required"'
        return response
