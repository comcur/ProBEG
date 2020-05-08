# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division
from django.core.validators import validate_email, MaxValueValidator, MinValueValidator
from django.core.mail import EmailMultiAlternatives, send_mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.db.models.signals import pre_delete
from django.core.files.base import ContentFile
from django.core.urlresolvers import reverse
from django.utils.encoding import force_text
from django.db.models.query import Prefetch
from django.contrib.auth.models import User
from django.forms import SplitDateTimeField
from django.db.models import Q, F, Max
from django.dispatch import receiver
from django.contrib import messages
from django.utils import timezone
from django.conf import settings
from cStringIO import StringIO
from django.db import models
from itertools import chain
from PIL import Image

from collections import OrderedDict
from calendar import monthrange
import datetime
import bleach
import time
import os
import io
import re

import results_util
from transliteration_v5 import transliterate
import models_klb

import starrating.aggr.race_deletion

ADMIN_ID = 1

INFO_MAIL = 'info@probeg.org'
KLB_MAIL = 'klb@probeg.org'
TOP_MAIL = 'top@probeg.org'
SITE_NAME = u'Портал для любителей бега «ПроБЕГ»'
INFO_MAIL_HEADER = u'{} <{}>'.format(SITE_NAME, INFO_MAIL) # Letters with this header will NOT reach Asana when sent to info@
ROBOT_MAIL_HEADER = u'Робот сайта ПроБЕГ <base@probeg.org>' # It shouldn't be info@ for these letters to reach Asana
SITE_URL = 'https://base.probeg.org'
SITE_URL_OLD = 'https://probeg.org'

LOG_FILE_SOCIAL = results_util.LOG_DIR + '/social_networks.log'
LOG_FILE_KLB_REPORTS = results_util.LOG_DIR + '/klb_reports.log'

XLSX_FILES_DIR = settings.MEDIA_ROOT + 'dj_media/xlsx_reports'

try:
	USER_ADMIN = User.objects.get(pk=ADMIN_ID)
	USER_ROBOT_CONNECTOR = User.objects.get(pk=4)
	USER_SKOBLINA = User.objects.get(pk=24)
except:
	USER_ADMIN = None
	USER_ROBOT_CONNECTOR = None
	USER_SKOBLINA = None

SERIES_WITH_ALLOWED_EVENTS_WITHOUT_CITY = [515, 1331, 2574, ] # Like 'Побегай 1-го января' or 'КЛБМатч'
PARSEK_CLUB_ID = 94
ROSTOV_RUNNING_CLUB_ID = 128
CLUB_ID_FOR_ADMINS = ROSTOV_RUNNING_CLUB_ID
SAMPLE_EDITOR_ID = 53 # http://base.probeg.org/user/53/

DEFAULT_ORDER_FOR_DB_STRUCTURE = 'zzz'

DATE_MIN = datetime.date(1900, 1, 1)
DATE_MAX = datetime.date(2100, 12, 31)

def int_safe(s):
	try:
		res = int(s)
	except:
		res = 0
	return res

def float_safe(s):
	try:
		res = float(s)
	except:
		res = 0.
	return res

months = [''] * 13
months[1] = u'января'
months[2] = u'февраля'
months[3] = u'марта'
months[4] = u'апреля'
months[5] = u'мая'
months[6] = u'июня'
months[7] = u'июля'
months[8] = u'августа'
months[9] = u'сентября'
months[10] = u'октября'
months[11] = u'ноября'
months[12] = u'декабря'

CUR_KLB_YEAR = 2020
NEXT_KLB_YEAR = 0
NEXT_KLB_YEAR_AVAILABLE_FOR_ALL = False
KLB_DIPLOM_YEAR = 2019
def is_active_klb_year(year, is_admin=False):
	# if is_admin and (year == ACTIVE_KLB_YEAR_FOR_ADMIN):
	# 	return True
	# return (year > 0) and (year in [CUR_KLB_YEAR, NEXT_KLB_YEAR])
	if year == CUR_KLB_YEAR:
		return True
	return year and (year == NEXT_KLB_YEAR) and (NEXT_KLB_YEAR_AVAILABLE_FOR_ALL or is_admin)

# There must be fields n_starts_XXXX, total_length_XXXX, total_time_XXXX in Runner table!
CUR_RUNNERS_ORDERING_YEAR = 2020

MAX_URL_LENGTH = 600
DAYS_IN_DEFAULT_CALENDAR = 31
LAST_PROTOCOLS_EVENT_NUMBER = 10
NADYA_CALENDAR_YEAR_START = 2018
NADYA_CALENDAR_YEAR_END = 2020
MIN_RUNNER_AGE = 0
MAX_RUNNER_AGE = 120
FIRST_YEAR_FOR_STAT_UPDATE = 2010
FIRST_YEAR_WITH_KLBMATCH_STAT_BY_REGIONS = 2015

VK_POSSIBLE_PREFIXES = ('http://vk.com', 'http://www.vk.com', 'https://vk.com', 'https://www.vk.com', )
FB_POSSIBLE_PREFIXES = ('http://facebook.com', 'http://www.facebook.com', 'https://facebook.com', 'https://www.facebook.com', )
IN_POSSIBLE_PREFIXES = ('http://instagram.com', 'http://www.instagram.com', 'https://instagram.com', 'https://www.instagram.com', )

def date2str(mydate, with_nbsp=True, short_format=False):
	if short_format:
		return mydate.strftime('%d.%m.%Y')
	else:
		return "{}{}{} {}".format(mydate.day, '&nbsp;' if with_nbsp else ' ', months[mydate.month], mydate.year)
def dates2str(start_date, finish_date):
	if not finish_date:
		return date2str(start_date)
	if start_date.year == finish_date.year:
		if start_date.month == finish_date.month:
			return "{}–{}&nbsp;{} {}".format(
				start_date.day, finish_date.day, months[start_date.month], start_date.year)
		else:
			return "{}&nbsp;{}&nbsp;– {}&nbsp;{} {}".format(
				start_date.day, months[start_date.month], finish_date.day, months[finish_date.month], start_date.year)
	else:
		return "{}&nbsp;– {}".format(
				date2str(start_date), date2str(finish_date))

def secs2time(value, fill_hours=True):
	seconds = value % 60
	value //= 60
	minutes = value % 60
	value //= 60
	hours = value
	return (unicode(hours).zfill(2) if fill_hours else unicode(hours)) + ":" + unicode(minutes).zfill(2) + ":" + unicode(seconds).zfill(2)

def centisecs2time(value, round_hundredths=False, show_zero_hundredths=False):
	hundredths = value % 100
	value //= 100
	if hundredths and round_hundredths:
		hundredths = 0
		value += 1
	seconds = value % 60
	value //= 60
	minutes = value % 60
	value //= 60
	hours = value
	res = unicode(hours).zfill(1) + ":" + unicode(minutes).zfill(2) + ":" + unicode(seconds).zfill(2)
	if hundredths or show_zero_hundredths:
		res += "," + unicode(hundredths).zfill(2)
	return res
def tuple2centiseconds(hours, minutes, seconds, centiseconds = 0):
	return ((hours * 60 + minutes) * 60 + seconds) * 100 + centiseconds
def string2centiseconds(result):
	res = re.match(r'^(\d{1,3}):(\d{1,2}):(\d{1,2})$', result) # Hours:minutes:seconds
	if res:
		hours = int(res.group(1))
		minutes = int(res.group(2))
		seconds = int(res.group(3))
		if (minutes < 60) and (seconds < 60):
			return tuple2centiseconds(hours, minutes, seconds)
	res = re.match(r'^(\d{1,2}):(\d{1,2})$', result) # minutes:seconds
	if res:
		minutes = int(res.group(1))
		seconds = int(res.group(2))
		if (minutes < 60) and (seconds < 60):
			return tuple2centiseconds(0, minutes, seconds)
	res = re.match(r'^(\d{1,2}):(\d{1,2}):(\d{1,2})[\.,](\d{1,2})$', result) # Hours:minutes:seconds[.,]centiseconds
	if res:
		hours = int(res.group(1))
		minutes = int(res.group(2))
		seconds = int(res.group(3))
		centiseconds = int(res.group(4))
		if len(res.group(4)) == 1:
			centiseconds *= 10
		if (minutes < 60) and (seconds < 60):
			return tuple2centiseconds(hours, minutes, seconds, centiseconds)
	res = re.match(r'^(\d{1,2})[\.:,](\d{1,2})[\.,](\d{1,2})$', result) # minutes[:.,]seconds[.,]centiseconds
	if res:
		minutes = int(res.group(1))
		seconds = int(res.group(2))
		centiseconds = int(res.group(3))
		if len(res.group(3)) == 1:
			centiseconds *= 10
		if (minutes < 60) and (seconds < 60):
			return tuple2centiseconds(0, minutes, seconds, centiseconds)
	res = re.match(r'^(\d{1,2})[\.,](\d{1,2})$', result) # seconds[.,]centiseconds
	if res:
		seconds = int(res.group(1))
		centiseconds = int(res.group(2))
		if len(res.group(2)) == 1:
			centiseconds *= 10
		if seconds < 60:
			return tuple2centiseconds(0, 0, seconds, centiseconds)
	return 0

def meters2string(length, with_nbsp=True):
	if length:
		return u'{}{}м'.format(length, u'&nbsp;' if with_nbsp else u' ')
	return ''

def total_length2string(length, with_nbsp=True):
	if length:
		res = []
		meters = length % 1000
		kilometers = length // 1000
		if kilometers:
			res.append(u'{}{}км'.format(kilometers, u'&nbsp;' if with_nbsp else u' '))
		if meters:
			res.append(u'{}{}м'.format(meters, u'&nbsp;' if with_nbsp else u' '))
		return ' '.join(res)
	return ''
def total_time2string(centiseconds, with_br=True):
	if centiseconds:
		value = centiseconds
		hundredths = value % 100
		value //= 100
		seconds = value % 60
		value //= 60
		minutes = value % 60
		value //= 60
		hours = value % 24
		days = value // 24
		time = unicode(hours).zfill(2) + ":" + unicode(minutes).zfill(2) + ":" + unicode(seconds).zfill(2)
		if hundredths:
			time += "," + unicode(hundredths).zfill(2)
		res = []
		if days:
			res.append(u'{} {}'.format(days, u'сутки' if (days == 1) else u'суток'))
		res.append(time)
		return (u'<br/>' if with_br else u' ').join(res)
	return ''

GENDER_UNKNOWN = 0
GENDER_FEMALE = 1
GENDER_MALE = 2
GENDER_CHOICES = (
	(GENDER_UNKNOWN, u'Не указан'),
	(GENDER_FEMALE, u'Женский'),
	(GENDER_MALE, u'Мужской'),
)
def string2gender(s):
	if not s:
		return GENDER_UNKNOWN
	if not isinstance(s, basestring):
		return GENDER_UNKNOWN
	letter = s[0].upper()
	if letter in [u'М', u'M', u'Ч', u'Ю']:
		return GENDER_MALE
	if letter in [u'Ж', u'F', u'W', u'Д', u'K', u'N']:
		return GENDER_FEMALE
	if u'ЮНИОРКИ' in s.upper():
		return GENDER_FEMALE
	return GENDER_UNKNOWN

def is_admin(user):
	return user.groups.filter(name="admins").exists() if user else False

def replace_symbols(s):
	res = s
	for s_old, s_new in [(u' - ', u' — '), (u'<<', u'«'), (u'>>', u'»'), (u'&lt;&lt;', u'«'), (u'&gt;&gt;', u'»'), (u' ,', u','), (u' .', u'.')]:
		res = res.replace(s_old, s_new)
	return res

MAX_EMAIL_LENGTH = 100
def is_email_correct(email):
	try:
		validate_email(email)
		return (len(email) <= MAX_EMAIL_LENGTH)
	except:
		return False

MAX_PHONE_NUMBER_LENGTH = 50
MAX_POSTAL_ADDRESS_LENGTH = 200
def is_phone_number_correct(phone):
	if not isinstance(phone, basestring):
		return False
	if re.match(ur'^[\+8][0123456789 -–—\(\)]{10,19}$', phone) is None:
		return False
	return (10 <= sum(c.isdigit() for c in phone) <= 15)

def get_runner_ids_for_user(user): # Returns the set with all runners' id that belong to clubs runned by user
	club_ids = set(user.club_editor_set.values_list('club_id', flat=True))
	return set(Club_member.objects.filter(club_id__in=club_ids).values_list('runner_id', flat=True))

def make_thumb(image_field, thumb_field, max_width, max_height):
	if not image_field:
		if thumb_field:
			thumb_field.delete()
		return True
	avatar_ext = os.path.splitext(image_field.path)[1][1:].lower() # image_field.file.content_type
	if avatar_ext in ['jpg', 'jpeg']:
		DJANGO_TYPE = 'image/jpeg'
		PIL_TYPE = 'jpeg'
		FILE_EXTENSION = 'jpg'
	elif avatar_ext == 'png':
		DJANGO_TYPE = 'image/png'
		PIL_TYPE = 'png'
		FILE_EXTENSION = 'png'
	elif avatar_ext == 'gif':
		DJANGO_TYPE = 'image/gif'
		PIL_TYPE = 'gif'
		FILE_EXTENSION = 'gif'
	else:
		return False
	image = Image.open(StringIO(image_field.read()))
	image.thumbnail((max_width, max_height), Image.ANTIALIAS)
	temp_handle = StringIO()
	image.save(temp_handle, PIL_TYPE)
	temp_handle.seek(0)

	suf = SimpleUploadedFile(os.path.split(image_field.name)[-1], temp_handle.read(), content_type=DJANGO_TYPE)
	thumb_field.save('{}_thumb.{}'.format(os.path.splitext(suf.name)[0], FILE_EXTENSION), suf, save=True)
	return True

def write_log(s, debug=False):
	try:
		with io.open(results_util.LOG_FILE_ACTIONS, "a", encoding="utf8") as f:
			f.write(s + "\n")
	except:
		print 'Could not log the string "{}"!'.format(s)
	if debug:
		print s
	return s

def send_panic_email(subject, body, to_all=False):
	send_mail(
		subject,
		u'{}.\n\n Your robot'.format(body),
		ROBOT_MAIL_HEADER,
		['info@probeg.org'] if to_all else ['alexey.chernov@gmail.com'],
		fail_silently=False,
	)

def result_is_too_large(length, centiseconds):
	return ((centiseconds % 6000) == 0) \
		and (
			((length <= 10000) and (centiseconds >= 5*3600*100))
			or ((length <= 3000) and (centiseconds >= 2*3600*100))
			or ((length <= 1000) and (centiseconds >= 1*3600*100))
		)

class CustomDateTimeField(models.DateTimeField):
	def formfield(self, **kwargs):
		defaults = {'form_class': SplitDateTimeField,
					'input_date_formats': ['%d.%m.%Y']}
		defaults.update(kwargs)
		return super(CustomDateTimeField, self).formfield(**defaults)

DEFAULT_COUNTRY_SORT_VALUE = 10
class Country(models.Model):
	id = models.CharField(verbose_name=u'id (домен первого уровня)', max_length=3, primary_key=True)
	name = models.CharField(verbose_name=u'Название', max_length=100, db_index=True)
	nameEn = models.CharField(verbose_name=u'Название (англ.)', max_length=100, db_index=True)
	prep_case = models.CharField(verbose_name=u'Название в предложном падеже', max_length=100)
	value = models.SmallIntegerField(verbose_name=u'Приоритет при сортировке', default=DEFAULT_COUNTRY_SORT_VALUE)

	# Less than 10 if all the regions of country are in Region table.
	# Now Russia has 1, Ukraine and Belarus have 2.
	# If 1, then every city must have region.
	# If 0, then region of every city is special region, unique for each such country
	has_regions = models.SmallIntegerField(verbose_name=u'Есть ли регионы страны в БД', default=0)
	class Meta:
		db_table = "dj_country"
		index_together = [
			["value", "name"],
			["value", "nameEn"],
		]
	def __unicode__(self):
		return self.name

class District(models.Model):
	country = models.ForeignKey(Country, verbose_name=u'Страна', default="RU", on_delete=models.PROTECT)
	name = models.CharField(verbose_name=u'Краткое название', max_length=100, db_index=True)
	name_full = models.CharField(verbose_name=u'Полное название', max_length=100, default="")
	nameEn = models.CharField(verbose_name=u'Название (англ.)', max_length=100, default="")
	class Meta:
		db_table = "dj_district"
		verbose_name = u'Федеральный округ в России'
		index_together = [
			["country", "name"],
			["country", "nameEn"],
		]
	def __unicode__(self):
		return self.name

class Region(models.Model):
	country = models.ForeignKey(Country, verbose_name=u'Страна', default="RU", on_delete=models.PROTECT)
	district = models.ForeignKey(District, verbose_name=u'Федеральный округ', default=None, null=True, on_delete=models.PROTECT)
	name = models.CharField(verbose_name=u'Краткое название', max_length=100, db_index=True)
	name_full = models.CharField(verbose_name=u'Полное название', max_length=100, default="")
	nameEn = models.CharField(verbose_name=u'Название (англ.)', max_length=100, default="", db_index=True)
	active = models.BooleanField(verbose_name=u'Активен ли', default=True)
	population = models.IntegerField(verbose_name=u'Население', default=0)
	class Meta:
		db_table = "dj_region"
		index_together = [
			["country", "name"],
			["country", "nameEn"],
		]
	def __unicode__(self):
		return self.name_full

class City(models.Model):
	# country = models.ForeignKey(Country, default=None, null=True, on_delete=models.PROTECT) # Deprecated
	region = models.ForeignKey(Region, verbose_name=u'Регион (для России, Украины, Беларуси)', on_delete=models.PROTECT)
	raion = models.CharField(verbose_name=u'Район, округ, улус, повят, уезд', max_length=100, blank=True)
	city_type = models.CharField(verbose_name=u'Тип населённого пункта', max_length=100, blank=True)
	name = models.CharField(verbose_name=u'Русское название', max_length=100, db_index=True)
	nameEn = models.CharField(verbose_name=u'Название на языке оригинала или латиницей', max_length=100, db_index=True, blank=True)
	url_wiki = models.URLField(verbose_name=u'Ссылка на страницу в Википедии', max_length=200, blank=True)
	skip_region = models.BooleanField(verbose_name=u'Крупный город, не показывать регион, даже если он указан', default=False)

	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Создал город в базе', related_name='city_created_set',
		on_delete=models.SET_NULL, default=None, null=True, blank=True)
	added_time = models.DateTimeField(verbose_name=u'Время занесения в БД', auto_now_add=True)
	def clean(self):
		self.raion = self.raion.strip()
		self.city_type = self.city_type.strip()
		self.name = self.name.strip()
		self.nameEn = self.nameEn.strip()
		# raion and city_type must be both empty or both non-empty
		if (self.raion and not self.city_type) or (self.city_type and not self.raion):
			raise ValidationError(u'Район и тип населённого пункта должны быть либо оба заполнены, либо оба пусты.')
	class Meta:
		db_table = "dj_city"
		index_together = [
			["region", "name"],
			["region", "raion", "city_type", "name"],
			["region", "nameEn"],
		]
		unique_together = (("region", "raion", "name"),)
		ordering = ['name']
	def name_full(self, with_region=False, with_nbsp=True): # This adds region only when city is small, i.e. self.raion != ""
		res = ""
		if with_region and self.region.active and (self.raion or not self.skip_region):
			res += self.region.name_full + ', '
		if self.raion:
			res += self.raion + ', '
		if self.city_type:
			res += self.city_type + ('&nbsp;' if with_nbsp else ' ')
		res += self.name
		return res
	def nameWithCountry(self, writeRussia=False, with_region=True, with_nbsp=True): # By default, do not print "(Россия)"
		res = self.name_full(with_region=with_region, with_nbsp=with_nbsp)
		if (not self.region.active) and self.nameEn:
			res += " (" + self.nameEn + ")"
		if writeRussia or (self.region.country.id !="RU"):
			res = self.region.country.name + ", " + res
		return res
	# Examples:
	# Санкт-Петербург – Москва (Россия, так что страну не пишем)
	# Санкт-Петербург (Россия) – Нью-Йорк (США) (страны разные, так что пишем обе)
	# Лос-Анжелес – Нью-Йорк (США) (страна одна, пишем её только в конце)
	# Павлоград (Украина)
	# Санкт-Петербург
	def nameWithFinish(self, city_finish, with_nbsp=True):
		if city_finish:
			if self.region.country == city_finish.region.country:
				return self.name_full(with_nbsp=with_nbsp) + u" – " + city_finish.nameWithCountry(with_nbsp=with_nbsp)
			else:
				return self.nameWithCountry(writeRussia=True, with_nbsp=with_nbsp) + u" – " + city_finish.nameWithCountry(writeRussia=True, with_nbsp=with_nbsp)
		# So start=finish
		return self.nameWithCountry(with_nbsp=with_nbsp)
	def has_dependent_objects(self):
		return self.series_city_set.exists() or self.series_city_finish_set.exists() or \
			self.event_city_set.exists() or self.event_city_finish_set.exists() or self.user_profile_set.exists() or \
			self.club_set.exists() or self.klb_person_set.exists() or \
			self.city_conversion_set.exists() or self.result_set.exists() or self.runner_set.exists()
	def get_reverse_url(self, target):
		return reverse(target, kwargs={'city_id': self.id})
	def get_editor_url(self):
		return self.get_reverse_url('editor:city_details')
	def get_history_url(self):
		return self.get_reverse_url('editor:city_changes_history')
	def get_races_url(self):
		return self.get_reverse_url('results:races')
	def __unicode__(self):
		return self.name

CITY_MOSCOW_ID = 2310
CITY_SAINT_PETERSBURG_ID = 2544
REGION_MOSCOW_ID = 46
REGION_SAINT_PETERSBURG_ID = 64

class Country_conversion(models.Model):
	country = models.ForeignKey(Country, default=None, null=True, on_delete=models.PROTECT)
	country_raw = models.CharField(max_length=16, db_index=True, blank=True, unique=True)
	class Meta:
		db_table = "dj_country_conversion"
		verbose_name = u'Соответствие между написаниями стран и странами в БД. Не используется'

class Region_conversion(models.Model):
	country = models.ForeignKey(Country, default=None, null=True, on_delete=models.PROTECT)
	region = models.ForeignKey(Region, default=None, null=True, on_delete=models.PROTECT)
	country_raw = models.CharField(max_length=16, blank=True)
	district_raw = models.CharField(max_length=50, blank=True)
	region_raw = models.CharField(max_length=50, blank=True)
	class Meta:
		db_table = "dj_region_conversion"
		verbose_name = u'Соответствие между написаниями регионов и регионами в БД. Не используется'
		index_together = [
			["country_raw", "region_raw"],
		]
		unique_together = (("country_raw", "district_raw", "region_raw"),)

class City_conversion(models.Model):
	country = models.ForeignKey(Country, default=None, null=True, on_delete=models.PROTECT)
	region = models.ForeignKey(Region, default=None, null=True, on_delete=models.PROTECT)
	city = models.ForeignKey(City, default=None, null=True, on_delete=models.PROTECT)
	country_raw = models.CharField(max_length=16, blank=True)
	district_raw = models.CharField(max_length=50, blank=True)
	region_raw = models.CharField(max_length=50, blank=True)
	city_raw = models.CharField(max_length=40, blank=True)
	class Meta:
		db_table = "dj_city_conversion"
		verbose_name = u'Соответствие между написаниями городов и городами в БД. Не используется'
		index_together = [
			["region_raw", "city_raw"],
		]
		unique_together = (("country_raw", "district_raw", "region_raw", "city_raw"),)

SURFACE_DEFAULT = 0
SURFACE_HARD = 1
SURFACE_SOFT = 2
SURFACE_MOUNTAIN = 3
SURFACE_OBSTACLE = 4
SURFACE_ROAD = 5
SURFACE_STADIUM = 6
SURFACE_INDOOR = 7
SURFACE_TYPES = (
	(SURFACE_DEFAULT, u'не задано'),
	(SURFACE_ROAD, u'шоссе'),
	(SURFACE_STADIUM, u'стадион'),
	(SURFACE_INDOOR, u'манеж'),
	(SURFACE_SOFT, u'кросс или трейл'),
	(SURFACE_MOUNTAIN, u'горный бег'),
	(SURFACE_OBSTACLE, u'бег с препятствиями'),
	(SURFACE_HARD, u'стадион или шоссе'),
)
SERIES_TYPE_RUN = 0
SERIES_TYPE_DO_NOT_SHOW = 1
SERIES_TYPE_TRIATHLON = 2
SERIES_TYPES = (
	(SERIES_TYPE_RUN, u'бег'),
	(SERIES_TYPE_DO_NOT_SHOW, u'не показывать'),
	(SERIES_TYPE_TRIATHLON, u'триатлон'),
)

FAKE_ORGANIZER_ID = 2
FAKE_ORGANIZER_NAME = u'Организатор не указан'

class Series(models.Model):
	id = models.AutoField(primary_key=True, db_column='id')
	name = models.CharField(verbose_name=u'Название серии', max_length=250, blank=False, db_column='name')
	name_eng = models.CharField(verbose_name=u'Название серии латиницей, если есть', max_length=250, blank=True, db_column='dj_name_eng')
	country = models.ForeignKey(Country, default=None, null=True, blank=True, on_delete=models.PROTECT, db_column='dj_country_id')
	city = models.ForeignKey(City, verbose_name=u'Город старта', default=None, null=True, blank=True,
		on_delete=models.PROTECT, related_name="series_city_set", db_column='dj_city_id')
	city_finish = models.ForeignKey(City, default=None, null=True, blank=True,
		on_delete=models.PROTECT, related_name="series_city_finish_set", db_column='dj_city_finish_id')
	editors = models.ManyToManyField(settings.AUTH_USER_MODEL, through='Series_editor', through_fields=('series', 'user'),
		related_name='series_to_edit_set')
	organizer = models.ForeignKey('Organizer', verbose_name=u'Организатор', default=FAKE_ORGANIZER_ID, blank=True,
		on_delete=models.PROTECT, db_column='dj_organizer_id')

	country_raw = models.CharField(verbose_name=u'Страна (устар.)', max_length=100, db_column='country', blank=True)
	district_raw = models.CharField(verbose_name=u'Фед. округ (устар.)', max_length=100, db_column='fedokrug', blank=True)
	region_raw = models.CharField(verbose_name=u'Регион (устар.)', max_length=100, db_column='obl', blank=True)
	city_raw = models.CharField(verbose_name=u'Город (устар.)', max_length=100, db_column='city', blank=True)
	card_raw = models.CharField(max_length=100, db_column='card', blank=True) # Deprecated. Equals to id

	start_place = models.CharField(verbose_name=u'Место старта', max_length=100, blank=True, db_column='dj_start_place')
	series_type = models.SmallIntegerField(verbose_name=u'Тип соревнований', choices=SERIES_TYPES, default=SERIES_TYPE_RUN, db_column='VidP')
	surface_type = models.SmallIntegerField(verbose_name=u'Тип забега', db_column='dj_surface_type',
		choices=SURFACE_TYPES, default=SURFACE_DEFAULT)
	n_views = models.IntegerField(verbose_name=u'Число просмотров карточки серии', default=0, db_column='card_wiew')
	director = models.CharField(verbose_name=u'Организатор', max_length=250, db_column='dj_director', blank=True, db_index=True)
	contacts = models.CharField(verbose_name=u'Координаты организаторов', max_length=250, db_column='contacts', blank=True)
	url_site = models.URLField(verbose_name=u'Сайт серии', max_length=200, db_column='dj_url_main', blank=True, db_index=True)
	url_vk = models.URLField(verbose_name=u'Страничка ВКонтакте', max_length=100, db_column='dj_url_vk', blank=True)
	url_facebook = models.URLField(verbose_name=u'Страничка в фейсбуке', max_length=100, db_column='dj_url_facebook', blank=True)
	url_instagram = models.URLField(verbose_name=u'Страничка в инстраграме', max_length=100, db_column='dj_url_instagram', blank=True)
	is_parkrun = models.BooleanField(verbose_name=u'Эта серия — паркран или что-то похожее. Скрывать в календаре вместе с паркранами',
		default=False)
	is_parkrun_closed = models.BooleanField(verbose_name=u'Правда ли, что этот паркран сейчас закрыт', default=False)

	comment = models.CharField(verbose_name=u'Комментарий', max_length=250, db_column='komm', blank=True)
	comment_private = models.CharField(verbose_name=u'Комментарий администраторам (не виден посетителям)',
		max_length=250, db_column='dj_comment_private', blank=True)
	last_update = models.DateTimeField(verbose_name=u'Дата последнего обновления', auto_now=True, db_column='dj_last_update')
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Создал серию в базе', related_name='series_created_set',
		on_delete=models.SET_NULL, default=None, null=True, blank=True, db_column='dj_created_by')
	class Meta:
		db_table = 'probeg'
		verbose_name = u'Серия забегов'
		index_together = [
			['country', 'name'],
			['country', 'city', 'name'],
		]
		unique_together = (('name', 'city'), )
	def clean(self):
		self.name = self.name.strip()
		self.name = replace_symbols(self.name)
		if self.name == "":
			raise ValidationError(u'Название серии не может быть пустым.')
		if self.city_finish and not self.city:
			raise ValidationError(u'Нельзя указать город финиша, не указав город старта.')
		if self.city:
			self.country = self.city.region.country
			self.city_raw = self.city.name_full(with_nbsp=False)
			if self.city.region.country.has_regions:
				self.region_raw = self.city.region.name
			else:
				self.region_raw = ""
			if self.city.region.country.id == 'RU':
				self.district_raw = self.city.region.district.name
		else:
			self.city_raw = ""
			self.region_raw = ""
			self.district_raw = ""
		if self.country:
			self.country_raw = self.country.name
		else:
			self.country_raw = ""
		self.contacts = self.contacts.strip()
		self.url_site = self.url_site.strip()
		self.comment = self.comment.strip()
		self.comment_private = self.comment_private.strip()
		self.card_raw = unicode(self.id)
		self.name = results_util.fix_quotes(self.name)

		if self.name.startswith(results_util.RUSSIAN_PARKRUN_SITE):
			self.is_parkrun = True

		if self.url_vk and not self.url_vk.startswith(VK_POSSIBLE_PREFIXES):
			raise ValidationError({'url_vk': u'Адрес ВКонтакте должен начинаться со строк ' + u', '.join(VK_POSSIBLE_PREFIXES)})

		if self.url_facebook and not self.url_facebook.startswith(FB_POSSIBLE_PREFIXES):
			raise ValidationError({'url_facebook': u'Адрес страницы в фейсбуке должен начинаться со строк ' + u', '.join(FB_POSSIBLE_PREFIXES)})

		if self.url_instagram and not self.url_instagram.startswith(IN_POSSIBLE_PREFIXES):
			raise ValidationError({'url_instagram': u'Адрес страницы в инстаграме должен начинаться со строк ' + u', '.join(IN_POSSIBLE_PREFIXES)})
	def strCityCountry(self, with_nbsp=True):
		if not self.city:
			if self.country:
				return self.country.name
			else:
				return u"Неизвестно"
		# So self.city is not None
		return self.city.nameWithFinish(self.city_finish, with_nbsp=with_nbsp)
	def getCountry(self):
		if self.city:
			return self.city.region.country
		elif self.country:
			return self.country
		else:
			return None
	def has_dependent_objects(self):
		return self.event_set.exists() or self.document_set.exists()
	def get_url_logo(self):
		doc = self.document_set.filter(document_type=DOC_TYPE_LOGO).first()
		if doc:
			return doc.url_original if doc.url_original else doc.upload.name
		else:
			return ""
	def is_by_skoblina(self):
		return self.series_editor_set.filter(user_id=USER_SKOBLINA).exists()
	def is_russian_parkrun(self):
		return self.url_site.startswith(results_util.RUSSIAN_PARKRUN_SITE)
	def has_news_reviews_photos(self):
		return Document.objects.filter(event__series_id=self.id, document_type__in=[DOC_TYPE_PHOTOS, DOC_TYPE_IMPRESSIONS]).exists() \
			or News.objects.filter(event__series_id=self.id).exists()
	def get_reverse_url(self, target):
		return reverse(target, kwargs={'series_id': self.id})
	def get_absolute_url(self):
		return self.get_reverse_url('results:series_details')
	def get_editor_url(self):
		return self.get_reverse_url('editor:series_details')
	def get_history_url(self):
		return self.get_reverse_url('editor:series_changes_history')
	def get_update_url(self):
		return self.get_reverse_url('editor:series_update')
	def get_delete_url(self):
		return self.get_reverse_url('editor:series_delete')
	def get_create_event_url(self):
		return self.get_reverse_url('editor:event_create')
	def get_clone_url(self):
		return self.get_reverse_url('editor:series_create')
	def get_documents_update_url(self):
		return self.get_reverse_url('editor:series_documents_update')
	def get_old_url(self):
		return '{}/cards.php?id={}'.format(SITE_URL_OLD, self.id)
	def get_children(self):
		return self.event_set.all()
	def __unicode__(self):
		res = self.name
		fields = []
		if self.city:
			fields.append(self.city.name_full())
		if self.country and self.country.id != "RU":
			fields.append(self.country.name)
		if fields:
			res += " (" + ", ".join(fields) + ")"
		return res
	@classmethod
	def get_russian_parkruns(cls):
		return cls.objects.filter(url_site__startswith=results_util.RUSSIAN_PARKRUN_SITE).exclude(pk=results_util.OLD_PARKRUN_SERIES_ID)
	@classmethod
	def get_russian_parkrun_ids(cls):
		return set(cls.get_russian_parkruns().values_list('pk', flat=True))

class Series_editor(models.Model):
	user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
	series = models.ForeignKey(Series, on_delete=models.CASCADE)
	added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
		related_name="editors_added_by_user")
	added_time = models.DateTimeField(auto_now_add=True)
	class Meta:
		db_table = "dj_series_editor"
		verbose_name = u'Пользователь, имеющий права на работу с серией забегов'
		ordering = ['series__name']

KLB_STATUS_WRONG_YEAR = 0
KLB_STATUS_OK = 1
KLB_STATUS_ADDED_LATE = 2
KLB_STATUS_WRONG_DISTANCE_TYPE = 3
KLB_STATUS_SHORT_DISTANCE = 4
KLB_STATUS_SHORT_REAL_DISTANCE = 5
KLB_STATUS_SMALL_RESULT = 6
KLB_STATUS_NOT_IN_KLB = 7
KLB_STATUS_LONG_DISTANCE = 8
KLB_STATUS_ONLY_ONE_PARTICIPANT = 9
KLB_STATUSES = (
	(KLB_STATUS_WRONG_YEAR, u'год забега не относится к активным КЛБМатчам'),
	(KLB_STATUS_OK, u'ОК'),
	(KLB_STATUS_ADDED_LATE, u'забег слишком поздно добавлен в календарь'),
	(KLB_STATUS_WRONG_DISTANCE_TYPE, u'недопустимый тип дистанции'),
	(KLB_STATUS_SHORT_DISTANCE, u'в КЛБМатче учитываются только дистанции не короче 9500 км'),
	(KLB_STATUS_SHORT_REAL_DISTANCE, u'в КЛБМатче учитываются только результаты на дистанциях, фактическая длина которых не меньше 9500 м'),
	(KLB_STATUS_SMALL_RESULT, u'в КЛБМатче учитываются только результаты не короче 9500 км'),
	(KLB_STATUS_NOT_IN_KLB, u'не подлежит учёту в КЛБМатче'),
	(KLB_STATUS_LONG_DISTANCE, u'в КЛБМатче учитываются только дистанции не длиннее 300 км'),
	(KLB_STATUS_ONLY_ONE_PARTICIPANT, u'в КЛБМатче учитываются только забеги, на которых стартовало хотя бы два человека'),
)
DEFAULT_EVENT_LENGTH = datetime.timedelta(hours=4)
class Event(models.Model):
	id = models.AutoField(primary_key=True, db_column='id')
	name = models.CharField(verbose_name=u'Название забега', max_length=250, db_index=True, db_column='NameP')
	number = models.SmallIntegerField(verbose_name=u'Номер забега в серии', default=None, null=True, blank=True, db_column='dj_number')
	series = models.ForeignKey(Series, on_delete=models.CASCADE, db_column='Probeg_id')
	country = models.ForeignKey(Country, default=None, null=True, on_delete=models.PROTECT, db_column='dj_country_id') # Deprecated
	city = models.ForeignKey(City, verbose_name=u'Город старта', default=None, null=True, blank=True,
		on_delete=models.PROTECT, related_name="event_city_set", db_column='dj_city_id')
	city_finish = models.ForeignKey(City, verbose_name=u'Город финиша', default=None, null=True, blank=True,
		on_delete=models.PROTECT, related_name="event_city_finish_set", db_column='dj_city_finish_id')
	surface_type = models.SmallIntegerField(verbose_name=u'Тип забега', db_column='dj_surface_type',
		choices=SURFACE_TYPES, default=SURFACE_DEFAULT)

	country_raw = models.CharField(verbose_name=u'Страна (устар.)', max_length=100, db_column='countryp', blank=True)
	district_raw = models.CharField(verbose_name=u'Фед. округ (устар.)', max_length=100, db_column='fedokrugp', blank=True)
	region_raw = models.CharField(verbose_name=u'Регион (устар.)', max_length=100, db_column='oblp', blank=True)
	city_raw = models.CharField(verbose_name=u'Город (устар.)', max_length=100, db_column='cityp', blank=True)

	start_date = models.DateField(verbose_name=u'Дата старта', db_column='DateS')
	finish_date = models.DateField(verbose_name=u'Дата финиша (только если отличается от старта)', db_index=True,
		default=None, null=True, blank=True, db_column='DateF')
	arrival_date = models.DateField(verbose_name=u'Дата заезда (только если отличается от старта)',
		default=None, null=True, blank=True, db_column='DataZ')
	year_raw = models.SmallIntegerField(verbose_name=u'Год (устаревшее)', default=0, blank=True, db_column='Year')
	month_raw = models.SmallIntegerField(verbose_name=u'Месяц (устаревшее)', default=0, blank=True, db_column='Month')

	start_place = models.CharField(verbose_name=u'Место старта', max_length=100, blank=True, db_column='PlaceS')
	start_time = models.CharField(verbose_name=u'Время старта (ЧЧ:ММ), если известно', max_length=5, blank=True, db_column='TimeS')
	# TODO: make TimeField

	announcement = models.TextField(verbose_name=u'Дополнительная информация', db_column='Anons', blank=True)
	url_registration = models.URLField(verbose_name=u'URL страницы с регистрацией', max_length=MAX_URL_LENGTH, blank=True)
	url_announcement = models.CharField(verbose_name=u'URL анонса (устар.)', max_length=MAX_URL_LENGTH, db_column='Detail', blank=True)
	url_poster = models.CharField(verbose_name=u'URL афиши (устар.)', max_length=MAX_URL_LENGTH, db_column='Bill', blank=True)
	url_course = models.CharField(verbose_name=u'URL схемы трассы (устар.)', max_length=MAX_URL_LENGTH, db_column='Plan', blank=True)
	url_logo = models.CharField(verbose_name=u'URL логотипа (устар.)', max_length=MAX_URL_LENGTH, db_column='LabelP', blank=True)
	url_regulation = models.CharField(verbose_name=u'URL положения (устар.)', max_length=MAX_URL_LENGTH, db_column='AdressP', blank=True)
	url_regulation_stamped = models.CharField(verbose_name=u'URL положения с печатью (устар.)',
		max_length=MAX_URL_LENGTH, db_column='AdressPP', blank=True)
	url_protocol = models.CharField(verbose_name=u'URL протокола с результатами (устар.)',
		max_length=MAX_URL_LENGTH, db_column='AdressPr', blank=True)
	
	email = models.CharField(verbose_name=u'E-mail организаторов', max_length=MAX_EMAIL_LENGTH, db_column='Email', blank=True)
	contacts = models.CharField(verbose_name=u'Другие контакты организаторов', max_length=255, db_column='Adress', blank=True)
	url_site = models.URLField(verbose_name=u'Сайт/страница именно этого забега', max_length=MAX_URL_LENGTH, db_column='Site', blank=True)
	url_vk = models.URLField(verbose_name=u'Страничка, посвящённая событию, вКонтакте', max_length=MAX_URL_LENGTH, db_column='Tel', blank=True)
	url_facebook = models.URLField(verbose_name=u'Страничка, посвящённая событию, на Facebook',
		max_length=MAX_URL_LENGTH, db_column='Facebook', blank=True)

	distances_raw = models.CharField(verbose_name=u'Дистанции через запятую (устар.)', max_length=200, db_column='Dists', blank=True)
	cancelled = models.BooleanField(verbose_name=u'Пометьте, если забег отменён (это удалит все дистанции!)', db_index=True,
		default=False, db_column='otmenen')
	comment = models.CharField(verbose_name=u'Комментарий', max_length=250, db_column='Komm', blank=True)
	comment_private = models.CharField(verbose_name=u'Комментарий для администраторов (не будет доступен пользователям)',
		max_length=250, db_column='dj_comment_private', blank=True)
	last_update = models.DateTimeField(verbose_name=u'', auto_now=True, db_column='LastIzm')
	invisible = models.BooleanField(verbose_name=u'Пометьте, если забег не должен быть виден пользователям', db_index=True,
		default=False, db_column='unvisible') # 1 - do not show
	events_group = models.CharField(verbose_name=u'', max_length=100, db_column='GroupsProbeg', blank=True) # Not used now
	ak_race_id = models.CharField(verbose_name=u'ID забега в базе АК55', max_length=6, db_column='RACEID', blank=True)
	not_in_klb = models.BooleanField(verbose_name=u'Пометьте, если забег НЕ подлежит учёту в КЛБМатче',
		default=False, db_column='unklbmatch') # 1 - do not use in KLBMatch
	ask_for_protocol_sent = models.BooleanField(verbose_name=u'Мы уже писали организаторам запрос на протокол', default=False, db_column='dj_ask_for_protocol_sent')

	source = models.CharField(verbose_name=u'Источник информации', max_length=100, db_column='dj_source', blank=True)
	date_added_to_calendar = models.DateField(verbose_name=u'Дата появления забега в календаре',
		default=datetime.date.today, db_column='Date_In_Calend')
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Кто добавил забег на сайт',
		on_delete=models.SET_NULL, default=None, null=True, blank=True, db_column='dj_created_by')
	def clean(self):
		self.name = self.name.strip()
		self.name = replace_symbols(self.name)
		if self.city and (self.city == self.series.city) and (self.city_finish is None) and (self.series.city_finish is None):
			self.city = None
		if self.city and (self.city == self.series.city) and (self.city_finish == self.series.city_finish):
			self.city = None
			self.city_finish = None
		if self.city:
			self.city_raw = self.city.name_full()
			if self.city.region.country.has_regions:
				self.region_raw = self.city.region.name
			else:
				self.region_raw = ""
			if self.city.region.country.id == 'RU':
				self.district_raw = self.city.region.district.name
			self.country = self.city.region.country
		else:
			self.city_raw = ""
			self.region_raw = ""
			self.district_raw = ""
		self.country_raw = self.country.name if self.country else ""

		if self.start_date:
			if not (DATE_MIN <= self.start_date <= DATE_MAX):
				raise ValidationError(u'Невозможная дата забега')
			self.year_raw = self.start_date.year
			self.month_raw = self.start_date.month
			if self.finish_date == self.start_date:
				self.finish_date = None
			if self.finish_date and (self.finish_date < self.start_date):
				raise ValidationError(u'Дата окончания забега не может быть меньше даты начала.')

		self.name = results_util.fix_quotes(self.name)

		self.contacts = self.contacts.strip()
		self.announcement = self.announcement.strip()
		self.url_registration = self.url_registration.strip()
		self.url_announcement = self.url_announcement.strip()
		self.url_poster = self.url_poster.strip()
		self.url_course = self.url_course.strip()
		self.url_logo = self.url_logo.strip()
		self.url_regulation = self.url_regulation.strip()
		self.url_regulation_stamped = self.url_regulation_stamped.strip()
		self.url_protocol = self.url_protocol.strip()
		
		self.email = self.email.strip()
		self.contacts = self.contacts.strip()
		self.url_site = self.url_site.strip()
		self.url_vk = self.url_vk.strip()
		self.url_facebook = self.url_facebook.strip()
		self.comment = self.comment.strip()
		self.comment_private = self.comment_private.strip()

		if self.surface_type and (self.surface_type == self.series.surface_type):
			self.surface_type = SURFACE_DEFAULT

		if self.url_vk and not self.url_vk.startswith(VK_POSSIBLE_PREFIXES):
			raise ValidationError({'url_vk': u'Адрес ВКонтакте должен начинаться со строк ' + u', '.join(VK_POSSIBLE_PREFIXES)})

		if self.url_facebook and not self.url_facebook.startswith(FB_POSSIBLE_PREFIXES):
			raise ValidationError({'url_facebook': u'Адрес страницы в фейсбуке должен начинаться со строк ' + u', '.join(FB_POSSIBLE_PREFIXES)})
	class Meta:
		db_table = "ProbegYear"
		verbose_name = u'Забег'
		index_together = [
			["series", "start_date", "name"],
			["city", "name"],
			["start_date", "name"],
		]
		unique_together = (("series", "year_raw", "start_date", "start_time", "city"),)
	def date(self, format="%d.%m.%Y", with_time=False, with_nobr=True):
		if self.finish_date and format.startswith("%d.%m") and not with_time:
			if self.start_date.year == self.finish_date.year:
				if self.start_date.month == self.finish_date.month:
					res = '{}–{}'.format(self.start_date.strftime("%d"), self.finish_date.strftime(format))
				else:
					res = '{}–{}'.format(self.start_date.strftime("%d.%m"), self.finish_date.strftime(format))
				return ('<span class="nobr">' + res + '</span>') if with_nobr else res
		if not self.start_date:
			return "неизвестно"
		res = self.start_date.strftime(format)
		if with_time:
			res += ", " + self.start_time
		if self.finish_date:
			res += u" – " + self.finish_date.strftime(format)
		return res
	def dateFull(self, with_time=False):
		if not self.start_date:
			return "неизвестно"
		if not with_time or not self.start_time:
			return dates2str(self.start_date, self.finish_date)
		res = date2str(self.start_date) + ", " + self.start_time
		if self.finish_date:
			res += u" – " + date2str(self.finish_date)
		return res
	def dateWoYear(self):
		return self.date(format="%d.%m")
	def dateWithTime(self):
		return self.dateFull(with_time=True)
	def get_url_logo(self):
		doc = self.document_set.filter(document_type=DOC_TYPE_LOGO).first()
		if doc:
			return doc.url_original if doc.url_original else doc.upload.name
		else:
			return ""
	def getCountry(self):
		if self.city:
			return self.city.region.country
		if self.series.city:
			return self.series.city.region.country
		if self.series.country:
			return self.series.country
		return None
	def strCountry(self):
		country = self.getCountry()
		return country.name if country else u"Неизвестно"
	def strCityCountry(self, with_nbsp=True):
		if not self.city:
			return self.series.strCityCountry(with_nbsp=with_nbsp)
		# So self.city is not None
		return self.city.nameWithFinish(self.city_finish, with_nbsp=with_nbsp)
	def is_in_future(self):
		if self.start_date is None:
			return False
		return (datetime.date.today() <= self.start_date)
	def is_in_past(self):
		if self.start_date is None:
			return False
		return (datetime.date.today() >= self.start_date)
	def get_surface_type_name(self):
		if self.surface_type:
			return self.get_surface_type_display()
		self.series.get_surface_type_display()
	def is_too_old_for_klb_score(self): # If participant tells us about his result after >= 3 months or event, he gets only bonus score
		return (self.start_date < datetime.date.today() - datetime.timedelta(days=90))
	def show_date_added(self):
		return self.date_added_to_calendar > datetime.date(2000, 1, 2)
	def can_be_edited(self): # We allow series editors to edit events that are not older than 1 year
		return (self.start_date >= datetime.date.today() - datetime.timedelta(days=90))
	def has_races_wo_results(self): # Should we draw button "I have a result on this event"?
		return (datetime.date.today() >= self.start_date) and self.race_set.exclude(loaded__in=RESULTS_SOME_OR_ALL_OFFICIAL).exists()
	def ordered_race_set(self):
		return self.race_set.select_related('distance').order_by('distance__distance_type', '-distance__length', 'precise_name')
	def has_races_with_results(self): # Should we draw button "Create a news with results for this event"?
		return self.race_set.filter(loaded=RESULTS_LOADED, n_participants_finished__gt=0).exists()
	def has_news_reviews_photos(self):
		return self.document_set.filter(document_type__in=[DOC_TYPE_PHOTOS, DOC_TYPE_IMPRESSIONS]).exists() or self.news_set.exists()
	def city_id_for_link(self): # What city_id to use for link from races list?
		if self.city and not self.city_finish:
			return self.city.id
		if (not self.city) and self.series.city and not self.series.city_finish:
			return self.series.city.id
		return 0
	def email_correct(self):
		return is_email_correct(self.email)
	def first_email(self): # Return just first email if there are a few. For 'Add to calendar' button
		if self.email:
			return self.email.split(',')[0].strip()
		return ''
	def site(self):
		if self.url_site:
			return self.url_site
		else:
			return self.series.url_site
	def vk(self):
		if self.url_vk:
			return self.url_vk
		else:
			return self.series.url_vk
	def fb(self):
		if self.url_facebook:
			return self.url_facebook
		else:
			return self.series.url_facebook
	def getCity(self):
		if self.city:
			return self.city
		return self.series.city
	def getCityFinish(self):
		if self.city_finish:
			return self.city_finish
		if self.city:
			return None
		return self.series.city_finish
	def get_age_on_event_date(self, birthday):
		return results_util.get_age_on_date(self.start_date, birthday)
	def has_dependent_objects(self):
		return self.race_set.exists() or self.document_set.exists() or self.news_set.exists() or \
			self.review_set.exists() or self.photo_set.exists() or self.klb_result_set.exists()
	def get_xls_protocols(self):
		return self.document_set.filter(Q_IS_XLS_FILE, document_type__in=DOC_PROTOCOL_TYPES)
	def add_to_calendar(self, race, user):
		if Calendar.objects.filter(event=self, user=user).exists():
			return 0, u"Этот забег уже есть в Вашем календаре."
		else:
			Calendar.objects.create(event=self, race=race, user=user)
			return 1, ""
	def remove_from_calendar(self, user):
		items = Calendar.objects.filter(event=self, user=user)
		if items.exists():
			items.delete()
			return 1, ""
		else:
			return 0, u"Этого забега и нет в Вашем календаре."
	def get_documents_for_right_column(self):
		return self.document_set.exclude(document_type__in=DOC_TYPES_NOT_FOR_RIGHT_COLUMN).order_by('document_type', 'comment')
	def get_klb_status(self):
		if not is_active_klb_year(self.start_date.year):
			return KLB_STATUS_WRONG_YEAR
		if self.not_in_klb:
			return KLB_STATUS_NOT_IN_KLB
		country = self.getCountry()
		if country is None:
			return KLB_STATUS_OK
		# if country.id not in ('BY', 'RU', 'UA'):
		if country.id not in ('BY', 'RU'):
			return KLB_STATUS_OK
		if (self.date_added_to_calendar + datetime.timedelta(days=30)) <= self.start_date:
			return KLB_STATUS_OK
		return KLB_STATUS_ADDED_LATE
	def is_in_klb_but_added_late(self):
		if self.get_klb_status() == KLB_STATUS_ADDED_LATE:
			for race in self.race_set.all():
				if race.get_distance_klb_status() == KLB_STATUS_OK:
					return True
		return False
	def get_reverse_url(self, target):
		return reverse(target, kwargs={'event_id': self.id})
	def get_absolute_url(self):
		return self.get_reverse_url('results:event_details')
	def get_editor_url(self):
		return self.get_reverse_url('editor:event_details')
	def get_clone_url(self):
		return self.get_reverse_url('editor:event_create')
	def get_delete_url(self):
		return self.get_reverse_url('editor:event_delete')
	def get_protocol_details_url(self, protocol=None):
		if protocol:
			return reverse('editor:protocol_details', kwargs={'event_id': self.id, 'protocol_id': protocol.id})
		else:
			return self.get_reverse_url('editor:protocol_details')
	def get_change_series_url(self):
		return self.get_reverse_url('editor:event_change_series')
	def get_history_url(self):
		return self.get_reverse_url('editor:event_changes_history')
	def get_make_news_url(self):
		return self.get_reverse_url('editor:event_details_make_news') + '#news'
	def get_remove_races_with_no_results_url(self):
		return self.get_reverse_url('editor:remove_races_with_no_results')
	def get_add_to_calendar_url(self):
		return self.get_reverse_url('results:add_event_to_calendar')
	def get_remove_from_calendar_url(self):
		return self.get_reverse_url('results:remove_event_from_calendar')
	def get_klb_results_url(self):
		return self.get_reverse_url('results:event_klb_results')
	def get_old_klb_url(self):
		year = self.start_date.year
		if 2015 <= year <= 2017:
			return '{}/klb/{}/allraces.php?idpro={}'.format(SITE_URL_OLD, year, self.id)
		elif year >= 2011:
			return '{}/klb/{}/index.php?idpro={}'.format(SITE_URL_OLD, year, self.id)
		return ''
	def get_create_reg_step1_url(self):
		return self.get_reverse_url('editor:registration_create_step1')
	def get_reg_race_set(self, open_only=False):
		if hasattr(self, 'registration'):
			reg_races = Reg_race_details.objects.filter(race__event=self)
			if open_only:
				reg_races = reg_races.filter(is_open=True)
			return self.race_set.filter(pk__in=reg_races.values_list('race_id', flat=True)).select_related('reg_race_details').order_by(
				'distance__distance_type', '-distance__length', 'precise_name')
		return Race.objects.none()
	def get_reg_url(self):
		return self.get_reverse_url('results:reg_step1')
	def get_start_time_iso(self):
		res = self.start_date.isoformat()
		if self.start_time:
			res += ' ' + self.start_time[:6]
		return res
	def get_finish_time_iso(self):
		if self.finish_date:
			res = self.finish_date.isoformat()
			if self.start_time:
				res += ' ' + self.start_time[:6]
			return res
		elif self.start_time:
			res = datetime.datetime.combine(self.start_date, datetime.datetime.strptime(self.start_time[:6], '%H:%M').time()) + DEFAULT_EVENT_LENGTH
			return res.isoformat(chr(32))
		else:
			return self.start_date.isoformat()
	def __unicode__(self):
		return self.name if self.name else self.series.name
	@classmethod
	def get_visible_events(cls, year=None):
		res = cls.objects.filter(
			series__series_type__in=(SERIES_TYPE_RUN, SERIES_TYPE_DO_NOT_SHOW), # For parkruns
			cancelled=False,
			invisible=False)
		if year:
			res = res.filter(start_date__year=year)
		return res
	@classmethod
	def get_events_by_countries(cls, year, country_ids):
		return cls.get_visible_events(year).filter(
			Q(city__region__country_id__in=country_ids) | ( Q(city=None) & Q(series__city__region__country_id__in=country_ids) ))
	@classmethod
	def get_russian_events(cls, year):
		return cls.get_events_by_countries(year, ['RU'])
	def get_children(self):
		return self.race_set.all()

TYPE_TRASH = 0
TYPE_METERS = 1
TYPE_MINUTES = 2
TYPE_THRIATLON = 3
TYPE_STEPS = 4
TYPE_FLOORS = 5
TYPE_SWIMMING = 6
TYPE_RELAY = 7
TYPE_SWIMRUN = 8
TYPE_NORDIC_WALKING = 9
DIST_TYPES = (
	(TYPE_TRASH, u'странное'),
	(TYPE_METERS, u'метры'),
	(TYPE_MINUTES, u'минуты'),
	(TYPE_THRIATLON, u'триатлон'),
	(TYPE_STEPS, u'ступеньки'),
	(TYPE_FLOORS, u'этажи'),
	(TYPE_SWIMMING, u'плавание'),
	(TYPE_RELAY, u'эстафета (указывается общая длина дистанции в метрах)'),
	(TYPE_SWIMRUN, u'Swimrun'),
	(TYPE_NORDIC_WALKING, u'скандинавская ходьба'),
	)

MILE_IN_METERS = 1609.344

class Distance(models.Model):
	distance_raw = models.DecimalField(verbose_name=u'Длина дистанции (устар.)', default=0, max_digits=8, decimal_places=4, db_column='Dist')
	race_type_raw = models.CharField(verbose_name=u'Тип дистанции (устар.)', max_length=3, db_column='Dist_ed') # час/км/мил и т.д.

	distance_type = models.SmallIntegerField(verbose_name=u'Тип дистанции', default=1, choices=DIST_TYPES, db_column='dj_type')
	length = models.IntegerField(verbose_name=u'Длина дистанции (обычно — в метрах)', default=0, db_index=True, db_column='dj_length')
	name = models.CharField(verbose_name=u'Название дистанции (можно оставить пустым)', max_length=100, blank=True, db_column='dj_name')
	popularity_value = models.SmallIntegerField(verbose_name=u'Приоритет', default=0, db_column='dj_popularity_value')
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Кто добавил дистанцию в БД',
		on_delete=models.SET_NULL, default=None, null=True, blank=True, db_column='dj_created_by')
	added_time = models.DateTimeField(verbose_name=u'Время занесения в БД', auto_now_add=True, db_column='dj_added_time')
	class Meta:
		db_table = "dist"
		verbose_name = u'Дистанция'
		unique_together = (("distance_raw", "race_type_raw"), ("distance_type", "length"))
		index_together = [
			["popularity_value", "distance_type", "length"],
		]
	def clean(self):
		self.name = self.name.strip()
		if (self.distance_raw < 0) or (self.distance_raw > 9999.9999):
			raise ValidationError(u'Длина в старом стиле должна быть положительным числом меньше 10000.')
	def nameFromType(self):
		if self.distance_type == TYPE_METERS:
			return results_util.length2m_or_km(self.length)
		elif self.distance_type == TYPE_MINUTES:
			tmp = self.length
			minutes = tmp % 60
			tmp //= 60
			hours = tmp
			res = []
			if hours:
				res.append(unicode(hours) + u' часов')
			if minutes:
				res.append(unicode(minutes) + u' минут')
			return " ".join(res)
		elif self.distance_type == TYPE_STEPS:
			return unicode(self.length) + u' ступенек'
		elif self.distance_type == TYPE_FLOORS:
			return unicode(self.length) + u' этажей'
		elif self.distance_type == TYPE_NORDIC_WALKING:
			return u'скандинавская ходьба {}'.format(results_util.length2m_or_km(self.length))
		return u''
	def resultAsDistance(self, value, for_best_result=False):
		res = unicode(value)
		if for_best_result:
			if len(res) >= BEST_RESULT_LENGTH:
				return res
			if len(res) == BEST_RESULT_LENGTH - 1:
				return res + u'м'
		return res + u' м'
	def strResult(self, value, round_hundredths=False, for_best_result=False):
		if self.distance_type == TYPE_MINUTES:
			return self.resultAsDistance(value, for_best_result=for_best_result)
		else:
			return centisecs2time(value, round_hundredths)
	def get_pace(self, value): # In seconds per km
		if self.length == 0:
			return None
		if value == 0:
			return None
		if self.distance_type == TYPE_MINUTES:
			return int(round(self.length * 60 * 1000 / value))
		else:
			return int(round(value * 10 / self.length))
	def has_dependent_objects(self):
		return self.race_set.exists() or self.distance_real_set.exists() or self.split_set.exists()
	def get_reverse_url(self, target):
		return reverse(target, kwargs={'distance_id': self.id})
	def get_editor_url(self):
		return self.get_reverse_url('editor:distance_details')
	def get_update_url(self):
		return self.get_reverse_url('editor:distance_update')
	def get_delete_url(self):
		return self.get_reverse_url('editor:distance_delete')
	def get_history_url(self):
		return self.get_reverse_url('editor:distance_changes_history')
	def __unicode__(self):
		if self.name:
			return self.name
		else:
			return self.nameFromType()
	@classmethod
	def get_all_by_popularity(cls):
		return cls.objects.all().order_by('-popularity_value', 'distance_type', 'length')
	@classmethod
	def try_parse_distance(cls, distance_raw, distance_type=None): # Returns some number (0 if not parsed) and distance (if found)
		distance = None
		length = 0
		if distance_raw == '':
			return length, distance
		if distance_type in (None, TYPE_METERS):
			if distance_raw.endswith((u' м', u' m')):
				length = int_safe(distance_raw[:-2])
			elif distance_raw.endswith((u'0м', u'0m')):
				length = int_safe(distance_raw[:-1])
			elif distance_raw == u'марафон':
				length = 42195
			elif distance_raw in (u'полумарафон', u'half marathon net time'):
				length = 21098
			else:
				for suffix in (u'km net time', u'км', u'km', u'km netto', u'km::start', u'k'):
					if distance_raw.endswith(suffix):
						length = int(round(float_safe(distance_raw[:-len(suffix)].replace(',', '.')) * 1000))
			if (length == 0) and distance_raw:
				distance_with_same_name = Distance.objects.filter(distance_type=TYPE_METERS, name=distance_raw).first()
				if distance_with_same_name:
					return distance_with_same_name.length, distance_with_same_name
			if length and (distance_type is None):
				distance_type = TYPE_METERS
		if (length == 0) and (distance_type in (None, TYPE_MINUTES)):
			if distance_raw.endswith(u'мин'):
				length = int_safe(distance_raw[:-3])
			if distance_raw.endswith(u'минут'):
				length = int_safe(distance_raw[:-5])
			else:
				for suffix in (u'час', u'часа', u'часов'):
					if distance_raw.endswith(suffix):
						length = int(round(float_safe(distance_raw[:-len(suffix)].replace(',', '.')) * 60))
			if length and (distance_type is None):
				distance_type = TYPE_MINUTES
		if length == 0:
			length = int_safe(distance_raw)
		if length:
			if distance_type == TYPE_METERS:
				if length == 21100:
					length = 21098
				elif length == 42200:
					length = 42195
			distances = cls.objects.filter(length=length)
			if distance_type:
				distances = distances.filter(distance_type=distance_type)
			else:
				distances = distances.filter(distance_type=TYPE_METERS)
			distance = distances.first()
		return length, distance

RESULTS_NOT_LOADED = 0
RESULTS_LOADED = 1
RESULTS_SOME_UNOFFICIAL = 2
RESULTS_SOME_OFFICIAL = 3
LOADED_TYPES = (
	(RESULTS_NOT_LOADED, u'результатов нет'),
	(RESULTS_LOADED, u'загружены целиком'),
	(RESULTS_SOME_UNOFFICIAL, u'есть неофициальные результаты — добавленные пользователями и/или сгенерированные по КЛБ-результатам'),
	(RESULTS_SOME_OFFICIAL, u'загружена часть официальных результатов'),
)
RESULTS_SOME_OR_ALL_OFFICIAL = (RESULTS_LOADED, RESULTS_SOME_OFFICIAL)

BEST_RESULT_LENGTH = 10
class Race(models.Model):
	id = models.AutoField(primary_key=True, db_column='id')
	series_raw = models.IntegerField(verbose_name=u'id серии (устар.)', default=0, db_column='Probeg_id')
	event = models.ForeignKey(Event, verbose_name=u'Забег', on_delete=models.CASCADE, db_column='Probeg_Year_id')
	distance = models.ForeignKey(Distance, verbose_name=u'Официальная дистанция', on_delete=models.PROTECT, db_column='dj_distance_id')
	distance_real = models.ForeignKey(Distance, verbose_name=u'Фактическая дистанция (если отличается)',
		on_delete=models.PROTECT, related_name='distance_real_set', default=None, null=True, blank=True, db_column='dj_distance_real_id')
	surface_type = models.SmallIntegerField(verbose_name=u'Тип забега (укажите, только если отличается от всего забега)', db_column='dj_surface_type',
		choices=SURFACE_TYPES, default=SURFACE_DEFAULT)

	distance_raw = models.DecimalField(verbose_name=u'Длина дистанции (устар.)', default=0, max_digits=8, decimal_places=4, db_column='Dist')
	ak_distance_raw = models.CharField(verbose_name=u'Длина дистанции в базе AK55', max_length=10, blank=True, db_column='dj_ak_distance_raw')
	race_type_raw = models.CharField(verbose_name=u'Тип дистанции (устар.)', max_length=3, db_column='Dist_ed') # час/км/мил и т.д.
	n_participants = models.IntegerField(verbose_name=u'Число участников', default=None, null=True, blank=True, db_column='N_s')
	n_participants_men = models.IntegerField(verbose_name=u'Число участников-мужчин', default=None, null=True, blank=True, db_column='dj_n_participants_men')
	n_participants_finished = models.IntegerField(verbose_name=u'Число финишировавших', default=None, null=True, blank=True, db_column='N_u')
	n_participants_finished_men = models.IntegerField(verbose_name=u'Число финишировавших мужчин', default=None, null=True, blank=True, db_column='N_m')

	winner_male_fname = models.CharField(verbose_name=u'Имя', max_length=100, db_column='NameP1', blank=True)
	winner_male_lname = models.CharField(verbose_name=u'Мужчина-победитель. Фамилия', max_length=100, db_column='NameP2', blank=True)
	winner_male_city = models.CharField(verbose_name=u'Город', max_length=100, db_column='KoordP', blank=True)
	winner_male_result = models.CharField(verbose_name=u'Результат', max_length=BEST_RESULT_LENGTH, db_column='Rez', blank=True)
	winner_male_user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Мужчина-победитель. Пользователь', on_delete=models.SET_NULL,
		related_name='winner_male_user_set', default=None, null=True, blank=True)
	winner_male_runner = models.ForeignKey('Runner', verbose_name=u'Мужчина-победитель. Бегун', on_delete=models.SET_NULL,
		related_name='winner_male_runner_set', null=True, default=None, blank=True)
	is_male_course_record = models.BooleanField(verbose_name=u'Рекорд ли трассы для мужчин',
		default=False, blank=True, db_column='dj_is_male_course_record')
	winner_female_fname = models.CharField(verbose_name=u'Имя', max_length=100, db_column='NameP1f', blank=True)
	winner_female_lname = models.CharField(verbose_name=u'Женщина-победитель. Фамилия', max_length=100, db_column='NameP2f', blank=True)
	winner_female_city = models.CharField(verbose_name=u'Город', max_length=100, db_column='KoordPf', blank=True)
	winner_female_result = models.CharField(verbose_name=u'Результат', max_length=BEST_RESULT_LENGTH, db_column='Rezf', blank=True)
	winner_female_user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Женщина-победитель. Пользователь', on_delete=models.SET_NULL,
		related_name='winner_female_user_set', default=None, null=True, blank=True)
	winner_female_runner = models.ForeignKey('Runner', verbose_name=u'Женщина-победитель. Бегун', on_delete=models.SET_NULL,
		related_name='winner_female_runner_set', null=True, default=None, blank=True)
	is_female_course_record = models.BooleanField(verbose_name=u'Рекорд ли трассы для женщин',
		default=False, blank=True, db_column='dj_is_female_course_record')

	comment = models.CharField(verbose_name=u'Комментарий', max_length=250, db_column='Komm', blank=True)
	comment_private = models.CharField(verbose_name=u'Комментарий администраторам (не виден посетителям)',
		max_length=250, db_column='dj_comment_private', blank=True)
	precise_name = models.CharField(verbose_name=u'Уточнение названия', max_length=50, db_column='dj_precise_name', blank=True)
	gps_track = models.URLField(verbose_name=u'Ссылка на трек на Страве', max_length=300, db_column='dj_gps_track', blank=True)

	start_date = models.DateField(verbose_name=u'Дата старта (если отличается от даты старта забега)',
		default=None, null=True, blank=True, db_column='dj_start_date')
	start_time = models.TimeField(verbose_name=u'Время старта (если отличается от времени старта забега)',
		default=None, null=True, blank=True, db_column='dj_start_time')
	finish_date = models.DateField(verbose_name=u'Дата финиша (если отличается от даты старта)',
		default=None, null=True, blank=True, db_column='dj_finish_date', db_index=True)

	elevation_meters = models.IntegerField(verbose_name=u'Общий подъём в метрах', default=None, null=True, blank=True, db_column='dj_elevation_meters')
	descent_meters = models.IntegerField(verbose_name=u'Общий спуск в метрах', default=None, null=True, blank=True, db_column='dj_descent_meters')
	altitude_start_meters = models.IntegerField(verbose_name=u'Высота старта', default=None, null=True, blank=True, db_column='dj_altitude_start_meters')
	altitude_finish_meters = models.IntegerField(verbose_name=u'Высота финиша',
		default=None, null=True, blank=True, db_column='dj_altitude_finish_meters')

	start_lat = models.FloatField(verbose_name=u'Широта точки старта', default=None, null=True, blank=True, db_column='dj_start_lat')
	start_lon = models.FloatField(verbose_name=u'Долгота точки старта', default=None, null=True, blank=True, db_column='dj_start_lon')
	loaded = models.SmallIntegerField(verbose_name=u'Загружены ли результаты в базу данных результатов',
		default=RESULTS_NOT_LOADED, choices=LOADED_TYPES, db_column='dj_loaded')
	loaded_from = models.CharField(max_length=200, blank=True, db_column='dj_loaded_from')
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Кто добавил забег на сайт',
		on_delete=models.SET_NULL, default=None, null=True, blank=True, db_column='dj_created_by')

	was_checked_for_klb = models.BooleanField(verbose_name=u'Обработана в КЛБМатч', default=False, blank=True, db_column='dj_was_checked_for_klb')
	has_no_results = models.BooleanField(verbose_name=u'Результатов нет и не будет', default=False, blank=True, db_column='dj_has_no_results')
	is_for_handicapped = models.BooleanField(verbose_name=u'Для спортсменов с ограниченными возможностями',
		default=False, blank=True, db_column='dj_is_for_handicapped')
	is_multiday = models.BooleanField(verbose_name=u'Многодневный забег, в КЛБМатч считать только бонусы',
		default=False, blank=True, db_column='dj_is_multiday')

	price = models.IntegerField(verbose_name=u'Цена в рублях', default=None, null=True, blank=True, db_column='dj_price')
	price_can_change = models.BooleanField(verbose_name=u'Растёт ли цена со временем', default=False, blank=True, db_column='dj_price_can_change')
	itra_score = models.SmallIntegerField(verbose_name=u'Очки ITRA', default=0)
	def clean(self):
		if not (0 <= self.itra_score <= 6):
			raise ValidationError(u'Очки ITRA должны быть в пределах от 0 до 6')
		if self.itra_score:
			surface_type = self.surface_type
			if not surface_type:
				surface_type = self.event.surface_type
			if not surface_type:
				surface_type = self.event.series.surface_type
			if surface_type not in (SURFACE_SOFT, SURFACE_MOUNTAIN):
				raise ValidationError(u'Очки ITRA могут стоять только у кроссов, трейлов и горного бега')

		if self.distance_real:
			if self.distance_real == self.distance:
				raise ValidationError(u'Официальная и фактическая дистанции не могут совпадать.')
			if self.distance_real.distance_type != self.distance.distance_type:
				raise ValidationError(u'Типы официальной и фактической дистанций не могут отличаться.')

		if self.surface_type and (self.surface_type == self.event.surface_type):
			self.surface_type = SURFACE_DEFAULT

		self.series_raw = self.event.series.id
		self.distance_raw = self.distance.distance_raw
		self.race_type_raw = self.distance.race_type_raw	
	class Meta:
		db_table = "ProbegDist"
		verbose_name = u'Дистанция в рамках забега'
		index_together = [
			["event", "distance", "id"],
			["start_date", "start_time"],
		]
		unique_together = (
			("event", "distance_raw", "race_type_raw", "precise_name"), ("event", "distance", "precise_name"),
		)
	#def date(self):
	#	return self.start_date.strftime("%d.%m.%Y")
	def winner_male(self):
		res = self.winner_male_fname + " " + self.winner_male_lname
		# if self.winner_male_city:
		# 	res += " (" + self.winner_male_city + ")"
		return res
	def winner_female(self):
		res = self.winner_female_fname + " " + self.winner_female_lname
		# if self.winner_female_city:
		# 	res += " (" + self.winner_female_city + ")"
		return res
	def get_official_results(self):
		return self.result_set.filter(source=RESULT_SOURCE_DEFAULT).order_by('status', 'place', 'result', 'lname', 'fname', 'midname')
	def fill_winners_info(self, to_save=True):
		results = self.get_official_results()
		winner_male = results.filter(gender=GENDER_MALE, place_gender=1).order_by('lname', 'fname').first()
		if winner_male:
			self.winner_male_fname = winner_male.fname
			self.winner_male_lname = winner_male.lname
			self.winner_male_city = winner_male.strCity()
			self.winner_male_result = self.distance.strResult(winner_male.result, round_hundredths=True, for_best_result=True)
			self.winner_male_user = winner_male.user
			self.winner_male_runner = winner_male.runner
		else:
			self.winner_male_fname = ''
			self.winner_male_lname = ''
			self.winner_male_city = ''
			self.winner_male_result = ''
			self.winner_male_user = None
			self.winner_male_runner = None
		winner_female = results.filter(gender=GENDER_FEMALE, place_gender=1).order_by('lname', 'fname').first()
		if winner_female:
			self.winner_female_fname = winner_female.fname
			self.winner_female_lname = winner_female.lname
			self.winner_female_city = winner_female.strCity()
			self.winner_female_result = self.distance.strResult(winner_female.result, round_hundredths=True, for_best_result=True)
			self.winner_female_user = winner_female.user
			self.winner_female_runner = winner_female.runner
		else:
			self.winner_female_fname = ''
			self.winner_female_lname = ''
			self.winner_female_city = ''
			self.winner_female_result = ''
			self.winner_female_user = None
			self.winner_female_runner = None
		if to_save:
			self.save()
	def reset_winners_info(self, to_save=True):
		self.winner_male_fname = ''
		self.winner_male_lname = ''
		self.winner_male_city = ''
		self.winner_male_result = ''
		self.winner_male_user = None
		self.winner_male_runner = None
		self.winner_female_fname = ''
		self.winner_female_lname = ''
		self.winner_female_city = ''
		self.winner_female_result = ''
		self.winner_female_user = None
		self.winner_female_runner = None
		self.is_male_course_record = False
		self.is_female_course_record = False
		if to_save:
			self.save()
	def get_n_participants_finished_women(self):
		if self.n_participants_finished and (self.n_participants_finished_men is not None):
			return self.n_participants_finished - self.n_participants_finished_men
		return ""
	def get_n_participants_women(self):
		if self.n_participants and (self.n_participants_men is not None):
			return self.n_participants - self.n_participants_men
		return ""
	def get_men_percent(self):
		if self.n_participants_finished and self.n_participants_finished_men:
			return min(100, int(self.n_participants_finished_men * 100 / self.n_participants_finished))
		return 100
	def get_women_percent(self):
		return 100 - self.get_men_percent()
	def get_precise_name(self):
		res = unicode(self.distance)
		if self.precise_name:
			res += u' ({})'.format(self.precise_name)
		return res
	def distance_with_heights(self):
		res = self.get_precise_name()
		heights = []
		if self.elevation_meters:
			heights.append(u'+{}м'.format(self.elevation_meters))
		if self.descent_meters:
			heights.append(u'-{}м'.format(self.descent_meters))
		return res + ((' (' + ', '.join(heights) + ')') if heights else '')
	def distance_with_details(self, details_level=1):
		res = unicode(self.distance)
		details = []
		if self.precise_name:
			details.append(self.precise_name)
		if details_level:
			if self.elevation_meters:
				details.append(u'+{}&nbsp;м'.format(self.elevation_meters))
			if self.descent_meters:
				details.append(u'-{}&nbsp;м'.format(self.descent_meters))
			if self.surface_type:
				details.append(u'тип: {}'.format(self.get_surface_type_display()))
			if self.itra_score:
				details.append(u'ITRA {}'.format(self.itra_score))
			if not self.event.is_in_past():
				if self.start_date:
					if self.start_time:
						details.append(u'старт {} в&nbsp;{}'.format(self.start_date.strftime('%d.%m.%Y'), self.start_time.strftime("%H:%M")))
					else:
						details.append(u'старт {}'.format(self.start_date.strftime('%d.%m.%Y')))
				elif self.start_time:
					details.append(u'старт в&nbsp;{}'.format(self.start_time.strftime("%H:%M")))
			elif self.n_participants:
				details.append(u'{}&nbsp;результат{}'.format(self.n_participants, results_util.plural_ending_new(self.n_participants, 1)))
			elif self.loaded == RESULTS_SOME_OFFICIAL:
				details.append(u'загружена часть официальных результатов')
			elif self.loaded == RESULTS_SOME_UNOFFICIAL:
				n_unof = self.get_unofficial_results().count()
				if n_unof:
					details.append(u'{}&nbsp;неофициальны{} результат{}'.format(
						n_unof, results_util.plural_ending_new(n_unof, 5), results_util.plural_ending_new(n_unof, 1)))
		if details:
			res += ' (' + ', '.join(details) + ')'
		return res
	def get_pace(self, value): # In seconds per km
		if self.distance_real:
			return self.distance_real.get_pace(value)
		else:
			return self.distance.get_pace(value)
	def get_distance_klb_status(self): # Check only distances (official and real), not event
		if self.loaded == RESULTS_LOADED and self.n_participants == 1 and self.event.start_date.year >= 2019:
			return KLB_STATUS_ONLY_ONE_PARTICIPANT
		if self.distance.distance_type == TYPE_MINUTES:
			return KLB_STATUS_OK
		if self.distance.distance_type == TYPE_METERS:
			year = self.event.start_date.year
			if self.distance.length < models_klb.get_min_distance_for_score(year):
				return KLB_STATUS_SHORT_DISTANCE
			# if self.distance.length > models_klb.get_max_distance_for_score(year):
			# 	return KLB_STATUS_LONG_DISTANCE
			if self.distance_real and (self.distance_real.length < models_klb.get_min_distance_for_bonus(year)):
				return KLB_STATUS_SHORT_REAL_DISTANCE
			return KLB_STATUS_OK
		return KLB_STATUS_WRONG_DISTANCE_TYPE
	def get_klb_status(self):
		event_status = self.event.get_klb_status()
		if event_status != KLB_STATUS_OK:
			return event_status
		if self.start_date and (self.start_date.year != self.event.start_date.year):
			return KLB_STATUS_WRONG_YEAR
		return self.get_distance_klb_status()
	def get_distance_and_flag_for_klb(self):
		if self.distance_real and (self.distance_real.length < self.distance.length):
			distance = self.distance_real
			was_real_distance_used = DISTANCE_FOR_KLB_REAL
		else:
			distance = self.distance
			was_real_distance_used = DISTANCE_FOR_KLB_FORMAL
		return distance, was_real_distance_used
	def parse_result(self, value):
		if self.distance.distance_type == TYPE_MINUTES:
			return int_safe(value)
		else:
			return string2centiseconds(value)
	def get_reverse_url(self, target):
		return reverse(target, kwargs={'race_id': self.id})
	def get_absolute_url(self):
		return self.get_reverse_url('results:race_details')
	def get_details_url(self):
		return reverse('results:race_details', kwargs={'race_id': self.id, 'tab_editor': 1})
	def get_unoff_details_url(self):
		return reverse('results:race_details', kwargs={'race_id': self.id, 'tab_unofficial': 1})
	def get_update_url(self):
		return self.get_reverse_url('editor:race_update')
	def get_editor_url(self):
		return self.event.get_editor_url() + '#races'
	def get_reg_editor_url(self):
		return self.get_reverse_url('editor:reg_race_details')
	def get_results_editor_url(self):
		return self.get_reverse_url('editor:race_details')
	def get_update_stat_url(self):
		return self.get_reverse_url('editor:race_update_stat')
	def get_add_unoff_result_url(self):
		return self.get_reverse_url('editor:race_add_unoff_result')
	def get_ajax_runners_list_url(self):
		return self.get_reverse_url('editor:runners_list')
	def get_parkrun_reload_url(self):
		return self.get_reverse_url('editor:reload_parkrun_results')
	def get_result_list_url(self):
		return self.get_reverse_url('editor:race_result_list')
	def get_delete_off_results_url(self):
		return self.get_reverse_url('editor:race_delete_off_results')
	def get_klb_editor_url(self, page=None):
		if page is None:
			return self.get_reverse_url('editor:klb_race_details')
		else:
			return reverse('editor:klb_race_details', kwargs={'race_id': self.id, 'page': page})
	def get_klb_process_url(self):
		return self.get_reverse_url('editor:klb_race_process')
	def get_klb_add_results_url(self):
		return self.get_reverse_url('editor:klb_race_add_results')
	def get_unofficial_results(self):
		# return self.get_results_by_source(RESULT_SOURCE_USER)
		res = self.result_set.exclude(source=RESULT_SOURCE_DEFAULT).select_related('runner__klb_person', 'user__user_profile', 'result_on_strava')
		if self.distance.distance_type == TYPE_MINUTES:
			res = res.order_by('status', '-result')
		else:
			res = res.order_by('status', 'result')
		return res
	def __unicode__(self):
		# return unicode(self.event) + u" (" + unicode(self.distance) + u")"
		return self.distance_with_details(details_level=0)
	def name_with_event(self):
		return unicode(self.event) + u" (" + unicode(self.distance) + u")"
	def get_reg_question_set_for_today(self):
		return self.reg_question_set.filter(Q(finish_date__gte=datetime.date.today()) | Q(finish_date=None))
	@classmethod
	def get_races_by_countries(cls, year, country_ids):
		return Race.objects.filter(event__in=Event.get_events_by_countries(year, country_ids))
	@classmethod
	def get_russian_races(cls, year):
		return cls.get_races_by_countries(year, ['RU'])
	def delete(self, *args, **kwargs):
		starrating.aggr.race_deletion.delete_race_and_ratings(self, *args, **kwargs)

class Category_size(models.Model):
	race = models.ForeignKey(Race, on_delete=models.CASCADE)
	name = models.CharField(verbose_name=u'Название группы', max_length=100, blank=True)
	size = models.IntegerField(verbose_name=u'Число участников в группе', default=None, null=True, blank=True, db_index=True)
	class Meta:
		db_table = "dj_category_size"
		unique_together = (("race", "name"),)
		index_together = [
			["race", "size"],
		]

def validate_image(fieldfile_obj):
	try: # TODO Delete when removed avatars are back
		filesize = fieldfile_obj.file.size
		LIMIT_MB = 5
		if filesize > LIMIT_MB*1024*1024:
			raise ValidationError("Размер файла не может быть больше {} мегабайт.".format(LIMIT_MB))
	except:
		pass
def file_extension(filename, default="jpg"):
	if not ("." in filename):
		return default
	extension = filename.split(".")[-1].lower()
	if 2 <= len(extension) <= 5:
		return extension
	else:
		return default
def logo_name(instance, filename):
	new_name = "dj_media/clubs/logo/" + unicode(instance.id) + "." + file_extension(filename)
	fullname = os.path.join(settings.MEDIA_ROOT, new_name)
	try:
		os.remove(fullname)
	except:
		pass
	return new_name
def logo_thumb_name(instance, filename):
	new_name = "dj_media/clubs/logo/" + unicode(instance.id) + "_thumb." + file_extension(filename)
	fullname = os.path.join(settings.MEDIA_ROOT, new_name)
	try:
		os.remove(fullname)
	except:
		pass
	return new_name
INDIVIDUAL_RUNNERS_CLUB_NUMBER = 75
class Club(models.Model):
	id = models.AutoField(primary_key=True, db_column='IDKLB')
	name = models.CharField(verbose_name=u'Название', max_length=100, db_index=True, db_column='titul', blank=False)
	country = models.ForeignKey(Country, verbose_name=u'Страна (устар.)', default="RU", null=True, blank=True, on_delete=models.PROTECT,
		db_column='dj_country_id')
	city = models.ForeignKey(City, verbose_name=u'Город', default=None, null=True, blank=True, on_delete=models.PROTECT, db_column='dj_city_id')
	editors = models.ManyToManyField(settings.AUTH_USER_MODEL, through='Club_editor', through_fields=('club', 'user'),
		related_name='clubs_to_edit_set')
	is_active = models.BooleanField(verbose_name=u'Показывать ли клуб на странице клубов', db_column='dj_is_active', default=True, blank=True)
	is_member_list_visible = models.BooleanField(verbose_name=u'Виден ли всем список членов', db_column='dj_is_member_list_visible',
		default=False, blank=True)
	members_can_pay_themselves = models.BooleanField(verbose_name=u'Могут ли члены клуба платить за участие в КЛБМатче по одному', default=False, blank=True)

	country_raw = models.CharField(verbose_name=u'Страна (устар.)', max_length=100, db_column='Strana', blank=True)
	region_raw = models.CharField(verbose_name=u'Регион (устар.)', max_length=100, db_column='Obl', blank=True)
	city_raw = models.CharField(verbose_name=u'Город (устар.)', max_length=100, db_column='Gorod', blank=True)

	url_site = models.CharField(verbose_name=u'Сайт клуба', max_length=200, db_column='www', blank=True)
	url_logo = models.CharField(verbose_name=u'Логотип клуба (устар.)', max_length=100, db_column='Emblema', blank=True)
	logo = models.ImageField(verbose_name=u'Файл с эмблемой (не больше 2 мегабайт)', max_length=255, upload_to=logo_name,
		validators=[validate_image], blank=True)
	logo_thumb = models.ImageField(max_length=255, upload_to=logo_thumb_name, blank=True)
	url_vk = models.URLField(verbose_name=u'Страничка ВКонтакте', max_length=100, blank=True)
	url_facebook = models.URLField(verbose_name=u'Страничка в фейсбуке', max_length=100, blank=True)

	birthday = models.DateField(verbose_name=u'Дата рождения', db_column='DataSozdan', default=None, null=True, blank=True)
	n_members = models.IntegerField(verbose_name=u'Число членов', db_column='NMembers', default=None, null=True, blank=True)
	address_street = models.CharField(verbose_name=u'Почтовый адрес', max_length=MAX_POSTAL_ADDRESS_LENGTH, db_column='Adres', blank=True)
	email = models.EmailField(verbose_name=u'E-mail', max_length=MAX_EMAIL_LENGTH, db_column='email', blank=True)
	phone_club = models.CharField(verbose_name=u'Телефон', max_length=MAX_PHONE_NUMBER_LENGTH, db_column='tfonklb', blank=True)
	phone_mob = models.CharField(verbose_name=u'Мобильный телефон', max_length=MAX_PHONE_NUMBER_LENGTH, db_column='tfon', blank=True)
	phone_rab = models.CharField(verbose_name=u'Рабочий телефон', max_length=MAX_PHONE_NUMBER_LENGTH, db_column='tfonrab', blank=True)
	phone_dom = models.CharField(verbose_name=u'Домашний телефон', max_length=MAX_PHONE_NUMBER_LENGTH, db_column='tfondom', blank=True)
	other_contacts = models.CharField(verbose_name=u'Другие контакты', max_length=200, db_column='OtherContacts', blank=True)

	head_name = models.CharField(verbose_name=u'Имя', max_length=100, db_column='Predsedatel', blank=True)
	head_address = models.CharField(verbose_name=u'Почтовый адрес', max_length=MAX_POSTAL_ADDRESS_LENGTH, db_column='AdresPr', blank=True)
	head_email = models.EmailField(verbose_name=u'E-mail', max_length=MAX_EMAIL_LENGTH, db_column='emailPr', blank=True)
	head_ICQ = models.CharField(verbose_name=u'ICQ', max_length=100, db_column='PrContactICQ', blank=True)
	head_skype = models.CharField(verbose_name=u'Skype', max_length=100, db_column='PrContactSkype', blank=True)
	head_vk = models.URLField(verbose_name=u'Страничка ВКонтакте', max_length=100, blank=True)
	head_facebook = models.URLField(verbose_name=u'Страничка в фейсбуке', max_length=100, blank=True)
	head_other_contacts = models.CharField(verbose_name=u'Другие контакты', max_length=200, db_column='dj_head_other_contacts', blank=True)

	speaker_name = models.CharField(verbose_name=u'Контактное лицо', max_length=100, db_column='dj_speaker_name', blank=True)
	speaker_email = models.EmailField(verbose_name=u'E-mail контактного лица', max_length=MAX_EMAIL_LENGTH, db_column='dj_speaker_email', blank=True)

	color = models.CharField(verbose_name=u'Цвет (устар.)', max_length=7, db_column='color', blank=True)
	tales = models.TextField(verbose_name=u'История клуба', max_length=20000, db_column='Tales', blank=True)
	training_timetable = models.CharField(verbose_name=u'Расписание регулярных тренировок', max_length=100, db_column='dj_training_timetable', blank=True)
	training_cost = models.CharField(verbose_name=u'Стоимость тренировок', max_length=100, db_column='dj_training_cost', blank=True)
	# can_add_results_to_ex_members = models.BooleanField(verbose_name=u'Предлагать ли добавлять результаты бывшим членам клуба',
	# 	default=True, db_column='dj_can_add_results_to_ex_members', blank=True)

	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Кто добавил в БД', on_delete=models.SET_NULL,
		default=None, null=True, blank=True)
	added_time = models.DateTimeField(verbose_name=u'Время занесения в БД', auto_now_add=True, null=True, blank=True)
	last_update_time = models.DateTimeField(verbose_name=u'Дата последнего обновления', null=True, blank=True)
	comment_private = models.CharField(verbose_name=u'Комментарий администраторам (не виден посетителям)',
		max_length=250, db_column='dj_comment_private', blank=True)
	class Meta:
		db_table = "KLB1"
		index_together = [
			["country", "name"],
		]
	def clean(self):
		if self.city:
			self.city_raw = self.city.name_full(with_nbsp=False)
			if self.city.region.country.has_regions:
				self.region_raw = self.city.region.name
			else:
				self.region_raw = ""
			self.country_raw = self.city.region.country.name
		else:
			self.city_raw = ""
			self.region_raw = ""
			self.country_raw = ""

		if self.url_vk and not self.url_vk.startswith(VK_POSSIBLE_PREFIXES):
			raise ValidationError({'url_vk': u'Адрес ВКонтакте должен начинаться со строк ' + u', '.join(VK_POSSIBLE_PREFIXES)})
		if self.url_facebook and not self.url_facebook.startswith(FB_POSSIBLE_PREFIXES):
			raise ValidationError({'url_facebook': u'Адрес страницы в фейсбуке должен начинаться со строк ' + u', '.join(FB_POSSIBLE_PREFIXES)})
		if self.head_vk and not self.head_vk.startswith(VK_POSSIBLE_PREFIXES):
			raise ValidationError({'head_vk': u'Адрес ВКонтакте должен начинаться со строк ' + u', '.join(VK_POSSIBLE_PREFIXES)})
		if self.head_facebook and not self.head_facebook.startswith(FB_POSSIBLE_PREFIXES):
			raise ValidationError({'head_facebook': u'Адрес страницы в фейсбуке должен начинаться со строк ' + u', '.join(FB_POSSIBLE_PREFIXES)})
	def make_thumbnail(self):
		return make_thumb(self.logo, self.logo_thumb, 140, 140)
	def strCity(self):
		if self.city:
			return self.city.nameWithCountry()
		return ''
	def strCityShort(self):
		if self.city:
			return self.city.nameWithCountry(with_region=False)
		return ''
	def get_next_team_name(self, year): # 'Парсек' for first team, 'Парсек-2' for second, et cetera
		n_year_teams = self.klb_team_set.filter(year=year).count()
		if n_year_teams == 0:
			return self.name
		else:
			return u'{}-{}'.format(self.name, n_year_teams + 1)
	def has_dependent_objects(self):
		return self.klb_team_set.exists()
	def get_active_members_list(self):
		today = datetime.date.today()
		return self.club_member_set.filter(
				Q(date_registered=None) | Q(date_registered__lte=today),
				Q(date_removed=None) | Q(date_removed__gte=today),
			)
	def get_active_members_or_klb_participants_runner_ids(self):
		return set(self.get_active_members_list().values_list('runner_id', flat=True)) \
			| set(Klb_participant.objects.filter(match_year__gte=CUR_KLB_YEAR, team__club=self).values_list('klb_person__runner__id', flat=True))
	def get_reverse_url(self, target):
		return reverse(target, kwargs={'club_id': self.id})
	def get_absolute_url(self):
		return self.get_reverse_url('results:club_details')
	def get_editor_url(self):
		return self.get_reverse_url('editor:club_details')
	def get_delete_url(self):
		return self.get_reverse_url('editor:club_delete')
	def get_history_url(self):
		return self.get_reverse_url('editor:club_changes_history')
	def get_planned_starts_url(self):
		return self.get_reverse_url('results:planned_starts')
	def get_club_records_url(self):
		return self.get_reverse_url('results:club_records')
	def get_payment_url(self):
		return self.get_reverse_url('results:klb_club_payment')
	def get_members_list_url(self):
		return self.get_reverse_url('results:club_members')
	def get_all_members_list_url(self):
		return self.get_reverse_url('results:club_members_all')
	def get_add_new_member_url(self):
		return self.get_reverse_url('editor:club_add_new_member')
	def get_add_cur_year_team_url(self):
		return self.get_reverse_url('editor:add_cur_year_team')
	def get_add_next_year_team_url(self):
		return self.get_reverse_url('editor:add_next_year_team')
	def __unicode__(self):
		res = self.name
		if self.city or self.country:
			res += u" ("
			if self.city:
				res += self.city.name
			if self.city and self.country:
				res += ", "
			if self.country:
				res += self.country.name
			res += u")"
		return res

class Club_editor(models.Model):
	user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
	club = models.ForeignKey(Club, on_delete=models.CASCADE)
	added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="club_editors_added_by_user")
	added_time = models.DateTimeField(auto_now_add=True)
	class Meta:
		db_table = "dj_club_editor"
		ordering = ['club__name']

class Club_name(models.Model):
	club = models.ForeignKey(Club, on_delete=models.CASCADE)
	name = models.CharField(verbose_name=u'Название', max_length=100, db_index=True, blank=False)
	added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
	added_time = models.DateTimeField(auto_now_add=True)
	class Meta:
		db_table = "dj_club_name"
		unique_together = (
			("club", "name"),
		)

def get_name_condition(lname, fname, midname):
	if midname:
		return Q(lname=lname, fname=fname, midname=midname) | Q(lname=lname, fname=fname, midname='')
	else:
		return Q(lname=lname, fname=fname)
class Extra_name(models.Model):
	runner = models.ForeignKey('Runner', verbose_name=u'Бегун', on_delete=models.CASCADE, null=True, default=None, blank=True)
	lname = models.CharField(verbose_name=u'Фамилия', max_length=100)
	fname = models.CharField(verbose_name=u'Имя', max_length=100)
	midname = models.CharField(verbose_name=u'Отчество (необязательно)', max_length=100, blank=True)
	comment = models.CharField(verbose_name=u'Комментарий', max_length=1000, blank=True)
	added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
	added_time = models.DateTimeField(verbose_name=u'Время занесения в БД', auto_now_add=True)
	class Meta:
		db_table = "dj_extra_name"
		index_together = [
			["runner", "lname", "fname", "midname"],
		]
	def get_name_condition(self):
		return get_name_condition(self.lname, self.fname, self.midname)
	def __unicode__(self):
		res = self.fname
		if self.midname != "":
			res += " " + self.midname
		res += " " + self.lname
		return res

PROFILE_NEWS_NOTHING = 0
PROFILE_NEWS_CITY = 1
PROFILE_NEWS_REGION = 2
PROFILE_NEWS_DISTRICT = 3
PROFILE_NEWS_COUNTRY = 4
PROFILE_NEWS_ALL = 5
PROFILE_NEWS_DEFAULT = PROFILE_NEWS_ALL
PROFILE_NEWS_CHOICES = (
	(PROFILE_NEWS_NOTHING, u'никакие'),
	(PROFILE_NEWS_CITY, u'моего города'),
	(PROFILE_NEWS_REGION, u'моего региона (для России, Украины, Беларуси)'),
	(PROFILE_NEWS_DISTRICT, u'моего фед. округа (только для России)'),
	(PROFILE_NEWS_COUNTRY, u'моей страны'),
	(PROFILE_NEWS_ALL, u'все'),
)
AVATAR_SIZE = (200, 400)
def avatar_name(instance, filename):
	new_name = "dj_media/avatar/" + unicode(instance.user.id) + "." + file_extension(filename)
	fullname = os.path.join(settings.MEDIA_ROOT, new_name)
	try:
		os.remove(fullname)
	except:
		pass
	return new_name
def avatar_thumb_name(instance, filename):
	new_name = "dj_media/avatar/" + unicode(instance.user.id) + "_thumb." + file_extension(filename)
	fullname = os.path.join(settings.MEDIA_ROOT, new_name)
	try:
		os.remove(fullname)
	except:
		pass
	return new_name
VERIFICATION_CODE_LENGTH = 10

DEFAULT_WHEN_TO_ASK_FILL_MARKS = datetime.date(1900, 1, 1)

class User_profile(models.Model):
	user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
	midname = models.CharField(verbose_name=u'Отчество (необязательно)', max_length=100, blank=True)
	nickname = models.CharField(verbose_name=u'Ник для подписи новостей', max_length=100, blank=True)
	gender = models.SmallIntegerField(verbose_name=u'Пол', default=GENDER_UNKNOWN, choices=GENDER_CHOICES)
	comment = models.CharField(verbose_name=u'Комментарий', max_length=1000, blank=True)
	city = models.ForeignKey(City, verbose_name=u'Город', default=None, null=True, blank=True, on_delete=models.PROTECT)
	club = models.ForeignKey(Club, verbose_name=u'Клуб (не используется)', default=None, null=True, blank=True, on_delete=models.PROTECT)
	birthday = models.DateField(verbose_name=u'День рождения', db_index=True, default=None, null=True, blank=True)
	is_public = models.BooleanField(verbose_name=u'Показывать другим посетителям мой профиль на сайте', default=True, blank=True)
	avatar = models.ImageField(verbose_name=u'Аватар (не больше 2 мегабайт)', max_length=255, upload_to=avatar_name,
		validators=[validate_image], blank=True)
	avatar_thumb = models.ImageField(max_length=255, upload_to=avatar_thumb_name, blank=True)
	email_is_verified = models.BooleanField(verbose_name=u'Адрес электронной почты подтверждён', default=False, blank=True)
	email_verification_code = models.CharField(verbose_name=u'Код для проверки электронного адреса',
		max_length=VERIFICATION_CODE_LENGTH, blank=True)
	ok_to_send_news = models.BooleanField(verbose_name=u'Хочу получать письма с новостями сайта (не чаще раза в две недели)', default=True, blank=True)
	ok_to_send_results = models.BooleanField(verbose_name=u'Хочу получать письма при появлении в базе новых моих результатов', default=True, blank=True)
	is_agree_with_policy = models.BooleanField(verbose_name=u'Согласен на обработку моих персональных данных', default=False, blank=True)
	hide_parkruns_in_calendar = models.BooleanField(verbose_name=u'По умолчанию скрывать паркраны на страницах календаря', default=False, blank=True)
	strava_account = models.BigIntegerField(verbose_name=u'Аккаунт в Strava (число после strava.com/athletes/)', default=None, null=True, blank=True)

	n_starts = models.SmallIntegerField(verbose_name=u'Число финишей', default=None, null=True, blank=True)
	total_length = models.IntegerField(verbose_name=u'Общая пройденная дистанция в метрах', default=None, null=True, blank=True)
	total_time = models.IntegerField(verbose_name=u'Общее время на забегах в сотых секунды', default=None, null=True, blank=True)
	has_many_distances = models.BooleanField(verbose_name=u'Имеет ли больше разных дистанций, чем отображаем по умолчанию', default=False)
	n_possible_results = models.SmallIntegerField(verbose_name=u'Число результатов с подходящим именем', default=0)

	is_extended_editor = models.BooleanField(verbose_name=u'Может редактировать старые забеги', default=False)

	# Data for registration on events
	phone_number = models.CharField(verbose_name=u'Номер телефона', max_length=MAX_PHONE_NUMBER_LENGTH, blank=True)
	emergency_name = models.CharField(verbose_name=u'Имя знакомого на экстренный случай', max_length=20, blank=True)
	emergency_phone_number = models.CharField(verbose_name=u'Номер телефона знакомого на экстренный случай', max_length=MAX_PHONE_NUMBER_LENGTH, blank=True)
	zipcode = models.CharField(verbose_name=u'Почтовый индекс', max_length=8, blank=True)
	address = models.CharField(verbose_name=u'Почтовый адрес', max_length=100, blank=True)
	club_name = models.CharField(verbose_name=u'Клуб', max_length=50, blank=True)

	to_ask_fill_marks = models.BooleanField(verbose_name=u'Предлагать ли оценивать все забеги', default=True)
	when_to_ask_fill_marks = models.DateField(verbose_name=u'Дата, раньше которой не предлагать оценивать все забеги', default=DEFAULT_WHEN_TO_ASK_FILL_MARKS)

	__original_club_name = None
	def __init__(self, *args, **kwargs):
		super(User_profile, self).__init__(*args, **kwargs)
		self.__original_club_name = self.club_name
	def save(self, *args, **kwargs):
		if (self.club_name != self.__original_club_name) and hasattr(self.user, 'runner'):
			self.user.runner.club_name = self.club_name
			self.user.runner.save()
			log_obj_create(USER_ROBOT_CONNECTOR, self.user.runner, ACTION_UPDATE, field_list=['club_name'], verified_by=USER_ROBOT_CONNECTOR,
				comment=u'При изменении клуба у пользователя')
		super(User_profile, self).save(*args, **kwargs)
		self.__original_club_name = self.club_name
	def clean(self):
		self.midname = self.midname.strip()
	def make_thumbnail(self):
		return make_thumb(self.avatar, self.avatar_thumb, 200, 400)
	def get_name_condition(self):
		return get_name_condition(self.user.last_name, self.user.first_name, self.midname)
	def create_runner(self, creator, comment=''):
		user = self.user
		runner = Runner.objects.create(
			user=user,
			lname=user.last_name,
			fname=user.first_name,
			midname=self.midname,
			gender=self.gender,
			birthday=self.birthday,
			birthday_known=(self.birthday is not None),
			city=self.city,
			created_by=creator,
		)
		log_obj_create(creator, runner, ACTION_CREATE, comment=comment)
		return runner
	def get_active_klb_participants_with_teams(self):
		if hasattr(self.user, 'runner'):
			klb_person = self.user.runner.klb_person
			if klb_person:
				return klb_person.klb_participant_set.filter(match_year__gte=CUR_KLB_YEAR, team__isnull=False)
		return Klb_participant.objects.none()
	def can_add_results_to_others(self):
		if is_admin(self.user) or self.user.club_editor_set.exists():
			return True
		return self.get_active_klb_participants_with_teams().exists()
	def get_club_set_to_add_results(self):
		club_ids = set()
		club_editor_set = self.user.club_editor_set
		if club_editor_set.exists():
			club_ids = set(self.user.club_editor_set.values_list('club_id', flat=True))
		else:
			active_klb_participants_with_teams = self.get_active_klb_participants_with_teams()
			if active_klb_participants_with_teams.exists():
				club_ids = set(active_klb_participants_with_teams.values_list('team__club_id', flat=True))
		return Club.objects.filter(pk__in=club_ids).order_by('name') if club_ids else []
	def get_runners_to_add_results(self, race=None, race_is_for_klb=False, club=None, for_given_club_only=False):
		club_editor_set = self.user.club_editor_set
		club_ids = set()
		runner_ids = set()
		individual_participants_only = False

		if for_given_club_only:
			if club:
				club_ids = [club.id]
				runner_ids = set(Club_member.objects.filter(club_id__in=club_ids).values_list('runner_id', flat=True))
			else: # For individual KLB participants
				runner_ids = set(Klb_participant.objects.filter(match_year__in=[CUR_KLB_YEAR, NEXT_KLB_YEAR], team=None).values_list(
					'klb_person__runner__id', flat=True))
				individual_participants_only = True
		elif is_admin(self.user):
			club_ids = [CLUB_ID_FOR_ADMINS] # Just a hack so that admins understand how club leader's interface looks like
			# runner_ids = set(Club_member.objects.filter(club_id__in=club_ids).values_list('runner_id', flat=True))
			runner_ids = set(Klb_participant.objects.filter(match_year__in=[CUR_KLB_YEAR, NEXT_KLB_YEAR], team__club_id__in=club_ids).values_list(
				'klb_person__runner__id', flat=True))
		elif club_editor_set.exists():
			club_ids = set(club_editor_set.values_list('club_id', flat=True))
			runner_ids = set(Klb_participant.objects.filter(match_year__in=[CUR_KLB_YEAR, NEXT_KLB_YEAR], team__club_id__in=club_ids).values_list(
				'klb_person__runner__id', flat=True))
			if club_ids != set([PARSEK_CLUB_ID]): # Parsek has too many members altogether
				runner_ids |= set(Club_member.objects.filter(club_id__in=club_ids).values_list('runner_id', flat=True))
		else: # User is a regular member of some KLB team
			active_klb_participants_with_teams = self.get_active_klb_participants_with_teams()
			if active_klb_participants_with_teams.exists():
				active_team_ids = set(active_klb_participants_with_teams.values_list('team_id', flat=True))
				runner_ids = set(Klb_participant.objects.filter(team_id__in=active_team_ids).values_list('klb_person__runner__id', flat=True))
				club_ids = set(active_klb_participants_with_teams.values_list('team__club_id', flat=True))

		if not runner_ids:
			return []

		runners_already_in_race_ids = set()
		if race:
			event_date = race.event.start_date
			runners_already_in_race_ids = set(race.result_set.values_list('runner_id', flat=True))

			active_klb_participants = Klb_participant.objects.filter(
				Q(date_registered=None) | Q(date_registered__lte=event_date),
				Q(date_removed=None) | Q(date_removed__gte=event_date),
				was_deleted_from_team=False,
				match_year=event_date.year)
			if individual_participants_only:
				active_klb_participants = active_klb_participants.filter(team=None)
			else:
				active_klb_participants = active_klb_participants.filter(team__club__in=club_ids)

			active_klb_runner_ids = set(active_klb_participants.values_list('klb_person__runner__id', flat=True))
			runner_ids |= active_klb_runner_ids

		runners = Runner.objects.filter(pk__in=runner_ids)
		if race:
			runners = runners.filter(Q(deathday=None) | Q(deathday__gte=event_date))

		res = OrderedDict()
		for runner in runners.order_by('lname', 'fname', 'midname'):
			res[runner] = {
				'is_in_klb': race_is_for_klb and (runner.id in active_klb_runner_ids),
				'is_already_in_race': runner.id in runners_already_in_race_ids,
			}
			text = u'{} {} {}'.format(runner.lname, runner.fname, runner.midname)
			if runner.birthday:
				text += u' ({})'.format(runner.strBirthday(with_nbsp=False))

			if res[runner]['is_already_in_race']:
				text += u' — уже есть результат на этой дистанции'
			elif race_is_for_klb and not res[runner]['is_in_klb']:
				text += u' — не участвует в КЛБМатче'
			res[runner]['text'] = text
		return res
	def is_female(self):
		return self.gender == GENDER_FEMALE
	def get_avatar_url(self):
		if self.avatar:
			return '{}/{}'.format(SITE_URL_OLD, self.avatar.name)
		return ''
	def get_avatar_thumb_url(self):
		if self.avatar_thumb:
			return '{}/{}'.format(SITE_URL_OLD, self.avatar_thumb.name)
		return ''
	def get_total_length(self):
		return total_length2string(self.total_length)
	def get_total_time(self):
		return total_time2string(self.total_time)
	def get_strava_link(self):
		return 'https://www.strava.com/athletes/{}'.format(self.strava_account)
	def get_reverse_url(self, target):
		return reverse(target, kwargs={'user_id': self.user.id})
	def get_absolute_url(self):
		return self.get_reverse_url('results:user_details')
	def get_history_url(self):
		return self.get_reverse_url('editor:user_changes_history')
	def get_absolute_url_full(self):
		return self.get_reverse_url('results:user_details_full')
	def get_update_stat_url(self):
		return self.get_reverse_url('editor:user_update_stat')
	def get_find_results_url(self):
		return self.get_reverse_url('results:find_results')
	def get_all_payments_url(self):
		return self.get_reverse_url('editor:all_payments')
	def get_our_editor_url(self):
		return self.get_reverse_url('results:my_details')
	def get_strava_links_url(self):
		return self.get_reverse_url('results:my_strava_links')
	def get_editor_url(self):
		return '/admin/auth/user/{}'.format(self.user.id)
	def get_profile_editor_url(self):
		return '/admin/results/user_profile/{}'.format(self.id)
	class Meta:
		db_table = "dj_user_profile"
	def __unicode__(self):
		return self.user.get_full_name()

ACTION_CREATE = 0
ACTION_UPDATE = 1
ACTION_DELETE = 2
ACTION_DOCUMENT_CREATE = 3
ACTION_DOCUMENT_UPDATE = 4
ACTION_DOCUMENT_DELETE = 5
ACTION_NEWS_CREATE = 6
ACTION_NEWS_UPDATE = 7
ACTION_NEWS_DELETE = 8
ACTION_RACE_CREATE = 9
ACTION_RACE_UPDATE = 10
ACTION_RACE_DELETE = 11
ACTION_UNKNOWN = 12
ACTION_RESULTS_LOAD = 13
ACTION_RESULT_CREATE = 14
ACTION_RESULT_UPDATE = 15
ACTION_RESULT_DELETE = 16
ACTION_SOCIAL_POST = 17
ACTION_RESULT_CLAIM = 18
ACTION_RESULT_UNCLAIM = 19
ACTION_UNOFF_RESULT_CREATE = 20
ACTION_MERGE_FAILED = 21
ACTION_SPLIT_CREATE = 22
ACTION_SPLIT_UPDATE = 23
ACTION_SPLIT_DELETE = 24
ACTION_KLB_RESULT_CREATE = 25
ACTION_KLB_RESULT_UPDATE = 26
ACTION_KLB_RESULT_DELETE = 27
ACTION_KLB_PARTICIPANT_CREATE = 28
ACTION_KLB_PARTICIPANT_UPDATE = 29
ACTION_KLB_PARTICIPANT_DELETE = 30
ACTION_RESULT_MESSAGE_SEND = 31
ACTION_PERSON_ADD_TO_TEAM = 32
ACTION_PERSON_REMOVE_FROM_TEAM = 33
ACTION_PERSON_MOVE = 35
ACTION_NEWSLETTER_SEND = 34
ACTION_QUESTIONS_ORDER_CHANGE = 36
ACTION_QUESTION_CREATE = 37
ACTION_QUESTION_UPDATE = 38
ACTION_QUESTION_DELETE = 39
ACTION_QUESTION_CHOICE_CREATE = 40
ACTION_QUESTION_CHOICE_UPDATE = 41
ACTION_QUESTION_CHOICE_DELETE = 42
ACTION_REG_RACE_CREATE = 43
ACTION_REG_RACE_UPDATE = 44
ACTION_REG_RACE_DELETE = 45
ACTION_RACE_COST_CREATE = 46
ACTION_RACE_COST_UPDATE = 47
ACTION_RACE_COST_DELETE = 48
ACTION_REGISTRANT_CREATE = 49
ACTION_REGISTRANT_UPDATE = 50
ACTION_REGISTRANT_DELETE = 51
ACTION_CLUB_MEMBER_CREATE = 52
ACTION_CLUB_MEMBER_UPDATE = 53
ACTION_CLUB_MEMBER_DELETE = 54
ACTION_MARKS_CREATE = 55
ACTION_MARKS_DELETE = 56
ACTION_TYPES = (
	('', u'Любое'),
	(ACTION_CREATE, u'Создание'),
	(ACTION_UPDATE, u'Изменение'),
	(ACTION_DELETE, u'Удаление'),
	(ACTION_DOCUMENT_CREATE, u'Создание документа'),
	(ACTION_DOCUMENT_UPDATE, u'Изменение документа'),
	(ACTION_DOCUMENT_DELETE, u'Удаление документа'),
	(ACTION_NEWS_CREATE, u'Создание новости'),
	(ACTION_NEWS_UPDATE, u'Изменение новости'),
	(ACTION_NEWS_DELETE, u'Удаление новости'),
	(ACTION_RACE_CREATE, u'Создание дистанции'),
	(ACTION_RACE_UPDATE, u'Изменение дистанции'),
	(ACTION_RACE_DELETE, u'Удаление дистанции'),
	(ACTION_UNKNOWN, u'Непонятное действие'),
	(ACTION_RESULTS_LOAD, u'Загрузка результатов дистанции'),
	(ACTION_RESULT_CREATE, u'Создание результата'),
	(ACTION_RESULT_UPDATE, u'Изменение результата'),
	(ACTION_RESULT_DELETE, u'Удаление результата'),
	(ACTION_SOCIAL_POST, u'Публикация в соцсети новости'),
	(ACTION_RESULT_CLAIM, u'Присвоение результата'),
	(ACTION_RESULT_UNCLAIM, u'Отсоединение результата'),
	(ACTION_UNOFF_RESULT_CREATE, u'Добавление неофициального результата'),
	(ACTION_MERGE_FAILED, u'Не удалось объединить с бегуном'),
	(ACTION_SPLIT_CREATE, u'Создание промежуточного результата'),
	(ACTION_SPLIT_UPDATE, u'Изменение промежуточного результата'),
	(ACTION_SPLIT_DELETE, u'Удаление промежуточного результата'),
	(ACTION_KLB_RESULT_CREATE, u'Создание КЛБ-результата'),
	(ACTION_KLB_RESULT_UPDATE, u'Изменение КЛБ-результата'),
	(ACTION_KLB_RESULT_DELETE, u'Удаление КЛБ-результата'),
	(ACTION_KLB_PARTICIPANT_CREATE, u'Создание участника КЛБМатчей'),
	(ACTION_KLB_PARTICIPANT_UPDATE, u'Изменение участника КЛБМатчей'),
	(ACTION_KLB_PARTICIPANT_DELETE, u'Удаление участника КЛБМатчей'),
	(ACTION_RESULT_MESSAGE_SEND, u'Отправка новых результатов в письме'),
	(ACTION_PERSON_ADD_TO_TEAM, u'Добавление в команду участника КЛБМатчей'),
	(ACTION_PERSON_REMOVE_FROM_TEAM, u'Удаление из команды участника КЛБМатчей'),
	(ACTION_NEWSLETTER_SEND, u'Отправка письма с рассылкой'),
	(ACTION_PERSON_MOVE, u'Перемещение из другой команды участника КЛБМатчей'),
	(ACTION_QUESTIONS_ORDER_CHANGE, u'Изменение порядка вопросов'),
	(ACTION_QUESTION_CREATE, u'Создание вопроса'),
	(ACTION_QUESTION_UPDATE, u'Изменение вопроса'),
	(ACTION_QUESTION_DELETE, u'Удаление вопроса'),
	(ACTION_QUESTION_CHOICE_CREATE, u'Создание варианта ответа'),
	(ACTION_QUESTION_CHOICE_UPDATE, u'Изменение варианта ответа'),
	(ACTION_QUESTION_CHOICE_DELETE, u'Удаление варианта ответа'),
	(ACTION_REG_RACE_CREATE, u'Создание регистрации на дистанцию'),
	(ACTION_REG_RACE_UPDATE, u'Изменение регистрации на дистанцию'),
	(ACTION_REG_RACE_DELETE, u'Удаление регистрации на дистанцию'),
	(ACTION_RACE_COST_CREATE, u'Создание цены на дистанции'),
	(ACTION_RACE_COST_UPDATE, u'Изменение цены на дистанции'),
	(ACTION_RACE_COST_DELETE, u'Удаление цены на дистанции'),
	(ACTION_REGISTRANT_CREATE, u'Создание регистрации на забег'),
	(ACTION_REGISTRANT_UPDATE, u'Изменение регистрации на забег'),
	(ACTION_REGISTRANT_DELETE, u'Удаление регистрации на забег'),
	(ACTION_CLUB_MEMBER_CREATE, u'Создание члена клуба'),
	(ACTION_CLUB_MEMBER_UPDATE, u'Изменение члена клуба'),
	(ACTION_CLUB_MEMBER_DELETE, u'Удаление члена клуба'),
	(ACTION_MARKS_CREATE, u'Добавление оценок на дистанции'),
	(ACTION_MARKS_DELETE, u'Удаление оценок на дистанции'),
)
RESULT_ACTIONS = (
	ACTION_RESULT_CREATE, 
	ACTION_RESULT_UPDATE, 
	ACTION_RESULT_DELETE, 
	ACTION_RESULT_CLAIM, 
	ACTION_RESULT_UNCLAIM, 
	ACTION_UNOFF_RESULT_CREATE, 
	ACTION_KLB_RESULT_CREATE, 
	ACTION_KLB_RESULT_UPDATE, 
	ACTION_KLB_RESULT_DELETE,
)
UPDATE_COMMENT_FIELD_NAME = u'action_comment'
class Table_update(models.Model):
	model_name = models.CharField(verbose_name=u'Название модели таблицы', max_length=40)
	row_id = models.IntegerField(verbose_name=u'id строки в таблице', default=0)
	child_id = models.IntegerField(verbose_name=u'id затронутого документа или новости', default=None, null=True, blank=True, db_index=True)
	action_type = models.SmallIntegerField(verbose_name=u'Действие', choices=ACTION_TYPES, db_index=True)
	user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Совершивший действие',
		on_delete=models.SET_NULL, null=True, blank=True)
	is_verified = models.BooleanField(verbose_name=u'Проверен администратором', default=True, blank=True, db_index=True)
	verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Одобрил', related_name='table_update_verified_set',
		on_delete=models.SET_NULL, default=None, null=True, blank=True)
	verified_time = models.DateTimeField(verbose_name=u'Время одобрения', default=None, null=True, blank=True)
	added_time = models.DateTimeField(verbose_name=u'Время занесения в БД', auto_now_add=True)
	is_for_klb = models.BooleanField(verbose_name=u'Для зачёта в КЛБМатч', default=False, blank=True, db_index=True)
	class Meta:
		db_table = "dj_table_update"
		index_together = [
			["user", "added_time", "action_type", "model_name"],
			["verified_by", "added_time", "action_type", "model_name"],
			["row_id", "is_verified", "action_type", "is_for_klb"],
		]
	def append_comment(self, comment):
		if comment:
			field_update, _ = Field_update.objects.get_or_create(table_update=self, field_name=UPDATE_COMMENT_FIELD_NAME)
			field_update.new_value += u'; ' + comment
			field_update.save()
	def add_field(self, field_name, value):
		Field_update.objects.create(table_update=self, field_name=field_name, new_value=unicode(value)[:MAX_VALUE_LENGTH])
	def verify(self, user, comment=''):
		if self.is_verified:
			return False, u'Действие с id {} уже одобрил администратор {}.'.format(self.id, self.verified_by.get_full_name())
		self.is_verified = True
		self.verified_by = user
		self.verified_time = datetime.datetime.now()
		self.save()
		self.append_comment(comment)
		return True, ''
	def get_field(self, field):
		return self.field_update_set.filter(field_name=field).first()
	def get_loaded_from(self):
		return self.get_field('loaded_from')
	def get_comment(self):
		return self.get_field('comment')
	def get_absolute_url(self):
		return reverse('editor:action_details', kwargs={'table_update_id': self.id})
	def __unicode__(self):
		return u'Объект {} с id {}'.format(self.model_name, self.row_id)

MAX_VALUE_LENGTH = 255
class Field_update(models.Model):
	table_update = models.ForeignKey(Table_update, verbose_name=u'Обновление таблицы',
		on_delete=models.CASCADE, null=True, default=None, blank=True)
	field_name = models.CharField(verbose_name=u'Название изменённого поля', max_length=40)
	new_value = models.CharField(verbose_name=u'Новое значение поля', max_length=MAX_VALUE_LENGTH, blank=True)
	class Meta:
		db_table = "dj_field_update"

# Manual creation for unofficial series and result, for result claim
def log_obj_create(user, obj, action, field_list=None, child_object=None, comment='', is_for_klb=False, verified_by=None):
	child_id = child_object.id if child_object else None
	obj_with_attrs = child_object if child_object else obj # When adding result, we need its attributes, not event's
	if verified_by:
		is_verified = True
	else:
		# Results for KLBMatch aren't verified even if submitted by admin, so that we can approve them
		is_verified = (not is_for_klb) and is_admin(user)
	table_update = Table_update.objects.create(model_name=obj.__class__.__name__, child_id=child_id,
		row_id=obj.id, action_type=action, user=user, is_verified=is_verified, verified_by=verified_by, is_for_klb=is_for_klb)
	if field_list is None:
		field_list = [f.name for f in obj_with_attrs.__class__._meta.get_fields()]
	for field in field_list:
		if hasattr(obj_with_attrs, field) and getattr(obj_with_attrs, field):
			Field_update.objects.create(table_update=table_update, field_name=field,
				new_value=unicode(getattr(obj_with_attrs, field))[:MAX_VALUE_LENGTH])
	if comment:
		Field_update.objects.create(table_update=table_update, field_name=UPDATE_COMMENT_FIELD_NAME,
			new_value=comment[:MAX_VALUE_LENGTH])
def log_obj_delete(user, obj, child_object=None, action_type=ACTION_DELETE, comment=''):
	child_id = child_object.id if child_object else None
	table_update = Table_update.objects.create(model_name=obj.__class__.__name__, row_id=obj.id, action_type=action_type,
		user=user, is_verified=is_admin(user), child_id=child_id)
	if comment:
		Field_update.objects.create(table_update=table_update, field_name=UPDATE_COMMENT_FIELD_NAME,
			new_value=comment[:MAX_VALUE_LENGTH])

def log_klb_participant_delete(user, participant, comment=''):
	log_obj_delete(user, participant.klb_person, child_object=participant, action_type=ACTION_KLB_PARTICIPANT_DELETE, comment=comment)
	if participant.team:
		log_obj_delete(user, participant.team, child_object=participant, action_type=ACTION_PERSON_REMOVE_FROM_TEAM, comment=comment)


STATUS_FINISHED = 0
STATUS_DNF = 1
STATUS_DSQ = 2
STATUS_DNS = 3
STATUS_UNKNOWN = 4
STATUS_COMPLETED = 5
RESULT_STATUSES = (
	(STATUS_FINISHED, u'Финишировал'),
	(STATUS_DNF, u'DNF'),
	(STATUS_DSQ, u'DSQ'),
	(STATUS_DNS, u'DNS'),
	(STATUS_COMPLETED, u'Преодолел дистанцию'),
)
def string2status(s):
	if not s:
		return STATUS_UNKNOWN
	s = s.upper().strip()
	if s in ('Q', 'FINISHED', 'CONF'):
		return STATUS_FINISHED
	if (s in ('DNF', 'A')) or s.startswith(u'СОШ'):
		return STATUS_DNF
	if (s in ('DSQ', 'DQ')) or (u'дискв' in s):
		return STATUS_DSQ
	if (s == 'DNS') or s.startswith(u'НЕ СТАРТ'):
		return STATUS_DNS
	return STATUS_UNKNOWN

RESULT_SOURCE_DEFAULT = 0
RESULT_SOURCE_KLB = 1
RESULT_SOURCE_USER = 2
RESULT_SOURCE_NOVGOROD = 3
RESULT_SOURCES = (
	(RESULT_SOURCE_DEFAULT, 'из протокола'),
	(RESULT_SOURCE_KLB, 'из КЛБМатча'),
	(RESULT_SOURCE_USER, 'от пользователя'),
	(RESULT_SOURCE_NOVGOROD, 'из нижегородской базы'),
)
MAX_RESULT_COMMENT_LENGTH = 200
class Result(models.Model):
	user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Пользователь', on_delete=models.SET_NULL, default=None, null=True, blank=True)
	runner = models.ForeignKey('Runner', verbose_name=u'id бегуна', on_delete=models.SET_NULL, null=True, default=None, blank=True)
	# ak_person = models.ForeignKey(Ak_person_v2, verbose_name=u'id в базе АК55',
	# 	on_delete=models.SET_NULL, null=True, default=None, blank=True)
	parkrun_id = models.IntegerField(verbose_name=u'parkrun id', default=None, null=True, blank=True, db_index=True)
	race = models.ForeignKey(Race, verbose_name=u'Дистанция', on_delete=models.CASCADE)
	country = models.ForeignKey(Country, verbose_name=u'Страна', on_delete=models.PROTECT, default=None, null=True, blank=True)
	city = models.ForeignKey(City, verbose_name=u'Город', on_delete=models.PROTECT, default=None, null=True, blank=True)
	club = models.ForeignKey(Club, verbose_name=u'Клуб', on_delete=models.PROTECT, default=None, null=True, blank=True)

	country_name = models.CharField(verbose_name=u'Страна (название)', max_length=100, blank=True)
	city_name = models.CharField(verbose_name=u'Город (название)', max_length=100, blank=True)
	club_name = models.CharField(verbose_name=u'Клуб (название)', max_length=100, blank=True)

	name_raw = models.CharField(verbose_name=u'Имя целиком (сырое)', max_length=100, blank=True)
	lname_raw = models.CharField(verbose_name=u'Фамилия (сырая)', max_length=100, blank=True)
	fname_raw = models.CharField(verbose_name=u'Имя (сырое)', max_length=100, blank=True)
	midname_raw = models.CharField(verbose_name=u'Отчество (сырое)', max_length=100, blank=True)
	time_raw = models.CharField(verbose_name=u'Результат (сырой)', max_length=20, blank=True)
	gun_time_raw = models.CharField(verbose_name=u'Грязное время (сырое)', max_length=20, blank=True)
	country_raw = models.CharField(verbose_name=u'Страна (сырая)', max_length=100, blank=True)
	region_raw = models.CharField(verbose_name=u'Регион (сырой)', max_length=100, blank=True)
	city_raw = models.CharField(verbose_name=u'Город (сырой)', max_length=100, blank=True)
	club_raw = models.CharField(verbose_name=u'Клуб (сырой)', max_length=100, blank=True)
	birthyear_raw = models.SmallIntegerField(verbose_name=u'Год рождения (сырой)', default=None, null=True, blank=True)
	birthday_raw = models.DateField(verbose_name=u'Дата рождения (сырая)', default=None, null=True, blank=True)
	age_raw = models.SmallIntegerField(verbose_name=u'Возраст (сырой)', default=None, null=True, blank=True)
	place_raw = models.IntegerField(verbose_name=u'Место в абсолютном зачёте (сырое)', default=None, null=True, blank=True)
	place_gender_raw = models.IntegerField(verbose_name=u'Место среди своего пола (сырое)', default=None, null=True, blank=True)
	place_category_raw = models.IntegerField(verbose_name=u'Место в своей группе (сырое)', default=None, null=True, blank=True)
	comment_raw = models.CharField(verbose_name=u'Комментарий (сырой)', max_length=200, blank=True)
	status_raw = models.SmallIntegerField(verbose_name=u'Статус (сырой)', default=0, choices=RESULT_STATUSES)
	bib_raw = models.CharField(verbose_name=u'Стартовый номер (сырой)', max_length=10, blank=True)
	category_raw = models.CharField(verbose_name=u'Группа (сырая)', max_length=100, blank=True)
	gender_raw = models.CharField(verbose_name=u'Пол (сырой)', max_length=10, blank=True)
	ak_person_raw = models.CharField(verbose_name=u'id в базе АК55 (сырое)', max_length=6, blank=True)

	result = models.IntegerField(verbose_name=u'Результат', default=0) # in centiseconds/meters/steps/...
	gun_result = models.IntegerField(verbose_name=u'Грязное время', default=None, null=True, blank=True) # in centiseconds
	time_for_car = models.IntegerField(verbose_name=u'Время для странных дистанций', default=None, null=True, blank=True) # in centiseconds
	status = models.SmallIntegerField(verbose_name=u'Статус', default=0, choices=RESULT_STATUSES)
	# category = models.CharField(verbose_name=u'Группа', max_length=100, blank=True, db_index=True)
	category_size = models.ForeignKey(Category_size, verbose_name=u'Ссылка на размер группы',
		on_delete=models.PROTECT, default=None, null=True, blank=True)
	# categoryEn = models.CharField(verbose_name=u'Группа (англ)', max_length=100, blank=True) # TODO: remove at 2018-10-11
	place = models.IntegerField(verbose_name=u'Место в абсолютном зачёте', default=None, null=True, blank=True)
	place_gender = models.IntegerField(verbose_name=u'Место среди своего пола', default=None, null=True, blank=True)
	place_category = models.IntegerField(verbose_name=u'Место в своей группе', default=None, null=True, blank=True)
	comment = models.CharField(verbose_name=u'Комментарий', max_length=MAX_RESULT_COMMENT_LENGTH, blank=True)

	bib = models.CharField(verbose_name=u'Стартовый номер', max_length=10, blank=True)
	birthday = models.DateField(verbose_name=u'День или год рождения', default=None, null=True, blank=True, db_index=True)
	# If true, we know exact date of birth (otherwise usually birthday should be 01.01.)
	birthday_known = models.BooleanField(verbose_name=u'Известен ли день рождения', default=False)
	age = models.SmallIntegerField(verbose_name=u'Возраст', default=None, null=True, blank=True, db_index=True)
	lname = models.CharField(verbose_name=u'Фамилия', max_length=100, blank=True)
	fname = models.CharField(verbose_name=u'Имя', max_length=100, blank=True, db_index=True)
	midname = models.CharField(verbose_name=u'Отчество', max_length=100, blank=True, db_index=True)
	gender = models.SmallIntegerField(verbose_name=u'Пол', default=GENDER_UNKNOWN, choices=GENDER_CHOICES)
	do_not_count_in_stat = models.BooleanField(verbose_name=u'Не учитывать в статистике бегуна', default=False, db_index=True)
	
	source = models.SmallIntegerField(verbose_name=u'Источник результата', default=RESULT_SOURCE_DEFAULT, choices=RESULT_SOURCES)
	loaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Загрузил в БД',
		on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name="results_loaded_by_user")
	loaded_from = models.CharField(verbose_name=u'Источник', max_length=200, blank=True, db_index=True)
	added_time = models.DateTimeField(verbose_name=u'Время занесения в БД', auto_now_add=True, db_index=True)
	last_update = models.DateTimeField(verbose_name=u'Время последнего обновления', auto_now=True)
	class Meta:
		db_table = "dj_result"
		index_together = [
			["lname", "fname", "midname"],
			["race", "status", "place", "result", "lname", "fname", "midname", "gender", "category_size"],
			["race", "status", "place", "result", "lname", "fname", "midname", "category_size"],
			["race", "status", "place_gender"],
			["race", "status", "place_category"],
			["race", "source", "status", "result", "category_size"],
			["race", "lname", "fname", "midname"],
			["birthday_known", "birthday"],
			["loaded_by", "added_time"],
		]
	def clean(self):
		if self.birthday is None:
			self.birthday_known = False
	def add_for_mail(self, old_user=None):
		if self.user is None:
			return 0
		if self.status != STATUS_FINISHED:
			return 0
		if old_user and (old_user == self.user):
			return 0
		if self.user.result_for_mail_set.filter(result=self, is_sent=False).exists():
			return 0
		Result_for_mail.objects.create(user=self.user, result=self)
		return 1
	def try_add_birthday_to_runner(self, action_user):
		runner = self.runner
		if self.birthday_known:
			if not runner.birthday_known:
				runner.birthday = self.birthday
				runner.birthday_known = True
				runner.save()
				log_obj_create(action_user, runner, ACTION_UPDATE, field_list=['birthday', 'birthday_known'],
					comment=u'При добавлении результата с id {}'.format(self.id))
		elif self.birthday:
			if runner.birthday is None:
				runner.birthday = self.birthday
				runner.birthday_known = False
				runner.save()
				log_obj_create(action_user, runner, ACTION_UPDATE, field_list=['birthday'],
					comment=u'При добавлении результата с id {}'.format(self.id))
	# We want to add result 'self' to runner 'runner'.
	# If self.runner != None, we try to replace runner with self.runner
	def claim_for_runner(self, action_user, runner, comment='', is_for_klb=False, allow_merging_runners=False):
		self.refresh_from_db()
		runner.refresh_from_db()
		if self.runner == runner: # Great! No work is needed
			if self.user != runner.user:
				self.user = runner.user
				self.save()
				log_obj_create(action_user, self.race.event, ACTION_RESULT_UPDATE, field_list=['user'],
					child_object=self, comment=comment, is_for_klb=is_for_klb)
			return True, ''
		if self.user and runner.user and (self.user != runner.user):
			return False, u"Результат {} на забеге {} уже засчитан другому пользователю — с id {}.".format(
				self, self.race.name_with_event(), self.user.id)
		from_same_race = self.race.result_set.filter(runner=runner).first()
		if from_same_race:
			return False, u"Этому бегуну уже засчитан результат {} на забеге {}. Нельзя иметь два результата на одном забеге.".format(
				from_same_race, self.race.name_with_event())
		if runner.user:
			from_same_race = self.race.result_set.filter(user=runner.user).first()
			if from_same_race:
				return False, u"Этому пользователю уже засчитан результат {} на забеге {}. Нельзя иметь два результата на одном забеге.".format(
					from_same_race, self.race.name_with_event())
		if self.runner:
			if not allow_merging_runners:
				return False, u"Для присоединения результата {} бегуна {} со старта {} (id {}) нужно сначала объединить этого бегуна ".format(
					self.id, self.runner.get_name_and_id(), self.race.name_with_event(), self.race.id) \
					+ u' с бегуном {}'.format(runner.get_name_and_id())
			# So, self.runner != runner
			old_runner = self.runner
			res, msgError = runner.merge(old_runner, action_user)
			if res:
				log_obj_delete(action_user, old_runner, comment=u'При слиянии с бегуном {}'.format(runner.get_name_and_id()))
				old_runner.delete()
			return res, msgError
		# So, the result has no runner yet
		self.runner = runner
		field_list = ['runner']
		if runner.user:
			self.user = runner.user
			field_list.append('user')
		self.save()
		log_obj_create(action_user, self.race.event, ACTION_RESULT_UPDATE, field_list=field_list,
			child_object=self, comment=comment, is_for_klb=is_for_klb)
		if self.user and (self.user != action_user):
			self.add_for_mail()
		self.try_add_birthday_to_runner(action_user)
		return True, ''
	def unclaim_from_user(self, comment=''): # Returns <was result deleted?>
		user = self.user
		if self.source == RESULT_SOURCE_USER:
			log_obj_create(user, self.race.event, ACTION_RESULT_DELETE, child_object=self,
				comment=u'При отклеивании результата от пользователя с id {}. Комментарий: "{}"'.format(
				(user.id if user else ''), comment))
			self.delete()
			return True
		else:
			self.user = None
			self.save()
			log_obj_create(user, self.race.event, ACTION_RESULT_UPDATE, field_list=['user'], child_object=self,
				comment=u'При отклеивании результата от пользователя с id {}. Комментарий: "{}"'.format(
				(user.id if user else ''), comment))
			return False
	def unclaim_from_runner(self, user, comment=''): # When deleting from KLBMatch
		field_list = []
		runner = self.runner
		if runner:
			self.runner = None
			field_list.append('runner')
		if self.user:
			self.user = None
			field_list.append('user')
		if field_list:
			self.save()
			log_obj_create(user, self.race.event, ACTION_RESULT_UPDATE, field_list=field_list, child_object=self,
				comment=u'При удалении из КЛБМатча отсоединён от бегуна с id {}'.format(runner.id if runner else ''))
	def strClub(self):
		return self.club.name if self.club else self.club_name
	def clubLink(self):
		if self.club:
			return '<a href="' + self.club.get_absolute_url() + '">' + self.club.name + "</a>"
		else:
			return self.club_name
	def strCity(self):
		if self.city:
			return self.city.nameWithCountry()
		else:
			fields = []
			if self.city_name:
				fields.append(self.city_name)
			if self.country_name:
				fields.append(self.country_name)
			return ", ".join(fields)
	def strCountry(self):
		if self.country:
			return self.country.name
		else:
			return self.country_name
	def strName(self):
		if self.lname:
			if self.midname:
				return self.fname + " " + self.midname + " " + self.lname
			else:
				return self.fname + " " + self.lname
		elif self.runner:
			return self.runner.name()
		else:
			return '' # self.name_raw
	def strBirthday(self, with_nbsp=True, short_format=False):
		if self.birthday_known:
			return date2str(self.birthday, with_nbsp=with_nbsp, short_format=short_format)
		elif self.birthday:
			return unicode(self.birthday.year) + u' г.'
		else:
			return ''
	def strBirthdayShort(self):
		return self.strBirthday(short_format=True)
	def strBirthday_raw(self):
		if self.birthday_raw:
			return date2str(self.birthday_raw)
		elif self.birthyear_raw:
			return unicode(self.birthyear_raw) + u' г.'
		else:
			return ''
	def strPace(self):
		if self.status == STATUS_FINISHED:
			value = self.race.get_pace(self.result)
			if value:
				seconds = value % 60
				minutes = value // 60
				return u'{}:{}/км'.format(minutes, unicode(seconds).zfill(2))
		return ''
	def is_ok_for_klb(self):
		if self.status != STATUS_FINISHED:
			return False
		if self.race.distance.distance_type != TYPE_MINUTES:
			return True
		year = self.race.event.start_date.year
		return models_klb.get_min_distance_for_bonus(year) <= self.result # <= models_klb.get_max_distance_for_score(year)
	def get_klb_status(self):
		race_status = self.race.get_klb_status()
		if race_status == KLB_STATUS_OK:
			return KLB_STATUS_OK if self.is_ok_for_klb() else KLB_STATUS_SMALL_RESULT
		else:
			return race_status
	def get_place(self):
		if self.place:
			res = unicode(self.place)
			if self.race.n_participants_finished:
				res += u'&nbsp;из&nbsp;{}'.format(self.race.n_participants_finished)
			return res
		return ''
	def get_gender_place(self):
		if self.gender and self.place_gender:
			res = unicode(self.place_gender)
			gender_size = 0
			if (self.gender == GENDER_MALE):
				gender_size = self.race.n_participants_finished_men
			elif (self.gender == GENDER_FEMALE):
				gender_size = self.race.get_n_participants_finished_women()
			if gender_size:
				res += u'&nbsp;из&nbsp;{}'.format(gender_size)
			return res
		return ''
	def get_category_place(self):
		if self.place_category:
			res = unicode(self.place_category)
			if self.category_size and self.category_size.size:
				res += u'&nbsp;из&nbsp;{}'.format(self.category_size.size)
			return res
		return ''
	def get_runner_age(self):
		if self.runner and self.runner.birthday_known:
			return self.race.event.get_age_on_event_date(self.runner.birthday)
		return None
	def get_reverse_url(self, target):
		return reverse(target, kwargs={'result_id': self.id})
	def get_absolute_url(self):
		return self.get_reverse_url('results:result_details')
	def get_runner_or_user_url(self):
		if self.user and self.user.is_active and self.user.user_profile and self.user.user_profile.is_public:
			return self.user.user_profile.get_absolute_url()
		if self.runner:
			return self.runner.get_absolute_url()
		return ''
	def get_editor_url(self):
		return self.get_reverse_url('editor:result_details')
	def get_claim_url(self):
		return self.get_reverse_url('results:claim_result')
	def get_unclaim_url(self):
		return self.get_reverse_url('results:unclaim_result')
	def get_unclaim_with_race_url(self):
		return reverse('results:unclaim_result', kwargs={'result_id': self.id, 'race_id': self.race.id})
	def get_delete_unofficial_url(self):
		return self.get_reverse_url('results:delete_unofficial_result')
	def get_delete_url(self):
		return self.get_reverse_url('editor:result_delete')
	def get_klb_add_url(self):
		return self.get_reverse_url('editor:result_klb_add')
	def get_klb_delete_url(self):
		return self.get_reverse_url('editor:result_klb_delete')
	def get_klb_error_url(self):
		return self.get_reverse_url('editor:result_mark_as_error')
	def get_splits_update_url(self):
		return self.get_reverse_url('editor:result_splits_update')
	def get_gun_time(self):
		return self.race.distance.strResult(self.gun_result) if self.gun_result else ''
	def __unicode__(self):
		return self.race.distance.strResult(self.result) if self.status == STATUS_FINISHED else self.get_status_display()

class Lost_result(models.Model):
	""" Если при перезагрузке протокола удаляем официальный результат, который был привязан к бегуну и/или пользователю,
	и не нашли сразу нового результата, к которому сделать те же привязки, то кладем данные о результате сюда """
	user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Пользователь',
		on_delete=models.SET_NULL, default=None, null=True, blank=True)
	runner = models.ForeignKey('Runner', verbose_name=u'id бегуна',
		on_delete=models.SET_NULL, default=None, null=True, blank=True)
	race = models.ForeignKey(Race, verbose_name=u'Дистанция', on_delete=models.CASCADE)
	result = models.IntegerField(verbose_name=u'Результат', default=0) # in centiseconds/meters/steps/...
	status = models.SmallIntegerField(verbose_name=u'Статус', default=0, choices=RESULT_STATUSES)
	lname = models.CharField(verbose_name=u'Фамилия', max_length=100, blank=True)
	fname = models.CharField(verbose_name=u'Имя', max_length=100, blank=True)
	midname = models.CharField(verbose_name=u'Отчество', max_length=100, blank=True)
	strava_link = models.BigIntegerField(verbose_name=u'Ссылка на пробежку на Страве')
	loaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Загрузил в БД',
		on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name="lost_results_loaded_by_user")
	added_time = models.DateTimeField(verbose_name=u'Время занесения в БД', auto_now_add=True)
	class Meta:
		db_table = "dj_lost_result"
		index_together = [
			["race", "lname", "fname", "status", "result"],
		]
	def __unicode__(self):
		if self.status == STATUS_FINISHED:
			return self.race.distance.strResult(self.result)
		else:
			return self.get_status_display()

class Unclaimed_result(models.Model):
	""" Если пользователь сказал: никогда больше не показывайте этот результат моего тёзки, он не мой """
	user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Пользователь',
		on_delete=models.CASCADE, default=None, null=True, blank=True)
	result = models.ForeignKey(Result, verbose_name=u'Результат', on_delete=models.CASCADE)
	added_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Добавил в БД',
		on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name="unclaimed_results_added_by_user")
	added_time = models.DateTimeField(verbose_name=u'Время занесения в БД', auto_now_add=True)
	class Meta:
		db_table = "dj_unclaimed_result"

class Result_for_mail(models.Model):
	""" Для свежепривязанных результатов, о которых хотим послать письмо пользователю """
	user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Пользователь', on_delete=models.CASCADE)
	result = models.ForeignKey(Result, verbose_name=u'Результат', on_delete=models.CASCADE)
	is_sent = models.BooleanField(verbose_name=u'Отправлено ли письмо пользователю', default=False, db_index=True)
	added_time = models.DateTimeField(verbose_name=u'Время занесения в БД', auto_now_add=True)
	sent_time = models.DateTimeField(verbose_name=u'Время отправки письма', default=None, null=True, blank=True)
	class Meta:
		db_table = "dj_result_for_mail"

class Result_on_strava(models.Model):
	result = models.OneToOneField(Result, verbose_name=u'Результат', on_delete=models.CASCADE)
	link = models.BigIntegerField(verbose_name=u'Ссылка на пробежку на Страве')
	added_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Добавил в БД',
		on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name="results_on_strava_added_by_user")
	added_time = models.DateTimeField(verbose_name=u'Время занесения в БД', auto_now_add=True)
	class Meta:
		db_table = "dj_result_on_strava"
	def __unicode__(self):
		return 'https://www.strava.com/activities/{}'.format(self.link) if self.link else ''

class Split(models.Model):
	result = models.ForeignKey(Result, verbose_name=u'Итоговый результат', on_delete=models.CASCADE)
	distance = models.ForeignKey(Distance, verbose_name=u'Промежуточная дистанция', on_delete=models.PROTECT)
	value = models.IntegerField(verbose_name=u'Значение', default=0) # in centiseconds/meters/steps/...
	class Meta:
		db_table = "dj_split"
		unique_together = (("result", "distance"),)
	def __unicode__(self):
		return self.distance.strResult(self.value)

class City_change(models.Model):
	model = models.CharField(max_length=100, blank=True)
	row_id = models.IntegerField(default=0)
	field_name = models.CharField(max_length=100, blank=True)
	id_old = models.IntegerField(default=0)
	name_old = models.CharField(max_length=100, blank=True)
	id_new = models.IntegerField(default=0)
	name_new = models.CharField(max_length=100, blank=True)
	user_id = models.IntegerField(default=0)
	user_email = models.CharField(max_length=MAX_EMAIL_LENGTH, blank=True)
	timestamp = models.DateTimeField(auto_now=True, db_column='LastIzm')
	class Meta:
		db_table = "dj_city_change"

THUMBNAIL_SIZE = (240, 150)
def seconds_from_1970():
	return int(time.time())
def get_image_name(instance, thumb=False, full_path=False):
	res = "new/img/" + unicode(instance.image_name)
	if thumb:
		res += "_1"
	res += instance.image_extension
	if full_path:
		res = os.path.join(settings.MEDIA_ROOT, res)
	return res
def create_image_name(instance, filename, thumb=False):
	obj_name = 'thumbnail' if thumb else 'image'
	write_log("{} NEWS_IMAGE_CREATE Trying to upload {} {} for news {}, event {}.".format(
		datetime.datetime.now(), obj_name,
		filename, instance.title, instance.event))
	if not instance.image_name:
		instance.image_name = seconds_from_1970()
	if not instance.image_extension:
		instance.image_extension = "." + file_extension(filename, "jpg")
	filename = get_image_name(instance, thumb=thumb)
	full_name = get_image_name(instance, thumb=thumb, full_path=True)
	write_log("File to create {} is {}. Full name is '{}'. Does it exist? {}".format(
		obj_name, filename, full_name, os.path.exists(full_name)))
	try:
		if os.path.exists(full_name):
			os.remove(full_name)
	except:
		pass
	return filename
def create_image_thumb_name(instance, filename):
	return create_image_name(instance, filename, thumb=True)
IMAGE_ALIGN_CHOICES = (
	('l', u'картинка слева'),
	('r', u'картинка справа'),
	('n', u'не показывать картинку'),
)
NEWS_PREVIEW_LIMIT = 1000
class News(models.Model): # News on our site
	id = models.AutoField(primary_key=True, db_column='news_id')
	event = models.ForeignKey(Event, on_delete=models.SET_NULL, null=True, default=None, blank=True, db_column='Probeg_Year_id')

	news_date = models.DateField(verbose_name=u'Дата публикации (устар.)', db_column='news_date')
	time_raw = models.CharField(max_length=5, verbose_name=u'Время публикации (устар.)', db_column='news_time')
	date_posted = CustomDateTimeField(verbose_name=u'Время публикации', default=timezone.now, db_column='dj_date_posted')
	
	country_raw = models.CharField(verbose_name=u'Страна (устар.)', max_length=60, db_column='country', blank=True)
	district_raw = models.CharField(verbose_name=u'Фед. округ (устар.)', max_length=40, db_column='fedokrug', blank=True)
	region_raw = models.CharField(verbose_name=u'Регион (устар.)', max_length=60, db_column='obl', blank=True)

	title = models.CharField(verbose_name=u'Название', max_length=255, blank=True, db_column='news_title')
	content = models.TextField(max_length=60000, verbose_name=u'Текст новости', db_column='news_content', blank=True)
	preview = models.TextField(max_length=2000, verbose_name=u'Превью', db_column='dj_preview', blank=True)
	n_views = models.IntegerField(default=0, db_column='news_wiew')
	author = models.CharField(verbose_name=u'Автор', max_length=100, db_column='authors', blank=False)
	# Made by CPanel
	image_name = models.IntegerField(default=0, db_column='news_stamp')
	# .jpg, .jpeg, .png, .gif or ""
	image_extension = models.CharField(max_length=5, db_column='news_exp', blank=True)
	# l - to left edge, r - to rigth, n - no image, '' - rare value
	image_align = models.CharField(verbose_name=u'Как разместить картинку', max_length=1, db_column='news_img',
		choices=IMAGE_ALIGN_CHOICES, default='l')
	# Link to image:	 http://probeg.org/new/img/{{image_name}}{{image_extension}}
	# Link to thumbnail: http://probeg.org/new/img/{{image_name}}_1{{image_extension}}
	image = models.ImageField(verbose_name=u'Фотография', max_length=255, upload_to=create_image_name,
		blank=True, db_column='dj_image')
	image_thumb = models.ImageField(verbose_name=u'Фотография-иконка', max_length=255, upload_to=create_image_thumb_name,
		blank=True, db_column='dj_image_thumb')
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Создал новость',
		on_delete=models.SET_NULL, default=None, null=True, blank=True, db_column='dj_created_by')
	is_for_social = models.BooleanField(verbose_name=u'Только для соцсетей',
		default=False, db_column='dj_is_for_social')
	# url_link = models.URLField(verbose_name=u'Ссылка из поста', max_length=255, blank=True)
	def clean(self):
		self.content = replace_symbols(self.content)
		self.title = replace_symbols(self.title)
		if len(self.title) > 1:
			if (self.title[-1] == '.') and (self.title[-2] != '.'):
				self.title = self.title[:-1]
		self.news_date = self.date_posted.date()
		self.time_raw = self.date_posted.strftime("%H:%M")
		if not self.image_name:
			self.image_name = seconds_from_1970()
		if self.image and not self.image_extension:
			self.image_extension = "." + file_extension(self.image.name)
		if self.event:
			city = self.event.getCity()
			if city:
				region = city.region
				self.country_raw = region.country.name
				if region.district:
					self.district_raw = region.district.name
				if region.active:
					self.region_raw = region.name
		self.make_preview()
	def clean_image_align(self):
		if not self.image_thumb:
			# write_log("Image thumb is {}. Putting n".format(self.image_thumb))
			self.image_align = 'n'
		else:
			# write_log("Image thumb is {}. Putting l".format(self.image_thumb))
			self.image_align = 'l'
	def delete_images(self):
		try:
			if self.image_thumb:
				self.image_thumb.delete()
			if self.image_extension: # Otherwise it seems there should be no image files
				full_name = get_image_name(self, full_path=True)
				if os.path.exists(full_name):
					os.remove(full_name)
				full_thumb_name = get_image_name(self, thumb=True, full_path=True)
				if os.path.exists(full_thumb_name):
					os.remove(full_thumb_name)
				self.image_extension = ""
		except:
			write_log("{} NEWS_IMAGE_DELETE Error when deleting images for news «{}», id {}.".format(
				datetime.datetime.now(), self.title, self.id))
	def make_thumbnail(self):
		return make_thumb(self.image, self.image_thumb, 240, 150)
	def image_size(self):
		if self.image:
			try:
				return self.image.size
			except:
				return -1 # u'Ошибка. Возможно, файл не существует'
		else:
			return 0
	def plain_content(self):
		return bleach.clean(self.content.replace('<br', ' <br'), tags=[], attributes={}, styles=[], strip=True)
	def make_preview(self):
		plain_content = self.plain_content()
		cur_stop = -1
		if len(plain_content) < NEWS_PREVIEW_LIMIT:
			self.preview = plain_content
		else:
			plain_content = plain_content[:NEWS_PREVIEW_LIMIT]
			cur_stop = max([plain_content.rfind(symbol) for symbol in '.?!'])
			self.preview = plain_content[:cur_stop + 1] + ".."
	class Meta:
		db_table = "news"
		index_together = [
			["event", "date_posted"],
		]
	def twitter_max_length(self):
		return 92 if self.image else 116
	def get_reverse_url(self, target):
		return reverse(target, kwargs={'news_id': self.id})
	def get_absolute_url(self):
		if self.event:
			return reverse('results:event_details', kwargs={'event_id': self.event.id}) + '#news' + unicode(self.id)
		else:
			return self.get_reverse_url('results:news_details')
	def get_editor_url(self):
		if self.event:
			return reverse('editor:event_details', kwargs={'event_id': self.event.id, 'news_id': self.id}) + '#news'
		else:
			return self.get_reverse_url('editor:news_details')
	def get_history_url(self):
		return self.get_reverse_url('editor:news_changes_history')
	def get_social_post_url(self):
		return self.get_reverse_url('editor:news_post')
	def get_old_url(self):
		return '{}/new.php?id={}'.format(SITE_URL_OLD, self.id)
	def get_image_url(self):
		return '{}/{}'.format(SITE_URL_OLD, self.image.name) if self.image else ''
	def get_image_thumb_url(self):
		return '{}/{}'.format(SITE_URL_OLD, self.image_thumb.name) if self.image_thumb else ''
	def __unicode__(self):
		return self.title
@receiver(pre_delete, sender=News)
def pre_news_delete(sender, instance, **kwargs):
	if instance.image:
		try:
			instance.image.delete(False)
		except:
			pass
	if instance.image_thumb:
		try:
			instance.image_thumb.delete(False)
		except:
			pass

DOC_TYPE_UNKNOWN = 0
DOC_TYPE_REGULATION = 1
DOC_TYPE_REGULATION_STAMPED = 2
DOC_TYPE_ANNOUNCEMENT = 3
DOC_TYPE_POSTER = 4
DOC_TYPE_COURSE = 5
DOC_TYPE_LOGO = 6
DOC_TYPE_PROTOCOL = 7
DOC_TYPE_PROTOCOL_START = 8
DOC_TYPE_PHOTOS = 9
DOC_TYPE_PRESS_RELEASE = 10
DOC_TYPE_TEAM_LIST = 11
DOC_TYPE_HOW_TO_GET = 12
DOC_TYPE_IMPRESSIONS = 13
DOC_TYPE_TRAFFIC_PLAN = 14
DOC_TYPE_APPLICATION_FORM = 15
DOC_TYPE_PRELIMINARY_PROTOCOL = 16
DOCUMENT_TYPES = (
	(DOC_TYPE_UNKNOWN, u'Документ неизвестного типа'),
	(DOC_TYPE_REGULATION, u'Положение'),
	(DOC_TYPE_REGULATION_STAMPED, u'Положение с печатью'),
	(DOC_TYPE_ANNOUNCEMENT, u'Анонс'),
	(DOC_TYPE_POSTER, u'Афиша'),
	(DOC_TYPE_COURSE, u'Схема трассы'),
	(DOC_TYPE_LOGO, u'Логотип'),
	(DOC_TYPE_PROTOCOL, u'Протокол'),
	(DOC_TYPE_PRELIMINARY_PROTOCOL, u'Предварительный протокол'),
	(DOC_TYPE_PROTOCOL_START, u'Стартовый протокол'),
	(DOC_TYPE_PHOTOS, u'Ссылка на фото или видео'),
	(DOC_TYPE_PRESS_RELEASE, u'Пресс-релиз'),
	(DOC_TYPE_TEAM_LIST, u'Список команды'),
	(DOC_TYPE_HOW_TO_GET, u'Как добраться'),
	(DOC_TYPE_IMPRESSIONS, u'Отчёт'),
	(DOC_TYPE_TRAFFIC_PLAN, u'График движения'),
	(DOC_TYPE_APPLICATION_FORM, u'Бланк заявки'),
)
SERIES_DOCUMENT_TYPES = (
	(DOC_TYPE_UNKNOWN, u'Документ неизвестного типа'),
	(DOC_TYPE_LOGO, u'Логотип'),
)
DOCUMENT_SUFFIXES = {
	DOC_TYPE_UNKNOWN: u'XX',
	DOC_TYPE_REGULATION: u'Pl',
	DOC_TYPE_REGULATION_STAMPED: u'Pp',
	DOC_TYPE_ANNOUNCEMENT: u'An',
	DOC_TYPE_POSTER: u'Af',
	DOC_TYPE_COURSE: u'Sh',
	DOC_TYPE_LOGO: u'Lo',
	DOC_TYPE_PROTOCOL: u'Pr',
	DOC_TYPE_PROTOCOL_START: u'Ps',
	DOC_TYPE_PHOTOS: u'Ph',
	DOC_TYPE_PRESS_RELEASE: u'Pz',
	DOC_TYPE_TEAM_LIST: u'Sk',
	DOC_TYPE_HOW_TO_GET: u'Sd',
	DOC_TYPE_IMPRESSIONS: u'Im',
	DOC_TYPE_TRAFFIC_PLAN: u'Gd',
	DOC_TYPE_APPLICATION_FORM: u'Ap',
	DOC_TYPE_PRELIMINARY_PROTOCOL: u'PrelPr',
}
DOCUMENT_FIELD_NAMES = {
	DOC_TYPE_REGULATION: u'url_regulation',
	DOC_TYPE_REGULATION_STAMPED: u'url_regulation_stamped',
	DOC_TYPE_ANNOUNCEMENT: u'url_announcement',
	DOC_TYPE_POSTER: u'url_poster',
	DOC_TYPE_COURSE: u'url_course',
	DOC_TYPE_LOGO: u'url_logo',
	DOC_TYPE_PROTOCOL: u'url_protocol',
	DOC_TYPE_PRELIMINARY_PROTOCOL: u'url_protocol',
}
DOC_PROTOCOL_TYPES = (DOC_TYPE_PROTOCOL, DOC_TYPE_PRELIMINARY_PROTOCOL)
Q_IS_XLS_FILE = Q(upload__iendswith='.xls') | Q(upload__iendswith='.xlsx')
DOC_TYPES_NOT_FOR_RIGHT_COLUMN = (DOC_TYPE_UNKNOWN, DOC_TYPE_LOGO, DOC_TYPE_PHOTOS, DOC_TYPE_IMPRESSIONS)
MAX_EVENT_NAME_LENGTH = 20
def create_document_name(date, suffix, name, city_name, series_id, extension, sample=None):
	if sample:
		suffix += "_sample" + unicode(sample)
	return 'dj_media/uploads/{0}_{1}_{2}_{3}_{4}.{5}'.format(
			date, suffix, name, city_name, series_id, extension).replace(" ", "_")
def document_name(instance, filename):
	write_log("{} DOCUMENT_NAME_CREATE Trying to upload file {} of type {} for series {}, event {}.".format(
		datetime.datetime.now(), filename, instance.document_type, instance.series, instance.event))
	if instance.id:
		old_instance = Document.objects.get(pk=instance.id)
		if old_instance.upload:
			if os.path.isfile(old_instance.upload.path):
				write_log("There already is some file {}, so we just delete it.".format(old_instance.upload.name))
				os.remove(old_instance.upload.path)
			else:
				write_log("Error! There is some value {}, but no such file.".format(old_instance.upload.name))
	if instance.event:
		date = instance.event.start_date.strftime("%y%m%d")
	else:
		date = "000000"

	suffix = DOCUMENT_SUFFIXES[instance.document_type]

	if instance.event:
		name = unicode(instance.event)
		series_id = instance.event.series.id
		city = instance.event.getCity()
		city_name = city.name if city else ""
	elif instance.series:
		name = unicode(instance.series)
		series_id = instance.series.id
		city_name = instance.series.city.name if instance.series.city else ""
	else:
		name = ""
		series_id = 0
		city_name = ""
	name = transliterate(name)[:MAX_EVENT_NAME_LENGTH]
	city_name = transliterate(city_name)[:MAX_EVENT_NAME_LENGTH]
	extension = file_extension(filename, default="html")

	filename = create_document_name(date, suffix, name, city_name, series_id, extension)
	fullname = os.path.join(settings.MEDIA_ROOT, filename)
	sample = 1
	while os.path.exists(fullname):
		write_log("Oops, file {} already exists. Trying next sample number...".format(fullname))
		sample += 1
		filename = create_document_name(date, suffix, name, city_name, series_id, extension, sample=sample)
		fullname = os.path.join(settings.MEDIA_ROOT, filename)

	write_log("File name to create is {}. Full name is '{}'.".format(filename, fullname))
	return filename
LOAD_TYPE_UNKNOWN = 0
LOAD_TYPE_LOADED = 1
LOAD_TYPE_DO_NOT_TRY = 2
LOAD_TYPE_NOT_LOADED = 3
TRY_TO_LOAD_CHOICES = (
	(LOAD_TYPE_UNKNOWN, u'Неизвестно'),
	(LOAD_TYPE_LOADED, u'Загружено к нам'),
	(LOAD_TYPE_DO_NOT_TRY, u'Не пытаться загружать'),
	(LOAD_TYPE_NOT_LOADED, u'Не загружено, нужно загрузить'),
)
DOC_HIDE_NEVER = 0
DOC_HIDE_IF_EXTERNAL_EXISTS = 1
DOC_HIDE_ALWAYS = 2
DOC_HIDE_CHOICES = (
	(DOC_HIDE_NEVER, u'всегда'),
	(DOC_HIDE_IF_EXTERNAL_EXISTS, u'пока скрыть, но если ссылка на URL исчезнет, то показать'),
	(DOC_HIDE_ALWAYS, u'никогда (его будут видеть только админы)'),
)
class Document(models.Model):
	series = models.ForeignKey(Series, verbose_name=u'Серия', on_delete=models.CASCADE, null=True, default=None, blank=True)
	event = models.ForeignKey(Event, verbose_name=u'Забег', on_delete=models.CASCADE, null=True, default=None, blank=True)

	document_type = models.SmallIntegerField(verbose_name=u'Содержимое документа', default=DOC_TYPE_UNKNOWN, choices=DOCUMENT_TYPES, db_index=True)
	loaded_type = models.SmallIntegerField(verbose_name=u'Состояние загрузки', default=0, choices=TRY_TO_LOAD_CHOICES)
	upload = models.FileField(verbose_name=u'Файл для загрузки', max_length=255, upload_to=document_name, blank=True)
	hide_local_link = models.SmallIntegerField(verbose_name=u'Показывать ли всем ссылку на локальный файл', choices=DOC_HIDE_CHOICES,
		default=DOC_HIDE_NEVER)
	url_original = models.URLField(verbose_name=u'URL документа', max_length=MAX_URL_LENGTH, blank=True)
	comment = models.CharField(verbose_name=u'Комментарий (например, если есть несколько документов одного типа)', max_length=255, blank=True)
	is_processed = models.BooleanField(verbose_name=u'Обработан ли протокол полностью', default=False)

	author = models.CharField(verbose_name=u'Автор (для отчётов и фотографий)', max_length=100, blank=True)
	last_update = models.DateTimeField(verbose_name=u'Время последнего изменения', auto_now=True)
	date_posted = models.DateTimeField(verbose_name=u'Время занесения в БД', auto_now_add=True)
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Добавил документ',
		on_delete=models.SET_NULL, default=None, null=True, blank=True)
	class Meta:
		db_table = "dj_document"
		index_together = [
			["series", "document_type"],
			["event", "document_type", "is_processed"],
		]
	def clean(self):
		self.author = replace_symbols(self.author)
		self.comment = replace_symbols(self.comment)
	def file_size(self):
		if self.upload:
			try:
				return self.upload.size
			except:
				return -1 # u'Ошибка. Возможно, файл не существует'
		else:
			return 0
	def title(self):
		if self.author:
			return self.author
		if self.comment:
			return self.comment
		if self.url_original:
			return self.url_original
		return self.get_document_type_display() + " " + self.comment
	def process_review_or_photo(self): # For compatibility with old cards we should create entities in Review and Photo tables
		for doc_type, model in [(DOC_TYPE_PHOTOS, Photo), (DOC_TYPE_IMPRESSIONS, Review)]:
			if self.document_type == doc_type:
				if self.url_original:
					url = self.url_original
				else:
					url = os.path.join(settings.MEDIA_URL, self.upload.name)
				model_name = model.__name__.lower()
				if hasattr(self, model_name):
					doc = getattr(self, model_name)
					doc.author = self.author
					doc.url = url
					doc.comment = self.comment
					doc.save()
				elif model.objects.filter(event=self.event, url=url).exists():
					model.objects.filter(event=self.event, url=url).update(document=self, author=self.author,
						url=url, comment=self.comment, added_to_docs=True)
				else:
					model.objects.create(event=self.event, series_raw=self.event.series.id, document=self, author=self.author,
						url=url, comment=self.comment, added_to_docs=True)
	def get_editor_url(self):
		if self.event:
			return self.event.get_editor_url() + '#documents'
		if self.series:
			return self.series.get_editor_url() + '#documents'
		return '#'
	def get_upload_url(self):
		if self.upload:
			name = self.upload.name
			if name[:4] != "http":
				return '{}/{}'.format(SITE_URL_OLD, name)
			else:
				return name
		else:
			return '#'
	def get_main_url(self):
		if self.url_original:
			return self.url_original
		else:
			return self.get_upload_url()
	def get_mark_processed_url(self):
		return reverse('editor:protocol_mark_processed', kwargs={'protocol_id': self.id})
	def get_safe_url(self): # external URL; or internal if it's available for regular users
		if self.url_original.strip():
			return self.url_original
		if self.upload.name and (self.hide_local_link != DOC_HIDE_ALWAYS):
			return "/" + unicode(self.upload.name)
		return ''
	def update_event_field(self): # When we changed some field of document, we should update old field of event
		if self.event and (self.document_type in DOCUMENT_FIELD_NAMES):
			event = self.event
			new_value = self.get_safe_url()
			if not new_value:
				doc_type = DOC_TYPE_PROTOCOL if (self.document_type == DOC_TYPE_PRELIMINARY_PROTOCOL) else self.document_type
				doc = event.document_set.filter(~(Q(url_original='') & (Q(upload=None) | Q(hide_local_link=DOC_HIDE_ALWAYS))), document_type=doc_type).first()
				if doc:
					new_value = doc.get_safe_url()
			setattr(event, DOCUMENT_FIELD_NAMES[self.document_type], new_value)
			event.save()
	def mark_processed(self, user, comment=''):
		self.is_processed = True
		self.save()
		log_obj_create(user, self.event, ACTION_DOCUMENT_UPDATE, field_list=['is_processed'], child_object=self, comment=comment)
	def is_xls(self):
		if self.upload:
			return self.upload.name[-5:].lower().endswith(('.xls', '.xlsx'))
		return False
	def __unicode__(self):
		res = self.get_document_type_display()
		if self.comment:
			if self.document_type == DOC_TYPE_UNKNOWN:
				res = self.comment
			else:
				res += " " + self.comment
		if self.author:
			res += " (" + self.author + ")"
		return res
@receiver(pre_delete, sender=Document)
def pre_document_delete(sender, instance, **kwargs):
	if instance.upload:
		instance.upload.delete(False)
	event = None
	if instance.event:
		event = instance.event
		write_log("Document with id {} of type {} from event {} is being deleted".format(instance.id, instance.document_type, event.id))
	elif instance.series:
		series = instance.series
		write_log("Document with id {} of type {} from series {} is being deleted".format(instance.id, instance.document_type, series.id))
	else:
		write_log("Document with id {} of type {} with no event or series is being deleted".format(instance.id, instance.document_type))
	if event:
		if instance.document_type in DOCUMENT_FIELD_NAMES:
			new_doc = event.document_set.filter(document_type=instance.document_type).exclude(pk=instance.id).first()
			if new_doc:
				new_doc.update_event_field()
			else:
				setattr(event, DOCUMENT_FIELD_NAMES[instance.document_type], '')
				event.save()
		elif instance.document_type == DOC_TYPE_PHOTOS:
			photo = Photo.objects.filter(event=event, url=instance.url_original).first()
			if photo:
				photo.delete()
		elif instance.document_type == DOC_TYPE_IMPRESSIONS:
			review = Review.objects.filter(event=event, url=instance.url_original).first()
			if review:
				review.delete()

class Review(models.Model): # News from other sources: just links
	series_raw = models.IntegerField(verbose_name=u'id серии (устар.)', default=0, db_column='Probeg_id')
	event = models.ForeignKey(Event, on_delete=models.SET_NULL, null=True, default=None, db_column='Probeg_Year_id')
	document = models.OneToOneField(Document, on_delete=models.CASCADE, null=True, default=None, db_column='dj_document_id')

	author = models.CharField(max_length=100, db_column='namer', blank=True)
	url = models.CharField(max_length=MAX_URL_LENGTH, db_column='adressr', blank=True)
	comment = models.CharField(max_length=255, db_column='komm', blank=True)

	last_update = models.DateTimeField(auto_now=True, db_column='LastIzm')
	date_posted = models.DateTimeField(auto_now_add=True, db_column='dj_date_posted') # Default=NULL in MySQL!
	added_to_docs = models.BooleanField(verbose_name=u'Добавлен ли в таблицу документов',
		default=False, db_column='dj_added_to_docs')
	class Meta:
		db_table = "review"
		index_together = [
			["event", "date_posted"],
		]
		# unique_together = (("event", "url"),) # This index is too long for MySQL
	def clean(self):
		self.series_raw = self.event.series.id
	def __unicode__(self):
		return self.url

class Photo(models.Model): # Links to photos and albums
	series_raw = models.IntegerField(verbose_name=u'id серии (устар.)', default=0, db_column='Probeg_id')
	event = models.ForeignKey(Event, on_delete=models.CASCADE, db_column='Probeg_Year_id')
	document = models.OneToOneField(Document, on_delete=models.CASCADE, null=True, default=None, db_column='dj_document_id')

	author = models.CharField(max_length=100, blank=True, db_column='namef')
	url = models.CharField(max_length=MAX_URL_LENGTH, blank=True, db_column='adressf')
	comment = models.CharField(max_length=255, blank=True, db_column='komm')

	last_update = models.DateTimeField(auto_now=True, db_column='LastIzm')
	date_posted = models.DateTimeField(auto_now_add=True, db_column='dj_date_posted') # Default=NULL in MySQL!
	added_to_docs = models.BooleanField(verbose_name=u'Добавлено ли в таблицу документов',
		default=False, db_column='dj_added_to_docs')
	class Meta:
		db_table = "foto"
		index_together = [
			["event", "date_posted"],
		]
		# unique_together = (("event", "url"),) # This index is too long for MySQL
	def clean(self):
		self.series_raw = self.event.series.id
	def __unicode__(self):
		return self.url

class Payment(models.Model): # For Yandex payments
	notification_type = models.CharField(verbose_name=u'Тип перевода', max_length=30)
	operation_id = models.CharField(verbose_name=u'Идентификатор операции', max_length=30)
	amount = models.DecimalField(verbose_name=u'Сумма, пришедшая на счёт', max_digits=8, decimal_places=2)
	withdraw_amount = models.DecimalField(verbose_name=u'Сумма, списанная у отправителя', max_digits=8, decimal_places=2)
	currency = models.CharField(verbose_name=u'Код валюты (643 – рубль)', max_length=10)
	payment_datetime = models.DateTimeField(verbose_name=u'Время совершения перевода', db_index=True)
	sender = models.CharField(verbose_name=u'Номер счета отправителя', max_length=30)
	codepro = models.CharField(verbose_name=u'Защищён ли кодом протекции', max_length=10)
	label = models.CharField(verbose_name=u'Метка платежа', max_length=100)
	sha1_hash = models.CharField(verbose_name=u'SHA-1 хэш параметров уведомления', max_length=50)
	sha1_correct = models.BooleanField(verbose_name=u'Правилен ли ключ SHA-1?')
	test_notification = models.BooleanField(verbose_name=u'Тестовое ли уведомление?')
	unaccepted = models.BooleanField(verbose_name=u'Правда ли, что перевод не получен?')
	added_time = models.DateTimeField(verbose_name=u'Время занесения в БД', auto_now_add=True)
	class Meta:
		db_table = "dj_payment"

class Payment_moneta_response(models.Model):
	account_number = models.CharField(verbose_name=u'Номер счёта в магазине', max_length=50)
	transaction_id = models.CharField(verbose_name=u'Идентификатор заказа', max_length=100) # max_length for Moneta is 255
	moneta_operation_id = models.CharField(verbose_name=u'Номер заказа в Монете', max_length=100)
	moneta_subscriber_id = models.CharField(verbose_name=u'ID пользователя в Монете', max_length=100)
	moneta_user_account = models.CharField(verbose_name=u'Номер счёта пользователя в Монете', max_length=100)
	moneta_user_corr_account = models.CharField(verbose_name=u'Номер счёта плательщика для других платёжных систем', max_length=100)
	payment_system = models.CharField(verbose_name=u'Платёжная система, если не Монета', max_length=100)
	fee = models.DecimalField(verbose_name=u'Комиссия платёжной системы', max_digits=8, decimal_places=2, default=0)
	withdraw_amount = models.DecimalField(verbose_name=u'Сумма, списанная у отправителя', max_digits=8, decimal_places=2, default=0)
	currency = models.CharField(verbose_name=u'Код валюты', max_length=10)
	is_test_mode = models.BooleanField(verbose_name=u'Правда ли, что перевод получен в тестовом режиме', default=True)
	signature = models.CharField(verbose_name=u'Подпись MD5', max_length=32)
	is_signature_correct = models.BooleanField(verbose_name=u'Правильна ли подпись?', default=False, blank=True)
	added_time = models.DateTimeField(verbose_name=u'Время занесения в БД', auto_now_add=True)
	def get_amount(self):
		return self.withdraw_amount + self.fee
	class Meta:
		db_table = "dj_payment_moneta_response"

MIN_PAYMENT_AMOUNT = 10
MAX_PAYMENT_AMOUNT = 15000
PAYMENT_DUMMY_PREFIX = "dummy_"
class Payment_moneta(models.Model): # For Moneta.Ru payments
	amount = models.DecimalField(verbose_name=u'Сумма, списанная у отправителя', max_digits=8, decimal_places=2)
	transaction_id = models.CharField(verbose_name=u'Идентификатор заказа', max_length=100, db_index=True) # max_length for Moneta is 255

	is_test_mode = models.BooleanField(verbose_name=u'Правда ли, что перевод получен в тестовом режиме', default=False)
	is_dummy = models.BooleanField(verbose_name=u'Правда ли, что заказ фиктивный и на нулевую сумму', default=False)
	is_paid = models.BooleanField(verbose_name=u'Оплачен ли заказ', default=False, blank=True)
	is_active = models.BooleanField(verbose_name=u'Показывать ли заказ и предлагать ли для оплаты', default=True, blank=True)

	description = models.CharField(verbose_name=u'Описание заказа', max_length=1000) # max_length for Moneta is 500
	withdraw_amount = models.DecimalField(verbose_name=u'Сумма, зачисленная на счёт', max_digits=8, decimal_places=2, default=0)
	signature = models.CharField(verbose_name=u'Подпись MD5', max_length=32)
	user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Отправитель', on_delete=models.SET_NULL, default=None, null=True, blank=True)
	sender = models.CharField(verbose_name=u'Имя отправителя', max_length=100)
	added_time = models.DateTimeField(verbose_name=u'Время занесения в БД', auto_now_add=True)
	payment_time = models.DateTimeField(verbose_name=u'Время получения подтверждения перевода', db_index=True, default=None, null=True, blank=True)
	response = models.ForeignKey(Payment_moneta_response, verbose_name=u'Ответ Монеты, подтверждающий оплату',
		on_delete=models.SET_NULL, default=None, null=True, blank=True)
	def get_pay_url(self):
		return reverse('results:make_payment', kwargs={'payment_id': self.id})
	def get_absolute_url(self):
		return reverse('editor:payment_details', kwargs={'payment_id': self.id})
	def get_delete_url(self):
		return reverse('results:payment_delete', kwargs={'payment_id': self.id})
	def is_just_created(self):
		return (self.added_time + datetime.timedelta(minutes=5)) > timezone.now()
	def get_fee_percent(self):
		return '{:.2f}'.format(100 * (self.amount - self.withdraw_amount) / self.amount) if self.withdraw_amount else ''
	class Meta:
		db_table = "dj_payment_moneta"
		index_together = [
			["added_time", "is_paid", "is_active"],
		]

MEDAL_ORDER_DELIVERY_CHOICES = (
	(0, u'Заберу в рабочее время в Санкт-Петербурге в ДЦ «Маяк»: Московский проспект, 91А, м. Московские ворота' +
		u' (мы напишем вам телефон, по которому вы позвоните и договоритесь о встрече)', u'ДЦ «Маяк»'),
	(1, u'Заберу перед стартом на забеге в Санкт-Петербурге (перечислите в поле «Комментарий» летние забеги, которые вам подходят)', u'на старте'),
	(2, u'Отправьте мне медали посылкой (цена за доставку указана выше; после отправки мы пришлём вам скан квитанции и ссылку' +
		u' для оплаты точной суммы доставки)',
		u'посылка'),
	(3, u'Другой вариант доставки (укажите его в поле «Комментарий»)',
		u'другое'),
	(4, u'Заберу в Санкт-Петербурге на регистрации или на награждении марафона «Дорога жизни»' +
		u' (проверьте, что правильно указали мобильный, чтобы мы могли перед марафоном созвониться и договориться о встрече)',
		u'Дорога жизни'),
)
MEDAL_ORDER_CURRENT_CHOICES = (MEDAL_ORDER_DELIVERY_CHOICES[i] for i in [4, 2, 3])
class Medal_order(models.Model):
	lname = models.CharField(verbose_name=u'Фамилия', max_length=100)
	fname = models.CharField(verbose_name=u'Имя', max_length=100)
	zipcode = models.CharField(verbose_name=u'Почтовый индекс (если заказываете доставку)', max_length=8, blank=True)
	address = models.CharField(verbose_name=u'Почтовый адрес (если заказываете доставку)', max_length=MAX_POSTAL_ADDRESS_LENGTH, blank=True)
	email = models.CharField(verbose_name=u'E-mail для связи', max_length=MAX_EMAIL_LENGTH)
	phone_number = models.CharField(verbose_name=u'Мобильный телефон', max_length=MAX_PHONE_NUMBER_LENGTH, blank=True)

	year = models.SmallIntegerField(verbose_name=u'Год КЛБМатча', default=models_klb.MEDAL_PAYMENT_YEAR)
	n_medals = models.SmallIntegerField(verbose_name=u'Число медалей', default=1)
	delivery_method = models.SmallIntegerField(verbose_name=u'Способ доставки', choices=[(a, b) for a, b, c in MEDAL_ORDER_CURRENT_CHOICES],
		default=4)
	with_plate = models.BooleanField(verbose_name=u'Напечатать имя и команду участника на обратной стороне (60 ₽/штука)',
		default=False, blank=True)

	comment = models.CharField(verbose_name=u'Комментарий', max_length=500, blank=True)

	payment = models.OneToOneField(Payment_moneta, verbose_name=u'Платёж, которым оплачено участие', on_delete=models.SET_NULL,
		null=True, blank=True, default=None)
	created_time = models.DateTimeField(verbose_name=u'Дата создания', default=datetime.datetime.now, db_index=True)
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Кто добавил на сайт',
		on_delete=models.SET_NULL, default=None, null=True, blank=True)
	class Meta:
		db_table = "dj_medal_order"
	def to_show_name(self):
		return self.created_by and ((self.lname != self.created_by.last_name) or (self.fname != self.created_by.first_name))
	def get_delivery_method_short(self):
		return MEDAL_ORDER_DELIVERY_CHOICES[self.delivery_method][2]

class Friendship(models.Model): # Isn't used yet
	follower = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Следящий', related_name='follower_set',
		on_delete=models.CASCADE)
	target = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Цель', related_name='target_set',
		on_delete=models.CASCADE)
	added_time = models.DateTimeField(verbose_name=u'Время занесения в БД', auto_now_add=True)
	class Meta:
		db_table = "dj_friendship"
		unique_together = (("follower", "target"),)

class Calendar(models.Model):
	user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Пользователь', related_name='calendar_set', on_delete=models.CASCADE)
	event = models.ForeignKey(Event, verbose_name=u'Забег', related_name='calendar_set', on_delete=models.CASCADE)
	race = models.ForeignKey(Race, verbose_name=u'Дистанция', related_name='calendar_set', on_delete=models.CASCADE, default=None, null=True, blank=True)
	marked_as_checked = models.BooleanField(verbose_name=u'Отмечено как учтённое капитаном команды', default=False, db_index=True)
	added_time = models.DateTimeField(verbose_name=u'Время занесения в БД', auto_now_add=True)
	class Meta:
		db_table = "dj_calendar"
		unique_together = (("user", "event"),)
		ordering = ['user__last_name', 'user__first_name']

SOCIAL_TYPE_FB = 1
SOCIAL_TYPE_VK = 2
SOCIAL_TYPE_TWITTER = 3
SOCIAL_PAGE_TYPES = (
	(SOCIAL_TYPE_FB, u'Facebook'),
	(SOCIAL_TYPE_VK, u'ВКонтакте'),
	(SOCIAL_TYPE_TWITTER, u'Twitter'),
)
class Social_page(models.Model):
	page_type = models.SmallIntegerField(verbose_name=u'Тип страницы', choices=SOCIAL_PAGE_TYPES)
	page_id = models.CharField(verbose_name=u'id страницы', max_length=30)
	name = models.CharField(verbose_name=u'Название страницы', max_length=100)
	district = models.ForeignKey(District, verbose_name=u'Федеральный округ', default=None, null=True, blank=True,
		on_delete=models.PROTECT)
	is_for_all_news = models.BooleanField(verbose_name=u'Для всех новостей?', default=False, blank=True)
	url = models.URLField(verbose_name=u'Ссылка на страницу', max_length=200, blank=True)
	access_token = models.CharField(verbose_name=u'Токен для доступа к странице', max_length=200)
	token_secret = models.CharField(verbose_name=u'Секретный токен для твиттера', max_length=200, blank=True)
	class Meta:
		db_table = "dj_social_page"
		ordering = ['name', 'page_type']
	def get_absolute_url(self):
		return self.url
	def get_history_url(self):
		return reverse('editor:social_page_history', kwargs={'page_id': self.id})
	def __unicode__(self):
		return self.name + ' (' + self.url + ')'

class Social_news_post(models.Model):
	news = models.ForeignKey(News, verbose_name=u'Новость', related_name='social_post_set',
		on_delete=models.CASCADE)
	social_page = models.ForeignKey(Social_page, verbose_name=u'Страница в соцсети', related_name='news_set',
		on_delete=models.CASCADE)
	post_id = models.CharField(verbose_name=u'id поста', max_length=30)
	tweet = models.CharField(verbose_name=u'Текст поста в твиттер', max_length=400, blank=True)
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Опубликовал',
		on_delete=models.SET_NULL, default=None, null=True, blank=True)
	date_posted = models.DateTimeField(verbose_name=u'Время публикации', auto_now_add=True)
	class Meta:
		db_table = "dj_social_news_post"
		ordering = ['-date_posted']
	def get_absolute_url(self):
		if self.social_page.page_type == SOCIAL_TYPE_VK:
			return 'https://vk.com/wall-' + self.social_page.page_id + '_' + self.post_id
		elif self.social_page.page_type == SOCIAL_TYPE_FB:
			return 'https://www.facebook.com/permalink.php?story_fbid={}&id={}'.format(self.post_id, self.social_page.page_id) 
			# return self.social_page.url + '/posts/' + self.post_id
		elif self.social_page.page_type == SOCIAL_TYPE_TWITTER:
			return self.social_page.url + '/status/' + self.post_id
		return ''
	def __unicode__(self):
		return self.social_page.name + ' (' + self.date_posted.isoformat() + ')'

MESSAGE_TYPE_PERSONAL = 0
MESSAGE_TYPE_NEWSLETTER = 1
MESSAGE_TYPE_RESULTS_FOUND = 2
MESSAGE_TYPE_TO_ADMINS = 3
MESSAGE_TYPES = (
	(MESSAGE_TYPE_PERSONAL, u'Личное письмо'),
	(MESSAGE_TYPE_NEWSLETTER, u'Новостная рассылка'),
	(MESSAGE_TYPE_RESULTS_FOUND, u'Найдены новые результаты'),
	(MESSAGE_TYPE_TO_ADMINS, u'Письмо о действиях роботов'),
)
def get_attachment_name(instance, filename):
	sample = 0
	while True:
		res = "dj_media/attachments/" + datetime.datetime.today().strftime('%Y%m%d_%H%M%S_')
		if sample:
			res += '_sample{}'.format(sample)
		res += transliterate(filename)
		if os.path.exists(os.path.join(settings.MEDIA_ROOT, res)):
			sample += 1
		else:
			break
	return res
class Message_from_site(models.Model):
	table_update = models.ForeignKey(Table_update, verbose_name=u'Обновление таблицы',
		on_delete=models.SET_NULL, default=None, null=True, blank=True)
	sender_name = models.CharField(verbose_name=u'Ваше имя', max_length=100, blank=True)
	sender_email = models.CharField(verbose_name=u'Ваш электронный адрес (на него мы отправим ответ)', max_length=MAX_EMAIL_LENGTH, blank=True)
	target_email = models.CharField(verbose_name=u'Куда (можно несколько адресов через запятую)', max_length=MAX_EMAIL_LENGTH * 10, blank=True)
	cc = models.CharField(verbose_name=u'Копия (можно несколько адресов через запятую)', max_length=MAX_EMAIL_LENGTH, blank=True)
	bcc = models.CharField(verbose_name=u'Скрытая копия (можно несколько адресов через запятую)', max_length=MAX_EMAIL_LENGTH, blank=True)
	title = models.CharField(verbose_name=u'Тема сообщения', max_length=255, blank=True)
	body = models.TextField(max_length=40000, verbose_name=u'Текст сообщения')
	body_html = models.TextField(max_length=40000, verbose_name=u'Текст сообщения в HTML')
	page_from = models.CharField(verbose_name=u'С какой страницы отправлено', max_length=255, blank=True)
	attachment = models.FileField(verbose_name=u'Вы можете приложить к письму файл (не больше 20 МБ)', max_length=255,
		upload_to=get_attachment_name, blank=True)
	is_sent = models.BooleanField(verbose_name=u'Отправлено ли письмо', default=False, blank=True)
	message_type = models.SmallIntegerField(verbose_name=u'Тип письма', default=MESSAGE_TYPE_PERSONAL, choices=MESSAGE_TYPES)

	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Написал сообщение',
		on_delete=models.SET_NULL, default=None, null=True, blank=True)
	date_posted = models.DateTimeField(verbose_name=u'Время отправки', auto_now_add=True)
	def get_reverse_url(self, target):
		return reverse(target, kwargs={'message_id': self.id})
	def get_absolute_url(self):
		return self.get_reverse_url('editor:message_details')
	def get_unsubscribe_header(self):
		if self.message_type == MESSAGE_TYPE_NEWSLETTER:
			return {'List-Unsubscribe': '<mailto:{}?subject=unsubscribe-newsletters>'.format(INFO_MAIL)}
		if self.message_type == MESSAGE_TYPE_RESULTS_FOUND:
			return {'List-Unsubscribe': '<mailto:{}?subject=unsubscribe-results-found>'.format(INFO_MAIL)}
		return {}
	def try_send(self, attach_file=True):
		result = {}
		to = self.target_email.split(',')
		cc = self.cc.split(',')
		bcc = self.bcc.split(',')
		if len(to) > 1: # If we have more than one recipient, we put them all to BCC field
			bcc += to
			to = []

		headers = self.get_unsubscribe_header()
		headers['Reply-To'] = self.sender_email

		message = EmailMultiAlternatives(
			subject=self.title,
			body=self.body,
			from_email=self.sender_email,
			to=to,
			cc=cc,
			bcc=bcc,
			headers=self.get_unsubscribe_header(),
			)
		if self.body_html:
			message.attach_alternative(self.body_html, "text/html")
		try:
			if self.attachment and attach_file:
				message.attach_file(self.attachment.path)
			result['success'] = message.send()
			if result['success']:
				self.is_sent = True
				self.save()
			else:
				result['error'] = u'Мы сохранили ваше сообщение, но отправить его не получилось.'
		except Exception as e:
			result['success'] = 0
			result['error'] = repr(e)
		return result
	class Meta:
		db_table = "dj_message_from_site"

class Statistics(models.Model):
	name = models.CharField(verbose_name=u'Название поля', max_length=30, db_index=True)
	value = models.IntegerField(verbose_name=u'Значение', default=0)
	date_added = models.DateField(verbose_name=u'Дата расчёта', auto_now_add=True)
	last_update = models.DateTimeField(verbose_name=u'Дата последнего обновления', auto_now=True)
	class Meta:
		db_table = "dj_statistics"
		unique_together = (("name", "date_added"),)
	def __unicode__(self):
		return self.name + ' = ' + unicode(self.value)

DISABILITY_GROUPS = ((0, u'нет'), (1, u'первая'), (2, u'вторая'), (3, u'третья'), )
class Klb_person(models.Model):
	id = models.AutoField(primary_key=True, db_column='ID')
	# ak_person = models.OneToOneField(Ak_person_v2, verbose_name=u'id в базе АК55',
	# 	default=None, null=True, blank=True, on_delete=models.PROTECT, db_column='MANID')
	gender_raw = models.CharField(verbose_name=u'Пол (устар.)', max_length=1, db_column='Pol', blank=True)
	gender = models.SmallIntegerField(verbose_name=u'Пол', default=GENDER_UNKNOWN, db_index=True, choices=GENDER_CHOICES, db_column='dj_gender')

	country_raw = models.CharField(verbose_name=u'Страна (устар.)', max_length=100, db_column='country', blank=True)
	district_raw = models.CharField(verbose_name=u'Федеральный округ (устар.)', max_length=100, db_column='Okrug', blank=True)
	region_raw = models.CharField(verbose_name=u'Регион (устар.)', max_length=100, db_column='Oblast', blank=True)
	city_raw = models.CharField(verbose_name=u'Город (устар.)', max_length=100, db_column='Gorodp', blank=True)

	country = models.ForeignKey(Country, verbose_name=u'Страна', default="RU", null=True, on_delete=models.PROTECT, db_column='dj_country_id')
	city = models.ForeignKey(City, verbose_name=u'Город', default=None, null=True, on_delete=models.PROTECT, db_column='dj_city_id')

	email = models.CharField(verbose_name=u'E-mail', max_length=MAX_EMAIL_LENGTH, db_column='email', blank=True)
	phone_number = models.CharField(verbose_name=u'Мобильный телефон', max_length=MAX_PHONE_NUMBER_LENGTH, db_column='mobil', blank=True)
	skype = models.CharField(verbose_name=u'Skype', max_length=128, db_column='skype', blank=True)
	ICQ = models.CharField(verbose_name=u'ICQ', max_length=100, db_column='icq', blank=True)
	comment = models.CharField(verbose_name=u'Комментарий', max_length=250, db_column='comment', blank=True)
	status = models.CharField(verbose_name=u'Статус (устар.)', max_length=15, default=None, null=True, db_column='Status', blank=True) # Deprecated

	fname = models.CharField(verbose_name=u'Имя', max_length=100, db_column='Name')
	lname = models.CharField(verbose_name=u'Фамилия', max_length=100, db_column='Fam')
	midname = models.CharField(verbose_name=u'Отчество', max_length=100, db_column='Ot4estvo', blank=True)
	birthday = models.DateField(verbose_name=u'Дата рождения', db_index=True, db_column='DataRogdenia')
	nickname = models.CharField(verbose_name=u'Ник', max_length=100, db_column='Nik', blank=True)
	postal_address = models.CharField(verbose_name=u'Почтовый адрес', max_length=MAX_POSTAL_ADDRESS_LENGTH, blank=True)
	disability_group = models.SmallIntegerField(verbose_name=u'Группа инвалидности', default=0, choices=DISABILITY_GROUPS)

	added_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Кто добавил в таблицу', on_delete=models.SET_NULL,
		null=True, blank=True, related_name="klb_persons_added_by_user", db_column='dj_added_by')
	added_time = models.DateTimeField(verbose_name=u'Время создания', auto_now_add=True,
		null=True, blank=True, db_column='dj_added_time')
	last_update = models.DateTimeField(verbose_name=u'Последнее изменение', auto_now=True,
		null=True, blank=True, db_column='dj_last_update')
	def clean(self):
		if self.gender == GENDER_FEMALE:
			self.gender_raw = u'ж'
		elif self.gender == GENDER_MALE:
			self.gender_raw = u'м'
		if self.city:
			self.country = self.city.region.country
			self.city_raw = self.city.name_full(with_nbsp=False)
			if self.city.region.country.has_regions:
				self.region_raw = self.city.region.name
			else:
				self.region_raw = ""
			if self.city.region.country.id == 'RU':
				self.district_raw = self.city.region.district.name
		else:
			self.city_raw = ""
			self.region_raw = ""
			self.district_raw = ""
		if self.country:
			self.country_raw = self.country.name
		else:
			self.country_raw = ""
	def get_or_create_runner(self, user, comment=''): # TODO: remove
		# if self.ak_person and hasattr(self.ak_person, 'runner'):
		# 	runner = self.ak_person.runner
		# 	runner.klb_person = self
		# 	runner.save()
		# else:
		runner, runner_just_created = Runner.objects.get_or_create(klb_person=self, defaults={
				'lname': self.lname,
				'fname': self.fname,
				'midname': self.midname,
				'birthday': self.birthday,
				'birthday_known': (self.birthday is not None),
				'city': self.city,
				# ak_person=self.ak_person,
				'created_by': user,
			})
		if runner_just_created:
			log_obj_create(user, runner, ACTION_CREATE, comment=comment)
		return runner, runner_just_created
	def update_person_contact_fields_and_prepare_letter(self, user, team, email, phone_number, prepare_letter=False, year=None, disability_group=None):
		# If we just added or updated Klb_participant
		if team and team.year < 2018: # No need to create a letter
			return
		year = team.year if team else year # team can be None here
		person_changed_fields = []
		if email and (self.email != email):
			self.email = email
			person_changed_fields.append('email')
		if phone_number and (self.phone_number != phone_number):
			self.phone_number = phone_number
			person_changed_fields.append('phone_number')
		if (disability_group is not None) and (disability_group != self.disability_group):
			self.disability_group = disability_group
			person_changed_fields.append('disability_group')
		if person_changed_fields:
			self.save()
			log_obj_create(user, self, ACTION_UPDATE, field_list=person_changed_fields, comment=u'При добавлении участника в КЛБМатч-{}'.format(year))
		if prepare_letter and self.runner.user and (is_active_klb_year(year) or is_admin(self.runner.user)):
			User_added_to_team_or_club.objects.create(
				user=self.runner.user,
				team=team,
				added_by=user,
			)
	def create_participant(self, team, creator, year=CUR_KLB_YEAR, comment='', email='', phone_number='', add_to_club=False, disability_group=0):
		if team:
			year = team.year
			team_for_log = team
		else:
			team_for_log = Klb_team.objects.get(year=year, number=INDIVIDUAL_RUNNERS_CLUB_NUMBER)
		date_registered = datetime.date.today() if (year >= 2019) else (datetime.date.today() + datetime.timedelta(days=1)) # FIXME
		participant = Klb_participant(
			klb_person=self,
			match_year=year,
			team=team,
			date_registered=datetime.date.today(),
			email=email,
			phone_number=phone_number,
			added_by=creator,
		)
		participant.clean()
		participant.fill_age_group(commit=False)
		participant.save()
		log_obj_create(creator, self, ACTION_KLB_PARTICIPANT_CREATE, child_object=participant, comment=comment)
		log_obj_create(creator, team_for_log, ACTION_PERSON_ADD_TO_TEAM, child_object=participant, comment=comment)
		self.update_person_contact_fields_and_prepare_letter(creator, team_for_log, email, phone_number, prepare_letter=(team is not None),
			disability_group=disability_group)
		if add_to_club and team.club:
			club_member, is_changed = self.runner.add_to_club(creator, team.club, participant, datetime.date.today(), datetime.date(team.year, 12, 31))
			return participant, club_member, is_changed
		else:
			return participant, None, False
	def get_participant(self, year):
		return self.klb_participant_set.filter(match_year=year).first()
	def get_team(self, year):
		participant = self.get_participant(year)
		return participant.team if participant else None
	def has_dependent_objects(self):
		return self.klb_result_set.exists() or self.klb_participant_set.exists()
	def get_reverse_url(self, target):
		return reverse(target, kwargs={'person_id': self.id})
	def get_absolute_url(self):
		return self.get_reverse_url('results:klb_person_details')
	def get_editor_url(self):
		return self.get_reverse_url('editor:klb_person_details')
	def get_update_url(self):
		return self.get_reverse_url('editor:klb_person_update')
	def get_delete_url(self):
		return self.get_reverse_url('editor:klb_person_delete')
	def get_history_url(self):
		return self.get_reverse_url('editor:klb_person_changes_history')
	def get_refresh_url(self):
		return self.get_reverse_url('editor:klb_person_refresh_stat')
	def get_diplom_url(self):
		if KLB_DIPLOM_YEAR and self.klb_participant_set.filter(match_year=KLB_DIPLOM_YEAR).exists():
			return '{}/klb/{}/diplom/dip.php?ID={}'.format(SITE_URL_OLD, KLB_DIPLOM_YEAR, self.id)
		return '#'
	# def get_participant_update_url(self):
	# 	return self.get_reverse_url('editor:klb_person_participant_update')
	def get_old_url(self, year):
		if year > 2010:
			return '{}/klb/{}/persresults.php?ID={}'.format(SITE_URL_OLD, year, self.id)
		return ''
	def get_full_name_with_birthday(self):
		return u'{} {}{}{} ({})'.format(self.lname, self.fname, ' ' if self.midname else '', self.midname,
			date2str(self.birthday, with_nbsp=False, short_format=True))
	class Meta:
		db_table = "persons"
		index_together = [
			["lname", "fname", "midname", "birthday"],
			["country", "city"],
		]
	def __unicode__(self):
		return get_name(self)

DISTANCE_FOR_KLB_UNKNOWN = 0
DISTANCE_FOR_KLB_FORMAL = 1
DISTANCE_FOR_KLB_REAL = 2
DISTANCE_FOR_KLB_CHOICES = (
	(DISTANCE_FOR_KLB_UNKNOWN, u'неизвестно'),
	(DISTANCE_FOR_KLB_FORMAL, u'основная дистанция'),
	(DISTANCE_FOR_KLB_REAL, u'фактическая дистанция'),
)
class Klb_result(models.Model):
	id = models.AutoField(primary_key=True, db_column='IDres')
	event_raw = models.ForeignKey(Event, on_delete=models.PROTECT, db_column='ID_Probeg')
	klb_person = models.ForeignKey(Klb_person, on_delete=models.PROTECT, db_column='ider')
	klb_participant = models.ForeignKey('Klb_participant', on_delete=models.PROTECT, db_column='dj_klb_participant', default=None, null=True)
	result = models.OneToOneField(Result, default=None, null=True, on_delete=models.SET_NULL, db_column='dj_result_id')
	race = models.ForeignKey(Race, verbose_name=u'Дистанция', on_delete=models.PROTECT, default=None, null=True, blank=True, db_column='dj_race_id')

	distance_raw = models.CharField(max_length=20, db_column='Dist', blank=True)
	# time_raw = models.TimeField(default="00:00:00", db_column='FinTime')
	# It's TimeField in original DB but django doesn't work with time > 24 hours
	# time_raw = models.CharField(default="00:00:00", max_length=10, blank=True, db_column='FinTime')
	time_seconds_raw = models.IntegerField(default=0, db_column='FinTimeSec')
	klb_score = models.DecimalField(verbose_name=u'Основные очки', default=0, max_digits=5, decimal_places=3, db_column='o4ki')
	bonus_score = models.DecimalField(verbose_name=u'Бонусные очки', default=0, max_digits=5, decimal_places=3, db_column='dj_bonus_score')
	klb_score_13 = models.SmallIntegerField(default=0, db_column='o4ki13') # Something old and strange
	for_klb = models.SmallIntegerField(default=1, db_column='ppm') # if equals 0, shouldn't be counted in KLBMatch
	was_real_distance_used = models.SmallIntegerField(verbose_name=u'По какой дистанции посчитаны баллы',
		default=DISTANCE_FOR_KLB_UNKNOWN, choices=DISTANCE_FOR_KLB_CHOICES, db_column='dj_was_real_distance_used')
	is_in_best = models.BooleanField(verbose_name=u'Попадает ли в число учитывающихся основных', default=False, db_column='dj_is_in_best')
	is_in_best_bonus = models.BooleanField(verbose_name=u'Попадает ли в число учитывающихся бонусных', default=False, db_column='dj_is_in_best_bonus')
	is_error = models.BooleanField(verbose_name=u'Засчитан ли по ошибке', default=False, db_column='dj_is_error', db_index=True)

	last_update = models.DateTimeField(verbose_name=u'Время создания', auto_now_add=True, db_column='entertime') # TODO
	added_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Кто добавил в таблицу', on_delete=models.SET_NULL,
		null=True, blank=True, related_name="klb_results_added_by_user", db_column='dj_added_by')
	class Meta:
		db_table = "KLBresults"
		unique_together = (("klb_person", "race"),)
		index_together = [
			["klb_person", "is_in_best"],
			["klb_person", "is_in_best_bonus"],
			["race", "klb_score"],
		]
	def clean(self):
		if self.result:
			self.event_raw = self.result.race.event
		elif self.race:
			self.event_raw = self.race.event
	def strResult(self):
		if self.result:
			return unicode(self.result)
		if self.race:
			distance = self.race.distance
			if distance.distance_type == TYPE_MINUTES:
				return self.distance_raw + u' м'
			else:
				return secs2time(self.time_seconds_raw)
		return u'неизвестно'
	def total_score(self):
		return self.klb_score + self.bonus_score
	def get_team(self):
		return self.klb_person.get_team(self.race.event.start_date.year)
	def __unicode__(self):
		return u'{} {} (id {}): {}, {}'.format(
			self.klb_person.fname, self.klb_person.lname, self.klb_person.id, self.distance_raw, self.time_seconds_raw)

ORDERING_SCORE_SUM = 0
ORDERING_NAME = 1
ORDERING_BONUSES = 2
ORDERING_CLEAN_SCORE = 3
ORDERING_N_STARTS = 4
class Klb_team(models.Model):
	club = models.ForeignKey(Club, verbose_name=u'Клуб', on_delete=models.PROTECT, db_column='IDKLB')
	number = models.SmallIntegerField(verbose_name=u'Номер команды (не уникален)', db_column='IDCOM')
	year = models.SmallIntegerField(verbose_name=u'Год участия', db_column='god')
	name = models.CharField(verbose_name=u'Название команды', db_index=True, max_length=100, db_column='titul')
	score = models.DecimalField(verbose_name=u'Очки + бонусы', default=0, max_digits=7, decimal_places=3, db_column='O4ki')
	bonus_score = models.DecimalField(verbose_name=u'Бонусные очки', default=0, max_digits=7, decimal_places=3, db_column='Bonus')
	n_members = models.SmallIntegerField(verbose_name=u'Число заявленных за команду', default=0, db_column='dj_n_members')
	n_members_started = models.SmallIntegerField(verbose_name=u'Число стартовавших за команду', default=0, db_column='Started')
	place = models.SmallIntegerField(verbose_name=u'Место в Матче', null=True, default=None, db_column='dj_place')
	place_small_teams = models.SmallIntegerField(verbose_name=u'Место среди маленьких команд',
		null=True, default=None, db_column='dj_place_small_teams')
	place_medium_teams = models.SmallIntegerField(verbose_name=u'Место среди средних команд',
		null=True, default=None, db_column='dj_place_medium_teams')
	place_secondary_teams = models.SmallIntegerField(verbose_name=u'Место среди команд-дублёров', null=True, default=None)
	is_not_secondary_team = models.BooleanField(verbose_name=u'Не хочет участвовать в первенстве дублёров', default=False, blank=True)
	added_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Кто добавил в таблицу', on_delete=models.SET_NULL,
		null=True, blank=True, related_name="klb_teams_added_by_user", db_column='dj_added_by')
	added_time = models.DateTimeField(verbose_name=u'Время создания', auto_now_add=True,
		null=True, blank=True, db_column='dj_added_time')
	last_update = models.DateTimeField(verbose_name=u'Последнее изменение', auto_now=True,
		null=True, blank=True, db_column='dj_last_update')
	class Meta:
		db_table = "KLBcommand"
		unique_together = (("club", "number", "year"),)
		index_together = [
			["year", "place"],
			["year", "place_small_teams"],
			["year", "place_medium_teams"],
			["year", "place_secondary_teams"],
		]
	def get_reverse_url(self, target):
		return reverse(target, kwargs={'team_id': self.id})
	def get_absolute_url(self):
		return self.get_reverse_url('results:klb_team_details')
	def get_details_full_url(self):
		return self.get_reverse_url('results:klb_team_details_full')
	def get_score_changes_url(self):
		return self.get_reverse_url('results:klb_team_score_changes')
	def get_results_for_moderation_url(self):
		return self.get_reverse_url('results:klb_team_results_for_moderation')
	def get_refresh_stat_url(self):
		return self.get_reverse_url('results:klb_team_refresh_stat')
	def get_payment_url(self):
		return self.get_reverse_url('results:klb_team_payment')
	def get_contact_info_url(self):
		return self.get_reverse_url('editor:klb_team_contact_info')
	def get_did_not_run_url(self):
		return self.get_reverse_url('editor:klb_team_did_not_run')
	def get_add_old_participants_url(self):
		return self.get_reverse_url('editor:klb_team_add_old_participants')
	def get_delete_participants_url(self):
		return self.get_reverse_url('editor:klb_team_delete_participants')
	def get_add_new_participant_url(self):
		return self.get_reverse_url('editor:klb_team_add_new_participant')
	def get_move_participants_url(self):
		return self.get_reverse_url('editor:klb_team_move_participants')
	def get_change_name_url(self):
		return self.get_reverse_url('editor:klb_team_change_name')
	def get_history_url(self):
		return self.get_reverse_url('editor:klb_team_changes_history')
	def get_delete_url(self):
		return self.get_reverse_url('editor:klb_team_delete')
	def get_old_url(self):
		return '{}/klb/{}/team.php?detailcom={}'.format(SITE_URL_OLD, self.year, self.number)
	def get_clean_score(self):
		return self.score - self.bonus_score
	def get_next_team(self):
		if self.place is None:
			return None
		return Klb_team.objects.filter(year=self.year, place=self.place - 1).first()
	def get_prev_team(self):
		if self.place is None:
			return None
		return Klb_team.objects.filter(year=self.year, place=self.place + 1).first()
	def get_next_medium_team(self):
		if self.place_medium_teams is None:
			return None
		return Klb_team.objects.filter(year=self.year, place_medium_teams=self.place_medium_teams - 1).first()
	def get_prev_medium_team(self):
		if self.place_medium_teams is None:
			return None
		return Klb_team.objects.filter(year=self.year, place_medium_teams=self.place_medium_teams + 1).first()
	def get_next_small_team(self):
		if self.place_small_teams is None:
			return None
		return Klb_team.objects.filter(year=self.year, place_small_teams=self.place_small_teams - 1).first()
	def get_prev_small_team(self):
		if self.place_small_teams is None:
			return None
		return Klb_team.objects.filter(year=self.year, place_small_teams=self.place_small_teams + 1).first()
	def is_in_active_year(self):
		return is_active_klb_year(self.year)
	def update_context_for_team_page(self, context, user, ordering=ORDERING_CLEAN_SCORE):
		context['teams_number'] = Klb_team.get_teams_number(year=self.year)
		if self.place_medium_teams:
			context['medium_teams_number'] = Klb_team.get_medium_teams_number(year=self.year)
		elif self.place_small_teams:
			context['small_teams_number'] = Klb_team.get_small_teams_number(year=self.year)
		context['team'] = self
		context['participants'] = self.klb_participant_set.select_related('klb_person__runner__user__user_profile', 'team__club')
		fields_for_order = []
		if ordering == ORDERING_BONUSES:
			fields_for_order.append('-bonus_sum')
		elif ordering == ORDERING_CLEAN_SCORE:
			context['participants'] = context['participants'].annotate(clean_sum=F('score_sum') - F('bonus_sum'))
			fields_for_order.append('-clean_sum')
		elif ordering == ORDERING_SCORE_SUM:
			fields_for_order.append('-score_sum')
		elif ordering == ORDERING_N_STARTS:
			fields_for_order.append('-n_starts')
		elif ordering == ORDERING_NAME:
			fields_for_order += ['klb_person__lname', 'klb_person__fname']
		for field in ['-n_starts', 'klb_person__lname', 'klb_person__fname']:
			if field not in fields_for_order:
				fields_for_order.append(field)

		context['participants'] = context['participants'].order_by(*fields_for_order)
		context['CUR_KLB_YEAR'] = CUR_KLB_YEAR
		context['ordering'] = ordering
		context['n_runners_for_team_clean_score'] = models_klb.get_n_runners_for_team_clean_score(self.year)
		context['n_results_for_bonus_score'] = models_klb.get_n_results_for_bonus_score(self.year)
		if context['is_admin'] or context['is_editor']:
			cur_year_teams = self.club.klb_team_set.filter(year=self.year)
			context['has_old_participants_to_add'] = self.club.klb_team_set.filter(year=self.year - 1).exists() or self.club.club_member_set.exists()
			context['has_participants_to_delete'] = self.klb_participant_set.filter(n_starts=0).exists()
			context['can_be_deleted'] = is_active_klb_year(self.year, context['is_admin']) \
				and (not cur_year_teams.filter(number__gt=self.number).exists()) \
				and (not self.klb_participant_set.exists())
			context['can_add_participants'] = self.klb_participant_set.count() < models_klb.get_team_limit(self.year)
			context['can_move_participants'] = (cur_year_teams.count() > 1) and (datetime.date.today() <= datetime.date(self.year, 5, 31)) \
				and context['can_add_participants']
		return context
	def string_contains_team_or_club_name(self, s):
		s = s.lower()
		if (self.name.lower() in s) or (self.club.name.lower() in s):
			return True
		for club_name in self.club.club_name_set.values_list('name', flat=True):
			if club_name.lower() in s:
				return True
		return False
	def __unicode__(self):
		res = self.name
		if self.club.city:
			res += u' ({})'.format(self.club.city.name_full(with_nbsp=False))
		return res
	@classmethod
	def get_teams_number(cls, year):
		return cls.objects.filter(year=year, n_members__gt=0).exclude(number=INDIVIDUAL_RUNNERS_CLUB_NUMBER).count()
	@classmethod
	def get_large_teams_number(cls, year):
		return cls.objects.filter(year=year, n_members__gt=0, place_medium_teams=None, place_small_teams=None).exclude(
			number=INDIVIDUAL_RUNNERS_CLUB_NUMBER).count()
	@classmethod
	def get_medium_teams_number(cls, year):
		return cls.objects.filter(year=year, n_members__gt=0, place_medium_teams__isnull=False).count()
	@classmethod
	def get_small_teams_number(cls, year):
		return cls.objects.filter(year=year, n_members__gt=0, place_small_teams__isnull=False).count()

class Klb_report(models.Model):
	year = models.SmallIntegerField(verbose_name=u'Год КЛБМатча')
	file = models.FileField(verbose_name=u'Файл с данными', max_length=255)
	is_public = models.BooleanField(verbose_name=u'Доступен ли посетителям или только админам', default=False, blank=True)
	was_reported = models.BooleanField(verbose_name=u'Написали ли в письме админам, что этот слепок создан', default=False, blank=True)
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Кто создал', on_delete=models.SET_NULL, null=True, blank=True)
	time_created = models.DateTimeField(verbose_name=u'Время создания', auto_now_add=True)
	class Meta:
		db_table = "dj_klb_report"
@receiver(pre_delete, sender=Klb_report)
def pre_klb_report_delete(sender, instance, **kwargs):
	if instance.file:
		instance.file.delete(False)

KLB_REPORT_STAT_TEAMS = 1
KLB_REPORT_STAT_PARTICIPANTS = 2
KLB_REPORT_STAT_RESULTS = 3
KLB_REPORT_STAT_GOOD_DISTANCES = 4
KLB_REPORT_STAT_BAD_DISTANCES = 5
KLB_REPORT_STATS = (
	(KLB_REPORT_STAT_TEAMS, u'Число команд'),
	(KLB_REPORT_STAT_PARTICIPANTS, u'Число участников'),
	(KLB_REPORT_STAT_RESULTS, u'Число учтённых результатов'),
	(KLB_REPORT_STAT_GOOD_DISTANCES, u'Дистанции с хотя бы одним результатом'),
	(KLB_REPORT_STAT_BAD_DISTANCES, u'Дистанции, не учтённые в матче'),
)
class Klb_report_stat(models.Model):
	klb_report = models.ForeignKey(Klb_report, verbose_name=u'Слепок', on_delete=models.CASCADE)
	stat_type = models.SmallIntegerField(verbose_name=u'Параметр', choices=KLB_REPORT_STATS)
	value = models.IntegerField(verbose_name=u'Значение', default=0)
	time_created = models.DateTimeField(verbose_name=u'Время создания', auto_now_add=True)
	class Meta:
		db_table = "dj_klb_report_stat"
		unique_together = (('klb_report', 'stat_type'),)

class User_added_to_team_or_club(models.Model):
	""" События добавления пользователей сайта в команды КЛБМатча или в клубы — чтобы их предупредить о произошедшем.
		Ровно одно из полей team и club должно быть непусто. """
	user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Пользователь', on_delete=models.CASCADE)
	team = models.ForeignKey(Klb_team, verbose_name=u'Команда', on_delete=models.CASCADE, default=None, null=True, blank=True)
	club = models.ForeignKey(Club, verbose_name=u'Клуб', on_delete=models.CASCADE, default=None, null=True, blank=True)
	added_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Добавил в команду',
		on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name="added_to_klb_team_by_user")
	added_time = models.DateTimeField(verbose_name=u'Время занесения в БД', auto_now_add=True)
	sent_time = models.DateTimeField(verbose_name=u'Время отправки письма', default=None, null=True, blank=True)
	class Meta:
		db_table = "dj_user_added_to_team_or_club"

class Klb_age_group(models.Model):
	match_year = models.SmallIntegerField(verbose_name=u'Год матча')
	birthyear_min = models.SmallIntegerField(verbose_name=u'Минимальный год рождения', default=None, null=True)
	birthyear_max = models.SmallIntegerField(verbose_name=u'Максимальный год рождения', default=None, null=True)
	gender = models.SmallIntegerField(verbose_name=u'Пол', choices=GENDER_CHOICES)
	name = models.CharField(verbose_name=u'Название группы', max_length=40)
	n_participants = models.SmallIntegerField(verbose_name=u'Число участников', default=0)
	n_participants_started = models.SmallIntegerField(verbose_name=u'Число стартовавших участников', default=0)
	order_value = models.SmallIntegerField(verbose_name=u'Значение для сортировки', default=0)
	class Meta:
		db_table = "dj_klb_age_group"
		unique_together = (("match_year", "gender", "birthyear_min"), ("match_year", "gender", "birthyear_max"))
		index_together = [
			["match_year", "order_value", "gender", "birthyear_min"],
		]
	def get_absolute_url(self):
		return reverse('results:klb_age_group_details', kwargs={'age_group_id': self.id})
	def get_old_url(self):
		return '{}/klb/{}/memberso.php'.format(SITE_URL_OLD, self.match_year)
	def __unicode__(self):
		return self.name
	@classmethod
	def get_groups_by_year(cls, year):
		return cls.objects.filter(match_year=year).order_by('order_value', 'gender', '-birthyear_min')

PAID_STATUS_NO = 0
PAID_STATUS_FREE = 1
PAID_STATUS_FULL = 2
PAID_STATUSES = (
	(PAID_STATUS_NO, u'участие не оплачено'),
	(PAID_STATUS_FREE, u'участвует бесплатно'),
	(PAID_STATUS_FULL, u'участие оплачено'),
)

class Klb_participant(models.Model):
	id = models.AutoField(primary_key=True, db_column='dj_id')
	klb_person = models.ForeignKey(Klb_person, verbose_name=u'ID участника КЛБМатча', on_delete=models.CASCADE, db_column='idbegun')
	match_year = models.SmallIntegerField(verbose_name=u'Год матча', db_column='god')
	team_number = models.SmallIntegerField(verbose_name=u'Номер команды в этом году', db_column='klbgod')
	team = models.ForeignKey(Klb_team, verbose_name=u'Команда', on_delete=models.PROTECT, default=None, null=True, blank=True, db_column='dj_team_id')
	date_registered = models.DateField(verbose_name=u'Дата добавления в команду', default=None, null=True, blank=True, db_column='RegData')
	date_removed = models.DateField(verbose_name=u'Дата исключения из команды', default=None, null=True, blank=True, db_column='OutData')
	score_sum = models.DecimalField(verbose_name=u'Основные очки + бонус', default=0, max_digits=5, decimal_places=3, db_column='So4ki')
	bonus_sum = models.DecimalField(verbose_name=u'Бонусные очки', default=0, max_digits=5, decimal_places=3, db_column='Bonus')
	n_starts = models.SmallIntegerField(default=0, db_column='Starts')

	is_in_best = models.BooleanField(verbose_name=u'Попадает ли в число учитывающихся в этом году', default=False, db_column='dj_is_in_best')
	place = models.SmallIntegerField(verbose_name=u'Место в индивидуальном зачёте', null=True, default=None, db_column='dj_place')
	age_group = models.ForeignKey(Klb_age_group, verbose_name=u'Возрастная группа', on_delete=models.PROTECT, 
		default=None, null=True, blank=True, db_column='dj_klb_age_group_id')
	place_group = models.SmallIntegerField(verbose_name=u'Место в возрастной группе', null=True, default=None, db_column='dj_place_group')
	place_gender = models.SmallIntegerField(verbose_name=u'Место среди пола', null=True, default=None, db_column='dj_place_gender')
	
	email = models.CharField(verbose_name=u'E-mail', max_length=MAX_EMAIL_LENGTH, db_column='dj_email', blank=True)
	phone_number = models.CharField(verbose_name=u'Мобильный телефон', max_length=MAX_PHONE_NUMBER_LENGTH, db_column='dj_phone_number', blank=True)
	phone_number_clean = models.CharField(verbose_name=u'Мобильный телефон (только цифры)', max_length=MAX_PHONE_NUMBER_LENGTH,
		db_column='dj_phone_number_clean', blank=True)
	is_senior = models.BooleanField(verbose_name=u'Пенсионер ли', default=False, db_column='dj_is_senior')

	payment = models.ForeignKey(Payment_moneta, verbose_name=u'Платёж, которым оплачено участие', on_delete=models.SET_NULL,
		null=True, blank=True, default=None)
	is_paid_through_site = models.BooleanField(verbose_name=u'Сделан ли платёж через сайт', default=True, db_column='dj_is_paid_through_site')
	paid_status = models.SmallIntegerField(verbose_name=u'Оплачено ли участие', default=PAID_STATUS_NO, choices=PAID_STATUSES)
	wants_to_pay_zero = models.BooleanField(verbose_name=u'Хотят ли за него заплатить ноль', default=False, db_column='dj_wants_to_pay_zero')
	was_deleted_from_team = models.BooleanField(verbose_name=u'Был ли удалён из команды со всеми результатами', default=False, db_column='dj_was_deleted_from_team')

	added_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Кто добавил в таблицу', on_delete=models.SET_NULL,
		null=True, blank=True, related_name="klb_participants_added_by_user", db_column='dj_added_by')
	added_time = models.DateTimeField(verbose_name=u'Время создания', auto_now_add=True, null=True, blank=True, db_column='dj_added_time')
	last_update = models.DateTimeField(verbose_name=u'Последнее изменение', auto_now=True, null=True, blank=True, db_column='dj_last_update')
	class Meta:
		db_table = "KLBppX"
		index_together = [
			["klb_person", "match_year", "is_in_best"],
			["match_year", "age_group", "place_group"],
			["match_year", "place"],
			["match_year", "paid_status"],
			["phone_number_clean"],
			["team", "paid_status"],
		]
	def calculate_team_number(self):
		if self.team:
			return self.team.number
		else:
			return INDIVIDUAL_RUNNERS_CLUB_NUMBER
	def clean(self):
		self.team_number = self.calculate_team_number()
		self.is_senior = (self.klb_person.gender == GENDER_FEMALE and self.klb_person.birthday.year <= (self.match_year - results_util.SENIOR_AGE_FEMALE)) \
			or (self.klb_person.gender == GENDER_MALE and self.klb_person.birthday.year <= (self.match_year - results_util.SENIOR_AGE_MALE))
		self.phone_number_clean = ''.join(c for c in self.phone_number if c.isdigit())
		# TODO Remove in after 2020-01
		if self.match_year == 2020:
			today = datetime.date.today()
			if (today.year == 2020) and (today.month == 1):
				self.date_registered = min(self.date_registered, datetime.date(2020, 1, 1))
	def clean_sum(self):
		return self.score_sum - self.bonus_sum
	def get_next_overall(self):
		if self.place is None:
			return None
		return Klb_participant.objects.filter(match_year=self.match_year, place=self.place - 1).first()
	def get_prev_overall(self):
		if self.place is None:
			return None
		return Klb_participant.objects.filter(match_year=self.match_year, place=self.place + 1).first()
	def get_next_gender(self):
		if self.place_gender is None:
			return None
		return Klb_participant.objects.filter(match_year=self.match_year, klb_person__gender=self.klb_person.gender,
			place_gender=self.place_gender - 1).first()
	def get_prev_gender(self):
		if self.place_gender is None:
			return None
		return Klb_participant.objects.filter(match_year=self.match_year, klb_person__gender=self.klb_person.gender,
			place_gender=self.place_gender + 1).first()
	def get_next_group(self):
		if self.place_group is None:
			return None
		return Klb_participant.objects.filter(age_group=self.age_group, place_group=self.place_group - 1).first()
	def get_prev_group(self):
		if self.place_group is None:
			return None
		return Klb_participant.objects.filter(age_group=self.age_group, place_group=self.place_group + 1).first()
	def get_overall_group(self):
		return Klb_age_group.objects.filter(match_year=self.match_year, gender=GENDER_UNKNOWN).first()
	def get_gender_group(self):
		return Klb_age_group.objects.filter(match_year=self.match_year, gender=self.klb_person.gender, birthyear_min=None).first()
	def get_last_day_to_pay(self):
		if self.date_registered:
			day = monthrange(self.date_registered.year, self.date_registered.month)[1]
			return datetime.date(self.date_registered.year, self.date_registered.month, day)
		return None
	def create_stat(self, stat_type, value):
		if value:
			Klb_participant_stat.objects.create(klb_participant=self, stat_type=stat_type, value=value)
	def fill_age_group(self, commit=True):
		age_group = Klb_age_group.objects.filter(
				match_year=self.match_year,
				gender=self.klb_person.gender,
				birthyear_min__lte=self.klb_person.birthday.year,
				birthyear_max__gte=self.klb_person.birthday.year,
			).first()
		if age_group:
			if age_group == self.age_group:
				return 0
			else:
				self.age_group = age_group
				if commit:
					self.save()
				return 1
		else:
			return -1
	# Returns true; the club name set; user registration date
	# iff user is registered not later than the date (or event_date is None) of event and set the name of her club or team
	def did_user_set_correct_club(self, event_date=None):
		user_club = ''
		date_joined = None
		if self.team and self.klb_person.runner.user and hasattr(self.klb_person.runner.user, 'user_profile'):
			user = self.klb_person.runner.user
			date_joined = user.date_joined.date()
			if (event_date is None) or (date_joined <= event_date):
				user_club = user.user_profile.club_name
				user_club_lower = user_club.lower()
				if (self.team.name.lower() in user_club_lower) or (self.team.club.name.lower() in user_club_lower):
					return True, user_club, date_joined
				for club_name in self.team.club.club_name_set.all():
					if club_name.name.lower() in user_club_lower:
						return True, user_club, date_joined
		return False, user_club, date_joined
	def get_edit_contact_info_url(self):
		return reverse('editor:klb_participant_for_captain_details', kwargs={'participant_id': self.id})
	def __unicode__(self):
		return  u'{} {} (id {}): {}'.format(self.klb_person.fname, self.klb_person.lname, self.klb_person.id, self.match_year)

KLB_STAT_LENGTH = 1
KLB_STAT_N_MARATHONS = 2
KLB_STAT_N_ULTRAMARATHONS = 3
KLB_STAT_18_BONUSES = 4
KLB_STAT_N_MARATHONS_AND_ULTRA_MALE = 5
KLB_STAT_N_MARATHONS_AND_ULTRA_FEMALE = 6
KLB_STAT_CHOICES = (
	(KLB_STAT_LENGTH, u'Общая преодолённая дистанция'),
	(KLB_STAT_N_MARATHONS, u'Число марафонов'),
	(KLB_STAT_N_ULTRAMARATHONS, u'Число сверхмарафонов'),
	(KLB_STAT_18_BONUSES, u'Пройденное расстояние на 18 самых длинных стартах'),
	(KLB_STAT_N_MARATHONS_AND_ULTRA_MALE, u'Общее число марафонов и сверхмарафонов (мужчины)'),
	(KLB_STAT_N_MARATHONS_AND_ULTRA_FEMALE, u'Общее число марафонов и сверхмарафонов (женщины)'),
)
KLB_STAT_CHOICES_DICT = dict(KLB_STAT_CHOICES)
class Klb_participant_stat(models.Model):
	klb_participant = models.ForeignKey(Klb_participant, verbose_name=u'Участник КЛБМатча',
		on_delete=models.CASCADE, null=True, default=None, blank=True)
	stat_type = models.SmallIntegerField(verbose_name=u'Тип величины', choices=KLB_STAT_CHOICES)
	value = models.IntegerField(verbose_name=u'Значение', default=0)
	place = models.SmallIntegerField(verbose_name=u'Место', null=True, default=None)
	class Meta:
		db_table = "dj_klb_participant_stat"
		unique_together = (("klb_participant", "stat_type"),)
		index_together = [
			["stat_type", "place"],
		]
	def get_match_category(self):
		return Klb_match_category.get_categories_by_year(self.klb_participant.match_year).filter(stat_type=self.stat_type).first()
	def get_stat_url(self):
		category = self.get_match_category()
		if category:
			return category.get_absolute_url()
		return ''
	def __unicode__(self):
		if self.stat_type in [KLB_STAT_LENGTH, KLB_STAT_18_BONUSES]:
			return total_length2string(self.value)
		else:
			return unicode(self.value)

class Klb_team_score_change(models.Model):
	team = models.ForeignKey(Klb_team, verbose_name=u'Команда', on_delete=models.CASCADE)
	race = models.ForeignKey(Race, on_delete=models.CASCADE, default=None, blank=True, null=True)
	clean_sum = models.DecimalField(verbose_name=u'Чистые очки', default=0, max_digits=7, decimal_places=3)
	bonus_sum = models.DecimalField(verbose_name=u'Бонусные очки', default=0, max_digits=7, decimal_places=3)
	delta = models.DecimalField(verbose_name=u'Изменение с прошлого', default=0, max_digits=7, decimal_places=3)
	n_persons_touched = models.SmallIntegerField(verbose_name=u'Затронуто участников', default=0, db_column='Starts')
	comment = models.CharField(verbose_name=u'Комментарий', max_length=300, blank=True)
	added_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Администратор', on_delete=models.SET_NULL, null=True, blank=True)
	added_time = models.DateTimeField(verbose_name=u'Время создания', auto_now_add=True, null=True, blank=True)
	class Meta:
		db_table = "dj_klb_team_score_change"
		index_together = [
			["team", "added_time"],
		]
	def total_sum(self):
		return self.clean_sum + self.bonus_sum
	def __unicode__(self):
		return  u'Изменение у команды {} за {} год. Новые очки: {}, бонус: {}'.format(self.team.name, self.team.year, self.clean_sum, self.bonus_sum)
	@classmethod
	def get_last_score(cls, team):
		return cls.objects.filter(team=team).order_by('-added_time').first()

class Klb_match_category(models.Model):
	year = models.SmallIntegerField(verbose_name=u'Год')
	stat_type = models.SmallIntegerField(verbose_name=u'Тип величины', choices=KLB_STAT_CHOICES)
	n_participants_started = models.SmallIntegerField(verbose_name=u'Число стартовавших участников', default=0)
	class Meta:
		db_table = "dj_klb_match_category"
		unique_together = (("year", "stat_type"),)
	def get_absolute_url(self):
		return reverse('results:klb_match_category_details', kwargs={'match_category_id': self.id})
	def __unicode__(self):
		return self.get_stat_type_display()
	@classmethod
	def get_categories_by_year(cls, year):
		return cls.objects.filter(year=year).order_by('stat_type')

# Obj must have fields lname, fname, midname
def get_name(obj):
	if obj.midname:
		return u'{} {} {}'.format(obj.fname, obj.midname, obj.lname)
	if obj.lname:
		return u'{} {}'.format(obj.fname, obj.lname)
	return u'(неизвестно)'

def fill_user_value(results, user, user_for_action, comment=''):
	res = 0
	for result in results.select_related('race__event'):
		result.user = user
		result.save()
		log_obj_create(user_for_action, result.race.event, ACTION_RESULT_UPDATE, field_list=['user'], child_object=result, comment=comment)
		res += 1
	return res
class Runner(models.Model):
	klb_person = models.OneToOneField(Klb_person, verbose_name=u'id в КЛБМатче', on_delete=models.SET_NULL, default=None, null=True, blank=True)
	user = models.OneToOneField(settings.AUTH_USER_MODEL, verbose_name=u'id пользователя сайта', on_delete=models.SET_NULL,
		default=None, null=True, blank=True)
	# ak_person = models.OneToOneField(Ak_person_v2, verbose_name=u'id в базе АК55',
	# 	on_delete=models.SET_NULL, default=None, null=True, blank=True)
	parkrun_id = models.IntegerField(verbose_name=u'parkrun id', unique=True, default=None, null=True, blank=True, db_index=True)

	lname = models.CharField(verbose_name=u'Фамилия', max_length=100, blank=True)
	fname = models.CharField(verbose_name=u'Имя', max_length=100, blank=True, db_index=True)
	midname = models.CharField(verbose_name=u'Отчество', max_length=100, blank=True)
	birthday = models.DateField(verbose_name=u'День или год рождения', default=None, null=True, blank=True, db_index=True)
	# If true, we know exact date of birth (otherwise usually birthday should be 01.01.)
	birthday_known = models.BooleanField(verbose_name=u'Известен ли день рождения', default=False)
	gender = models.SmallIntegerField(verbose_name=u'Пол', default=GENDER_UNKNOWN, choices=GENDER_CHOICES)
	city = models.ForeignKey(City, verbose_name=u'Город', on_delete=models.PROTECT, default=None, null=True, blank=True)
	club_name = models.CharField(verbose_name=u'Клуб', max_length=100, blank=True)
	deathday = models.DateField(verbose_name=u'Дата смерти', default=None, null=True, blank=True, db_index=True)
	url_wiki = models.URLField(verbose_name=u'Ссылка на страницу с информацией о спортсмене', max_length=200, blank=True)

	n_starts = models.SmallIntegerField(verbose_name=u'Число финишей', default=None, null=True, blank=True)
	total_length = models.IntegerField(verbose_name=u'Общая пройденная дистанция в метрах', default=None, null=True, blank=True)
	total_time = models.IntegerField(verbose_name=u'Общее время на забегах в сотых секунды', default=None, null=True, blank=True)

	n_starts_2019 = models.SmallIntegerField(verbose_name=u'Число финишей в 2019', default=None, null=True, blank=True)
	total_length_2019 = models.IntegerField(verbose_name=u'Общая пройденная дистанция в метрах в 2019', default=None, null=True, blank=True)
	total_time_2019 = models.IntegerField(verbose_name=u'Общее время на забегах в сотых секунды в 2019', default=None, null=True, blank=True)
	n_starts_2020 = models.SmallIntegerField(verbose_name=u'Число финишей в 2020', default=None, null=True, blank=True)
	total_length_2020 = models.IntegerField(verbose_name=u'Общая пройденная дистанция в метрах в 2020', default=None, null=True, blank=True)
	total_time_2020 = models.IntegerField(verbose_name=u'Общее время на забегах в сотых секунды в 2020', default=None, null=True, blank=True)
	has_many_distances = models.BooleanField(verbose_name=u'Имеет ли больше разных дистанций, чем отображаем по умолчанию', default=False)

	n_parkrun_results = models.IntegerField(verbose_name=u'Число результатов на паркранах', default=0, blank=True)
	comment_private = models.CharField(verbose_name=u'Комментарий администраторам (не виден посетителям)', max_length=250, blank=True)
	private_data_hidden = models.BooleanField(verbose_name=u'Нужно ли скрыть персональные данные человека', default=False, db_index=True)

	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Создал бегуна', related_name='runners_created_set',
		on_delete=models.SET_NULL, default=None, null=True, blank=True)
	added_time = models.DateTimeField(verbose_name=u'Время создания в БД', auto_now_add=True)
	class Meta:
		db_table = "dj_runner"
		index_together = [
			["lname", "fname", "midname", "private_data_hidden"],
			["birthday_known", "birthday"],
			["n_starts", "lname", "fname"],
			["total_length", "lname", "fname"],
			["total_time", "lname", "fname"],
			["n_starts_2020", "lname", "fname"],
			["total_length_2020", "lname", "fname"],
			["total_time_2020", "lname", "fname"],
		]
	def get_common_fields(self, runner):
		common_fields = []
		for field in ['klb_person', 'user', 'parkrun_id']: # , 'ak_person'
			if (getattr(self, field) is not None) and (getattr(runner, field) is not None):
				common_fields.append(field)
		return common_fields
	def get_result_set(self):
		return self.result_set.select_related('klb_result__klb_person__runner', 'race__distance', 'race__distance_real',
			'race__event__series__city__region__country', 'race__event__city__region__country', 'race__event__series__country').order_by(
			'-race__event__start_date')
	def create_klb_person(self, creator, comment=''):
		if self.user and hasattr(self.user, 'user_profile'): # We try to update runner from user if possible
			profile = self.user.user_profile
			for field_name in ['midname', 'gender', 'city']:
				if getattr(profile, field_name) and not getattr(self, field_name):
					setattr(self, field_name, getattr(profile, field_name))
			if profile.birthday and not self.birthday_known:
				self.birthday = profile.birthday
				self.birthday_known = True
		person = Klb_person(
			added_by=creator,
			lname=self.lname,
			fname=self.fname,
			midname=self.midname,
			gender=self.gender,
			city=self.city,
			birthday=self.birthday,
		)
		person.clean()
		person.save()
		self.klb_person = person
		self.save()
		log_obj_create(creator, person, ACTION_CREATE, comment=comment)
		return person
	def merge(self, runner, user): # Moves all fields of runner to self. Returns <was merged?>, <error message>
		common_fields = self.get_common_fields(runner)
		if common_fields:
			write_log("{} RUNNER_MERGE Merging runner_id {} with runner_id {} is impossible. Common fields: [{}].".format(
				datetime.datetime.now(), self.id, runner.id, ', '.join(common_fields)))
			log_obj_create(user, self, ACTION_MERGE_FAILED, field_list=common_fields, child_object=runner,
				comment=u'Поглощение бегуна с id {} не удалось. Разобраться и ответить пользователю!'.format(runner.id))
			send_panic_email(
				'Runners merging is impossible',
				u'Problem occured when user {} (id {}) tried to merge runners {} and {}: they have common fields.'.format(
					user.get_full_name(), user.id, self.get_name_and_id(), runner.get_name_and_id())
			)
			if is_admin(user):
				return False, u'У обоих бегунов есть привязки к полям: {}. Поглощение бегуна невозможно.'.format(', '.join(common_fields))
			else:
				return False, u'У Вас и у нужного результата разные привязки к бегунам. Администраторы уже изучают вопрос.'

		comment = u'При приклеивании бегуна {} (id {}) к бегуну {} (id {})'.format(unicode(runner), runner.id, unicode(self), self.id)

		self_club_ids = set(self.club_member_set.values_list('club_id', flat=True))
		problem_club_members = list(runner.club_member_set.filter(club_id__in=self_club_ids))
		for club_member in problem_club_members:
			self_club_member = self.club_member_set.get(club_id=club_member.club_id)
			self_club_member.merge(user, club_member, comment=comment)
		for club_member in problem_club_members:
			log_obj_create(user, club_member.club, ACTION_CLUB_MEMBER_DELETE, child_object=club_member, field_list=[], comment=comment)
			club_member.delete()
		runner.club_member_set.update(runner=self)

		changed_fields = []
		problem_fields = []
		n_results_touched = 0
		if runner.user:
			self.user = runner.user
			n_results_touched += fill_user_value(self.result_set, self.user, user, comment=comment)
			runner.user = None
			changed_fields.append('user')
		elif self.user:
			n_results_touched += fill_user_value(runner.result_set, self.user, user, comment=comment)
		if runner.klb_person:
			self.klb_person = runner.klb_person
			runner.klb_person = None
			changed_fields.append('klb_person')
			n_results_touched += Result.objects.filter(klb_result__klb_person=self.klb_person).update(runner=self)
			if self.user:
				n_results_touched += fill_user_value(Result.objects.filter(klb_result__klb_person=self.klb_person), self.user, user, comment=comment)
		if runner.parkrun_id:
			self.parkrun_id = runner.parkrun_id
			runner.parkrun_id = None
			changed_fields.append('parkrun_id')
			if self.user:
				n_results_touched += fill_user_value(Result.objects.filter(parkrun_id=self.parkrun_id), self.user, user, comment=comment)
		if runner.city:
			if self.city:
				problem_fields.append(u'city (old value: {}, new value: {})'.format(self.city.name, runner.city.name))
			else:
				self.city = runner.city
				changed_fields.append('city')
		if runner.midname:
			if self.midname:
				problem_fields.append(u'midname (old value: {}, new value: {})'.format(self.midname, runner.midname))
			else:
				self.midname = runner.midname
				changed_fields.append('midname')
		if runner.birthday:
			if self.birthday:
				problem_fields.append(u'birthday (old value: {}, new value: {})'.format(
					self.birthday.isoformat() if self.birthday_known else self.birthday.year,
					runner.birthday.isoformat() if runner.birthday_known else runner.birthday.year))
			else:
				self.birthday = runner.birthday
				self.birthday_known = runner.birthday_known
				changed_fields.append('birthday')
				changed_fields.append('birthday_known')
		runner.save()
		self.save()
		n_results_touched += Result.objects.filter(runner=runner).update(runner=self)
		write_log("{} RUNNER_MERGE Merging runner {} with runner {} completed, changed fields: [{}], results touched: {}.".format(
			datetime.datetime.now(), self.get_name_and_id(), runner.get_name_and_id(), ', '.join(changed_fields), n_results_touched))
		if problem_fields:
			write_log("Problems with fields: {}. Change them manually if needed.".format(', '.join(problem_fields)))
		log_obj_create(user, self, ACTION_UPDATE, field_list=changed_fields, comment=u'Поглощение бегуна {}. Затронуто результатов: {}'.format(
			runner.get_name_and_id(), n_results_touched))
		return True, ''
	# Only when adding to KLBMatch. Returns <Club_member, needs to update stats?>
	def add_to_club(self, creator, club, participant, date_start, date_end):
		club_member = club.club_member_set.filter(runner=self).first()
		if club_member:
			field_list = []
			if club_member.date_removed and (club_member.date_removed < date_end):
				club_member.date_removed = date_end
				field_list.append('date_removed')
			if field_list:
				club_member.save()
				log_obj_create(creator, club, ACTION_CLUB_MEMBER_UPDATE, child_object=club_member, field_list=field_list,
					comment=u'При добавлении в команду КЛБМатча')
			return club_member, (len(field_list) > 0)
		else:
			club_member = Club_member.objects.create(
				runner=self,
				club=club,
				email=participant.email,
				phone_number=participant.phone_number,
				date_registered=date_start,
				date_removed=date_end,
				added_by=creator,
			)
			log_obj_create(creator, club, ACTION_CLUB_MEMBER_CREATE, child_object=club_member, comment=u'При добавлении в команду КЛБМатча')
			return club_member, True
	def strBirthday(self, with_nbsp=True):
		if self.birthday:
			if self.birthday_known:
				return date2str(self.birthday, with_nbsp=with_nbsp)
			else:
				return u'{}{}г.'.format(self.birthday.year, '&nbsp;' if with_nbsp else ' ')
		else:
			return ''
	def get_age_today(self):
		if self.birthday:
			today = datetime.date.today()
			return today.year - self.birthday.year - ((today.month, today.day) < (self.birthday.month, self.birthday.day))
		else:
			return None
	def name(self, with_midname=False):
		if self.midname and with_midname:
			return u'{} {} {}'.format(self.fname, self.midname, self.lname)
		return u'{} {}'.format(self.fname, self.lname) if self.lname else u'(неизвестно)'
	def get_lname_fname(self):
		return u'{} {}'.format(self.lname, self.fname) if self.lname else u'(неизвестно)'
	def name_with_midname(self):
		return self.name(with_midname=True)
	def get_name_for_ajax_select(self):
		return u'{} {} {} (id {}, {}, {}, {} стартов)'.format(self.lname, self.fname, self.midname, self.id,
			self.strBirthday(with_nbsp=False),
			self.city.nameWithCountry(with_nbsp=False) if self.city else '',
			self.n_starts if self.n_starts else 0)
	def get_name_condition(self):
		return get_name_condition(self.lname, self.fname, self.midname)
	def n_starts_cur_year(self):
		field = 'n_starts_{}'.format(CUR_RUNNERS_ORDERING_YEAR)
		return getattr(self, field) if hasattr(self, field) else None
	def get_total_length(self, with_nbsp=True):
		return total_length2string(self.total_length, with_nbsp=with_nbsp)
	def get_total_time(self, with_br=True):
		return total_time2string(self.total_time, with_br=with_br)
	def get_length_curyear(self, with_nbsp=True):
		return total_length2string(getattr(self,'total_length_{}'.format(CUR_RUNNERS_ORDERING_YEAR)), with_nbsp=with_nbsp)
	def get_time_curyear(self, with_br=True):
		return total_time2string(getattr(self,'total_time_{}'.format(CUR_RUNNERS_ORDERING_YEAR)), with_br=with_br)
	def get_n_starts_curyear(self):
		return getattr(self,'n_starts_{}'.format(CUR_RUNNERS_ORDERING_YEAR))
	def get_user_url(self):
		if self.user_id:
			return reverse('results:user_details', kwargs={'user_id': self.user_id})
		return ''
	def get_klb_url(self):
		if self.klb_person_id:
			return reverse('results:klb_person_details', kwargs={'person_id': self.klb_person_id})
		return ''
	# def get_ak_url(self):
	# 	if self.ak_person_id:
	# 		return 'http://probeg.org/rez.php?manid={}'.format(self.ak_person_id)
	# 	return ''
	def get_runner_or_user_url(self):
		if self.user and self.user.is_active and self.user.user_profile and self.user.user_profile.is_public:
			return self.user.user_profile.get_absolute_url()
		return self.get_absolute_url()
	def get_parkrun_url(self):
		if self.parkrun_id:
			return 'http://www.parkrun.ru/results/athleteresultshistory/?athleteNumber={}'.format(self.parkrun_id)
		return ''
	def get_possible_results(self):
		q_names = self.get_name_condition()
		for name in self.extra_name_set.all():
			q_names |= name.get_name_condition()

		results = Result.objects.filter(q_names).exclude(runner=self).select_related('race__event__series__city__region__country',
			'race__event__city__region__country', 'runner', 'user__user_profile', 'category_size').order_by('-race__event__start_date')
		if self.user:
			unclaimed_result_ids = set(self.user.unclaimed_result_set.values_list('result_id', flat=True))
			results = results.filter(runner__user=None, user=None).exclude(pk__in=unclaimed_result_ids)
		if self.birthday is None:
			return results
		# Otherwise, we can be more precise
		birthday = self.birthday
		q_age = Q(birthday=None)
		if self.birthday_known:
			q_age |= Q(birthday_known=True, birthday=birthday) | Q(birthday_known=False, birthday__year=birthday.year)
		else:
			q_age |= Q(birthday__year=birthday.year)
		results = results.filter(q_age)
		max_difference = 1 if self.birthday_known else 2 # We are more strict if we know exact birthday
		new_results = []
		for result in results:
			if (result.birthday is None) and result.age:
				if abs(result.race.event.get_age_on_event_date(self.birthday) - result.age) <= max_difference:
					new_results.append(result)
			else:
				new_results.append(result)
		return new_results
	def get_reverse_url(self, target):
		return reverse(target, kwargs={'runner_id': self.id})
	def get_absolute_url(self):
		return self.get_reverse_url('results:runner_details')
	def get_absolute_url_full(self):
		return self.get_reverse_url('results:runner_details_full')
	def get_editor_url(self):
		return self.get_reverse_url('editor:runner_details')
	def get_history_url(self):
		return self.get_reverse_url('editor:runner_changes_history')
	def get_update_url(self):
		return self.get_reverse_url('editor:runner_update')
	def get_delete_url(self):
		return self.get_reverse_url('editor:runner_delete')
	def get_update_stat_url(self):
		return self.get_reverse_url('editor:runner_update_stat')
	def get_person_create_url(self):
		return self.get_reverse_url('editor:klb_person_create')
	def get_add_name_url(self):
		return self.get_reverse_url('editor:runner_name_add')
	def get_find_results_url(self):
		return self.get_reverse_url('results:find_results')
	def get_name_and_id(self):
		return u'{} {} {} (id {})'.format(self.lname, self.fname, self.midname, self.id)
	def has_dependent_objects(self):
		return self.result_set.exists() or self.club_member_set.exists() or self.extra_name_set.exists() \
			or (self.klb_person is not None) or (self.user is not None)
	def __unicode__(self):
		return get_name(self)
		# res = u'{} {} {}'.format(self.fname, self.midname, self.lname) if self.lname else u'Бегун'
		# res += u' с '
		# ids = [u'id {}'.format(self.id)]
		# if self.klb_person_id:
		# 	ids.append(u'id в КЛБМатче {}'.format(self.klb_person_id))
		# if self.user_id:
		# 	ids.append(u'id пользователя сайта {}'.format(self.user_id))
		# # if self.ak_person_id:
		# # 	ids.append(u'id в базе АК55 {}'.format(self.ak_person_id))
		# if self.parkrun_id:
		# 	ids.append(u'parkrun id {}'.format(self.parkrun_id))
		# return  res + ', '.join(ids)

class Club_member(models.Model):
	runner = models.ForeignKey(Runner, verbose_name=u'ID участника забегов', on_delete=models.CASCADE)
	club = models.ForeignKey(Club, verbose_name=u'Клуб', on_delete=models.PROTECT)

	email = models.CharField(verbose_name=u'E-mail', max_length=MAX_EMAIL_LENGTH, blank=True)
	phone_number = models.CharField(verbose_name=u'Мобильный телефон', max_length=MAX_PHONE_NUMBER_LENGTH, blank=True)
	date_registered = models.DateField(verbose_name=u'Дата добавления в клуб', default=None, null=True)
	date_removed = models.DateField(verbose_name=u'Дата выхода из клуба', default=None, null=True, blank=True)

	added_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Кто добавил в таблицу', on_delete=models.SET_NULL, null=True, blank=True)
	added_time = models.DateTimeField(verbose_name=u'Время создания', auto_now_add=True, null=True, blank=True)
	last_update = models.DateTimeField(verbose_name=u'Последнее изменение', auto_now=True, null=True, blank=True)
	class Meta:
		db_table = "dj_club_member"
		unique_together = (("club", "runner"), )
		# unique_together = (("club", "runner", "date_registered"), )
	def merge(self, user, other, comment=''): # self.club_id must be equal to other.club_id
		fields_changed = []
		if other.date_registered is None:
			if self.date_registered:
				self.date_registered = None
				fields_changed.append('date_registered')
		elif self.date_registered and (other.date_registered < self.date_registered):
			self.date_registered = other.date_registered
			fields_changed.append('date_registered')
		if other.date_removed is None:
			if self.date_removed:
				self.date_removed = None
				fields_changed.append('date_removed')
		elif self.date_removed and (other.date_removed > self.date_removed):
			self.date_removed = other.date_removed
			fields_changed.append('date_removed')
		if fields_changed:
			log_obj_create(user, self.club, ACTION_CLUB_MEMBER_UPDATE, child_object=self, field_list=fields_changed, comment=comment)
			self.save()
	def is_already_removed(self):
		return self.date_removed and (self.date_removed < datetime.date.today())
	def print_date_registered(self):
		if self.date_registered is None:
			return ''
		if self.date_registered.month == 1 and self.date_registered.day == 1:
			return self.date_registered.year
		return self.date_registered.strftime("%d.%m.%Y")
	def print_date_removed(self):
		if self.date_removed is None:
			return ''
		if self.date_removed.month == 12 and self.date_removed.day == 31:
			return self.date_removed.year
		return self.date_removed.strftime("%d.%m.%Y")
	def get_reverse_url(self, target):
		return reverse(target, kwargs={'club_id': self.club_id, 'member_id': self.id})
	def get_editor_url(self):
		return self.get_reverse_url('editor:club_member_details')
	def get_delete_url(self):
		return self.get_reverse_url('editor:club_delete_member')
	def __unicode__(self):
		return  u'{}, клуб {}'.format(self.runner.name(), self.club)

class User_stat(models.Model):
	# Exactly one value of (user, runner, club_member) must be not None
	user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Пользователь', on_delete=models.CASCADE, null=True, default=None, blank=True)
	runner = models.ForeignKey(Runner, verbose_name=u'Бегун', on_delete=models.CASCADE, null=True, default=None, blank=True)
	club_member = models.ForeignKey(Club_member, verbose_name=u'Член клуба', on_delete=models.CASCADE, null=True, default=None, blank=True)
	distance = models.ForeignKey(Distance, verbose_name=u'Дистанция', on_delete=models.CASCADE)
	year = models.SmallIntegerField(verbose_name=u'Год', null=True, default=None, blank=True)

	n_starts = models.SmallIntegerField(verbose_name=u'Число участий')
	is_popular = models.BooleanField(verbose_name=u'Попадает ли в число популярных, если их слишком много', default=False)

	value_best = models.IntegerField(verbose_name=u'Личный рекорд', null=True, default=None, blank=True)
	pace_best = models.SmallIntegerField(verbose_name=u'Личный рекорд: темп (сек/км)', null=True, default=None, blank=True)
	best_result = models.ForeignKey(Result, default=None, null=True, blank=True, on_delete=models.SET_NULL)

	value_best_age_coef = models.IntegerField(verbose_name=u'Личный рекорд с учётом возрастного коэффициента', null=True, default=None, blank=True)
	best_result_age_coef = models.ForeignKey(Result, default=None, null=True, blank=True, on_delete=models.SET_NULL, related_name="best_result_age_coef_set")

	value_mean = models.IntegerField(verbose_name=u'Средний результат', null=True, default=None, blank=True)
	value_mean_age_coef = models.IntegerField(verbose_name=u'Средний результат с учётом возрастного коэффициента', null=True, default=None, blank=True)
	pace_mean = models.SmallIntegerField(verbose_name=u'Средний результат: темп (сек/км)', null=True, default=None, blank=True)

	last_update = models.DateTimeField(verbose_name=u'Дата последнего обновления', auto_now=True)
	def get_value_best(self):
		return self.distance.strResult(self.value_best)
	def get_value_best_age_coef(self):
		if self.value_best_age_coef is None:
			send_panic_email(
				'get_value_best_age_coef is called when value_best_age_coef is None',
				u'Problem occured with user {}, runner {}, club_member {}'.format(self.user_id, self.runner_id, self.club_member_id)
			)
			return ''
		return self.distance.strResult(self.value_best_age_coef)
	def get_value_mean(self):
		return self.distance.strResult(self.value_mean)
	class Meta:
		db_table = "dj_user_stat"
		unique_together = (("user", "distance", "year"), ("runner", "distance", "year"), ("club_member", "distance", "year"), )
	def __unicode__(self):
		return u'Статистика пользователя {} на дистанции {}'.format(user.get_full_name(), distance.name)

class Coefficient(models.Model):
	year = models.SmallIntegerField(verbose_name=u'Год')
	gender = models.SmallIntegerField(verbose_name=u'Пол')
	age = models.SmallIntegerField(verbose_name=u'Возраст')
	length = models.IntegerField(verbose_name=u'Дистанция')
	value = models.DecimalField(verbose_name=u'Коэффициент', max_digits=5, decimal_places=4)
	class Meta:
		db_table = "dj_coefficient"
		index_together = [
			["year", "gender", "age", "length"],
		]
	def __unicode__(self):
		return 'Gender: {}, Age: {}, length: {}, value: {}'.format(self.gender, self.age, self.length, self.value)
	@classmethod
	def get_klb_coefficient(cls, year, gender, age, length):
		if 20 <= age <= 30:
			return 1
		elif age < 8:
			age = 8
		elif age > 90:
			age = 90
		length_to_use = None
		if length <= 10000:
			length_to_use = 10000
		elif length == 15000:
			length_to_use = 15000
		elif length == 20000:
			length_to_use = 20000
		elif 21097 <= length <= 21100:
			length_to_use = 21100
		elif length == 30000:
			length_to_use = 30000
		elif 42195 <= length <= 42200:
			length_to_use = 42200
		elif length >= 100000:
			length_to_use = 100000
		coefs = cls.objects.filter(age=age, gender=gender, year=2016 if year <= 2016 else 2017)
		if length_to_use:
			return coefs.filter(length=length_to_use).first().value
		coef_left = coefs.filter(length__lt=length).order_by('-length').first()
		coef_right = coefs.filter(length__gt=length).order_by('length').first()
		return (length - coef_left.length) * (coef_right.value - coef_left.value) / (coef_right.length - coef_left.length) + coef_left.value

class Sport_class(models.Model):
	year = models.SmallIntegerField(verbose_name=u'Год')
	gender = models.SmallIntegerField(verbose_name=u'Пол')
	length = models.IntegerField(verbose_name=u'Дистанция')
	master_value = models.IntegerField(verbose_name=u'Результат МС в сотых секунды')
	third_class_value = models.IntegerField(verbose_name=u'Результат 3 разряда в сотых секунды')
	class Meta:
		db_table = "dj_sport_class"
		index_together = [
			["year", "gender", "length"],
		]
	def __unicode__(self):
		return 'Year: {}, Gender: {}, length: {}, master value: {}, 3 class value: {}'.format(
			self.year, self.gender, self.length, self.master_value, self.third_class_value)

class Letter_of_series(models.Model):
	letter = models.CharField(verbose_name=u'Первая буква названия', max_length=1)
	n_series = models.IntegerField(verbose_name=u'Число серий', default=0)
	is_checked = models.BooleanField(verbose_name=u'Проверена ли', default=False)
	class Meta:
		db_table = "dj_letter_of_series"

class Runner_name(models.Model):
	name = models.CharField(verbose_name=u'Имя', max_length=30, unique=True, blank=False)
	gender = models.SmallIntegerField(verbose_name=u'Пол', choices=GENDER_CHOICES[1:])
	class Meta:
		db_table = "dj_runner_name"

class Age_category(models.Model):
	name = models.CharField(verbose_name=u'Название группы', max_length=100, unique=True)
	birthyear_min = models.SmallIntegerField(verbose_name=u'Минимальный год рождения', default=None, null=True)
	birthyear_max = models.SmallIntegerField(verbose_name=u'Максимальный год рождения', default=None, null=True)
	age_min = models.SmallIntegerField(verbose_name=u'Минимальный возраст', default=None, null=True)
	age_max = models.SmallIntegerField(verbose_name=u'Максимальный возраст', default=None, null=True)
	is_bad = models.BooleanField(verbose_name=u'Безнадежное название', default=False)
	class Meta:
		db_table = "dj_age_category"

class Nn_runner(models.Model):
	runner = models.OneToOneField(Runner, verbose_name=u'Участник забегов', on_delete=models.SET_NULL,
		default=None, null=True, blank=True, db_column='dj_runner_id')
	lname = models.CharField(verbose_name=u'Фамилия', max_length=30, blank=True, db_column='family')
	fname = models.CharField(verbose_name=u'Имя', max_length=30, blank=True, db_column='name1')
	midname = models.CharField(verbose_name=u'Отчество', max_length=30, blank=True, db_column='name2')
	birthday = models.DateField(verbose_name=u'День рождения', default=None, null=True, blank=True, db_column='bday')
	birthyear = models.SmallIntegerField(verbose_name=u'Год рождения', default=0, db_column='byear')
	gender = models.SmallIntegerField(verbose_name=u'Пол', default=0, db_column='pol')
	city = models.ForeignKey(City, verbose_name=u'Город', on_delete=models.PROTECT, default=None, null=True, blank=True, db_column='dj_city_id')
	city_name = models.CharField(verbose_name=u'Название города', max_length=30, blank=True, db_column='city')
	club_name = models.CharField(verbose_name=u'Клуб', max_length=30, blank=True, db_column='club')
	def get_birthday(self):
		if self.birthday:
			return self.birthday.isoformat()
		if self.birthyear:
			return self.birthyear
		return u'(no birthday)'
	class Meta:
		db_table = "NNrunners"

class Registration(models.Model):
	event = models.OneToOneField(Event, on_delete=models.CASCADE)
	is_step2_passed = models.BooleanField(verbose_name=u'Пройден ли второй шаг', default=False)

	start_date = CustomDateTimeField(verbose_name=u'Время открытия регистрации')
	finish_date = CustomDateTimeField(verbose_name=u'Время закрытия регистрации')
	is_open = models.BooleanField(verbose_name=u'Можно ли открывать', default=False)

	is_midname_needed = models.BooleanField(verbose_name=u'Все участники должны указать отчество', default=False)
	is_address_needed = models.BooleanField(verbose_name=u'Все участники должны указать свой почтовый адрес', default=False)

	created_time = models.DateTimeField(verbose_name=u'Дата создания', default=datetime.datetime.now)
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Кто добавил на сайт',
		on_delete=models.SET_NULL, default=None, null=True, blank=True)
	class Meta:
		db_table = "dj_registration"
	def is_open_now(self):
		return self.is_open and (self.start_date <= timezone.now() <= self.finish_date)
	def get_reverse_url(self, target):
		return reverse(target, kwargs={'event_id': self.event.id})
	def get_create_step2_url(self):
		return self.get_reverse_url('editor:registration_create_step2')
	def get_absolute_url(self):
		return self.get_reverse_url('results:reg_step1')
	def get_info_url(self):
		return self.get_reverse_url('editor:registration_info')
	def get_delete_url(self):
		return self.get_reverse_url('editor:registration_delete')
	def get_editor_url(self):
		return self.get_reverse_url('editor:registration_details')
	def get_registrant_set(self):
		return Registrant.objects.filter(race__event=self.event).select_related('race__distance', 'city__region__country', 'user__user_profile', 'race_cost').order_by(
			'race__distance__distance_type', '-race__distance__length', 'lname', 'fname')
	def has_dependent_objects(self):
		return Registrant.objects.filter(race__event=self.event).exists() or Promocode.objects.filter(race__event=self.event).exists() \
			or Promocode.objects.filter(race__event=self.event).exists() or self.event.promocode_set.exists() \
			or Reg_question.objects.filter(event=self.event).exists() or Reg_race_details.objects.filter(race__event=self.event).exists()

class Promocode(models.Model):
	event = models.ForeignKey(Event, on_delete=models.CASCADE, default=None, blank=True, null=True)
	race = models.ForeignKey(Race, on_delete=models.CASCADE, default=None, blank=True, null=True)
	name = models.CharField(verbose_name=u'Текст кода', max_length=30, blank=False)
	finish_date = models.DateField(verbose_name=u'Дата окончания действия кода', default=None, blank=True, null=True)
	percent = models.DecimalField(verbose_name=u'Скидка в процентах', max_digits=5, decimal_places=2, default=None, blank=True, null=True)
	amount = models.IntegerField(verbose_name=u'Скидка в рублях', default=None, blank=True, null=True)
	times_to_use = models.IntegerField(verbose_name=u'Сколько раз может быть использован', default=None, blank=True, null=True)
	times_used = models.IntegerField(verbose_name=u'Сколько раз был использован')
	created_time = models.DateTimeField(verbose_name=u'Дата создания', default=datetime.datetime.now)
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Кто добавил на сайт',
		on_delete=models.SET_NULL, default=None, null=True, blank=True)
	class Meta:
		db_table = "dj_promocode"
		unique_together = (("event", "name"), ("race", "name"), )

REG_MAX_RACE_COST = 99999.99
REG_MIN_RACE_COST = 10
class Race_cost(models.Model):
	race = models.ForeignKey(Race, on_delete=models.CASCADE)
	finish_date = models.DateField(verbose_name=u'Дата окончания действия цены', default=None, blank=True, null=True)
	cost = models.DecimalField(verbose_name=u'Цена', max_digits=7, decimal_places=2)
	name = models.CharField(verbose_name=u'Название тарифа', max_length=50, blank=True)
	age_min = models.SmallIntegerField(verbose_name=u'Минимальный возраст участника на день забега', default=None, blank=True, null=True)
	age_max = models.SmallIntegerField(verbose_name=u'Минимальный возраст участника на день забега', default=None, blank=True, null=True)
	created_time = models.DateTimeField(verbose_name=u'Дата создания', default=datetime.datetime.now)
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Кто добавил на сайт',
		on_delete=models.SET_NULL, default=None, null=True, blank=True)
	class Meta:
		db_table = "dj_race_cost"
		unique_together = (("race", "finish_date", "name", "cost"),)
		ordering = ['finish_date', 'name', ]
	def name_and_details(self, with_br=True):
		res = u''
		if self.finish_date:
			res += u'до {}:'.format(self.finish_date)
		else:
			res += u'до закрытия регистрации:'
		if self.name or self.age_min or self.age_max:
			if with_br:
				res += u'<br/>'
			else:
				res += u' '
			res += u'('
			if self.name:
				res += self.name
				if self.age_min or self.age_max:
					res += u', '
			if self.age_min and self.age_max:
				res += u'от {} до {} лет'.format(self.age_min, self.age_max)
			elif self.age_min:
				res += u'от {} лет'.format(self.age_min)
			elif self.age_max:
				res += u'до {} лет'.format(self.age_max)
			res += u')'
		return res
	def price_details(self):
		res = u'' # u'{} руб.'.format(self.cost)
		details = []
		details.append(self.name if self.name else u'без названия')
		if self.age_min and self.age_max:
			details.append(u'от {} до {} лет'.format(self.age_min, self.age_max))
		elif self.age_min:
			details.append(u'от {} лет'.format(self.age_min))
		elif self.age_max:
			details.append(u'до {} лет'.format(self.age_max))
		return res + u' (' + ', '.join(details) + u')'
	def __unicode__(self):
		res = u'{} руб.'.format(self.cost)
		if self.name:
			res += u' ({})'.format(self.name)
		return res
	@classmethod
	def get_default_cost(cls):
		return 100

AGE_VALIDATORS = [MaxValueValidator(MAX_RUNNER_AGE), MinValueValidator(MIN_RUNNER_AGE)]
class Reg_race_details(models.Model):
	race = models.OneToOneField(Race, on_delete=models.CASCADE)
	is_open = models.BooleanField(verbose_name=u'Можно ли открывать', default=True)

	age_min = models.SmallIntegerField(verbose_name=u'Минимальный возможный возраст участника на день забега',
		validators=AGE_VALIDATORS, default=None, blank=True, null=True)
	age_max = models.SmallIntegerField(verbose_name=u'Минимальный возможный возраст участника на день забега',
		validators=AGE_VALIDATORS, default=None, blank=True, null=True)

	participants_limit = models.SmallIntegerField(verbose_name=u'Максимальное число участников', default=0)
	queue_limit = models.SmallIntegerField(verbose_name=u'Максимальный размер листа ожидания', default=0)
	can_be_transferred = models.BooleanField(verbose_name=u'Свою регистрацию можно передать другому человеку', default=False)
	transfer_cost = models.DecimalField(verbose_name=u'Стоимость передачи регистрации', max_digits=7, decimal_places=2,
		default=None, blank=True, null=True)
	transfer_finish_date = models.DateField(verbose_name=u'Последний день передачи регистраций', default=None, blank=True, null=True)
	is_participants_list_open = models.BooleanField(verbose_name=u'Публиковать список зарегистрированных на дистанцию', default=False)
	created_time = models.DateTimeField(verbose_name=u'Дата создания', default=datetime.datetime.now)
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Кто добавил на сайт',
		on_delete=models.SET_NULL, default=None, null=True, blank=True)
	class Meta:
		db_table = "dj_reg_race_details"
	def get_current_race_cost_date(self):
		cost_date = self.race.race_cost_set.exclude(finish_date=None).order_by('finish_date').first()
		return cost_date.finish_date if cost_date else None
	def has_several_race_costs(self, cost_date=None):
		if cost_date is None:
			cost_date = self.get_current_race_cost_date()
		return self.race.race_cost_set.filter(finish_date=cost_date).count() > 1
	def get_current_race_costs(self, registrant, cost_date=None): # Use only if has_several_race_costs() is False!
		if cost_date is None:
			cost_date = self.get_current_race_cost_date()
		res = self.race.race_cost_set.filter(finish_date=cost_date).order_by('-cost')
		if registrant.birthday:
			age = self.race.event.get_age_on_event_date(registrant.birthday)
			res = res.filter(Q(age_min=None) | Q(age_min__lte=age), Q(age_max=None) | Q(age_max__gte=age))
		return res
	def race_cost_set_by_date(self):
		return list(self.race.race_cost_set.exclude(finish_date=None)) + list(self.race.race_cost_set.filter(finish_date=None))
	def get_prices_by_dates(self):
		res = []
		prev_date = None
		costs = []
		names = []
		first_loop = True
		for race_cost in self.race_cost_set_by_date():
			if first_loop:
				prev_date = race_cost.finish_date
				first_loop = False
			if race_cost.finish_date != prev_date:
				res.append((prev_date, costs, names))
				prev_date = race_cost.finish_date
				costs = []
				names = []
			costs.append(u'{} руб.'.format(race_cost.cost))
			names.append(race_cost.price_details())
		if costs:
			res.append((prev_date, costs, names))
		return res
	def get_reverse_url(self, target):
		return reverse(target, kwargs={'race_id': self.race.id})
	def get_absolute_url(self, registrant_id):
		return reverse('results:reg_step2', kwargs={'race_id': self.race.id, 'registrant_id': registrant_id})

def question_image_name(instance, filename):
	new_name = "dj_media/registration/images/questions/" + unicode(instance.id) + "." + file_extension(filename)
	fullname = os.path.join(settings.MEDIA_ROOT, new_name)
	try:
		os.remove(fullname)
	except:
		pass
	return new_name
class Reg_question(models.Model):
	event = models.ForeignKey(Event, on_delete=models.CASCADE)
	race_set = models.ManyToManyField(Race, through='Reg_question_race', blank=True)
	number = models.SmallIntegerField(verbose_name=u'Номер вопроса', default=0)
	title = models.CharField(verbose_name=u'Краткое название', max_length=50, blank=True)
	name = models.CharField(verbose_name=u'Текст вопроса', max_length=500, blank=True)
	finish_date = models.DateField(verbose_name=u'До какой даты показывать вопрос', default=None, blank=True, null=True)
	image = models.ImageField(verbose_name=u'Изображение к вопросу (не больше 2 мегабайт)', max_length=255, upload_to=question_image_name,
		validators=[validate_image], blank=True)
	multiple_answers = models.BooleanField(verbose_name=u'Можно ли дать несколько ответов', default=False)
	is_required = models.BooleanField(verbose_name=u'Обязательно ли дать хотя бы один ответ', default=True)
	created_time = models.DateTimeField(verbose_name=u'Дата создания', default=datetime.datetime.now)
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Кто добавил на сайт',
		on_delete=models.SET_NULL, default=None, null=True, blank=True)
	class Meta:
		db_table = "dj_reg_question"
		unique_together = (("event", "title"),)
		ordering = ['number']
	def clean(self):
		if self.number == 0:
			max_number = 0
			if self.event:
				max_number = self.event.reg_question_set.aggregate(Max('number'))['number__max']
			self.number = (max_number + 1) if max_number else 1
	def file_size(self):
		if self.image:
			try:
				return self.image.size
			except:
				return -1 # u'Ошибка. Возможно, файл не существует'
		else:
			return 0
	def get_default_choice(self): # Only if multiple_answers == False
		choice = self.reg_question_choice_set.filter(is_visible=True, is_default=True).first()
		if choice:
			return choice.id
		else:
			return None
	def get_reverse_url(self, target):
		return reverse(target, kwargs={'question_id': self.id})
	def get_editor_url(self):
		return self.get_reverse_url('editor:question_details')

class Reg_question_race(models.Model):
	reg_question = models.ForeignKey(Reg_question, on_delete=models.CASCADE)
	race = models.ForeignKey(Race, on_delete=models.CASCADE)
	added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
	added_time = models.DateTimeField(auto_now_add=True)
	class Meta:
		db_table = "dj_reg_question_race"
		unique_together = (("reg_question", "race"),)

class Reg_question_choice(models.Model):
	reg_question = models.ForeignKey(Reg_question, on_delete=models.CASCADE)
	number = models.SmallIntegerField(verbose_name=u'Номер варианта ответа', default=0)
	name = models.CharField(verbose_name=u'Вариант ответа', max_length=100, blank=True)
	cost = models.DecimalField(verbose_name=u'Цена', max_digits=7, decimal_places=2, default=0)
	is_visible = models.BooleanField(verbose_name=u'Показывать этот вариант', default=True)
	is_default = models.BooleanField(verbose_name=u'Отмечать по умолчанию', default=False)
	created_time = models.DateTimeField(verbose_name=u'Дата создания', default=datetime.datetime.now)
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Кто добавил на сайт',
		on_delete=models.SET_NULL, default=None, null=True, blank=True)
	class Meta:
		db_table = "dj_reg_question_choice"
		unique_together = (("reg_question", "name"),)
		ordering = ['number']
	def get_name_with_price(self):
		if self.cost > 0:
			return self.name + u' ({} руб.)'.format(self.cost)
		elif self.cost < 0:
			return self.name + u' (скидка {} руб.)'.format(-self.cost)
		else:
			return self.name
	def clean(self):
		if self.number == 0:
			max_number = 0
			if self.reg_question:
				max_number = self.reg_question.reg_question_choice_set.aggregate(Max('number'))['number__max']
			self.number = (max_number + 1) if max_number else 1

def time_to_delete_registrant(): # When to delete registrant if the user didn't pay for registration
	n_days = 2 if datetime.datetime.now().hour > 19 else 1
	return datetime.datetime.combine(datetime.date.today() + datetime.timedelta(days=n_days), datetime.datetime.min.time())
class Registrant(models.Model):
	race = models.ForeignKey(Race, on_delete=models.CASCADE)
	user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
	promocode = models.ForeignKey(Promocode, on_delete=models.SET_NULL, verbose_name=u'Использованный промокод', default=None, blank=True, null=True)
	race_cost = models.ForeignKey(Race_cost, on_delete=models.SET_NULL, verbose_name=u'Тариф', default=None, null=True)

	registers_himself = models.BooleanField(verbose_name=u'Регистрирует сам себя', default=True)
	gender = models.SmallIntegerField(verbose_name=u'Пол', default=GENDER_MALE, choices=GENDER_CHOICES[1:])
	lname = models.CharField(verbose_name=u'Фамилия', max_length=100)
	fname = models.CharField(verbose_name=u'Имя', max_length=100)
	midname = models.CharField(verbose_name=u'Отчество (необязательно)', max_length=100, blank=True)
	city = models.ForeignKey(City, verbose_name=u'Город', default=None, null=True, blank=True, on_delete=models.PROTECT)
	birthday = models.DateField(verbose_name=u'Дата рождения', default=None, null=True)
	email = models.EmailField(verbose_name=u'Адрес электронной почты', max_length=MAX_EMAIL_LENGTH, default='')
	phone_number = models.CharField(verbose_name=u'Номер телефона', max_length=MAX_PHONE_NUMBER_LENGTH)
	emergency_name = models.CharField(verbose_name=u'Имя знакомого на экстренный случай', max_length=20)
	emergency_phone_number = models.CharField(verbose_name=u'Номер телефона знакомого на экстренный случай', max_length=MAX_PHONE_NUMBER_LENGTH)
	zipcode = models.CharField(verbose_name=u'Почтовый индекс', max_length=8, blank=True)
	address = models.CharField(verbose_name=u'Почтовый адрес', max_length=MAX_POSTAL_ADDRESS_LENGTH, blank=True)
	club_name = models.CharField(verbose_name=u'Клуб', max_length=50, blank=True)

	comment = models.CharField(verbose_name=u'Комментарий', max_length=1000, blank=True)

	number_in_queue = models.SmallIntegerField(verbose_name=u'Номер в листе ожидания', default=None, null=True, blank=True)
	price = models.DecimalField(verbose_name=u'Стоимость', max_digits=7, decimal_places=2, default=0)
	is_paid = models.BooleanField(verbose_name=u'Оплачено ли участие', default=False)
	paid_amount = models.DecimalField(verbose_name=u'Сколько заплачено', max_digits=7, decimal_places=2, default=0)

	time_to_delete = models.DateTimeField(verbose_name=u'Время удаления в случае неоплаты', default=time_to_delete_registrant, null=True, blank=True)

	created_time = models.DateTimeField(verbose_name=u'Дата создания', default=datetime.datetime.now)
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Кто добавил на сайт', related_name='registrant_created_set',
		on_delete=models.SET_NULL, default=None, null=True, blank=True)
	class Meta:
		db_table = "dj_registrant"

# We save data of other people that were registered by current user to make future registrations simpler
class Saved_registrant(models.Model):
	user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
	gender = models.SmallIntegerField(verbose_name=u'Пол', default=GENDER_MALE, choices=GENDER_CHOICES[1:])
	lname = models.CharField(verbose_name=u'Фамилия', max_length=100, blank=True)
	fname = models.CharField(verbose_name=u'Имя', max_length=100, blank=True)
	midname = models.CharField(verbose_name=u'Отчество (необязательно)', max_length=100, blank=True)
	city = models.ForeignKey(City, verbose_name=u'Город', default=None, null=True, blank=True, on_delete=models.PROTECT)
	birthday = models.DateField(verbose_name=u'Дата рождения', default=None, null=True, blank=True)
	email = models.EmailField(verbose_name=u'Адрес электронной почты', max_length=MAX_EMAIL_LENGTH, blank=True)
	phone_number = models.CharField(verbose_name=u'Номер телефона', max_length=MAX_PHONE_NUMBER_LENGTH, blank=True)
	emergency_name = models.CharField(verbose_name=u'Имя знакомого на экстренный случай', max_length=20, blank=True)
	emergency_phone_number = models.CharField(verbose_name=u'Номер телефона знакомого на экстренный случай', max_length=MAX_PHONE_NUMBER_LENGTH, blank=True)
	zipcode = models.CharField(verbose_name=u'Почтовый индекс', max_length=8, blank=True)
	address = models.CharField(verbose_name=u'Почтовый адрес', max_length=MAX_POSTAL_ADDRESS_LENGTH, blank=True)
	club_name = models.CharField(verbose_name=u'Клуб', max_length=50, blank=True)
	created_time = models.DateTimeField(verbose_name=u'Дата создания', default=datetime.datetime.now)
	class Meta:
		db_table = "dj_saved_registrant"
	def __unicode__(self):
		return u'{} {} ({})'.format(self.fname, self.lname, self.birthday.strftime('%d.%m.%Y'))

class Reg_answer(models.Model):
	registrant = models.ForeignKey(Registrant, on_delete=models.CASCADE)
	reg_question_choice = models.ForeignKey(Reg_question_choice, on_delete=models.PROTECT)
	created_time = models.DateTimeField(verbose_name=u'Дата создания', default=datetime.datetime.now)
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Кто добавил на сайт',
		on_delete=models.SET_NULL, default=None, null=True, blank=True)
	class Meta:
		db_table = "dj_reg_answer"

class Reg_age_category(models.Model):
	race = models.ForeignKey(Race, on_delete=models.CASCADE)
	name = models.CharField(verbose_name=u'Название группы', max_length=100, unique=True)
	# birthday_min = models.DateField(verbose_name=u'Минимальный день рождения', default=None, null=True)
	# birthday_max = models.DateField(verbose_name=u'Максимальный день рождения', default=None, null=True)
	age_min = models.SmallIntegerField(verbose_name=u'Минимальный возраст', validators=AGE_VALIDATORS, default=None, blank=True, null=True)
	age_max = models.SmallIntegerField(verbose_name=u'Максимальный возраст', validators=AGE_VALIDATORS, default=None, blank=True, null=True)
	# is_determined_by_day = models.BooleanField(verbose_name=u'Определяется ли по возрасту на день забега', default=True)
	created_time = models.DateTimeField(verbose_name=u'Дата создания', default=datetime.datetime.now)
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Кто добавил на сайт',
		on_delete=models.SET_NULL, default=None, null=True, blank=True)
	class Meta:
		db_table = "dj_reg_age_category"
	# def clean(self):
	# 	race_day = self.race.event.start_date
	# 	if self.age_min:
	# 		year_max = race_day.year
	# 	else:
	# 		self.birthday_max = None

def organizer_logo_name(instance, filename):
	new_name = "dj_media/organizers/logo/" + unicode(instance.id) + "." + file_extension(filename)
	fullname = os.path.join(settings.MEDIA_ROOT, new_name)
	try:
		os.remove(fullname)
	except:
		pass
	return new_name



class DefaultOrganizerManager(models.Manager):
	def get_queryset(self):
		return super(DefaultOrganizerManager, self).get_queryset().exclude(id=FAKE_ORGANIZER_ID)

	@property
	def fake_object(self):
		return super(DefaultOrganizerManager, self).get_queryset().all().get(id=FAKE_ORGANIZER_ID)


class Organizer(models.Model):
	objects = DefaultOrganizerManager()
	all_objects = models.Manager()

	name = models.CharField(verbose_name=u'Название', max_length=100)
	url_site = models.URLField(verbose_name=u'Сайт', max_length=200, blank=True)
	url_vk = models.URLField(verbose_name=u'Страничка ВКонтакте', max_length=100, blank=True)
	url_facebook = models.URLField(verbose_name=u'Страничка в фейсбуке', max_length=100, blank=True)
	url_instagram = models.URLField(verbose_name=u'Страничка в инстраграме', max_length=100, blank=True)
	logo = models.ImageField(verbose_name=u'Логотип (не больше 2 мегабайт)', max_length=255, upload_to=organizer_logo_name,
		validators=[validate_image], blank=True)
	user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Представитель организатора на ПроБЕГе',
		on_delete=models.SET_NULL, default=None, null=True, blank=True)

	is_corporation = models.BooleanField(verbose_name=u'Юридическое ли лицо', default=False)
	inn = models.CharField(verbose_name=u'ИНН', max_length=12, blank=True)
	kpp = models.CharField(verbose_name=u'КПП', max_length=9, blank=True)
	bank_name = models.CharField(verbose_name=u'Название банка', max_length=100, blank=True)
	current_account = models.CharField(verbose_name=u'Расчетный счет', max_length=20, blank=True)
	corr_account = models.CharField(verbose_name=u'Корреспондентский счет', max_length=20, blank=True)
	bik = models.CharField(verbose_name=u'БИК', max_length=9, blank=True)
	card_number = models.CharField(verbose_name=u'Номер банковской карты', max_length=18, blank=True)
	card_owner = models.CharField(verbose_name=u'Имя владельца карты', max_length=50, blank=True)
	snils = models.CharField(verbose_name=u'СНИЛС', max_length=14, blank=True)

	created_time = models.DateTimeField(verbose_name=u'Дата создания', auto_now_add=True)
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Кто добавил на сайт', related_name='organizers_created_set',
		on_delete=models.SET_NULL, default=None, null=True, blank=True)
	class Meta:
		db_table = "dj_organizer"
	def get_reverse_url(self, target):
		return reverse(target, kwargs={'organizer_id': self.id})
	def get_absolute_url(self):
		return self.get_reverse_url('results:organizer_details')
	def get_editor_url(self):
		return self.get_reverse_url('editor:organizer_details')
	def get_add_series_url(self):
		return self.get_reverse_url('editor:organizer_add_series')
	def get_history_url(self):
		return self.get_reverse_url('editor:organizer_changes_history')
	def has_dependent_objects(self):
		return self.series_set.exists()
	def __unicode__(self):
		return self.name
	def get_children(self):
		return self.series_set.all()

class Useful_label(models.Model):
	name = models.CharField(verbose_name=u'Название', max_length=100, unique=True)
	priority = models.IntegerField(verbose_name=u'Приоритет', default=0)
	created_time = models.DateTimeField(verbose_name=u'Дата создания', auto_now_add=True)
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Кто добавил на сайт',
		on_delete=models.SET_NULL, default=None, null=True, blank=True)
	class Meta:
		db_table = "dj_useful_label"
		index_together = [
			['priority', 'name'],
		]
		ordering = ['priority', 'name']

class Useful_link(models.Model):
	name = models.CharField(verbose_name=u'Название', max_length=100, unique=True)
	url = models.URLField(verbose_name=u'Ссылка', max_length=MAX_URL_LENGTH)
	labels = models.ManyToManyField(Useful_label, through='Link_label')
	created_time = models.DateTimeField(verbose_name=u'Дата создания', auto_now_add=True)
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Кто добавил на сайт',
		on_delete=models.SET_NULL, default=None, null=True, blank=True)
	class Meta:
		db_table = "dj_useful_link"
		ordering = ('name', )

class Link_label(models.Model):
	label = models.ForeignKey(Useful_label, on_delete=models.CASCADE)
	link = models.ForeignKey(Useful_link, on_delete=models.CASCADE)
	priority = models.IntegerField(verbose_name=u'Приоритет для данной ссылки внутри данной метки', default=0)
	created_time = models.DateTimeField(verbose_name=u'Дата создания', auto_now_add=True)
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Кто добавил на сайт',
		on_delete=models.SET_NULL, default=None, null=True, blank=True)
	class Meta:
		db_table = "dj_link_label"
		unique_together = (('label', 'link'),)
		ordering = ('label', 'priority')

class Race_size(models.Model):
	race = models.OneToOneField(Race, on_delete=models.CASCADE)
	n_results = models.IntegerField(verbose_name=u'Число результатов')
	last_update = models.DateTimeField(verbose_name=u'Дата создания', auto_now=True)
	class Meta:
		db_table = "dj_race_size"

class Course_certificate(models.Model):
	series = models.ForeignKey(Series, on_delete=models.SET_NULL, default=None, null=True, blank=True)
	name = models.CharField(verbose_name=u'Название для списка сертифицированных трасс', max_length=100)
	city = models.ForeignKey(City, on_delete=models.SET_NULL, default=None, null=True, blank=True)
	start_place = models.CharField(verbose_name=u'Место старта', max_length=100)
	distances = models.CharField(verbose_name=u'Дистанции через запятую', max_length=100)

	file_scheme = models.CharField(verbose_name=u'Схема (путь к файлу после probeg.org/, без слеша', max_length=200)
	file_scheme_desc = models.CharField(verbose_name=u'Расширение файла схемы', max_length=5)

	file_report = models.CharField(verbose_name=u'Подробный отчёт (путь к файлу после probeg.org/, без слеша', max_length=200)
	file_report_desc = models.CharField(verbose_name=u'Расширение файла отчёта', max_length=5)
	file_report_size = models.SmallIntegerField(verbose_name=u'Примерный размер файла отчёта в мегабайтах', default=0)

	measurer_name = models.CharField(verbose_name=u'Измеритель', max_length=50)
	measurement_date = models.DateField(verbose_name=u'Дата измерения')
	created_time = models.DateTimeField(verbose_name=u'Время создания', auto_now_add=True)
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Кто добавил на сайт',
		on_delete=models.SET_NULL, default=None, null=True, blank=True)
	class Meta:
		db_table = "dj_course_certificate"

RECORD_AGE_GROUP_TYPE_YOUNG = 0
RECORD_AGE_GROUP_TYPE_ABSOLUTE = 1
RECORD_AGE_GROUP_TYPE_SENIOR = 2
RECORD_AGE_GROUP_TYPES = (
	(RECORD_AGE_GROUP_TYPE_YOUNG, u'Молодёжь'),
	(RECORD_AGE_GROUP_TYPE_ABSOLUTE, u'Абсолют'),
	(RECORD_AGE_GROUP_TYPE_SENIOR, u'Ветераны'),
)
AGE_GROUP_RECORDS_AGE_GAP = 5
class Record_age_group(models.Model):
	age_min = models.SmallIntegerField(verbose_name=u'Минимальный возраст', default=None, null=True, unique=True)
	age_group_type = models.SmallIntegerField(verbose_name=u'Тип возрастной группы', choices=RECORD_AGE_GROUP_TYPES, default=RECORD_AGE_GROUP_TYPE_SENIOR)
	class Meta:
		db_table = "dj_record_age_group"
		verbose_name = u'Возрастная группа для рекордов стран'
		ordering = ['age_group_type', 'age_min']
	def get_full_name_in_prep_case(self, gender):
		if self.age_min is None:
			return ''
		gender_letter = results_util.GENDER_CHOICES[gender][1][0]
		if self.age_group_type == RECORD_AGE_GROUP_TYPE_YOUNG:
			return u' в группе {}<{}'.format(gender_letter, self.age_min)
		if self.age_min < 100:
			return u' в группе {}{}'.format(gender_letter, self.age_min)
			# return u' в возрастной группе {}–{}'.format(self.age_min, self.age_min + AGE_GROUP_RECORDS_AGE_GAP - 1)
		return u'в группе {}{}+'.format(gender_letter, self.age_min)
	def __unicode__(self):
		if self.age_min is None:
			return u'Абсолют'
		if self.age_group_type == RECORD_AGE_GROUP_TYPE_YOUNG:
			return '<{}'.format(self.age_min)
		return unicode(self.age_min)
	def range(self):
		if self.age_min is None:
			return u'Абсолют'
		if self.age_group_type == RECORD_AGE_GROUP_TYPE_YOUNG:
			return '<{}'.format(self.age_min)
		return u'{}–{}'.format(self.age_min, self.age_min + AGE_GROUP_RECORDS_AGE_GAP - 1)

RECORD_RESULT_ORDERING = ['country', 'gender', 'age_group', 'distance', 'is_indoor', 'cur_place', 'was_record_ever', 'date']
class Record_result(models.Model):
	country = models.ForeignKey(Country, verbose_name=u'Страна', on_delete=models.PROTECT)
	gender = models.SmallIntegerField(verbose_name=u'Пол', choices=GENDER_CHOICES[1:])
	age_group = models.ForeignKey(Record_age_group, verbose_name=u'Возрастная группа', on_delete=models.PROTECT)
	age_on_event_date = models.SmallIntegerField(verbose_name=u'Полных лет на день забега', default=None, null=True, blank=True)
	distance = models.ForeignKey(Distance, verbose_name=u'Дистанция', on_delete=models.PROTECT)
	is_indoor = models.BooleanField(verbose_name=u'В закрытом помещении?', default=False)

	cur_place = models.SmallIntegerField(verbose_name=u'Текущее место (только для первой тройки на сегодня)', default=None, null=True, blank=True)
	was_record_ever = models.BooleanField(verbose_name=u'Было ли какое-то время рекордным результатом?', default=False)
	is_official_record = models.BooleanField(verbose_name=u'Был ли когда-либо официальным рекордом по версии ВФЛА?', default=False)

	fname = models.CharField(verbose_name=u'Имя', max_length=100, blank=True)
	lname = models.CharField(verbose_name=u'Фамилия', max_length=100, blank=True)
	city = models.ForeignKey(City, verbose_name=u'Город', on_delete=models.PROTECT, default=None, null=True, blank=True)
	value = models.IntegerField(verbose_name=u'Результат числом', default=None, null=True, blank=True)
	runner = models.ForeignKey(Runner, verbose_name=u'Бегун', on_delete=models.SET_NULL, null=True, default=None, blank=True)
	result = models.ForeignKey(Result, verbose_name=u'Результат', on_delete=models.SET_NULL, null=True, default=None, blank=True)

	race = models.ForeignKey(Race, verbose_name=u'Забег', on_delete=models.SET_NULL, null=True, default=None, blank=True)
	date = models.DateField(verbose_name=u'Дата или год старта', null=True, default=None, blank=True)
	is_date_known = models.BooleanField(verbose_name=u'Известна ли точная дата старта', default=False)

	comment = models.CharField(verbose_name=u'Комментарий', max_length=250, blank=True)
	is_from_shatilo = models.BooleanField(verbose_name=u'Взят из базы Шатило?', default=False)
	added_time = models.DateTimeField(verbose_name=u'Время занесения в БД', auto_now_add=True, db_index=True)
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=u'Кто добавил результат',
		on_delete=models.SET_NULL, default=None, null=True, blank=True)
	class Meta:
		db_table = 'dj_record_result'
		verbose_name = u'Рекордный результат для какой-то страны в какой-то возрастной группе'
		ordering = RECORD_RESULT_ORDERING
		index_together = [
			RECORD_RESULT_ORDERING,
			['country', 'gender', 'age_group', 'distance', 'is_indoor', 'date'],
			['country', 'gender', 'age_group', 'distance', 'is_indoor', 'value', 'date'],
		]
		unique_together = (
			('country', 'gender', 'age_group', 'distance', 'is_indoor', 'cur_place'),
		)
	def fill_and_save_if_needed(self):
		to_save = False
		if self.result:
			if self.race is None:
				self.race = self.result.race
				to_save = True
			if not self.is_date_known:
				self.date = self.race.event.start_date
				self.is_date_known = True
				to_save = True
			if not self.value:
				self.value = self.result.result
				to_save = True
			if self.result.runner:
				if not self.runner:
					self.runner = self.result.runner
					to_save = True
				if self.runner.city:
					if not self.city:
						self.city = self.runner.city
						to_save = True
			else:
				if (not self.lname) and self.result.lname:
					self.lname = self.result.lname
					to_save = True
				if (not self.fname) and self.result.fname:
					self.fname = self.result.fname
					to_save = True
			if self.runner and self.runner.birthday_known and not self.age_on_event_date:
				self.age_on_event_date = self.race.event.get_age_on_event_date(self.runner.birthday)
				to_save = True
		if to_save:
			self.save()
		return to_save
	def get_value(self):
		if self.value is None:
			return ''
		if self.distance_id == results_util.DIST_1HOUR_ID:
			return meters2string(self.value)
		return centisecs2time(self.value, show_zero_hundredths=(self.distance.length <= 10000))
	def get_reverse_url(self, target):
		return reverse(target, kwargs={'record_result_id': self.id})
	def get_editor_url(self):
		return self.get_reverse_url('editor:age_group_record_details')
	def get_delete_url(self):
		return self.get_reverse_url('editor:age_group_record_delete')
	def get_group_url(self):
		age = self.age_group.age_min
		return reverse('results:age_group_record_details', kwargs={'country_id': self.country_id, 'gender_code': self.get_gender_code(),
			'age': age if age else 0, 'distance_code': self.get_distance_code(), 'is_indoor': 1 if self.is_indoor else 0})
	def get_gender_code(self):
		return results_util.GENDER_CODES.get(self.gender, '')
	def get_distance_code(self):
		return results_util.DISTANCE_CODES.get(self.distance_id, '')
	def __unicode__(self):
		return (unicode(self.result) if self.result else self.get_value())[results_util.RECORD_RESULT_SYMBOLS_TO_CUT[self.distance_id]:]

class Possible_record_result(models.Model):
	country = models.ForeignKey(Country, verbose_name=u'Страна', on_delete=models.PROTECT)
	gender = models.SmallIntegerField(verbose_name=u'Пол', choices=GENDER_CHOICES[1:])
	age_group = models.ForeignKey(Record_age_group, verbose_name=u'Возрастная группа', on_delete=models.PROTECT)
	age_on_event_date = models.SmallIntegerField(verbose_name=u'Полных лет на день забега', default=None, null=True, blank=True)
	distance = models.ForeignKey(Distance, verbose_name=u'Дистанция', on_delete=models.PROTECT)
	is_indoor = models.BooleanField(verbose_name=u'В закрытом помещении?', default=False)

	result = models.ForeignKey(Result, verbose_name=u'Результат', on_delete=models.CASCADE)
	can_be_prev_record = models.BooleanField(verbose_name=u'Мог ли этот результат быть рекордным какое-то время', default=False)
	added_time = models.DateTimeField(verbose_name=u'Время занесения в БД', auto_now_add=True, db_index=True)
	class Meta:
		db_table = 'dj_possible_record_result'
		verbose_name = u'Возможный рекордный результат для какой-то страны в какой-то возрастной группе'
		index_together = [('country', 'gender', 'age_group', 'distance', 'is_indoor', ), ]
	def __unicode__(self):
		return unicode(self.result)

class Result_not_for_age_group_record(models.Model):
	country = models.ForeignKey(Country, verbose_name=u'Страна', on_delete=models.PROTECT)
	age_group = models.ForeignKey(Record_age_group, verbose_name=u'Возрастная группа', on_delete=models.PROTECT)
	result = models.ForeignKey(Result, verbose_name=u'Результат', on_delete=models.CASCADE)

class Function_call(models.Model):
	name = models.CharField(verbose_name=u'Название', max_length=100, db_index=True)
	args = models.CharField(verbose_name=u'Параметры', max_length=100)
	description = models.CharField(verbose_name=u'Описание функции', max_length=100)
	error = models.CharField(verbose_name=u'Ошибка выполнения', max_length=100)
	start_time = models.DateTimeField(verbose_name=u'Время запуска', db_index=True)
	running_time = models.DurationField(verbose_name=u'Время работы', default=None, null=True)
	message = models.ForeignKey(Message_from_site, verbose_name=u'Письмо об этом вызове', default=None, null=True, on_delete=models.PROTECT)
	class Meta:
		db_table = 'dj_function_call'
		verbose_name = u'Попытка вызова функции'
	def __unicode__(self):
		return u'{}({})'.format(self.name, self.args)
