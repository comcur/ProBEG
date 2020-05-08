# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib import admin

# Register your models here.

import models

admin.site.register(models.Parameter)
admin.site.register(models.Method)

admin.site.register(models.Primary)
admin.site.register(models.Group)

admin.site.register(models.Series_overall)
