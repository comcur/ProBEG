# -*- coding: utf-8 -*-
from __future__ import division
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import permission_required

from editor.views.views_common import *
from results.models import *

@group_required('admins', 'editors')
def regions(request, country_id=None, detailed=False):
	context = {}
	list_title = u"Регионы"

	regions = Region.objects.select_related('country').filter(Q(active=1) | Q(country__has_regions=0))

	if country_id:
		country = get_object_or_404(Country, pk=country_id)
		context['country'] = country
		regions = regions.filter(country=country)
		list_title += u" в стране " + country.name
		#form = CitySearchForm({'country': country.id})

	regions = regions.annotate(num_cities=Count('city', distinct=True)).order_by('country__value', 'country__name', 'name')

	context['regions'] = regions
	context['list_title'] = list_title

	return render(request, "editor/regions.html", context)
