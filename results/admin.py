from django.contrib import admin

import models

admin.site.register(models.Country)
admin.site.register(models.District)
admin.site.register(models.Region)
admin.site.register(models.City)

admin.site.register(models.Series)
admin.site.register(models.Event)
admin.site.register(models.Race)
admin.site.register(models.Distance)

admin.site.register(models.Result)
admin.site.register(models.Klb_person)
admin.site.register(models.Klb_participant)
admin.site.register(models.Klb_result)

admin.site.register(models.User_profile)
