# -*- coding: utf-8 -*-
# from django.core.validators import URLValidator, _lazy_re_compile
from django.contrib.auth.models import User
from django.contrib import messages
from tinymce.widgets import TinyMCE
from django.db.models import Count
from django import forms

from collections import OrderedDict
import datetime
import os
# import re

from results.forms import CustomDateInput, CustomDateTimeInput, CustomTimeInput, UserModelChoiceField
from results.forms import ModelFormWithCity, FormWithCity, RoundedFieldsForm, RoundedFieldsModelForm, RegionOrCountryField
from results.forms import validate_email, validate_phone_number
from results import models, models_klb, results_util

def validate_date(value):
	if value and value < models.DATE_MIN:
		raise forms.ValidationError(u'Вы не можете вводить даты до 1900 года. Если это правда нужно, напишите нам')
	if value and value > models.DATE_MAX:
		raise forms.ValidationError(u'Вы не можете вводить даты после 2099 года. Если это правда нужно, напишите нам')

class ResultValueField(forms.IntegerField):
	def __init__(self, *args, **kwargs):
		kwargs['widget'] = forms.TextInput()
		super(ResultValueField, self).__init__(*args, **kwargs)
	def to_python(self, value):
		if value is None:
			return None
		if value == '':
			return None
		if value == '0':
			return 0
		if self.distance_type == models.TYPE_MINUTES:
			res = results_util.int_safe(value)
			if res:
				return res
			raise forms.ValidationError(u'Недопустимый результат в метрах: {}'.format(value))
		else:
			res = models.string2centiseconds(value)
			if res:
				return res
			raise forms.ValidationError(u'Недопустимый результат в секундах: {}'.format(value))
	def prepare_value(self, value):
		if value is None:
			return ''
		if value == 0:
			return '0'
		if self.distance_type == models.TYPE_MINUTES:
			return value
		else:
			return models.centisecs2time(value)

# When searching through all cities list
class CitySearchForm(forms.Form):
	country = forms.ModelChoiceField(
		label=u"Страна",
		queryset=models.Country.objects.all().order_by('value', 'name'),
		empty_label="(любая)",
		required=False)
	region = forms.ModelChoiceField(
		label=u"Регион",
		queryset=models.Region.objects.filter(active=1).order_by('name'),
		empty_label="(любой)",
		required=False)
	detailed = forms.BooleanField(
		label=u"Подробно",
		required=False)

# When viewing/changing/creating city
class CityForm(forms.ModelForm):
	region = RegionOrCountryField(required=True)
	class Meta:
		model = models.City
		fields = ['region', 'raion', 'city_type', 'name', 'nameEn', 'url_wiki', 'skip_region']
		widgets = {
			'raion': forms.TextInput(attrs={'size': 50}),
			'city_type': forms.TextInput(attrs={'size': 50}),
			'name': forms.TextInput(attrs={'size': 50}),
			'nameEn': forms.TextInput(attrs={'size': 50}),
			'url_wiki': forms.TextInput(attrs={'size': 100}),
		}

# When going to change old city to new one
class ForCityForm(FormWithCity):
	region = RegionOrCountryField()
	def __init__(self, *args, **kwargs):
		super(ForCityForm, self).__init__(*args, **kwargs)
		self.order_fields(['region', 'city_id'])

# When viewing/changing/creating distance
class DistanceForm(forms.ModelForm):
	def clean(self):
		cleaned_data = super(DistanceForm, self).clean()
		distance_type = cleaned_data.get("distance_type")
		length = cleaned_data.get("length")
		if distance_type == models.TYPE_METERS:
			if length <= 9999:
				self.instance.distance_raw = length
				self.instance.race_type_raw = u'м'
			elif length <= 9999999:
				self.instance.distance_raw = length / 1000.
				self.instance.race_type_raw = u'км'
			else:
				raise forms.ValidationError(u'Слишком большая длина дистанции.')
		elif distance_type == models.TYPE_RELAY:
			if length <= 9999999:
				self.instance.distance_raw = length / 1000.
				self.instance.race_type_raw = u'эст'
			else:
				raise forms.ValidationError(u'Слишком большая длина дистанции.')
		elif distance_type == models.TYPE_SWIMMING:
			if length <= 9999999:
				self.instance.distance_raw = length / 1000.
				self.instance.race_type_raw = u'пл'
			else:
				raise forms.ValidationError(u'Слишком большая длина дистанции.')
		elif distance_type == models.TYPE_NORDIC_WALKING:
			if length <= 9999999:
				self.instance.distance_raw = length / 1000.
				self.instance.race_type_raw = u'хдб'
			else:
				raise forms.ValidationError(u'Слишком большая длина дистанции.')
		else:
			if length <= 9999:
				self.instance.distance_raw = length
			else:
				raise forms.ValidationError(u'Слишком большая длина дистанции.')
			if distance_type == models.TYPE_TRASH:
				self.instance.race_type_raw = u'Q'
			elif distance_type == models.TYPE_MINUTES:
				self.instance.race_type_raw = u'мин'
			elif distance_type == models.TYPE_STEPS:
				self.instance.race_type_raw = u'ст'
			elif distance_type == models.TYPE_FLOORS:
				self.instance.race_type_raw = u'эт'
			elif distance_type == models.TYPE_THRIATLON:
				self.instance.race_type_raw = u'трт'
			elif distance_type == models.TYPE_SWIMRUN:
				self.instance.race_type_raw = u'swr'
			elif distance_type == models.TYPE_NORDIC_WALKING:
				self.instance.race_type_raw = u'хдб'
	class Meta:
		model = models.Distance
		fields = ['distance_type', 'length', 'name', 'popularity_value']

# When going to change old city to new one
class ForDistanceForm(forms.Form):
	new_distance = forms.ModelChoiceField(
		label=u"Дистанция",
		queryset=models.Distance.objects.order_by('distance_type', 'length'),
		required=False,
	)

# When searching through all series list
class SeriesSearchForm(FormWithCity):
	country = forms.ModelChoiceField(
		label=u"Страна",
		queryset=models.Country.objects.annotate(num_events=Count('series')).filter(num_events__gt=0).order_by('value', 'name'),
		empty_label="(любая)",
		required=False)
	region = forms.ModelChoiceField(
		label=u"Регион",
		queryset=models.Region.objects.filter(active=1).order_by('name'),
		empty_label="(любой)",
		required=False)
	series_name = forms.CharField(
		label=u'Часть названия серии',
		max_length=100,
		required=False)
	with_events = forms.BooleanField(
		label=u"и все их пробеги",
		required=False)
	date_from = forms.DateField(
		label=u"не раньше",
		widget=CustomDateInput,
		initial=datetime.date(datetime.datetime.now().year, 1, 1),
		required=False)
	date_to = forms.DateField(
		label=u"не позже",
		widget=CustomDateInput,
		initial=datetime.date(datetime.datetime.now().year, 12, 31),
		required=False)

# When viewing/changing/creating series
class SeriesForm(ModelFormWithCity):
	region = forms.ModelChoiceField(
		label=u"Регион города старта (если он в России, Украине, Беларуси)",
		queryset=models.Region.objects.filter(active=1).order_by('name'),
		empty_label="не указан",
		required=False)
	country = forms.ModelChoiceField(
		label=u"Страна города старта (для остальных стран)",
		queryset=models.Country.objects.filter(value__gt=2).order_by('value', 'name'),
		empty_label="не указана",
		required=False)
	city_finish = forms.ModelChoiceField(
		label=u"Город финиша",
		queryset=models.City.objects.order_by('name'),
		empty_label="укажите, только если отличается от старта",
		required=False)
	def __init__(self, *args, **kwargs):
		super(SeriesForm, self).__init__(*args, **kwargs)
		if (self.instance.id is None) or not self.instance.is_russian_parkrun():
			# We need this field only if we're editing existing Russian parkrun
			del self.fields['is_parkrun_closed']
	class Meta:
		model = models.Series
		fields = ['name', 'name_eng', 'region', 'country', 'city_id', 'start_place', 'city_finish',
			'country_raw', 'district_raw', 'region_raw', 'city_raw', 'series_type', 'surface_type',
			'director', 'contacts', 'url_site', 'comment', 'comment_private', 'url_vk', 'url_facebook', 'url_instagram',
			'is_parkrun', 'is_parkrun_closed',
		]
		widgets = {
			'name': forms.TextInput(attrs={'size': 100}),
			'name_eng': forms.TextInput(attrs={'size': 100}),
			#'country': u'Страна',
			#'region': u'Регион (для России, Украины, Беларуси)',
			#'city': u'Город (населённый пункт) старта',
			#'city_finish': u'Город финиша (если отличается от старта)',

			'country_raw': forms.TextInput(attrs={'size': 50, 'disabled': 1}),
			'district_raw': forms.TextInput(attrs={'size': 50, 'disabled': 1}),
			'region_raw': forms.TextInput(attrs={'size': 50, 'disabled': 1}),
			'city_raw': forms.TextInput(attrs={'size': 50, 'disabled': 1}),

			#'series_type': u'Вид мероприятия',
			#'n_views': forms.TextInput(attrs={'size': 50, 'readonly': 1}),
			'director': forms.TextInput(attrs={'size': 100}),
			'contacts': forms.TextInput(attrs={'size': 100}),
			'url_site': forms.TextInput(attrs={'size': 100}),
			'url_events': forms.TextInput(attrs={'size': 100}),
			'url_vk': forms.TextInput(attrs={'size': 100}),
			'url_facebook': forms.TextInput(attrs={'size': 100}),
			'url_instagram': forms.TextInput(attrs={'size': 100}),
			'start_place': forms.TextInput(attrs={'size': 50}),
			
			'comment': forms.TextInput(attrs={'size': 100}),
			'comment_private': forms.TextInput(attrs={'size': 100}),
		}
	def clean(self):
		cleaned_data = super(SeriesForm, self).clean()
		name = cleaned_data.get('name')
		city = cleaned_data['city']
		if city and models.Series.objects.filter(name=name, city=city).exclude(pk=self.instance.id).exists():
			raise forms.ValidationError(
				u'Серия с таким названием в этом городе уже есть. Пожалуйста, выберите другое название или напишите нам на info@probeg.org')

# When changing event
class EventForm(ModelFormWithCity):
	region = RegionOrCountryField()
	def __init__(self, *args, **kwargs):
		user = kwargs.pop('user')
		super(EventForm, self).__init__(*args, **kwargs)
		self.fields['city_id'].label += u' (укажите, только если отличается от города серии)'
		if 'city_finish' in self.fields:
			self.fields['city_finish'].label += u' (укажите, только если отличается от старта и от города финиша серии)'
		self.fields['cancelled'].label = u'Пометьте, если забег отменён (это удалит все дистанции!)'
		self.fields['invisible'].label = u'Пометьте, если забег не нужно отображать посетителям'
		self.fields['not_in_klb'].label = \
			u'Пометьте, если забег не нужно учитывать в КЛБМатче (не ставьте, если единственная проблема — дата добавления в календарь)'
		self.fields['surface_type'].label += u' (укажите, только если отличается от покрытия серии)'
		if models.Klb_result.objects.filter(race__event=self.instance).exists():
			n_klb_results = models.Klb_result.objects.filter(race__event=self.instance).count()
			self.fields['not_in_klb'].label += u' ({} результат{} в КЛБМатче уже есть)'.format(n_klb_results, results_util.plural_ending_new(n_klb_results, 1))
			self.fields['not_in_klb'].disabled = True
		if not models.is_admin(user):
			self.fields['date_added_to_calendar'].disabled = True
	def clean(self):
		cleaned_data = super(EventForm, self).clean()
		series = self.instance.series
		if 'city_finish' in self.fields:
			if cleaned_data.get('city_finish') and not cleaned_data.get('city'):
				raise forms.ValidationError(u'Нельзя указать город финиша, не указав город старта.')
		if series.id not in models.SERIES_WITH_ALLOWED_EVENTS_WITHOUT_CITY:
			if (not cleaned_data['city']) and (not series.city):
				raise forms.ValidationError(u'Не указан город серии, так что нужно указать город пробега.')
			if (series.series_type != models.SERIES_TYPE_TRIATHLON) \
					and (cleaned_data['surface_type'] == models.SURFACE_DEFAULT) and (series.surface_type == models.SURFACE_DEFAULT):
				raise forms.ValidationError(u'Нужно указать тип забега либо у серии, либо у забега.')
	class Meta:
		model = models.Event
		fields = ['name', 'number', 'region', 'city_id', 'surface_type',
			# 'city_finish', 
			'start_date', 'finish_date', 'arrival_date', 'start_place', 'start_time',
			'announcement',
			'url_registration',
			# 'url_announcement', 'url_poster', 'url_course', 'url_logo',
			# 'url_regulation', 'url_regulation_stamped', 'url_protocol',
			'email', 'contacts', 'url_site', 'url_vk', 'url_facebook',
			# 'distances_raw',
			'cancelled', 'comment', 'comment_private', 'invisible',
			# 'ak_race_id',
			'source', 'not_in_klb', 'date_added_to_calendar', #'created_by',
			]
		widgets = {
			'name': forms.TextInput(attrs={'size': 100}),

			'url_registration': forms.TextInput(attrs={'size': 100}),
			'url_announcement': forms.TextInput(attrs={'size': 100, 'readonly': 1}),
			'url_poster': forms.TextInput(attrs={'size': 100, 'readonly': 1}),
			'url_course': forms.TextInput(attrs={'size': 100, 'readonly': 1}),
			'url_logo': forms.TextInput(attrs={'size': 100, 'readonly': 1}),
			'url_regulation': forms.TextInput(attrs={'size': 100, 'readonly': 1}),
			'url_regulation_stamped': forms.TextInput(attrs={'size': 100, 'readonly': 1}),
			'url_protocol': forms.TextInput(attrs={'size': 100, 'readonly': 1}),

			'email': forms.TextInput(attrs={'size': 100}),
			'contacts': forms.TextInput(attrs={'size': 100}),
			'start_place': forms.TextInput(attrs={'size': 50}),

			'url_site': forms.TextInput(attrs={'size': 50}),
			'url_vk': forms.TextInput(attrs={'size': 50}),
			'url_facebook': forms.TextInput(attrs={'size': 50}),
			
			# 'distances_raw': forms.TextInput(attrs={'size': 100, 'readonly': 1}),

			'start_date': CustomDateInput,
			'finish_date': CustomDateInput,
			'arrival_date': CustomDateInput,
			'start_time': CustomTimeInput,
			'date_added_to_calendar': CustomDateInput,
			'announcement': TinyMCE(attrs={'cols': 60, 'rows': 10}),

			'comment': forms.TextInput(attrs={'size': 100}),
			'comment_private': forms.TextInput(attrs={'size': 100}),
			'source': forms.TextInput(attrs={'size': 100}),
		}

# When going to change old series to new one
class ForSeriesForm(forms.Form):
	new_series_id = forms.IntegerField(
		label=u"id новой серии",
		min_value=0,
		required=False)

# When going to change old event to new one
class ForEventForm(forms.Form):
	new_event_id = forms.IntegerField(
		label=u"id нового забега",
		min_value=0,
		required=False)

# When going to change old runner to new one
class ForRunnerForm(forms.Form):
	new_runner_id = forms.IntegerField(
		label=u"id нового бегуна",
		min_value=0,
		required=False)
# class ForRunnerForm(forms.ModelForm):
# 	class Meta:
# 		model = models.Runner
# 		fields = ['id']
# 		widgets = {
# 			'id': forms.NumberInput(),
# 		}

# When viewing/changing/creating race
class RaceForm(forms.ModelForm):
	distance = forms.ModelChoiceField(
		label=u"Официальная дистанция",
		queryset=models.Distance.objects.none(),
		required=True)
	distance_real = forms.ModelChoiceField(
		label=u"Фактическая дистанция (если отличается)",
		queryset=models.Distance.objects.none(),
		required=False)
	def __init__(self, *args, **kwargs):
		super(RaceForm, self).__init__(*args, **kwargs)
		distances = models.Distance.get_all_by_popularity()
		self.fields['distance'].queryset = distances
		self.fields['distance_real'].queryset = distances
	class Meta:
		model = models.Race
		fields = ['distance', 'distance_real', 'precise_name', 'n_participants', 'n_participants_finished', 'n_participants_finished_men',
			'winner_male_fname', 'winner_male_lname', 'winner_male_city', 'winner_male_result',
			'winner_female_fname', 'winner_female_lname', 'winner_female_city', 'winner_female_result',
			'comment', 'comment_private', 'has_no_results', 'is_for_handicapped', 'is_multiday', 'gps_track',
			'start_date', 'start_time', 'finish_date', 'surface_type',
			'elevation_meters', 'descent_meters', 'altitude_start_meters', 'altitude_finish_meters',
			'start_lat', 'start_lon', 'event', 'created_by', 'price', 'price_can_change', 'itra_score',
			 # 'loaded',
		]
		widgets = {
			'start_date': CustomDateInput(),
			'start_time': CustomTimeInput(),
			'finish_date': CustomDateInput(),
			'event': forms.HiddenInput(),
			'created_by': forms.HiddenInput(),
		}
		labels = {
			'precise_name': u'Уточнение названия (скобки не нужны)',
		}

class DocumentForm(forms.ModelForm):
	# url_original = forms.URLField(validators=[URLValidatorWithUnderscores()])
	try_to_load = forms.BooleanField(
		label=u"Попытаться загрузить с указанного URL к нам на сервер",
		required=False)
	def __init__(self, *args, **kwargs):
		super(DocumentForm, self).__init__(*args, **kwargs)
		if self.instance.series_id:
			self.fields['hide_local_link'].widget = forms.HiddenInput()
	def clean(self):
		cleaned_data = super(DocumentForm, self).clean()
		if cleaned_data['document_type'] == models.DOC_TYPE_UNKNOWN:
			raise forms.ValidationError(u'Пожалуйста, укажите тип документа')
		if (cleaned_data.get('upload') == False) and self.instance.upload:
			if os.path.isfile(self.instance.upload.path):
				self.instance.upload.delete(False)
	class Meta:
		model = models.Document
		fields = ['document_type', 'upload', 'url_original', 'try_to_load', 'comment', 'event', 'series', 'author', 'hide_local_link', 'created_by']
		widgets = {
			'url_original': forms.URLInput(attrs={'size': '75%'}), # , validators=[URLValidatorWithUnderscores()]
			'event': forms.HiddenInput(),
			'created_by': forms.HiddenInput(),
		}

class NewsForm(forms.ModelForm):
	class Meta:
		model = models.News
		fields = ['title', 'content', 'author', 'image', 'event', 'date_posted', 'is_for_social', 'created_by',]
		widgets = {
			'content': TinyMCE(attrs={'cols': 60, 'rows': 10}),
			#'date_posted': CustomDateTimeInput,
			'event': forms.HiddenInput(),
			'created_by': forms.HiddenInput(),
		}

class SeriesDocumentForm(forms.ModelForm): # TODO. Doesn't work - has_changed is always true!
	try_to_load = forms.BooleanField(
		label=u"Попытаться загрузить к нам на сервер",
		required=False)
	document_type = forms.ChoiceField(
		label=u"Страна",
		choices=models.DOCUMENT_TYPES,
		required=True)
	class Meta:
		model = models.Document
		fields = ['document_type', 'upload', 'url_original', 'try_to_load', 'comment', 'event', 'series']

class SmallResultForm(forms.ModelForm):
	class Meta:
		model = models.Result
		fields = ['runner', 'user',
			# 'ak_person',
			# 'parkrun_id',
			'lname', 'fname', 'midname', 'result', 'gun_result', 'status',
			'bib', 'city_name', 'country_name', 'city_name', 'club_name',
			# 'category',
			'birthday', 'birthday_known', 'age', 'gender',
			'comment', 'place', 'place_category', 'place_gender', 'do_not_count_in_stat',
			]
		widgets = {
			'runner': forms.NumberInput(),
			'user': forms.NumberInput(),
			# 'ak_person': forms.TextInput(attrs={'size': 8}),
			# 'parkrun_id': forms.NumberInput(),
			'lname': forms.TextInput(attrs={'size': 10}),
			'fname': forms.TextInput(attrs={'size': 10}),
			'midname': forms.TextInput(attrs={'size': 10}),
			'result': forms.NumberInput(attrs={'size': 7}),
			'gun_result': forms.NumberInput(attrs={'size': 7}),
			'bib': forms.TextInput(attrs={'size': 5}),
			# 'category': forms.TextInput(attrs={'size': 10, 'readonly': True}),
			'country_name': forms.TextInput(attrs={'size': 10}),
			'city_name': forms.TextInput(attrs={'size': 10}),
			'club_name': forms.TextInput(attrs={'size': 10}),
			'birthday': CustomDateInput(),
			'comment': forms.TextInput(attrs={'size': 6}),
			'age': forms.NumberInput(attrs={'style': 'width: 50px;'}),
			'place': forms.NumberInput(attrs={'style': 'width: 50px;'}),
			'place_category': forms.NumberInput(attrs={'style': 'width: 50px;'}),
			'place_gender': forms.NumberInput(attrs={'style': 'width: 50px;'}),
		}
		# labels = {
		# 	'category': u'Группа (не изменяется)',
		# }

class UserSearchForm(RoundedFieldsForm):
	lname = forms.CharField(
		label='',
		widget=forms.TextInput(attrs={'placeholder': u'Фамилия'}),
		max_length=100,
		required=False)
	fname = forms.CharField(
		label='',
		widget=forms.TextInput(attrs={'placeholder': u'Имя'}),
		max_length=100,
		required=False)
	midname = forms.CharField(
		label='',
		widget=forms.TextInput(attrs={'placeholder': u'Отчество'}),
		max_length=100,
		required=False)
	email = forms.CharField(
		label='',
		widget=forms.TextInput(attrs={'placeholder': u'E-mail'}),
		max_length=100,
		required=False)
	birthday_from = forms.DateField(
		label=u"Родился не раньше",
		widget=CustomDateInput,
		required=False)
	birthday_to = forms.DateField(
		label=u"не позже",
		widget=CustomDateInput,
		required=False)

OBJECT_TYPES = OrderedDict([
	("", u'все'),
	("Series", u'серии'),
	("Event", u'пробеги'),
	("City", u'города'),
	("News", u'новости вне забегов'),
	("Distance", u'дистанции'),
	("Club", u'клубы'),
	("Klb_team", u'команды'),
	("Extra_name", u'имена пользователей'),
	("User_profile", u'профили пользователей'),
])
# When searching through all changes in Table_update
class ActionSearchForm(FormWithCity):
	country = forms.ModelChoiceField(
		label=u"Страна",
		queryset=models.Country.objects.annotate(num_events=Count('series')).filter(num_events__gt=0).order_by('value', 'name'),
		empty_label="(любая)",
		required=False)
	region = forms.ModelChoiceField(
		label=u"Регион",
		queryset=models.Region.objects.filter(active=1).order_by('name'),
		empty_label="(любой)",
		required=False)
	unverified = forms.BooleanField(
		label=u"Только неодобренные",
		initial=True,
		required=False)
	user = UserModelChoiceField(
		label=u"Совершённые пользователем",
		queryset=User.objects.filter(is_active=True).order_by('last_name', 'first_name'),
		empty_label="(любым)",
		required=False)
	object_type = forms.ChoiceField(
		label=u"Тип объекта",
		choices=OBJECT_TYPES.items(),
		required=False)
	action_type = forms.ChoiceField(
		label=u"Действие",
		choices=models.ACTION_TYPES,
		required=False)
	date_from = forms.DateField(
		label=u"Не раньше",
		widget=CustomDateInput(),
		required=False)
	date_to = forms.DateField(
		label=u"Не позже",
		widget=CustomDateInput(),
		required=False)

class SocialPageForm(forms.ModelForm):
	class Meta:
		model = models.Social_page
		fields = ['page_type', 'page_id', 'name', 'district', 'url', 'access_token', 'is_for_all_news', 'token_secret']
		widgets = {
			'page_id': forms.TextInput(attrs={'size': 10}),
			'name': forms.TextInput(attrs={'size': 30}),
			'url': forms.TextInput(attrs={'size': 30}),
			'access_token': forms.TextInput(attrs={'size': 10}),
			'token_secret': forms.TextInput(attrs={'size': 10}),
		}

class RunnerForm(ModelFormWithCity):
	region = RegionOrCountryField()
	def __init__(self, *args, **kwargs):
		super(RunnerForm, self).__init__(*args, **kwargs)
		if self.instance.user:
			self.fields['club_name'].disabled = True
			self.fields['club_name'].label += u' (можно изменить только у соотв. пользователя)'
	def clean(self):
		cleaned_data = super(RunnerForm, self).clean()
		if cleaned_data['gender'] == models.GENDER_UNKNOWN:
			raise forms.ValidationError(u'Пожалуйста, укажите пол бегуна')
		birthday = cleaned_data.get('birthday')
		birthday_known = cleaned_data.get('birthday_known', False)
		if birthday and (not birthday_known) and ( (birthday.month > 1) or (birthday.day > 1)):
			raise forms.ValidationError(
				u'Вы не забыли поставить галочку «Известен ли день рождения»? Если неизвестен, укажите день рождения 1 января')
		if birthday_known and (birthday is None):
			cleaned_data['birthday_known'] = False
			self.cleaned_data = cleaned_data
	class Meta:
		model = models.Runner
		fields = ['klb_person', 'user',
			'parkrun_id', 'lname', 'fname', 'midname', 'gender', 'birthday', 'birthday_known', 'deathday',
			'region', 'city_id', 'club_name', 'url_wiki', 'comment_private', 'private_data_hidden',
		]
		widgets = {
			'klb_person': forms.NumberInput(),
			'user': forms.NumberInput(),
			# 'ak_person': forms.TextInput(attrs={'maxlength': 6}),
			'birthday': CustomDateInput(),
			'deathday': CustomDateInput(),
			'url_wiki': forms.TextInput(attrs={'size': 50}),
			'comment_private': forms.TextInput(attrs={'size': 50}),
		}

class ClubForm(ModelFormWithCity):
	region = RegionOrCountryField()
	is_actual = forms.BooleanField(
		label=u"Отметьте, если вся информация о клубе актуальна",
		required=False)
	def __init__(self, *args, **kwargs):
		is_admin = kwargs.pop('is_admin')
		super(ClubForm, self).__init__(*args, **kwargs)
		if not is_admin:
			del self.fields['is_active']
	def clean(self):
		cleaned_data = super(ClubForm, self).clean()
		if 'is_actual' in cleaned_data:
			self.instance.last_update_time = datetime.datetime.now()
	class Meta:
		model = models.Club
		fields = ['name', 'city_id', 'url_site', 'logo', 'birthday', 'n_members', 'address_street',
			'email', 'phone_club', 'other_contacts', 'url_vk', 'url_facebook',
			'head_name', 'head_address', 'head_email', 'phone_mob', 'phone_rab', 'phone_dom',
			'head_ICQ', 'head_skype', 'head_vk', 'head_facebook', 'head_other_contacts',
			'speaker_name', 'speaker_email',
			'tales', 'training_timetable', 'training_cost',
			'is_active', 'is_member_list_visible', 'members_can_pay_themselves',
			]
		widgets = {
			'birthday': CustomDateInput(),
			'tales': TinyMCE(attrs={'cols': 60, 'rows': 10}),
			
			'head_name': forms.TextInput(attrs={'style': 'width: 100%;'}),
			'head_address': forms.TextInput(attrs={'style': 'width: 100%;'}),
			'head_email': forms.TextInput(attrs={'style': 'width: 100%;'}),
			'phone_number': forms.TextInput(attrs={'style': 'width: 100%;'}),
			'phone_rab': forms.TextInput(attrs={'style': 'width: 100%;'}),
			'phone_dom': forms.TextInput(attrs={'style': 'width: 100%;'}),
			'head_ICQ': forms.TextInput(attrs={'style': 'width: 100%;'}),
			'head_skype': forms.TextInput(attrs={'style': 'width: 100%;'}),
			'head_vk': forms.TextInput(attrs={'style': 'width: 100%;'}),
			'head_facebook': forms.TextInput(attrs={'style': 'width: 100%;'}),
			'head_other_contacts': forms.TextInput(attrs={'style': 'width: 100%;'}),

			'name': forms.TextInput(attrs={'style': 'width: 100%;'}),
			'url_site': forms.TextInput(attrs={'style': 'width: 100%;'}),
			'address_street': forms.TextInput(attrs={'style': 'width: 100%;'}),
			'email': forms.TextInput(attrs={'style': 'width: 100%;'}),
			'phone_club': forms.TextInput(attrs={'style': 'width: 100%;'}),
			'other_contacts': forms.TextInput(attrs={'style': 'width: 100%;'}),
			'url_vk': forms.TextInput(attrs={'style': 'width: 100%;'}),
			'url_facebook': forms.TextInput(attrs={'style': 'width: 100%;'}),
			'training_timetable': forms.TextInput(attrs={'style': 'width: 100%;'}),
			'training_cost': forms.TextInput(attrs={'style': 'width: 100%;'}),
			'speaker_name': forms.TextInput(attrs={'style': 'width: 100%;'}),
			'speaker_email': forms.TextInput(attrs={'style': 'width: 100%;'}),
		}
		labels = {
			'members_can_pay_themselves': u'Участники клуба могут оплатить' \
				+ u' участие в матче каждый за себя. Я как руководитель клуба обязуюсь заплатить' \
				+ u' не позже 31 мая за всех членов команд клуба, кто не оплатит участие сам',
		}

class KlbPersonForm(forms.ModelForm):
	# region = RegionOrCountryField()
	class Meta:
		model = models.Klb_person
		fields = ['nickname', 'email', 'phone_number', 'postal_address', 'skype', 'ICQ', 'disability_group', 'comment', ]

class KlbParticipantForm(RoundedFieldsModelForm):
	def __init__(self, *args, **kwargs):
		self.year = kwargs.pop('year')
		super(KlbParticipantForm, self).__init__(*args, **kwargs)
		self.fields['team'].queryset = models.Klb_team.objects.filter(year=self.year, n_members__lte=models_klb.get_team_limit(self.year)).exclude(
			number=models.INDIVIDUAL_RUNNERS_CLUB_NUMBER).order_by('name')
		self.fields['team'].empty_label = u'Индивидуальный участник'
		if self.year <= 2017:
			del self.fields['email']
			del self.fields['phone_number']
		if self.instance.id:
			self.fields['team'].widget.attrs.update({'disabled': 'disabled'})
	def clean(self):
		cleaned_data = super(KlbParticipantForm, self).clean()
		if self.year >= 2018:
			if (not cleaned_data.get('email')) and (not cleaned_data.get('phone_number')):
				raise forms.ValidationError(u'Нужно заполнить хотя бы что-то одно из электронной почты и телефона участника')
	def clean_email(self):
		email = self.cleaned_data.get('email', '')
		validate_email(email)
		return email
	def clean_phone_number(self):
		phone_number = self.cleaned_data.get('phone_number', '')
		validate_phone_number(phone_number)
		return phone_number
	class Meta:
		model = models.Klb_participant
		fields = ['team', 'date_registered', 'date_removed', 'email', 'phone_number']
		widgets = {
			'date_registered': CustomDateInput(),
			'date_removed': CustomDateInput(),
		}

class KlbParticipantForTeamCaptainForm(RoundedFieldsModelForm):
	def clean(self):
		cleaned_data = super(KlbParticipantForTeamCaptainForm, self).clean()
		if (not cleaned_data.get('email')) and (not cleaned_data.get('phone_number')):
			raise forms.ValidationError(u'Нужно заполнить хотя бы что-то одно из электронной почты и телефона участника')
	def clean_email(self):
		email = self.cleaned_data.get('email', '')
		validate_email(email)
		return email
	def clean_phone_number(self):
		phone_number = self.cleaned_data.get('phone_number', '')
		validate_phone_number(phone_number)
		return phone_number
	class Meta:
		model = models.Klb_participant
		fields = ['email', 'phone_number', ]

class SplitForm(ModelFormWithCity):
	result_str = forms.CharField(
		label=u'Время (чч:мм:сс или чч:мм:сс,хх)',
		max_length=11,
		required=True)
	def __init__(self, *args, **kwargs):
		self.distance = kwargs.pop('distance')
		super(SplitForm, self).__init__(*args, **kwargs)
		self.fields['distance'].queryset = models.Distance.get_all_by_popularity().filter(distance_type=self.distance.distance_type)
		if self.instance.value:
			if self.distance.distance_type == models.TYPE_MINUTES:
				self.fields['result_str'].initial = self.instance.value
			else:
				self.fields['result_str'].initial = models.total_time2string(self.instance.value)
	def clean(self):
		cleaned_data = super(SplitForm, self).clean()
		if 'result_str' in self.changed_data:
			if self.distance.distance_type == models.TYPE_MINUTES:
				cleaned_data['value'] = results_util.int_safe(cleaned_data['result_str'])
				if cleaned_data['value'] == 0:
					raise forms.ValidationError(u'Укажите просто целое число пройденных метров')
			else:
				cleaned_data['value'] = models.string2centiseconds(cleaned_data['result_str'])
				if cleaned_data['value'] == 0:
					raise forms.ValidationError(u'Укажите результат в формате чч:мм:сс,хх или чч:мм:сс')
	class Meta:
		model = models.Split
		fields = ['result', 'distance', 'value', 'result_str',]
		widgets = {
			'result': forms.HiddenInput(),
			'value': forms.HiddenInput(),
		}

class SplitFormSet(forms.BaseModelFormSet):
	def clean(self):
		"""Checks that no two splits have the same distance."""
		super(SplitFormSet, self).clean()
		if any(self.errors):
			# Don't bother validating the formset unless each form is valid on its own
			return
		distances = []
		for form in self.forms:
			distance = form.cleaned_data.get('distance')
			if distance and (distance in distances):
				raise forms.ValidationError(u'Не может быть двух промежуточных результатов с равными дистанциями.')
			distances.append(distance)

class MySelectWidget(forms.Select):
	""" Subclass of Django's select widget that allows disabling options. """
	def __init__(self, *args, **kwargs):
		self.disabled_choices = kwargs.pop('disabled_choices', set())
		super(MySelectWidget, self).__init__(*args, **kwargs)

	def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
		option_dict = super(MySelectWidget, self).create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
		if value in self.disabled_choices:
			option_dict['attrs']['disabled'] = 'disabled'
		return option_dict

class KlbResultForm(forms.Form):
	runner_id = forms.ChoiceField(
		label=u"Участник матча",
		widget=MySelectWidget,
		required=False)
	time_str = forms.CharField(
		label=u'Результат (если время – чч:мм:сс или чч:мм:сс,хх, если расстояние – число в метрах)',
		max_length=20,
		required=True)
	# is_for_klb = forms.BooleanField(
	# 	label=u'Провести в КЛБМатч?',
	# 	required=False)
	def __init__(self, *args, **kwargs):
		self.race = kwargs.pop('race')
		is_admin = kwargs.pop('is_admin')
		race_is_for_klb = kwargs.pop('race_is_for_klb')
		choices = kwargs.pop('runner_choices')
		disabled_choices = kwargs.pop('disabled_choices')
		super(KlbResultForm, self).__init__(*args, **kwargs)

		self.fields['runner_id'].choices = choices
		self.fields['runner_id'].widget.disabled_choices = disabled_choices

		if race_is_for_klb:
			self.fields['is_for_klb'] = forms.BooleanField(
				label=u'Провести в КЛБМатч?',
				required=False
			)
			self.fields['is_for_klb'].widget.attrs.update({'class': 'chkbox'})
			if is_admin:
				self.fields['only_bonus_score'] = forms.BooleanField(
					label=u'Считать только бонусы?',
					required=False
				)
				self.fields['only_bonus_score'].widget.attrs.update({'class': 'gender'})
	def clean(self):
		cleaned_data = super(KlbResultForm, self).clean()
		if cleaned_data.get('runner_id'):
			runner = models.Runner.objects.filter(pk=cleaned_data['runner_id']).first()
			if runner:
				result = self.race.parse_result(cleaned_data.get('time_str', ''))
				if result == 0:
					raise forms.ValidationError(u'Пожалуйста, введите результат в указанном формате.')
				cleaned_data['runner'] = runner
				cleaned_data['result'] = result
				self.cleaned_data = cleaned_data

# When adding new people to KLB team
class RunnerForKlbForm(ModelFormWithCity):
	region = RegionOrCountryField(required=True)
	new_city_name = forms.CharField(
		label=u'Или введите новый населённый пункт, если нужного нет в регионе',
		max_length=100,
		required=False)
	email = forms.CharField(
		label=u'Адрес электронной почты',
		max_length=models.MAX_EMAIL_LENGTH,
		validators=[validate_email],
		required=False)
	phone_number = forms.CharField(
		label=u'Мобильный телефон',
		max_length=models.MAX_PHONE_NUMBER_LENGTH,
		validators=[validate_phone_number],
		required=False)
	and_to_club_members = forms.BooleanField(
		widget=forms.HiddenInput(),
		required=False)
	def __init__(self, *args, **kwargs):
		self.user = kwargs.pop('user', None)
		self.year = kwargs.pop('year', models.CUR_KLB_YEAR)
		super(RunnerForKlbForm, self).__init__(*args, **kwargs)
		if self.year <= 2017:
			del self.fields['email']
			del self.fields['phone_number']
		for field in self.fields:
			self.fields[field].widget.attrs.update({'class': 'form-control', 'width': '50%'})
		for field_name in ['lname', 'fname', 'gender', 'birthday']:
			self.fields[field_name].required = True
		self.fields['gender'].choices = models.GENDER_CHOICES[1:]
		self.fields['gender'].initial = models.GENDER_MALE
	def clean(self):
		cleaned_data = super(RunnerForKlbForm, self).clean()
		city = cleaned_data.get('city')
		new_city_name = cleaned_data.get('new_city_name', '').strip()
		if new_city_name and city:
			raise forms.ValidationError(u'Либо выберите город из выпадающего списка, либо введите название нового города, но не одновременно')
		if (not new_city_name) and (not city):
			raise forms.ValidationError(u'Либо выберите город из выпадающего списка, либо введите название нового города')
		if self.year >= 2018:
			if (not cleaned_data.get('email')) and (not cleaned_data.get('phone_number')):
				raise forms.ValidationError(u'Нужно заполнить хотя бы что-то одно из электронной почты и телефона участника')
		if new_city_name:
			region = cleaned_data["region"]
			new_city = models.City.objects.filter(region=region, name=new_city_name).first()
			if not new_city:
				new_city = models.City.objects.create(region=region, name=new_city_name, created_by=self.user)
				models.log_obj_create(self.user, new_city, action=models.ACTION_CREATE, field_list=['region', 'name', 'created_by'])
			self.cleaned_data['city'] = new_city
			self.instance.city = new_city
	class Meta:
		model = models.Runner
		fields = ['lname', 'fname', 'midname', 'gender', 'birthday', 'email', 'phone_number', 'region', 'city_id', 'new_city_name', ]
		widgets = {
			'birthday': CustomDateInput(),
		}
		labels = {
			'birthday': u'Дата рождения (ДД.ММ.ГГГГ)',
			'midname': u'Отчество (необязательно)',
		}

# For creating new runners from results
class RunnerNameForm(forms.ModelForm):
	class Meta:
		model = models.Runner_name
		fields = ['name', 'gender']

class ModelHorizontalForm(forms.ModelForm):
	def __init__(self, *args, **kwargs):
		super(ModelHorizontalForm, self).__init__(*args, **kwargs)
		for field_name in self.fields:
			field = self.fields[field_name]
			if field.widget.__class__.__name__ == 'CheckboxInput':
				field.label_suffix = ''
			else:
				field.widget.attrs.update({'class': 'form-control'})

class RegistrationForm(ModelHorizontalForm):
	def __init__(self, *args, **kwargs):
		super(RegistrationForm, self).__init__(*args, **kwargs)
		if self.instance.id is None:
			self.fields['is_open'].widget = forms.HiddenInput()
	def clean(self):
		cleaned_data = super(RegistrationForm, self).clean()
		if 'finish_date' in cleaned_data:
			event = self.instance.event
			if event.start_date <= cleaned_data['finish_date'].date():
				raise forms.ValidationError(u'Регистрация должна закрываться не позже, чем за 1 день до старта забега')
			if 'start_date' in cleaned_data:
				if cleaned_data['start_date'] >= cleaned_data['finish_date']:
					raise forms.ValidationError(u'Регистрация должна закрываться позже, чем открываться')
	class Meta:
		model = models.Registration
		fields = ['start_date', 'finish_date', 'is_open', 'is_midname_needed', 'is_address_needed',
		]
		# widgets = {
		# 	'start_date': CustomDateTimeInput(),
		# 	'finish_date': CustomDateTimeInput(),
		# }

class RegRaceForm(ModelHorizontalForm):
	def __init__(self, *args, **kwargs):
		is_sample = kwargs.pop('is_sample', False)
		super(RegRaceForm, self).__init__(*args, **kwargs)
		if is_sample:
			self.fields['race'].required = False
			self.fields['created_by'].required = False
			self.fields['is_open'].widget = forms.HiddenInput()
			self.fields['can_be_transferred'].disabled = True
			self.fields['can_be_transferred'].label += u' (пока не работает)'
	class Meta:
		model = models.Reg_race_details
		fields = ['race', 'is_open', 'participants_limit', 'queue_limit', 'is_participants_list_open', 'can_be_transferred', 'transfer_cost',
			'transfer_finish_date', 'created_by', 
		]
		widgets = {
			'transfer_finish_date': CustomDateInput(),
			'participants_limit': forms.NumberInput(),
			'queue_limit': forms.NumberInput(),
			'transfer_cost': forms.NumberInput(),
			'race': forms.HiddenInput(),
			'created_by': forms.HiddenInput(),
		}

MOVE_NOT = 1
MOVE_TO_FIRST = 2
MOVE_TO_PREV = 3
MOVE_TO_NEXT = 4
MOVE_TO_LAST = 5
QUESTION_MOVE_CHOICES = (
	(MOVE_NOT, u'куда?'),
	(MOVE_TO_FIRST, u'на первое место'),
	(MOVE_TO_PREV, u'на один вверх'),
	(MOVE_TO_NEXT, u'на один вниз'),
	(MOVE_TO_LAST, u'на последнее место'),
)
QUESTION_MOVE_CHOICES_FOR_NEW = (
	(MOVE_TO_FIRST, u'на первое место'),
	(MOVE_TO_LAST, u'на последнее место'),
)
class RegQuestionForm(forms.ModelForm):
	class Meta:
		model = models.Reg_question
		fields = ['title', 'name', 'finish_date', 'multiple_answers', 'is_required', 'created_by', 'event', 'image', ]
		widgets = {
			'finish_date': CustomDateInput(),
			'event': forms.HiddenInput(),
			'created_by': forms.HiddenInput(),
		}

class RegQuestionRaceForm(forms.ModelForm): # The same but only with race_set field. For question_details page
	def __init__(self, *args, **kwargs):
		super(RegQuestionRaceForm, self).__init__(*args, **kwargs)
		question = self.instance
		event = question.event
		if event:
			self.fields['race_set'].queryset = event.get_reg_race_set()
		else:
			self.fields['race_set'].queryset = models.Race.objects.none()
	class Meta:
		model = models.Reg_question
		fields = ['race_set', ]
		widgets = {
			'race_set': forms.CheckboxSelectMultiple()
		}

class RaceCostForm(forms.ModelForm):
	def clean(self):
		cleaned_data = super(RaceCostForm, self).clean()
		if ('DELETE' not in cleaned_data) and cleaned_data.get('finish_date') and (cleaned_data.get('cost') is None):
			raise forms.ValidationError(u'Раз указана дата, нужно указать и цену. Можно поставить ноль')
		if cleaned_data.get('age_min') and cleaned_data.get('age_max') and (cleaned_data['age_min'] > cleaned_data['age_max']):
			raise forms.ValidationError(u'Минимальный допустимый возраст не может быть больше максимального: {}, {}'.format(
				cleaned_data['age_min'], cleaned_data['age_max']))
	class Meta:
		model = models.Race_cost
		fields = ['race', 'finish_date', 'cost', 'name', 'created_by', 'age_min', 'age_max', ]
		widgets = {
			'finish_date': CustomDateInput(),
			'cost': forms.NumberInput(),
			'race': forms.HiddenInput(),
			'created_by': forms.HiddenInput(),
			'age_min': forms.NumberInput(attrs={'min': 0, 'max': models.MAX_RUNNER_AGE}),
			'age_max': forms.NumberInput(attrs={'min': 0, 'max': models.MAX_RUNNER_AGE}),
		}

class RaceCostFormSet(forms.BaseModelFormSet):
	def clean(self):
		"""Checks that there are no two prices with same cost and name."""
		super(RaceCostFormSet, self).clean()
		if any(self.errors):
			# Don't bother validating the formset unless each form is valid on its own
			return
		has_finish_price = False
		price_dates = set()
		finish_prices_for_age = [False] * (models.MAX_RUNNER_AGE + 1)
		for form in self.forms:
			cleaned_data = form.cleaned_data
			if not cleaned_data.get('DELETE'):
				race_cost = form.instance
				if race_cost.id or cleaned_data.get('finish_date') or cleaned_data.get('name') or (cleaned_data.get('cost') is not None):
					if cleaned_data.get('finish_date') is None:
						has_finish_price = True
						age_min = max(race_cost.age_min, 0) if race_cost.age_min else 0
						age_max = min(race_cost.age_max, models.MAX_RUNNER_AGE) if race_cost.age_max else models.MAX_RUNNER_AGE
						for age in range(age_min, age_max + 1):
							finish_prices_for_age[age] = True
					pair = (cleaned_data.get('finish_date'), cleaned_data.get('name'))
					if pair in price_dates:
						raise forms.ValidationError(u'Нельзя создать две цены с одинаковыми датой и названием')
					price_dates.add(pair)
		if not has_finish_price:
			raise forms.ValidationError(
				u'Должна быть указана хотя бы одна цена, действующая до закрытия регистрации. У такой цены не нужно указывать дату')
		for age in range(models.MAX_RUNNER_AGE + 1):
			if not finish_prices_for_age[age]:
				raise forms.ValidationError(
					u'Должна быть указана цена до окончания регистрации для каждого возраста. Сейчас такой цены нет для возраста {}'.format(age))
		if not has_finish_price:
			raise forms.ValidationError(
				u'Должна быть указана хотя бы одна цена, действующая до закрытия регистрации. У такой цены не нужно указывать дату')

class RegChoiceForm(ModelHorizontalForm):
	class Meta:
		model = models.Reg_question_choice
		fields = ['name',
				'cost',
				'is_visible',
				'is_default',
				'reg_question',
				'created_by',
				]
		widgets = {
			'name': forms.TextInput(attrs={'placeholder': u'Название пункта'}),
			'cost': forms.NumberInput(),
			'reg_question': forms.HiddenInput(),
			'created_by': forms.HiddenInput(),
		}

class RegChoiceFormSet(forms.BaseModelFormSet):
	def clean(self):
		"""Checks that if we can choose only one choice, then there must be not more than one default answer."""
		super(RegChoiceFormSet, self).clean()
		if any(self.errors):
			# Don't bother validating the formset unless each form is valid on its own
			return
		if len(self.forms) > 1:
			question = self.forms[0].instance.reg_question
			if not question.multiple_answers:
				n_default_answers = 0
				for form in self.forms:
					if form.cleaned_data.get('is_default'):
						n_default_answers += 1
						if n_default_answers > 1:
							raise forms.ValidationError(u'Вариантов ответа по умолчанию на вопрос «{}» может быть не больше одного'.format(question.title))

class RaceCheckForm(ModelHorizontalForm):
	is_checked = forms.BooleanField(
		required=False)
	def __init__(self, *args, **kwargs):
		super(RaceCheckForm, self).__init__(*args, **kwargs)
		for field in self.fields:
			self.fields[field].label = self.instance.distance_with_details()
	class Meta:
		model = models.Race
		fields = ['id']
		widgets = {
			'id': forms.HiddenInput(),
		}

# Should be used only if registration is open not for all distances of event
class RegNewRaceForm(forms.Form):
	race_new = forms.ModelChoiceField(
		queryset=models.Race.objects.none(),
		empty_label=None,
		required=True)
	race_template = forms.ModelChoiceField(
		queryset=models.Race.objects.none(),
		empty_label=u'никакую',
		required=False)
	def __init__(self, *args, **kwargs):
		event = kwargs.pop('event')
		super(RegNewRaceForm, self).__init__(*args, **kwargs)
		races_with_reg_ids = set(models.Reg_race_details.objects.filter(race__event=event).values_list('race_id', flat=True))
		self.fields['race_template'].queryset = event.race_set.filter(pk__in=races_with_reg_ids)
		self.fields['race_new'].queryset = event.race_set.exclude(pk__in=races_with_reg_ids)

class ClubMemberForm(RoundedFieldsModelForm):
	def clean_email(self):
		email = self.cleaned_data.get('email', '')
		validate_email(email)
		return email
	def clean_phone_number(self):
		phone_number = self.cleaned_data.get('phone_number', '')
		validate_phone_number(phone_number)
		return phone_number
	def clean_date_registered(self):
		date_registered = self.cleaned_data.get('date_registered')
		validate_date(date_registered)
		return date_registered
	def clean_date_removed(self):
		date_removed = self.cleaned_data.get('date_removed')
		validate_date(date_removed)
		return date_removed
	def clean(self):
		cleaned_data = super(ClubMemberForm, self).clean()
		date_registered = self.cleaned_data.get('date_registered')
		date_removed = self.cleaned_data.get('date_removed')
		if date_registered and date_removed and date_registered > date_removed:
			raise forms.ValidationError(u'Дата вступления в клуб не может быть больше даты выхода из клуба')
	class Meta:
		model = models.Club_member
		fields = ['email', 'phone_number', 'date_registered', 'date_removed']
		widgets = {
			'date_registered': CustomDateInput(),
			'date_removed': CustomDateInput(),
		}
		labels = {
			'birthday': u'Дата рождения. Её будем видеть только мы; это позволит точнее находить результаты бегуна'
		}

# When adding new people to club
class RunnerForClubForm(ModelFormWithCity):
	region = RegionOrCountryField(required=False)
	new_city_name = forms.CharField(
		label=u'Или введите новый населённый пункт, если нужного нет в регионе',
		max_length=100,
		required=False)
	email = forms.CharField(
		label=u'Адрес электронной почты',
		max_length=models.MAX_EMAIL_LENGTH,
		validators=[validate_email],
		required=False)
	phone_number = forms.CharField(
		label=u'Мобильный телефон',
		max_length=models.MAX_PHONE_NUMBER_LENGTH,
		validators=[validate_phone_number],
		required=False)
	date_registered = forms.DateField(
		label=u'Дата появления в клубе',
		widget=CustomDateInput(),
		required=True)
	def __init__(self, *args, **kwargs):
		self.user = kwargs.pop('user', None)
		super(RunnerForClubForm, self).__init__(*args, **kwargs)
		for field in self.fields:
			self.fields[field].widget.attrs.update({'class': 'form-control', 'width': '50%'})
		for field_name in ['lname', 'fname', 'gender', 'birthday']:
			self.fields[field_name].required = True
		self.fields['gender'].choices = models.GENDER_CHOICES[1:]
		self.fields['gender'].initial = models.GENDER_MALE
	def clean_date_registered(self):
		date_registered = self.cleaned_data.get('date_registered')
		validate_date(date_registered)
		return date_registered
	def clean(self):
		cleaned_data = super(RunnerForClubForm, self).clean()
		city = cleaned_data.get('city')
		new_city_name = cleaned_data.get('new_city_name', '').strip()
		if new_city_name and city:
			raise forms.ValidationError(u'Либо выберите город из выпадающего списка, либо введите название нового города, но не одновременно')
		if new_city_name and not cleaned_data.get('region'):
			raise forms.ValidationError(u'Укажите, в каком регионе (для России, Украины и Беларуси) или в какой стране находится этот населённый пункт')
		if new_city_name:
			region = cleaned_data["region"]
			new_city = models.City.objects.filter(region=region, name=new_city_name).first()
			if not new_city:
				new_city = models.City.objects.create(region=region, name=new_city_name, created_by=self.user)
				models.log_obj_create(self.user, new_city, action=models.ACTION_CREATE, field_list=['region', 'name', 'created_by'])
			self.cleaned_data['city'] = new_city
			self.instance.city = new_city
	class Meta:
		model = models.Runner
		fields = ['lname', 'fname', 'midname', 'gender', 'birthday', 'email', 'phone_number', 'region', 'city_id', 'new_city_name', 'date_registered',]
		widgets = {
			'birthday': CustomDateInput(),
		}
		labels = {
			'birthday': u'Дата рождения (ДД.ММ.ГГГГ)',
		}

# When viewing/changing/creating race organizer
class OrganizerForm(forms.ModelForm):
	def __init__(self, *args, **kwargs):
		super(OrganizerForm, self).__init__(*args, **kwargs)
		for field in self.fields:
			self.fields[field].widget.attrs.update({'class': 'form-control', 'width': '50%'})
	def clean(self):
		cleaned_data = super(OrganizerForm, self).clean()
		name = cleaned_data.get('name')
		if models.Organizer.objects.filter(name=name).exclude(pk=self.instance.id).exists():
			raise forms.ValidationError(u'Организатор с таким именем уже есть')
	class Meta:
		model = models.Organizer
		fields = ['name', 'url_site', 'url_vk', 'url_facebook', 'url_instagram', 'logo',
			'user', 'is_corporation', 'inn', 'kpp',
			'bank_name', 'current_account', 'corr_account', 'bik',
			'card_number', 'card_owner', 'snils',
		]
		widgets = {
			'user': forms.NumberInput(),
		}

class UsefulLabelForm(forms.ModelForm):
	insert_before = forms.ChoiceField(
		label=u"Вставить перед",
		required=True)
	def __init__(self, *args, **kwargs):
		super(UsefulLabelForm, self).__init__(*args, **kwargs)
		other_labels = models.Useful_label.all()
		if self.instance.id:
			other_labels = other_labels.exclude(pk=self.instance.id)
		insert_before.choices = [(0, u'в конец')] + [(label.id, label.name) for label in other_labels]
		insert_before.default = 0
	class Meta:
		model = models.Useful_label
		fields = ['name', ]

class UsefulLinkForm(forms.ModelForm):
	class Meta:
		model = models.Useful_link
		fields = ['name', 'url', 'labels', ]

class RecordResultForm(forms.ModelForm):
	distance = forms.ModelChoiceField(
		label=u"Дистанция",
		queryset=models.Distance.objects.filter(pk__in=results_util.DISTANCES_FOR_COUNTRY_RECORDS).order_by('distance_type', '-length'),
		required=True,
	)
	country = forms.ModelChoiceField(
		label=u"Страна",
		queryset=models.Country.objects.filter(pk__in=('BY', 'RU', 'UA')).order_by('value'),
		required=True,
	)
	value = ResultValueField(
		label='Результат',
		min_value=0,
		required=False,
	)
	def __init__(self, *args, **kwargs):
		distance_type = kwargs.pop('distance_type')
		value_label = u'Результат в метрах' if (distance_type == models.TYPE_MINUTES) else u'Результат в формате 1:23:45,67'
		super(RecordResultForm, self).__init__(*args, **kwargs)
		self.fields['value'].label = value_label
		self.fields['value'].distance_type = distance_type
	def clean(self):
		cleaned_data = super(RecordResultForm, self).clean()
		return cleaned_data
	class Meta:
		model = models.Record_result
		fields = [
			'country', 'gender', 'age_group', 'distance', 'is_indoor',
			'cur_place', 'was_record_ever', 'is_official_record', 'fname', 'lname', 'city', 'runner', 'result', 'value', 'race',
			'date', 'is_date_known', 'comment', 'is_from_shatilo', ]
		widgets = {
			'runner': forms.NumberInput(attrs={'size': 7}),
			'result': forms.NumberInput(attrs={'size': 7}),
			'city': forms.NumberInput(attrs={'size': 7}),
			'cur_place': forms.NumberInput(attrs={'size': 7}),
			'race': forms.NumberInput(attrs={'size': 7}),
			'date': CustomDateInput(),
		}
		labels = {
			'runner': u'ID бегуна',
			'result': u'ID результата',
			'race': u'ID забега (/race/...)',
		}

MONTHS = (
	(1, u'январь'),
	(2, u'февраль'),
	(3, u'март'),
	(4, u'апрель'),
	(5, u'май'),
	(6, u'июнь'),
	(7, u'июль'),
	(8, u'август'),
	(9, u'сентябрь'),
	(10, u'октябрь'),
	(11, u'ноябрь'),
	(12, u'декабрь'),
)
MAX_YEAR = max(models.CUR_KLB_YEAR, models.NEXT_KLB_YEAR)
class MonthYearForm(RoundedFieldsForm): # For the list of loaded protocols by month
	month = forms.ChoiceField(
		label=u"",
		choices=MONTHS,
		required=True)
	year = forms.ChoiceField(
		label=u"",
		choices=[(year, year) for year in range(MAX_YEAR - 5, MAX_YEAR + 1)],
		required=True)
