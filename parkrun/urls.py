"""parkrun URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
	https://docs.djangoproject.com/en/1.9/topics/http/urls/
Examples:
Function views
	1. Add an import:  from my_app import views
	2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
	1. Add an import:  from other_app.views import Home
	2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
	1. Import the include() function: from django.conf.urls import url, include
	2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.conf.urls import include, url
from django.contrib import admin
from django.views.generic import RedirectView, TemplateView
from results.views import views_site
#import probeg_auth.views
from django.conf import settings

urlpatterns = [
	url(r'^about/$', views_site.about, name='about'),
	url(r'^about_new_site/$', views_site.about_new_site, name='about_new_site'),
	url(r'^contacts/$', views_site.contacts, name='contacts'),
	url(r'^protocol/$', views_site.protocol, name='protocol'),
	url(r'^social_links/$', views_site.social_links, name='social_links'),
	url(r'^results_binding/$', views_site.results_binding, name='results_binding'),
	url(r'^how_to_help/$', views_site.how_to_help, name='how_to_help'),
	url(r'^login_problems/$', views_site.login_problems, name='login_problems'),

	# url(r'^best_russian_races_2017/$', views_site.best_russian_races_2017, name='best_russian_races_2017'),
	url(r'^sport_classes/$', views_site.sport_classes, name='sport_classes'),

	url(r'^measurement/$', views_site.measurement_about, name='measurement_about'),

	url(r'^robots\.txt/$', TemplateView.as_view(template_name='misc/robots.txt', content_type='text/plain')),
	url(r'^ads\.txt/$', TemplateView.as_view(template_name='misc/ads.txt', content_type='text/plain')),
	url(r'^favicon.png$', RedirectView.as_view(url='https://probeg.org/dj_static/images/man-square2.png'), name='favicon'),

	url(r'', include('results.urls')),
	url(r'^admin/', admin.site.urls),
	url(r'^editor/', include('editor.urls', namespace='editor')),
	# url(r'^', include('django.contrib.auth.urls', namespace='auth')),
	# url(r'', include('social.apps.django_app.urls', namespace='social')),
	url(r'', include('social_django.urls', namespace='social')),
	
	url(r'', include('probeg_auth.urls', namespace='probeg_auth')),
	url(r'^tinymce/', include('tinymce.urls')),
	url(r'', include('starrating.urls', namespace='starrating')),
]

if settings.DEBUG:
	import debug_toolbar
	urlpatterns = [
		url(r'^__debug__/', include(debug_toolbar.urls)),
   ] + urlpatterns
