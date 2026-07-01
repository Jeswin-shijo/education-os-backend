"""User data-access layer."""
from __future__ import annotations

from typing import Optional

from django.contrib.auth import get_user_model

from core.repositories import BaseRepository

User = get_user_model()


class UserRepository(BaseRepository):
    model = User

    def __init__(self):
        super().__init__(User)

    def get_by_email(self, email: str) -> Optional["User"]:
        if not email:
            return None
        return self.get_queryset().filter(email__iexact=email.strip()).first()

    def email_exists(self, email: str) -> bool:
        return self.get_queryset().filter(email__iexact=email.strip()).exists()

    def by_role(self, role: str):
        return self.get_queryset().filter(role=role)

    def active(self):
        return self.get_queryset().filter(is_active=True)
