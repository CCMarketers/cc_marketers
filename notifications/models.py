from django.db import models
from django.conf import settings


class Notification(models.Model):
    class NotifType(models.TextChoices):
        CHAT_MESSAGE        = "chat_message",        "New Message"
        SUBMISSION_APPROVED = "submission_approved", "Submission Approved"
        SUBMISSION_REJECTED = "submission_rejected", "Submission Rejected"
        NEW_SUBMISSION      = "new_submission",      "New Submission"
        WALLET_CREDIT       = "wallet_credit",       "Wallet Credited"
        WALLET_WITHDRAWAL   = "wallet_withdrawal",   "Withdrawal Update"
        REFERRAL_SIGNUP     = "referral_signup",     "New Referral"

    # Icons mapped per type — consumed by templates / JS
    ICON_MAP = {
        "chat_message":        "💬",
        "submission_approved": "✅",
        "submission_rejected": "❌",
        "new_submission":      "📋",
        "wallet_credit":       "💰",
        "wallet_withdrawal":   "🏦",
        "referral_signup":     "👥",
    }

    recipient   = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    notif_type  = models.CharField(max_length=30, choices=NotifType.choices)
    title       = models.CharField(max_length=120)
    message     = models.TextField()
    link        = models.CharField(max_length=300, blank=True)  # URL to jump to
    is_read     = models.BooleanField(default=False, db_index=True)
    created_at  = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "is_read"]),
        ]

    def __str__(self):
        return f"[{self.notif_type}] → {self.recipient} | {self.title}"

    @property
    def icon(self):
        return self.ICON_MAP.get(self.notif_type, "🔔")

    def to_dict(self):
        """Serialise for WebSocket / JSON responses."""
        return {
            "id":         self.id,
            "type":       self.notif_type,
            "icon":       self.icon,
            "title":      self.title,
            "message":    self.message,
            "link":       self.link,
            "is_read":    self.is_read,
            "created_at": self.created_at.isoformat(),
        }