from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.users.managers import CustomUserManager


class UserRole(models.TextChoices):
    CUSTOMER = "customer", _("Покупатель")
    MANAGER = "manager", _("Менеджер")
    ADMIN = "admin", _("Администратор")


class User(AbstractBaseUser, PermissionsMixin):
    """
    Кастомная модель пользователя с авторизацией по Email.
    """

    email = models.EmailField(
        _("Email адрес"),
        unique=True,
        db_index=True,
        error_messages={
            "unique": _("Пользователь с таким email уже существует."),
        },
    )
    first_name = models.CharField(_("Имя"), max_length=150, blank=True)
    last_name = models.CharField(_("Фамилия"), max_length=150, blank=True)
    phone = models.CharField(_("Телефон"), max_length=20, blank=True)
    role = models.CharField(
        _("Роль"),
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.CUSTOMER,
        db_index=True,
    )

    is_staff = models.BooleanField(
        _("Статус персонала"),
        default=False,
        help_text=_("Определяет доступ пользователя в панель администратора."),
    )
    is_active = models.BooleanField(
        _("Активен"),
        default=True,
        help_text=_("Снимите отметку вместо удаления учетной записи."),
    )
    date_joined = models.DateTimeField(_("Дата регистрации"), default=timezone.now)
    updated_at = models.DateTimeField(_("Дата обновления"), auto_now=True)

    objects = CustomUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = _("Пользователь")
        verbose_name_plural = _("Пользователи")
        ordering = ["-date_joined"]

    def __str__(self):
        return self.email

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email
