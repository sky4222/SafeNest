"""Alarm rule preserved from your uploaded monitor; thresholds need validation."""
class AlarmPolicy:
    """Prototype decision rule. Tune thresholds with recorded validation data."""

    def __init__(self, scream_threshold=0.70, impact_threshold=0.70,
                 relation_seconds=15, cooldown_seconds=30):
        self.scream_threshold = float(scream_threshold)
        self.impact_threshold = float(impact_threshold)
        self.relation_seconds = float(relation_seconds)
        self.cooldown_seconds = float(cooldown_seconds)
        self.last_impact = None
        self.last_alarm = None
        self.scream_streak = 0

    def evaluate(self, scores, now):
        impact = float(scores[1])
        scream = float(scores[2])
        if impact >= self.impact_threshold:
            self.last_impact = now
        self.scream_streak = self.scream_streak + 1 if scream >= self.scream_threshold else 0
        reason = None
        if scream >= self.scream_threshold and self.last_impact is not None:
            if now - self.last_impact <= self.relation_seconds:
                reason = 'scream_after_recent_impact'
        if reason is None and self.scream_streak >= 2:
            reason = 'two_consecutive_high_scream_scores'
        if reason is not None and self.last_alarm is not None:
            if now - self.last_alarm < self.cooldown_seconds:
                reason = None
        if reason is not None:
            self.last_alarm = now
        return reason


