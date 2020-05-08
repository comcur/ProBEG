# -*- coding: utf-8 -*-

MAX_CLEAN_SCORE = 16

# MIN_DISTANCE_FOR_SCORE = 10000 # Are true only for years from 2015
# MAX_DISTANCE_FOR_SCORE = 250000
# MIN_DISTANCE_FOR_BONUS = 9800

MIN_TEAM_SIZE = 3

def get_min_distance_for_score(year):
	if year >= 2018:
		return 9500
	else: # true only for year >= 2015
		return 10000

def get_max_distance_for_score(year):
	if year >= 2018:
		return 300000
	else: # true only for year >= 2015
		return 250000

def get_min_distance_for_bonus(year):
	if year >= 2018:
		return 9500
	else: # true only for year >= 2015
		return 9800

def get_small_team_limit(year):
	if year >= 2017:
		return 18
	elif year >= 2015:
		return 15
	else:
		return 12

def get_medium_team_limit(year):
	return 40

def get_team_limit(year):
	if year >= 2020:
		return 90
	elif year >= 2017:
		return 100
	elif year == 2016:
		return 110
	elif year == 2015:
		return 120
	else:
		return 150

def get_n_runners_for_team_clean_score(year):
	if year >= 2016:
		return 15
	else:
		return 12

def get_n_results_for_clean_score(year):
	if year >= 2019:
		return 4
	else:
		return 3

def get_n_results_for_bonus_score(year):
	if year >= 2017:
		return 18
	else:
		return 20

def get_bonus_score_denominator(year):
	if year >= 2019:
		return 200000
	else:
		return 100000

def get_max_bonus_for_one_race(year):
	if year >= 2019:
		return 6
	else:
		return 20

def get_max_bonus_per_year(year):
	if year >= 2019:
		return 20
	else:
		return 100

def get_participation_price(year):
	if year >= 2019:
		return 120
	return 100

def get_regulations_link(year):
	if year >= 2011:
		return 'docs/Pl_KLBMatch_{}.pdf'.format(year % 1000)
	return ''

def get_regulations_changes_link(year):
	if year >= 2018:
		return 'docs/Pl_KLBMatch_{}_izm.pdf'.format(year % 1000)
	return ''

def get_old_match_link(year):
	if 2011 <= year <= 2016:
		return 'http://probeg.org/klb/{}/'.format(year)
	return ''

def get_last_month_to_pay_for_teams(year):
	return 5

MEDAL_PAYMENT_YEAR = 2019
MEDAL_PRICE = 300
PLATE_PRICE = 60
