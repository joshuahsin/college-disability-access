from django.contrib import admin

from .models import Campus, Comment, Confirmation, Feature, Submission, Venue, User

admin.site.register(User)
admin.site.register(Campus)
admin.site.register(Venue)
admin.site.register(Feature)
admin.site.register(Submission)
admin.site.register(Confirmation)
admin.site.register(Comment)
