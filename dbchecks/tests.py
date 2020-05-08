# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.test import TestCase

# Create your tests here.

import unittest
import doctest
import dbchecks

# https://stackoverflow.com/questions/2380527/django-doctests-in-views-py, answer by Andre Miras

def load_tests(loader, tests, ignore):
    tests.addTests(doctest.DocTestSuite(dbchecks))
    return tests
