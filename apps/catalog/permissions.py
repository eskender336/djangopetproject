from rest_framework import permissions

from apps.users.models import UserRole


class IsAdminOrManagerOrReadOnly(permissions.BasePermission):
    """
    Разрешает безопасные методы (GET, HEAD, OPTIONS) всем пользователям (AllowAny).
    Для методов записи (POST, PUT, PATCH, DELETE) требует, чтобы пользователь был
    аутентифицирован и являлся администратором, менеджером или персоналом (is_staff / is_superuser).
    """

    def has_permission(self, request, view) -> bool:
        if request.method in permissions.SAFE_METHODS:
            return True

        if not request.user or not request.user.is_authenticated:
            return False

        return bool(
            request.user.is_staff
            or request.user.is_superuser
            or getattr(request.user, "role", None) in (UserRole.ADMIN, UserRole.MANAGER)
        )
