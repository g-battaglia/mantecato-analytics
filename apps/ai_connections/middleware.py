"""Public protocol CORS only; never open session consent/management to CORS."""

from django.http import HttpResponse


class PublicOAuthCorsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        public = request.path.startswith(("/oauth/", "/.well-known/oauth-"))
        private = request.path.startswith("/settings/ai-connections/")
        if public and request.method == "OPTIONS":
            response = HttpResponse(status=204)
        else:
            response = self.get_response(request)
        if public:
            response["Access-Control-Allow-Origin"] = "*"
            response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
            response["Cache-Control"] = "no-store"
        if private:
            response["Cache-Control"] = "no-store"
            # Chromium navigation POSTs with no-referrer emit Origin:null,
            # breaking same-origin CSRF. No credentials appear in these URLs;
            # same-origin still suppresses cross-origin referrer disclosure.
            response["Referrer-Policy"] = "same-origin"
        return response
