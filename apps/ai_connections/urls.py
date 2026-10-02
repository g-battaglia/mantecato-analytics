from django.urls import path

from apps.ai_connections import oauth, views

urlpatterns = [
    path("settings/ai-connections/", views.index, name="ai_connections"),
    path("settings/ai-connections/consent/", oauth.consent, name="ai_consent"),
    path("settings/ai-connections/tokens/", views.create_personal_token, name="ai_personal_token"),
    path("settings/ai-connections/<uuid:connection_id>/revoke/", views.revoke, name="ai_revoke"),
    path("settings/ai-connections/<uuid:connection_id>/reduce/", views.reduce, name="ai_reduce"),
    path(".well-known/oauth-authorization-server", oauth.authorization_metadata),
    path(".well-known/oauth-protected-resource", oauth.resource_metadata),
    path(".well-known/oauth-protected-resource/mcp", oauth.resource_metadata),
    path("oauth/register/", oauth.register),
    path("oauth/authorize/", oauth.authorize),
    path("oauth/token/", oauth.token),
    path("oauth/revoke/", oauth.revoke_token),
]
