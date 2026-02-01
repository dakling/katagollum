from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import GameStateViewSet, ChatViewSet, InitializeGameView, FirstMoveView

router = DefaultRouter()
router.register(r"games", GameStateViewSet, basename="game")
router.register(r"chat", ChatViewSet, basename="chat")

urlpatterns = [
    path("", include(router.urls)),
    path("initialize/", InitializeGameView.as_view(), name="initialize-game"),
    path("games/<int:game_id>/first_move/", FirstMoveView.as_view(), name="first-move"),
]
