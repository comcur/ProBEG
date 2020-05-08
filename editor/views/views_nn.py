# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division
from django.db.models import Q
import io
from results import models

def connect_runners_with_birthday():
	n_results = 0
	n_midnames_filled = 0
	n_cities_filled = 0
	n_clubs_filled = 0
	for nn_runner in models.Nn_runner.objects.exclude(birthday=None).filter(runner=None): #.exclude(pk=987):
		runners = models.Runner.objects.filter(lname=nn_runner.lname, fname=nn_runner.fname, birthday=nn_runner.birthday, birthday_known=True)
		if not runners.exists():
			continue
		if runners.count() > 1:
			print 'More than one runner:', nn_runner.lname, nn_runner.fname, nn_runner.birthday.isoformat(), nn_runner.birthday
			continue
		runner = runners.first()

		link = models.SITE_URL + runner.get_absolute_url()

		if hasattr(runner, 'nn_runner'):
			print u'Problem with nn_runner {} {} {}: similar runner {} already has nn_runner with ID {} {} {}'.format(
				nn_runner.lname, nn_runner.fname, nn_runner.id, link, runner.nn_runner.lname, runner.nn_runner.fname, runner.nn_runner.id)
			continue

		if nn_runner.midname:
			if runner.midname:
				if nn_runner.midname.startswith(runner.midname):
					if nn_runner.midname != runner.midname:
						runner.midname = nn_runner.midname.title()
						n_midnames_filled += 1
				else:
					print 'Problem with midnames:', link, nn_runner.lname, nn_runner.fname, nn_runner.birthday.isoformat(), nn_runner.midname, runner.midname
					# continue
			else:
				runner.midname = nn_runner.midname.title()
				n_midnames_filled += 1
		if nn_runner.city_name:
			# if nn_runner.city_name == u'Киров': # Is needed when there are two cities with same name
			# 	cities = models.City.objects.filter(pk=2209)
			# else:
			# 	cities = models.City.objects.filter(name=nn_runner.city_name)
			cities = models.City.objects.filter(name=nn_runner.city_name)
			if not cities.exists():
				print 'City does not exist:', nn_runner.city_name
				continue
			elif cities.count() > 1:
				print 'More than one city exists:', nn_runner.city_name
				continue
			city = cities.first()
			if runner.city:
				if (runner.city != city):
					print 'Problem with cities:', link, nn_runner.lname, nn_runner.fname, nn_runner.birthday.isoformat(), city.name, runner.city.name
					# continue
			else:
				runner.city = city
				n_cities_filled += 1
		if nn_runner.club_name:
			if runner.club_name:
				if (runner.club_name != nn_runner.club_name):
					print 'Problem with clubs:', link, nn_runner.lname, nn_runner.fname, nn_runner.birthday.isoformat(), nn_runner.club_name, runner.club_name
					continue
			else:
				runner.club_name = nn_runner.club_name
				n_clubs_filled += 1
		runner.save()
		nn_runner.runner = runner
		nn_runner.save()
		n_results += 1
	print 'Done! NNRunners touched, midnames, cities, clubs:', n_results, n_midnames_filled, n_cities_filled, n_clubs_filled

def connect_runners_with_fi_maybe_o():
	n_doubles = 0
	n_midnames_filled = 0
	n_cities_filled = 0
	n_clubs_filled = 0
	with io.open('20180617_nnrunners.txt', 'w', encoding="utf8") as output_file:
		for nn_runner in models.Nn_runner.objects.filter(runner=None).order_by('lname', 'fname', 'midname'):
			runners = models.Runner.objects.filter(lname=nn_runner.lname, fname=nn_runner.fname)
			if nn_runner.midname:
				runners = runners.filter(midname__in=('', nn_runner.midname))
			if nn_runner.birthday:
				runners = runners.filter(Q(birthday=None) | Q(birthday__year=nn_runner.birthday.year, birthday_known=False) | Q(birthday=nn_runner.birthday))
			elif nn_runner.birthyear:
				runners = runners.filter(Q(birthday=None) | Q(birthday__year=nn_runner.birthyear))
			if not runners.exists():
				continue
			if runners.count() > 0:
				output_file.write(u'\nFor nn_runner {} {} {} {} {}\n'.format(
					nn_runner.id, nn_runner.lname, nn_runner.fname, nn_runner.get_birthday(), nn_runner.city_name))
				output_file.write(u'we have {} dj_runners:\n'.format(runners.count()))
				for runner in runners:
					output_file.write(u'{}{} {} {} {} {}\n'.format(models.SITE_URL, runner.get_absolute_url(),
						runner.lname, runner.fname, runner.strBirthday(with_nbsp=False), runner.city if runner.city else ''))
				n_doubles += 1
				continue
			runner = runners.first()

			link = models.SITE_URL + runner.get_absolute_url()

			if hasattr(runner, 'nn_runner'):
				output_file.write(u'Problem with nn_runner {} {} {}: similar runner {} already has nn_runner with ID {} {} {}\n'.format(
					nn_runner.lname, nn_runner.fname, nn_runner.id, link, runner.nn_runner.lname, runner.nn_runner.fname, runner.nn_runner.id))
				continue
		output_file.write('Total {} nn_runners with somebody similar\n'.format(n_doubles))
	# 	if nn_runner.midname:
	# 		if runner.midname:
	# 			if nn_runner.midname.startswith(runner.midname):
	# 				if nn_runner.midname != runner.midname:
	# 					runner.midname = nn_runner.midname.title()
	# 					n_midnames_filled += 1
	# 			else:
	# 				print 'Problem with midnames:', link, nn_runner.lname, nn_runner.fname, nn_runner.birthday.isoformat(), nn_runner.midname, runner.midname
	# 				# continue
	# 		else:
	# 			runner.midname = nn_runner.midname.title()
	# 			n_midnames_filled += 1
	# 	if nn_runner.city_name:
	# 		# if nn_runner.city_name == u'Киров': # Is needed when there are two cities with same name
	# 		# 	cities = models.City.objects.filter(pk=2209)
	# 		# else:
	# 		# 	cities = models.City.objects.filter(name=nn_runner.city_name)
	# 		cities = models.City.objects.filter(name=nn_runner.city_name)
	# 		if not cities.exists():
	# 			print 'City does not exist:', nn_runner.city_name
	# 			continue
	# 		elif cities.count() > 1:
	# 			print 'More than one city exists:', nn_runner.city_name
	# 			continue
	# 		city = cities.first()
	# 		if runner.city:
	# 			if (runner.city != city):
	# 				print 'Problem with cities:', link, nn_runner.lname, nn_runner.fname, nn_runner.birthday.isoformat(), city.name, runner.city.name
	# 				# continue
	# 		else:
	# 			runner.city = city
	# 			n_cities_filled += 1
	# 	if nn_runner.club_name:
	# 		if runner.club_name:
	# 			if (runner.club_name != nn_runner.club_name):
	# 				print 'Problem with clubs:', link, nn_runner.lname, nn_runner.fname, nn_runner.birthday.isoformat(), nn_runner.club_name, runner.club_name
	# 				continue
	# 		else:
	# 			runner.club_name = nn_runner.club_name
	# 			n_clubs_filled += 1
	# 	runner.save()
	# 	nn_runner.runner = runner
	# 	nn_runner.save()
	# 	n_results += 1
	# print 'Done! NNRunners touched, midnames, cities, clubs:', n_results, n_midnames_filled, n_cities_filled, n_clubs_filled

def fill_cities_for_just_connected_runners():
	n_fixed = 0
	print 'Total:', models.Nn_runner.objects.exclude(runner=None).filter(runner__city=None, city__isnull=False).count()
	for nn_runner in models.Nn_runner.objects.exclude(runner=None).filter(runner__city=None, city__isnull=False).select_related('runner'):
		nn_runner.runner.city = nn_runner.city
		nn_runner.runner.save()
		n_fixed += 1
	print 'Done! Fixed:', n_fixed
