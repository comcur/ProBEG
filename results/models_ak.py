# -*- coding: utf-8 -*-
from django.db import models

class Ak_race(models.Model): # For persons in runners160403
	id = models.CharField(primary_key=True, max_length=6, db_column='RACEID')
	race_date = models.DateField(db_column='DATE_RACE')
	number = models.SmallIntegerField(default=None, null=True, blank=True, db_column='NUM_RACE')
	name = models.CharField(max_length=80, blank=True, db_column='NAME_RACE')
	place = models.CharField(max_length=80, blank=True, db_column='PLACE_RACE')
	distance = models.CharField(max_length=10, blank=True, db_column='DISTANCE')
	temperature_start = models.SmallIntegerField(default=None, null=True, blank=True, db_column='T_START')
	temperature_finish = models.SmallIntegerField(default=None, null=True, blank=True, db_column='T_FINISH')
	district_raw = models.CharField(max_length=40, db_column='fedokrug', blank=True)
	region_raw = models.CharField(max_length=50, db_column='obl', blank=True)
	city_raw = models.CharField(max_length=50, db_column='city', blank=True)
	class Meta:
		db_table = "races160403"
	def __unicode__(self):
		return self.name + "(id " + self.id + ")"

class Ak_person(models.Model): # For persons in runners160403
	id = models.CharField(primary_key=True, max_length=6, db_column='MANID')
	name = models.CharField(max_length=32, blank=True, db_column='NAME')
	name_alternative = models.CharField(max_length=32, blank=True, db_column='NAME_ALT')
	lname = models.CharField(max_length=20, blank=True, db_column='F_NAME')
	fname = models.CharField(max_length=16, blank=True, db_column='I_NAME')
	midname = models.CharField(max_length=20, blank=True, db_column='O_NAME')
	club_raw = models.CharField(max_length=30, blank=True, db_column='CLUB')
	birthday_raw = models.DateField(default=None, null=True, db_column='DATEBIRTH')
	birthyear_raw = models.SmallIntegerField(default=None, null=True, blank=True, db_column='YEARBIRTH')
	deathday_raw = models.DateField(default=None, null=True, db_column='DATEDEATH')
	deathyear_raw = models.SmallIntegerField(default=None, null=True, blank=True, db_column='YEARDEATH')
	gender_raw = models.CharField(max_length=1, blank=True, db_column='SEX')
	country_raw = models.CharField(max_length=16, blank=True, db_column='COUNTRY')
	region_raw = models.CharField(max_length=20, blank=True, db_column='OBLAST')
	city_raw = models.CharField(max_length=30, blank=True, db_column='CITY')
	class Meta:
		db_table = "runners160403"
	def __unicode__(self):
		return self.name + "(id " + self.id + ")"

class Ak_result(models.Model): # For rezult160403
	ak_race = models.ForeignKey(Ak_race, default=None, null=True, on_delete=models.PROTECT, db_column='RACEID')
	ak_person = models.ForeignKey(Ak_person, default=None, null=True, on_delete=models.PROTECT, db_column='MANID')
	race_date = models.DateField(default=None, null=True, db_column='DATE_RACE')
	distance = models.CharField(max_length=10, blank=True, db_column='DISTANCE') # Can be comma instead of dot!
	bib = models.CharField(max_length=6, blank=True, db_column='NOMER')
	time_raw = models.CharField(max_length=10, blank=True, db_column='RESULT')
	result = models.DecimalField(default=0, max_digits=6, decimal_places=1, db_column='SECONDS')
	place = models.IntegerField(default=None, null=True, blank=True, db_column='MESTO')
	category = models.CharField(max_length=6, blank=True, db_column='V_GROUP')
	place_category = models.IntegerField(default=None, null=True, blank=True, db_column='V_MESTO')
	name_raw = models.CharField(max_length=24, blank=True, db_column='NAME')
	birthyear_raw = models.SmallIntegerField(default=None, null=True, blank=True, db_column='YEARBIRTH')
	birthday_raw = models.DateField(default=None, null=True, db_column='DATEBIRTH')
	country_raw = models.CharField(max_length=16, blank=True, db_column='COUNTRY')
	city_raw = models.CharField(max_length=16, blank=True, db_column='CITY')
	club_raw = models.CharField(max_length=40, blank=True, db_column='CLUB')
	age_raw = models.SmallIntegerField(default=None, null=True, blank=True, db_column='AGE')
	comment = models.CharField(max_length=100, blank=True, db_column='COMMENT')
	is_in_v2 = models.SmallIntegerField(verbose_name=u'Есть в 160706', default=0)
	class Meta:
		db_table = "rezult160403"
	def __unicode__(self):
		return unicode(self.result) + "(id " + unicode(self.id) + ")"

class Ak_race_v2(models.Model):
	id = models.CharField(primary_key=True, max_length=6, db_column='RACEID')
	race_date = models.DateField(db_column='DATE_RACE')
	number = models.SmallIntegerField(default=None, null=True, blank=True, db_column='NUM_RACE')
	name = models.CharField(max_length=80, blank=True, db_column='NAME_RACE')
	place = models.CharField(max_length=80, blank=True, db_column='PLACE_RACE')
	distance = models.CharField(max_length=10, blank=True, db_column='DISTANCE')
	temperature_start = models.SmallIntegerField(default=None, null=True, blank=True, db_column='T_START')
	temperature_finish = models.SmallIntegerField(default=None, null=True, blank=True, db_column='T_FINISH')
	district_raw = models.CharField(max_length=40, db_column='fedokrug', blank=True)
	region_raw = models.CharField(max_length=50, db_column='obl', blank=True)
	city_raw = models.CharField(max_length=50, db_column='city', blank=True)
	is_compared_to_v1 = models.SmallIntegerField(verbose_name=u'Сравнили с 160403', default=0)
	class Meta:
		db_table = "races160706"
	def __unicode__(self):
		return self.name + "(id " + self.id + ")"

class Ak_person_v2(models.Model):
	id = models.CharField(primary_key=True, max_length=6, db_column='MANID')
	name = models.CharField(max_length=32, blank=True, db_column='NAME')
	name_alternative = models.CharField(max_length=32, blank=True, db_column='NAME_ALT')
	lname = models.CharField(max_length=20, blank=True, db_column='F_NAME')
	fname = models.CharField(max_length=16, blank=True, db_column='I_NAME')
	midname = models.CharField(max_length=20, blank=True, db_column='O_NAME')
	club_raw = models.CharField(max_length=30, blank=True, db_column='CLUB')
	birthday_raw = models.DateField(default=None, null=True, db_column='DATEBIRTH')
	birthyear_raw = models.SmallIntegerField(default=None, null=True, blank=True, db_column='YEARBIRTH')
	deathday_raw = models.DateField(default=None, null=True, db_column='DATEDEATH')
	deathyear_raw = models.SmallIntegerField(default=None, null=True, blank=True, db_column='YEARDEATH')
	gender_raw = models.CharField(max_length=1, blank=True, db_column='SEX')
	country_raw = models.CharField(max_length=16, blank=True, db_column='COUNTRY')
	region_raw = models.CharField(max_length=20, blank=True, db_column='OBLAST')
	city_raw = models.CharField(max_length=30, blank=True, db_column='CITY')
	# city = models.ForeignKey('City', verbose_name=u'Город',
	# 	on_delete=models.SET_NULL, default=None, null=True, blank=True, db_column='dj_city_id')
	class Meta:
		db_table = "runners160706"
		index_together = [
			["lname"],
			["fname"],
			["midname"],
			["club_raw"],
		]
	def get_old_url(self):
		return 'http://probeg.org/rez.php?manid={}'.format(self.id)
	def __unicode__(self):
		return self.name + " (id " + self.id + ")"

class Ak_result_v2(models.Model):
	ak_race = models.ForeignKey(Ak_race_v2, default=None, null=True, on_delete=models.PROTECT, db_column='RACEID')
	ak_person = models.ForeignKey(Ak_person_v2, default=None, null=True, on_delete=models.PROTECT, db_column='MANID')
	race_date = models.DateField(db_column='DATE_RACE')
	distance = models.CharField(max_length=10, blank=True, db_column='DISTANCE') # Can be comma instead of dot!
	bib = models.CharField(max_length=6, blank=True, db_column='NOMER')
	time_raw = models.CharField(max_length=10, blank=True, db_column='RESULT')
	result = models.DecimalField(default=0, max_digits=6, decimal_places=1, db_column='SECONDS')
	place = models.IntegerField(default=None, null=True, blank=True, db_column='MESTO')
	category = models.CharField(max_length=6, blank=True, db_column='V_GROUP')
	place_category = models.IntegerField(default=None, null=True, blank=True, db_column='V_MESTO')
	name_raw = models.CharField(max_length=24, blank=True, db_column='NAME')
	birthyear_raw = models.SmallIntegerField(default=None, null=True, blank=True, db_column='YEARBIRTH')
	birthday_raw = models.DateField(default=None, null=True, db_column='DATEBIRTH')
	country_raw = models.CharField(max_length=16, blank=True, db_column='COUNTRY')
	city_raw = models.CharField(max_length=16, blank=True, db_column='CITY')
	club_raw = models.CharField(max_length=40, blank=True, db_column='CLUB')
	age_raw = models.SmallIntegerField(default=None, null=True, blank=True, db_column='AGE')
	comment = models.CharField(max_length=100, blank=True, db_column='COMMENT')
	# 0 - Not in v1, 1 - is in v1, 2 - its race wasn't present in v1, 3 - updated after v1
	is_in_v1 = models.SmallIntegerField(verbose_name=u'Есть в 160403', default=0)
	class Meta:
		db_table = "rezult160706"
	def __unicode__(self):
		return unicode(self.result) + "(id " + unicode(self.id) + ")"

CUR_AK_RESULT_MODEL = Ak_result_v2
CUR_AK_RACE_MODEL = Ak_race_v2
CUR_AK_PERSON_MODEL = Ak_person_v2
