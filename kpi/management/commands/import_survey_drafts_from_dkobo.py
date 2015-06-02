from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.contrib.auth.models import User
from django.conf import settings
from django.forms.models import model_to_dict
from optparse import make_option
import os
import json
import glob
import random
# from django.utils import timezone
from django.contrib.sites.models import Site
import dateutil.parser

import re

from kpi.models import Collection
from kpi.models import Asset

from pyxform.xls2json_backends import csv_to_dict
from StringIO import StringIO


from jsonfield import JSONField
from taggit.managers import TaggableManager

from django.db import models
class SurveyDraft(models.Model):
    '''
    SurveyDrafts belong to a user and contain the minimal representation of
    the draft survey of the user and of the question library.
    '''
    class Meta:
        app_label = 'koboform'

    user = models.ForeignKey(User, related_name="survey_drafts")
    name = models.CharField(max_length=255, null=False)
    body = models.TextField()
    description = models.CharField(max_length=255, null=True)
    date_created = models.DateTimeField()
    date_modified = models.DateTimeField()
    summary = JSONField()
    asset_type = models.CharField(max_length=32, null=True)
    tags = TaggableManager()


def _csv_to_dict(content):
    out_dict = {}
    for (key, sheet) in csv_to_dict(StringIO(content.encode('utf-8'))).items():
        if not re.search(r'_header$', key):
            out_dict[key] = sheet
    return out_dict


def _set_auto_field_update(kls, field_name, val):
    field = filter(lambda f: f.name == field_name, kls._meta.fields)[0]
    field.auto_now = val
    field.auto_now_add = val

def _import_user_assets(from_user, to_user):
    user = to_user

    user_survey_drafts = user.survey_drafts.filter(asset_type=None)
    user_qlib_assets = user.survey_drafts.exclude(asset_type=None)

    def _import_asset(asset, parent_collection=None):
        survey_dict = _csv_to_dict(asset.body)
        obj = {
            'name': asset.name,
            'date_created': asset.date_created,
            'date_modified': asset.date_modified,
            'owner': user,
        }

        if parent_collection is not None:
            obj['parent'] = parent_collection
            del obj['name']
        new_asset = Asset(**obj)

        _set_auto_field_update(Asset, "date_created", False)
        _set_auto_field_update(Asset, "date_modified", False)
        new_asset.content = survey_dict
        new_asset.date_created = obj['date_created']
        new_asset.date_modified = obj['date_modified']
        new_asset.save()
        _set_auto_field_update(Asset, "date_created", True)
        _set_auto_field_update(Asset, "date_modified", True)


    for survey_draft in user_survey_drafts.all():
        print 'importing sd %s %d' % (survey_draft.name, survey_draft.id)
        _import_asset(survey_draft)

    (qlib, created) = Collection.objects.get_or_create(name="question library", owner=user)

    for qlib_asset in user_qlib_assets.all():
        print 'importing qla %s %d' % (qlib_asset.name, qlib_asset.id)
        _import_asset(survey_draft, qlib)

    _set_auto_field_update(Asset, "date_created", False)
    _set_auto_field_update(Asset, "date_modified", False)
    qlib.date_created = user.date_joined
    qlib.date_modified = user.date_joined
    qlib.save()
    _set_auto_field_update(Asset, "date_created", True)
    _set_auto_field_update(Asset, "date_modified", True)


class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
        make_option('--destroy',
            action='store_true',
            dest='destroy',
            default=False,
            help='Delete all collections, assets, and tasks for user'),
        make_option('--destination',
            action='store',
            dest='destination',
            default=False,
            help='A uid of a destination collection that will contain the imported asset(s)'),
        make_option('--allusers',
            action='store_true',
            dest='all_users',
            default=False,
            help='migrate all the users at once'),
        make_option('--username',
            action='store',
            dest='username',
            default=False,
            help='specify the user to migrate'),
        make_option('--to-username',
            action='store',
            dest='to_username',
            default=False,
            help='specify the user to migrate the assets TO (default: same as --username)'),
        )

    def handle(self, *args, **options):
        users = User.objects.none()
        if options.get('username'):
            users = [User.objects.get(username=options.get('username'))]
        elif options.get('all_users'):
            users = User.objects.all()
        else:
            raise Exception('must specify either --username=username or --allusers')
        to_user = False
        if options.get('to_username'):
            to_user = User.objects.get(username=options.get('to_username'))

        for from_user in users:
            if not to_user:
                to_user = from_user
            print "user has %d collections" % to_user.owned_collections.count()
            print "user has %d assets" % to_user.assets.count()
            to_user.owned_collections.all().delete()
            to_user.assets.all().delete()
            print "user has %d collections" % to_user.owned_collections.count()
            print "user has %d assets" % to_user.assets.count()
            _import_user_assets(from_user, to_user)