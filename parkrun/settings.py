# -*- coding: utf-8 -*-
"""
Django settings for parkrun project.

Generated by 'django-admin startproject' using Django 1.9.5.

For more information on this file, see
https://docs.djangoproject.com/en/1.9/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.9/ref/settings/
"""

import os
import re
import private_settings

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.9/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = private_settings.SECRET_KEY

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False
ADMINS = [('Alexey Chernov', 'alexey.chernov@gmail.com'), ('Vladimir Postnikov', 'vp111@yandex.ru')]
MANAGERS = [('Alexey Chernov', 'alexey.chernov@gmail.com'), ('Vladimir Postnikov', 'vp111@yandex.ru')]
SERVER_EMAIL = 'errors@probeg.org'

ALLOWED_HOSTS = ['probeg.org', 'base.probeg.org']


# Application definition

INSTALLED_APPS = [
	'results.apps.ResultsConfig',
	'starrating.apps.StarratingConfig',
	'probeg_auth.apps.ProbegAuthConfig',
	'editor.apps.EditorConfig',
	'django.contrib.admin',
	'django.contrib.auth',
	'django.contrib.contenttypes',
	'django.contrib.sessions',
	'django.contrib.messages',
	'django.contrib.staticfiles',
	'django.contrib.humanize',
	'social_django',
	'menu',
	'tinymce',
	'django_tables2',
]

MIDDLEWARE = [
	'django.middleware.common.BrokenLinkEmailsMiddleware',
	'django.middleware.security.SecurityMiddleware',
	'django.contrib.sessions.middleware.SessionMiddleware',
	'django.middleware.common.CommonMiddleware',
	'django.middleware.csrf.CsrfViewMiddleware',
	'django.contrib.auth.middleware.AuthenticationMiddleware',
	'django.contrib.auth.middleware.SessionAuthenticationMiddleware',
	'django.contrib.messages.middleware.MessageMiddleware',
	'django.middleware.clickjacking.XFrameOptionsMiddleware',
	'social_django.middleware.SocialAuthExceptionMiddleware',
]

SOCIAL_AUTH_PIPELINE = (
	'social_core.pipeline.social_auth.social_details',
	'social_core.pipeline.social_auth.social_uid',
	'social_core.pipeline.social_auth.auth_allowed',
	'social_core.pipeline.social_auth.social_user',
	'social_core.pipeline.user.get_username',
	'social_core.pipeline.social_auth.associate_by_email',
	'social_core.pipeline.user.create_user',
	'social_core.pipeline.social_auth.associate_user',
	'social_core.pipeline.social_auth.load_extra_data',
	'social_core.pipeline.user.user_details',
)

ROOT_URLCONF = 'parkrun.urls'

TEMPLATES = [
	{
		'BACKEND': 'django.template.backends.django.DjangoTemplates',
		'DIRS': [],
		'APP_DIRS': True,
		'OPTIONS': {
			'context_processors': [
				'django.template.context_processors.debug',
				'django.template.context_processors.request',
				'django.contrib.auth.context_processors.auth',
				'django.contrib.messages.context_processors.messages',
				'django.contrib.auth.context_processors.auth',
				# 'django.core.context_processors.debug',
				# 'django.core.context_processors.i18n',
				# 'django.core.context_processors.media',
				# 'django.core.context_processors.static',
				# 'django.core.context_processors.tz',
				# 'django.core.context_processors.request', # for django-simple-menu

				# 'social.apps.django_app.context_processors.backends',
				# 'social.apps.django_app.context_processors.login_redirect',
				
				'social_django.context_processors.backends',
				'social_django.context_processors.login_redirect',
			],
		},
	},
]

WSGI_APPLICATION = 'parkrun.wsgi.application'


# Database
# https://docs.djangoproject.com/en/1.9/ref/settings/#databases

DATABASES = {
	'default': {
		'ENGINE': 'django.db.backends.mysql',
		'HOST': '127.0.0.1',
		'NAME': 'probegorg',
		'USER': private_settings.DB_USER,
		'PASSWORD': private_settings.DB_PASSWORD,
		'OPTIONS': {
			 "init_command": "SET foreign_key_checks = 0;",
		},
	}
}


# Password validation
# https://docs.djangoproject.com/en/1.9/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
	{
		'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
	},
	{
		'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
		'OPTIONS': {
			'min_length': 6,
		}
	},
	{
		'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
	},
	{
		'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
	},
]


# Internationalization
# https://docs.djangoproject.com/en/1.9/topics/i18n/

LANGUAGE_CODE = 'ru-RU'

TIME_ZONE = 'Europe/Moscow'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.9/howto/static-files/

MEDIA_ROOT = '/var/www/vhosts/probeg.org/httpdocs/'
MEDIA_URL = 'http://probeg.org/'
STATIC_ROOT = '/var/www/vhosts/probeg.org/httpdocs/dj_static/'
STATIC_URL = 'https://probeg.org/dj_static/'

DATA_UPLOAD_MAX_NUMBER_FIELDS = None

LOGIN_URL = 'probeg_auth:login'
LOGIN_REDIRECT_URL = 'results:home'
LOGOUT_REDIRECT_URL = 'probeg_auth:login'

AUTHENTICATION_BACKENDS = (
	# 'social.backends.google.GoogleOAuth2',
	# 'social.backends.odnoklassniki.OdnoklassnikiOAuth2',

	# 'social.backends.facebook.FacebookOAuth2',
	# 'social.backends.twitter.TwitterOAuth',
	# 'social.backends.vk.VKOAuth2',

	'social_core.backends.facebook.FacebookOAuth2',
	'social_core.backends.twitter.TwitterOAuth',
	'social_core.backends.vk.VKOAuth2',

	'django.contrib.auth.backends.ModelBackend',
)


SOCIAL_AUTH_LOGIN_URL = '/'
SOCIAL_AUTH_LOGIN_ERROR_URL = '/' # '/login-error/'
SOCIAL_AUTH_USER_MODEL = 'auth.User'
SOCIAL_AUTH_UID_LENGTH = 223
SOCIAL_AUTH_USERNAME_IS_FULL_EMAIL = True
SOCIAL_AUTH_LOGIN_REDIRECT_URL = '/'
SOCIAL_AUTH_NEW_USER_REDIRECT_URL = '/details/'

SOCIAL_AUTH_FACEBOOK_KEY = private_settings.SOCIAL_AUTH_FACEBOOK_KEY
SOCIAL_AUTH_FACEBOOK_SECRET = private_settings.SOCIAL_AUTH_FACEBOOK_SECRET
SOCIAL_AUTH_FACEBOOK_SCOPE = ['email']
SOCIAL_AUTH_FACEBOOK_PROFILE_EXTRA_PARAMS = {'fields': 'id,name,email',}

# For Rundata Standalone
SOCIAL_AUTH_VK_OAUTH2_KEY = private_settings.SOCIAL_AUTH_VK_OAUTH2_KEY
SOCIAL_AUTH_VK_OAUTH2_SECRET = private_settings.SOCIAL_AUTH_VK_OAUTH2_SECRET
SOCIAL_AUTH_VK_OAUTH2_SCOPE = ['email']

SOCIAL_AUTH_TWITTER_KEY = private_settings.SOCIAL_AUTH_TWITTER_KEY
SOCIAL_AUTH_TWITTER_SECRET = private_settings.SOCIAL_AUTH_TWITTER_SECRET

EMAIL_USE_TLS = True
EMAIL_HOST = 'probeg.org'
EMAIL_PORT = 25
EMAIL_HOST_USER = 'base@probeg.org'
EMAIL_HOST_PASSWORD = private_settings.EMAIL_HOST_PASSWORD
DEFAULT_FROM_EMAIL = u'Портал для любителей бега «ПроБЕГ» <info@probeg.org>'

TINYMCE_JS_URL = os.path.join(STATIC_URL, "tinymce/tinymce.min.js")
TINYMCE_JS_ROOT = os.path.join(STATIC_ROOT, "tinymce")
TINYMCE_DEFAULT_CONFIG = {
	'theme': 'modern',
	'plugins': 'link code paste image',
	'paste_as_text': True,
	'convert_urls': False,
}

IGNORABLE_404_URLS = [
	re.compile(r'^/favicon\.ico$'),
	re.compile(r'^/robots\.txt$'),
	re.compile(r'^/wp'),
	re.compile(r'^/runner/'),
	re.compile(r'^/result/'),
	re.compile(r'^/sitemap.xml'),
	re.compile(r'^/event/'),
	re.compile(r'^/series/'),
	re.compile(r'^/klb/person/'),
	re.compile(r'^/editor/runner/'),
	re.compile(r'^/editor/klb/person/'),
	re.compile(r'^/news/'),
	re.compile(r'^/index\.php'),
	re.compile(r'^/klbklb'),
	re.compile(r'/index\.php$'),
]

LOGGING = {
	'version': 1,
	'disable_existing_loggers': False,
	'formatters': {
		'simple': {
			'format': '%(asctime)s %(name)s:%(levelname)s %(pathname)s.%(lineno)d %(message)s',
			'datefmt': '%y%m%d %H:%M:%S',
		},
		'simple2': {
			'format': '%(asctime)s %(name)s:%(levelname)s %(message)s',
			'datefmt': '%y%m%d %H:%M:%S',
		},
	},
	'handlers': {
		'file_root': {
			'level': 'DEBUG',
			'class': 'logging.FileHandler',
			'filename': BASE_DIR + '/logs/other.log',
			'formatter': 'simple',
		},
		'file_django_web': {
			'level': 'DEBUG',
			'class': 'logging.FileHandler',
			'filename': BASE_DIR + '/logs/django_web.log',
			'formatter': 'simple',
		},
		'file_django_request': {
			'level': 'DEBUG',
			'class': 'logging.FileHandler',
			'filename': BASE_DIR + '/logs/django.request.log',
			'formatter': 'simple',
		},
		'file_klb_report': {
			'level': 'DEBUG',
			'class': 'logging.FileHandler',
			'filename': BASE_DIR + '/logs/klb_report.log',
			'formatter': 'simple',
		},
		'file_db_structure': {
			'level': 'DEBUG',
			'class': 'logging.FileHandler',
			'filename': BASE_DIR + '/logs/db_structure.log',
			'formatter': 'simple',
		},
		'file_vk': {
			'level': 'DEBUG',
			'class': 'logging.FileHandler',
			'filename': BASE_DIR + '/logs/vk.log',
			'formatter': 'simple',
		},
		'file_dbchecks': {
			'level': 'DEBUG',
			'class': 'logging.FileHandler',
			'filename': BASE_DIR + '/logs/dbchecks.log',
			'formatter': 'simple2',
		},
		'file_sr_dbchecks': {
			'level': 'DEBUG',
			'class': 'logging.FileHandler',
			'filename': BASE_DIR + '/logs/sr_dbchecks.log',
			'formatter': 'simple2',
		},
		'file_sr_views': {
			'level': 'DEBUG',
			'class': 'logging.FileHandler',
			'filename': BASE_DIR + '/logs/sr_views.log',
			'formatter': 'simple',
		},
		'file_sr_updater': {
			'level': 'DEBUG',
			'class': 'logging.FileHandler',
			'filename': BASE_DIR + '/logs/sr_updater.log',
			'formatter': 'simple2',
		},
		'file_structure_modification': {
			'level': 'DEBUG',
			'class': 'logging.FileHandler',
			'filename': BASE_DIR + '/logs/modifications_of_structure.log',
			'formatter': 'simple',
		},
		'file_new_code': {
			'level': 'DEBUG',
			'class': 'logging.FileHandler',
			'filename': BASE_DIR + '/logs/new_code.log',
			'formatter': 'simple',
		},
	},
	'loggers': {
		'': {
			'handlers' : ['file_root'],
			'level': 'INFO',
			'propagate': False
		},
		'django': {
			'handlers': ['file_django_web'],
			'level': 'INFO',
			'propagate': False
		},
		'django.request': {
			'handlers': ['file_django_request'],
			'level': 'INFO',
			'propagate': False
		},
		'editor.views.views_klb_report': {
			'handlers' : ['file_klb_report'],
			'level': 'INFO',
			'propagate': False
		},
		'editor.views.views_db_structure': {
			'handlers' : ['file_db_structure'],
			'level': 'INFO',
			'propagate': False
		},
		'vk': {
			'handlers' : ['file_vk'],
			'level': 'INFO',
			'propagate': False
		},
		'dbchecks': {
			'handlers' : ['file_dbchecks'],
			'level': 'DEBUG',
			'propagate': False
		},
		'sr_dbchecks': {
			'handlers' : ['file_sr_dbchecks'],
			'level': 'INFO',
			'propagate': False
		},
		'sr_views': {
			'handlers' : ['file_sr_views'],
			'level': 'DEBUG',
			'propagate': False
		},
		'sr_updater': {
			'handlers' : ['file_sr_updater'],
			'level': 'INFO',
			'propagate': False
		},
		'structure_modification': {
			'handlers' : ['file_structure_modification'],
			'level': 'DEBUG',
			'propagate': False
		},
		'new_code': {
			'handlers' : ['file_new_code'],
			'level': 'DEBUG',
			'propagate': False
		},
	},
}

X_FRAME_OPTIONS = 'ALLOW-FROM https://webvisor.com/'
# X_FRAME_OPTIONS = 'ALLOWALL' # Temprorary for installing SSL

CACHES = {
	'default': {
		'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
		'LOCATION': '/home/admin/parkrun/cache',
		'TIMEOUT': 60 * 60 * 4,
		'OPTIONS': {
			'MAX_ENTRIES': 1000
		}
	}
}

from local_settings import *
