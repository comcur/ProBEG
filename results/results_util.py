# -*- coding: utf-8 -*-
from __future__ import division
from django.conf import settings

import datetime
import urllib2
import time
import os
import re

plural_endings_array = [
	(), # 0
	(u'', u'а', u'ов'), # 1 # For e.g. 'результат'
	(u'а', u'ы', u''),  # 2 # For e.g. 'трасса', 'команда','женщина'
	(u'ь', u'и', u'ей'), # 3 # For e.g. 'новость'
	(u'я', u'и', u'й'), # 4 # For e.g. 'дистанция'
	(u'й', u'х', u'х'), # 5 # For e.g. 'завершивши_ся', 'предстоящий', 'похожий'
	(u'й', u'х', u'х'), # 6 # For e.g. 'обработанный'
	(u'е', u'я', u'й'), # 7 # For e.g. 'предупреждение'
	(u'ка', u'ки', u'ок'), # 8 # For e.g. 'ошибка'
	(u'', u'а', u''),   # 9 # For e.g. 'человек'
	(), # 10 # For e.g. 'планиру?т'
	(u'год', u'года', u'лет'), # 11 # For e.g. 'год/лет'
	(u'', u'и', u'и'), # 12 # For e.g. 'ваш'
	(u'а', u'', u''),   # 13 # For e.g. 'мужчина'
	(u'и', u'ях', u'ях'), # 14 # For e.g. 'о дистанциях'
	(u'е', u'ах', u'ах'), # 15 # For e.g. 'о забегах'
	(u'а', u'ов', u'ов'), # 16 # For e.g. 'с трёх забегов'
	(u'', u'ы', u'ы'), # 17 # For e.g. 'добавлен'
	(u'и', u'', u''), # 18 # For e.g. 'не меньше ... тысяч'
	(u'а', u'и', u'и'), # 19 # For e.g. 'тысяча'
	(u'у', u'и', u''), # 20 # For e.g. 'зафиксировали 5 тысяч'
	(u'', u'о', u'о'), # 21 # For e.g. 'проведено'
]

def plural_ending_new(value, word_type):
	if value is None:
		value = 0
	value %= 100
	if word_type == 10:
		return u'е' if (value == 1) else u'ю'
	endings = plural_endings_array[word_type]
	if 11 <= value <= 19:
		return endings[2]
	value %= 10
	if value == 0:
		return endings[2]
	if value == 1:
		return endings[0]
	if value >= 5:
		return endings[2]
	return endings[1]

def plural_ending(value, endings):
	if value is None:
		value = 0
	value %= 100
	if 11 <= value <= 19:
		return endings[2]
	value %= 10
	if value == 0:
		return endings[2]
	if value == 1:
		return endings[0]
	if value >= 5:
		return endings[2]
	return endings[1]
def plural_ending_1(value): # For e.g. 'результат'
	return plural_ending(value, [u'', u'а', u'ов'])
def plural_ending_2(value): # For e.g. 'трасса', 'команда','женщина'
	return plural_ending(value, [u'а', u'ы', u''])
def plural_ending_5(value): # For e.g. 'завершивши_ся', 'предстоящий', 'похожий'
	return plural_ending(value, [u'й', u'х', u'х'])
def plural_ending_9(value): # For e.g. 'человек'
	return plural_ending(value, [u'', u'а', u''])
def plural_ending_11(value): # For e.g. 'год/лет'
	return plural_ending(value, [u'год', u'года', u'лет'])
def plural_ending_13(value): # For e.g. 'мужчина'
	return plural_ending(value, [u'а', u'', u''])

def int_safe(s):
	try:
		res = int(s)
	except:
		res = 0
	return res

def get_first_digits_as_number(s):
	s += ' '
	for i in range(len(s)):
		if not s[i].isdigit():
			return int_safe(s[:i])

LOG_DIR = settings.BASE_DIR + '/logs'
LOG_FILE_ACTIONS = LOG_DIR + '/django_actions.log'
def write_log(s):
	f = open(LOG_FILE_ACTIONS, "a")
	try:
		f.write(datetime.datetime.today().isoformat(' ') + " " + s + "\n")
	except:
		f.write(datetime.datetime.today().isoformat(' ') + " " + s.encode('utf-8') + "\n")
	f.close()
	return s

MAX_FILE_SIZE = 20 * 1024 * 1024
# Read URL so that the site thinks we're just browser. Returns <Success?>, <data or error text>, <file size>
def read_url(url):
	headers = {
		'User-Agent' : 'YaBrowser/16.2.0.3539 Safari/537.36',
		'Referer' : 'https://www.google.com/',
		'ACCEPT_LANGUAGE' : 'en,ru;q=0.8',
		'ACCEPT_ENCODING' : 'utf-8',
		'ACCEPT' : 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
	}
	req = urllib2.Request(url, headers=headers)
	downloaded = False
	for try_number in range(5):
		try:
			response = urllib2.urlopen(req)
			downloaded = True
			break
		except urllib2.HTTPError as e:
			write_log(u"HTTP Error with URL " + url + ". Try number " + str(try_number))
			write_log(u"Error code: " + unicode(e.code))
			time.sleep(1)
		except urllib2.URLError as e:
			write_log(u"URL Error with URL " + url + ". Try number " + str(try_number))
			write_log(u"Reason: " + unicode(e.reason))
			time.sleep(1)
		except:
			pass
	if not downloaded:
		return 0, u"Could not reach the url '{}'".format(url), 0
	try:
		file_size = int_safe(response.info().getheaders("Content-Length")[0])
	except:
		file_size = 0
	if file_size > MAX_FILE_SIZE:
		return 0, u"The file '{}' size '{}' is too large".format(url, file_size), 0
	return 1, response, file_size

STRAVA_ACTIVITY_PREFIX = 'strava.com/activities/'
STRAVA_ACTIVITY_APP_PREFIX = 'strava.app.link/'
def maybe_strava_activity_number(s):
	if STRAVA_ACTIVITY_PREFIX in s:
		maybe_number = get_first_digits_as_number(s.split(STRAVA_ACTIVITY_PREFIX)[-1])
		if maybe_number:
			return maybe_number
	if STRAVA_ACTIVITY_APP_PREFIX in s:
		maybe_code = s.split(STRAVA_ACTIVITY_APP_PREFIX)[-1]
		url = 'http://' + STRAVA_ACTIVITY_APP_PREFIX + maybe_code
		result, response, _ = read_url(url)
		if result:
			match = re.search(r'strava.com/activities/(\d{1,15})/', response.read())
			if match:
				return int(match.group(1))
	return None

def get_age_on_date(event_date, birthday):
	if birthday and event_date:
		return event_date.year - birthday.year - ((event_date.month, event_date.day) < (birthday.month, birthday.day))
	return None

DIST_24HOURS_ID = 197
DIST_100KM_ID = 167
DIST_50KM_ID = 155
DIST_MARATHON_ID = 152
DIST_30KM_ID = 140
DIST_HALFMARATHON_ID = 127
DIST_1HOUR_ID = 192
DIST_20KM_ID = 124
DIST_15KM_ID = 109
DIST_10KM_ID = 83
DIST_5KM_ID = 47
DIST_3KM_ID = 28
DIST_1500M_ID = 11
DIST_800M_ID = 334
DIST_400M_ID = 258
DIST_200M_ID = 272
DIST_100M_ID = 232
DISTANCE_ANY = -1
DISTANCE_WHOLE_EVENTS = -2

DISTANCES_FOR_CLUB_STATISTICS = (
	DIST_MARATHON_ID,
	DIST_HALFMARATHON_ID,
	DIST_10KM_ID,
	DIST_5KM_ID,
	DIST_1HOUR_ID,
)

DISTANCES_FOR_COUNTRY_RECORDS = (
	DIST_MARATHON_ID,
	DIST_HALFMARATHON_ID,
	DIST_1HOUR_ID,
	DIST_10KM_ID,
	DIST_5KM_ID,
	DIST_1500M_ID,
	DIST_800M_ID,
	DIST_400M_ID,
	DIST_200M_ID,
	DIST_100M_ID,
)

DISTANCES_FOR_RATING = (
	DIST_100KM_ID,
	DIST_MARATHON_ID,
	DIST_HALFMARATHON_ID,
	DIST_1HOUR_ID,
	DIST_10KM_ID,
	DIST_5KM_ID,
	DIST_24HOURS_ID,
	DIST_3KM_ID,
	DIST_15KM_ID,
	DIST_20KM_ID,
	DIST_30KM_ID,
	DIST_50KM_ID,
)

RECORD_RESULT_SYMBOLS_TO_CUT = {
	DIST_MARATHON_ID: 0,
	DIST_HALFMARATHON_ID: 0,
	DIST_1HOUR_ID: 0,
	DIST_10KM_ID: 0,
	DIST_5KM_ID: 2,
	DIST_1500M_ID: 2,
	DIST_800M_ID: 3,
	DIST_400M_ID: 3,
	DIST_200M_ID: 3,
	DIST_100M_ID: 5,
}

DISTANCES_TOP_FOUR = (
	DIST_MARATHON_ID,
	DIST_HALFMARATHON_ID,
	DIST_10KM_ID,
	DIST_5KM_ID,
)

DISTANCES_FOR_REPORT_LARGEST_EVENTS = (
	DIST_100KM_ID,
	DIST_MARATHON_ID,
	DIST_30KM_ID,
	DIST_HALFMARATHON_ID,
	DIST_1HOUR_ID,
	DIST_15KM_ID,
	DIST_10KM_ID,
	DIST_5KM_ID,
)

DISTANCE_CODES = {
	DIST_24HOURS_ID: '24hours',
	DIST_100KM_ID: '100km',
	DIST_50KM_ID: '50km',
	DIST_MARATHON_ID: 'marathon',
	DIST_30KM_ID: '30km',
	DIST_HALFMARATHON_ID: 'half',
	DIST_1HOUR_ID: '1hour',
	DIST_20KM_ID: '20km',
	DIST_15KM_ID: '15km',
	DIST_10KM_ID: '10km',
	DIST_5KM_ID: '5km',
	DIST_3KM_ID: '3km',
	DIST_1500M_ID: '1500m',
	DIST_800M_ID : '800m',
	DIST_400M_ID : '400m',
	DIST_200M_ID : '200m',
	DIST_100M_ID : '100m',
	DISTANCE_ANY: 'any',
	DISTANCE_WHOLE_EVENTS: 'sum',
}
DISTANCE_CODES_INV = {v: k for k, v in DISTANCE_CODES.iteritems()}

THREE_COUNTRY_IDS = ('RU', 'UA', 'BY')

GENDER_UNKNOWN = 0
GENDER_FEMALE = 1
GENDER_MALE = 2
GENDER_CHOICES = (
	(GENDER_UNKNOWN, u'Не указан'),
	(GENDER_FEMALE, u'Женский'),
	(GENDER_MALE, u'Мужской'),
)
GENDER_CODES = {
	GENDER_UNKNOWN: 'unknown',
	GENDER_FEMALE: 'female',
	GENDER_MALE: 'male',
}
GENDER_CODES_INV = {v: k for k, v in GENDER_CODES.iteritems()}

RUSSIAN_PARKRUN_SITE = 'https://www.parkrun.ru'
OLD_PARKRUN_SERIES_ID = 1887

SENIOR_AGE_MALE = 60
SENIOR_AGE_FEMALE = 55

def restart_django():
	touch_fname = '/home/admin/chernov/touch_me'
	with open(touch_fname, 'a'):
		os.utime(touch_fname, None)

def fix_quotes(s):
	if s.count(u'"') == 2:
		return s.replace(u'"', u'«', 1).replace(u'"', u'»', 1)
	return s

# Convert distance in meters to either '15 км' or '2345 м'
def length2m_or_km(length):
	if length % 1000:
		return u'{} м'.format(length)
	else:
		return u'{} км'.format(length // 1000)
