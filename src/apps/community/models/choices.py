from django.db import models


class Visibility(models.TextChoices):
    PUBLIC = "public", "Public"
    FOLLOWERS = "followers", "Followers"
    PRIVATE = "private", "Private"


class FeedPolicy(models.TextChoices):
    HIDDEN = "hidden", "Hidden"
    NORMAL = "normal", "Normal"
    FEATURED = "featured", "Featured"
