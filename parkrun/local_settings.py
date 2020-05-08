# -*- coding: utf-8 -*-

import private_settings
import settings
import socket
import os

this_host_name = socket.gethostname()
current_dir = os.getcwd()

BASE_DIR = settings.BASE_DIR

if this_host_name == 'probeg.org':  # this is the production server
	pass
elif current_dir == '/var/django/parkrun-igor':
	INSTALLED_APPS = settings.INSTALLED_APPS + [
		'django_extensions',
		'debug_toolbar',
	]

	MIDDLEWARE_CLASSES = [
		'debug_toolbar.middleware.DebugToolbarMiddleware'
	] + settings.MIDDLEWARE_CLASSES
# https://django-debug-toolbar.readthedocs.io/en/latest/installation.html :
# The order of MIDDLEWARE and MIDDLEWARE_CLASSES is important.
# You should include the Debug Toolbar middleware as early as possible in the list. 
# However, it must come after any other middleware that encodes the response’s content,
# such as GZipMiddleware.

	# DISABLE_PANELS = {}  # https://django-debug-toolbar.readthedocs.io/en/latest/panels.html#redirects


	INTERNAL_IPS = ['127.0.0.1']

	DEBUG = True
	ALLOWED_HOSTS = ['igor-base.probeg.org', '127.0.0.1']
	EMAIL_HOST = 'localhost'

	MEDIA_ROOT = '/var/www/vhosts/probeg.org-igor/httpdocs/'
	MEDIA_URL = 'https://probeg.org/'
	STATIC_ROOT = '/var/django/dj_stati'
	STATIC_URL = '/static/'

	DATABASES = {
		'default': {
			'ENGINE': 'django.db.backends.mysql',
			'HOST': '127.0.0.1',
			'NAME': 'probegorg_ig',
			'USER': private_settings.DB_USER,
			'PASSWORD': private_settings.DB_PASSWORD,
			'OPTIONS': {
				 "init_command": "SET foreign_key_checks = 1;",
			},
		}
	}

	CACHES = {
	'default': {
		'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
		}
	}

elif current_dir == '/home/admin/parkrun':
	INSTALLED_APPS = settings.INSTALLED_APPS + [
		'django_extensions',
		'debug_toolbar',
	]
	MIDDLEWARE_CLASSES = [
		'debug_toolbar.middleware.DebugToolbarMiddleware'
	] + settings.MIDDLEWARE_CLASSES
	INTERNAL_IPS = ['127.0.0.1']

	DEBUG = True
	ALLOWED_HOSTS = ['test-base.probeg.org', '127.0.0.1']
	EMAIL_HOST = 'localhost'

	MEDIA_ROOT = '/var/www/vhosts/probeg.org-igor/httpdocs/'
	MEDIA_URL = 'https://probeg.org/'
	STATIC_ROOT = '/var/www/vhosts/probeg.org-igor/httpdocs/dj_static/'
	STATIC_URL = '/static/'

	DATABASES = {
		'default': {
			'ENGINE': 'django.db.backends.mysql',
			'HOST': '127.0.0.1',
			'NAME': 'probegorg_ig',
			'USER': private_settings.DB_USER,
			'PASSWORD': private_settings.DB_PASSWORD,
			'OPTIONS': {
				 "init_command": "SET foreign_key_checks = 1;",
			},
		}
	}

	CACHES = {
	'default': {
		'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
		}
	}

else:
	assert False, this_host_name + ':' + current_dir
