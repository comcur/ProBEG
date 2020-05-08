# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand
from editor.views.views_klb_report import generate_klb_reports

class Command(BaseCommand):
	def handle(self, *args, **options):
		generate_klb_reports()
		# generate_klb_reports(roles=('client', ))
