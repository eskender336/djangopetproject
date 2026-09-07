from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status
from rest_framework.response import Response

from apps.users.models import User
from apps.users.serializers import UserProfileSerializer, UserRegistrationSerializer


@extend_schema(tags=["Users"])
class RegisterView(generics.CreateAPIView):
    """
    Регистрация нового пользователя.
    """

    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        profile_serializer = UserProfileSerializer(user)
        return Response(
            {
                "message": "Пользователь успешно зарегистрирован.",
                "user": profile_serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["Users"])
class ProfileView(generics.RetrieveUpdateAPIView):
    """
    Просмотр и редактирование профиля текущего пользователя.
    """

    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user
