# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand

from editor.views.views_mail import send_newsletters, send_to_klb_participants

class Command(BaseCommand):
	help = "Sends newsletter to all users who didn't ask to stop"

	def add_arguments(self, parser):
		parser.add_argument('filename')
		parser.add_argument('title')
		parser.add_argument('--test', action='store_true')

	def handle(self, *args, **options):
		# print 'Filename:', options['filename']
		# print options['title']
		# print u'Title: "{}"'.format(options['title'].decode().encode('utf-8'))
		send_newsletters(filename=options['filename'], title=options['title'], test_mode=options['test'])
		# send_to_klb_participants(filename=options['filename'], title=options['title'])
