"""Scoped grants and hashed credentials; never analytics payloads or raw secrets."""

import uuid

from authlib.oauth2.rfc6749 import ClientMixin
from django.conf import settings
from django.db import models
from django.utils import timezone


class OAuthClient(models.Model, ClientMixin):
    client_id = models.CharField(max_length=2048, primary_key=True)
    name = models.CharField(max_length=120)
    redirect_uris = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def get_client_id(self):
        return self.client_id

    def get_default_redirect_uri(self):
        return self.redirect_uris[0] if self.redirect_uris else None

    def get_allowed_scope(self, scope):
        return scope if scope is not None else "sites:read analytics:read"

    def check_redirect_uri(self, uri):
        return uri in self.redirect_uris

    def check_client_secret(self, secret):
        return False

    def check_endpoint_auth_method(self, method, endpoint):
        return method == "none"

    def check_response_type(self, response_type):
        return response_type == "code"

    def check_grant_type(self, grant_type):
        return grant_type in ("authorization_code", "refresh_token")


class AIConnection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    client = models.ForeignKey(OAuthClient, on_delete=models.PROTECT)
    auth_method = models.CharField(
        max_length=16, choices=[("oauth", "OAuth"), ("personal", "Token")]
    )
    scopes = models.JSONField(default=list)
    website_ids = models.JSONField(default=list)
    authorized_scopes = models.JSONField(default=list)
    authorized_websites = models.JSONField(default=list)
    auth_fingerprint = models.CharField(max_length=64)
    notice_version = models.CharField(max_length=40)
    notice_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    verified_at = models.DateTimeField(null=True)
    last_used_at = models.DateTimeField(null=True)
    revoked_at = models.DateTimeField(null=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["user", "-created_at", "-id"])]


class OAuthCredential(models.Model):
    digest = models.CharField(max_length=64, primary_key=True)
    kind = models.CharField(max_length=16)
    connection = models.ForeignKey(AIConnection, null=True, on_delete=models.CASCADE)
    payload = models.JSONField(default=dict)
    expires_at = models.DateTimeField(db_index=True)
    consumed_at = models.DateTimeField(null=True)

    def get_redirect_uri(self):
        return self.payload.get("redirect_uri")

    def get_scope(self):
        return " ".join(sorted(set(self.payload.get("scopes", [])) & set(self.connection.scopes)))

    @property
    def code_challenge(self):
        return self.payload.get("code_challenge")

    @property
    def code_challenge_method(self):
        return "S256"

    def check_client(self, client):
        return self.connection.client_id == client.client_id

    def is_expired(self):
        return self.expires_at <= timezone.now()


class AIActivity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    connection = models.ForeignKey(AIConnection, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    action = models.CharField(max_length=48)
    outcome = models.CharField(max_length=32)
    website_id = models.UUIDField(null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["user", "-created_at", "-id"])]
