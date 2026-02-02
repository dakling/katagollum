from django.db import models


class GameState(models.Model):
    BOARD_SIZE_CHOICES = [(9, 9), (13, 13), (19, 19)]

    id = models.AutoField(primary_key=True)
    board_size = models.IntegerField(choices=BOARD_SIZE_CHOICES, default=19)
    komi = models.FloatField(default=6.5)
    handicap = models.IntegerField(default=0)
    user_color = models.CharField(
        max_length=1, choices=[("B", "Black"), ("W", "White")], default="B"
    )
    game_over = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    persona = models.CharField(max_length=50, default="arrogant")

    def __str__(self):
        return f"Game {self.id} ({self.board_size}x{self.board_size})"

    @property
    def ai_color(self):
        return "W" if self.user_color == "B" else "B"


class Move(models.Model):
    game = models.ForeignKey(GameState, on_delete=models.CASCADE, related_name="moves")
    color = models.CharField(max_length=1, choices=[("B", "Black"), ("W", "White")])
    coordinate = models.CharField(max_length=5)
    move_number = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.color} {self.coordinate} (move {self.move_number})"


class ChatMessage(models.Model):
    game = models.ForeignKey(GameState, on_delete=models.CASCADE, related_name="chat_messages")
    role = models.CharField(max_length=20, choices=[("user", "User"), ("assistant", "Bot")])
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."
