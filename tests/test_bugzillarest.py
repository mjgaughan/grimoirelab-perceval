#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2016 Bitergia
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#
# Authors:
#     Santiago Dueñas <sduenas@bitergia.com>
#

import datetime
import shutil
import sys
import tempfile
import unittest

import httpretty

if not '..' in sys.path:
    sys.path.insert(0, '..')

from perceval.cache import Cache
from perceval.errors import CacheError
from perceval.errors import BackendError
from perceval.backends.bugzillarest import BugzillaREST, BugzillaRESTClient


BUGZILLA_SERVER_URL = 'http://example.com'
BUGZILLA_LOGIN_URL = BUGZILLA_SERVER_URL + '/rest/login'
BUGZILLA_BUGS_URL = BUGZILLA_SERVER_URL + '/rest/bug'
BUGZILLA_BUGS_COMMENTS_1273442_URL =  BUGZILLA_SERVER_URL + '/rest/bug/1273442/comment'
BUGZILLA_BUGS_HISTORY_1273442_URL =  BUGZILLA_SERVER_URL + '/rest/bug/1273442/history'
BUGZILLA_BUGS_ATTACHMENTS_1273442_URL =  BUGZILLA_SERVER_URL + '/rest/bug/1273442/attachment'
BUGZILLA_BUG_1273439_URL =  BUGZILLA_SERVER_URL + '/rest/bug/1273439/'
BUGZILLA_BUG_947945_URL =  BUGZILLA_SERVER_URL + '/rest/bug/947945/'


def read_file(filename, mode='r'):
    with open(filename, mode) as f:
        content = f.read()
    return content

def setup_http_server():
    http_requests = []

    bodies_bugs = [read_file('data/bugzilla_rest_bugs.json', mode='rb'),
                   read_file('data/bugzilla_rest_bugs_next.json', mode='rb'),
                   read_file('data/bugzilla_rest_bugs_empty.json', mode='rb')]
    body_comments = read_file('data/bugzilla_rest_bug_comments.json', mode='rb')
    body_history = read_file('data/bugzilla_rest_bug_history.json', mode='rb')
    body_attachments = read_file('data/bugzilla_rest_bug_attachments.json', mode='rb')

    def request_callback(method, uri, headers):
        if uri.startswith(BUGZILLA_BUGS_COMMENTS_1273442_URL):
            body = body_comments
        elif uri.startswith(BUGZILLA_BUGS_HISTORY_1273442_URL):
            body = body_history
        elif uri.startswith(BUGZILLA_BUGS_ATTACHMENTS_1273442_URL):
            body = body_attachments
        elif uri.startswith(BUGZILLA_BUG_1273439_URL):
            if uri.endswith('comment'):
                body = '{ "bugs" : {"1273439" : {"comments" : []} } }'
            elif uri.endswith('history'):
                body = '{ "bugs" : [{"history" : []}] }'
            else:
                body = '{ "bugs" : {"1273439" : []} }'
        elif uri.startswith(BUGZILLA_BUG_947945_URL):
            if uri.endswith('comment'):
                body = '{ "bugs" : {"947945" : {"comments" : []} } }'
            elif uri.endswith('history'):
                body = '{ "bugs" : [{"history" : []}] }'
            else:
                body = '{ "bugs" : {"947945" : []} }'
        else:
            body = bodies_bugs.pop(0)

        http_requests.append(httpretty.last_request())

        return (200, headers, body)

    httpretty.register_uri(httpretty.GET,
                           BUGZILLA_BUGS_URL,
                           responses=[
                                httpretty.Response(body=request_callback) \
                                for _ in range(3)
                           ])

    http_urls = [BUGZILLA_BUGS_COMMENTS_1273442_URL,
                 BUGZILLA_BUGS_HISTORY_1273442_URL,
                 BUGZILLA_BUGS_ATTACHMENTS_1273442_URL]
    suffixes = ['comment', 'history', 'attachment']

    for http_url in [BUGZILLA_BUG_1273439_URL, BUGZILLA_BUG_947945_URL]:
        for suffix in suffixes:
            http_urls.append(http_url + suffix)

    for req_url in http_urls:
        httpretty.register_uri(httpretty.GET,
                               req_url,
                               responses=[
                                    httpretty.Response(body=request_callback)
                               ])

    return http_requests


class TestBugzillaRESTBackend(unittest.TestCase):
    """Bugzilla REST backend tests"""

    def test_initialization(self):
        """Test whether attributes are initializated"""

        bg = BugzillaREST(BUGZILLA_SERVER_URL, origin='test',
                          max_bugs=5)

        self.assertEqual(bg.url, BUGZILLA_SERVER_URL)
        self.assertEqual(bg.origin, 'test')
        self.assertEqual(bg.max_bugs, 5)
        self.assertIsInstance(bg.client, BugzillaRESTClient)

        # When origin is empty or None it will be set to
        # the value in url
        bg = BugzillaREST(BUGZILLA_SERVER_URL)
        self.assertEqual(bg.url, BUGZILLA_SERVER_URL)
        self.assertEqual(bg.origin, BUGZILLA_SERVER_URL)

        bg = BugzillaREST(BUGZILLA_SERVER_URL, origin='')
        self.assertEqual(bg.url, BUGZILLA_SERVER_URL)
        self.assertEqual(bg.origin, BUGZILLA_SERVER_URL)

    @httpretty.activate
    def test_fetch(self):
        """Test whether a list of bugs is returned"""

        http_requests = setup_http_server()

        bg = BugzillaREST(BUGZILLA_SERVER_URL, max_bugs=2)
        bugs = [bug for bug in bg.fetch()]

        self.assertEqual(len(bugs), 3)

        self.assertEqual(bugs[0]['data']['id'], 1273442)
        self.assertEqual(len(bugs[0]['data']['comments']), 7)
        self.assertEqual(len(bugs[0]['data']['history']), 6)
        self.assertEqual(len(bugs[0]['data']['attachments']), 1)
        self.assertEqual(bugs[0]['origin'], BUGZILLA_SERVER_URL)
        self.assertEqual(bugs[0]['uuid'], '68494ad0072ed9e09cecb8235649a38c443326db')
        self.assertEqual(bugs[0]['updated_on'], 1465257689.0)

        self.assertEqual(bugs[1]['data']['id'], 1273439)
        self.assertEqual(len(bugs[1]['data']['comments']), 0)
        self.assertEqual(len(bugs[1]['data']['history']), 0)
        self.assertEqual(len(bugs[1]['data']['attachments']), 0)
        self.assertEqual(bugs[1]['origin'], BUGZILLA_SERVER_URL)
        self.assertEqual(bugs[1]['uuid'], 'd306162de06bc759f9bd9227fe3fd5f08aeb0dde')
        self.assertEqual(bugs[1]['updated_on'], 1465257715.0)

        self.assertEqual(bugs[2]['data']['id'], 947945)
        self.assertEqual(len(bugs[2]['data']['comments']), 0)
        self.assertEqual(len(bugs[2]['data']['history']), 0)
        self.assertEqual(len(bugs[2]['data']['attachments']), 0)
        self.assertEqual(bugs[2]['origin'], BUGZILLA_SERVER_URL)
        self.assertEqual(bugs[2]['uuid'], '33edda925351c3310fc3e12d7f18a365c365f6bd')
        self.assertEqual(bugs[2]['updated_on'], 1465257743.0)

        # Check requests
        expected = [{
                     'last_change_time' : ['1970-01-01T00:00:00Z'],
                     'limit' : ['2'],
                     'order' : ['changeddate'],
                     'include_fields' : ['_all']
                    },
                    {}, {}, {'exclude_fields' : ['data']},
                    {}, {}, {'exclude_fields' : ['data']},
                    {
                     'last_change_time' : ['1970-01-01T00:00:00Z'],
                     'offset' : ['2'],
                     'limit' : ['2'],
                     'order' : ['changeddate'],
                     'include_fields' : ['_all']
                    },
                    {}, {}, {'exclude_fields' : ['data']},
                    {
                     'last_change_time' : ['1970-01-01T00:00:00Z'],
                     'offset' : ['4'],
                     'limit' : ['2'],
                     'order' : ['changeddate'],
                     'include_fields' : ['_all']
                    }
                    ]

        self.assertEqual(len(http_requests), len(expected))

        for i in range(len(expected)):
            self.assertDictEqual(http_requests[i].querystring, expected[i])

    @httpretty.activate
    def test_fetch_empty(self):
        """Test whether it works when no bugs are fetched"""

        body = read_file('data/bugzilla_rest_bugs_empty.json')
        httpretty.register_uri(httpretty.GET,
                               BUGZILLA_BUGS_URL,
                               body=body, status=200)

        bg = BugzillaREST(BUGZILLA_SERVER_URL)
        bugs = [bug for bug in bg.fetch()]

        self.assertEqual(len(bugs), 0)


class TestBugzillaRESTBackendCache(unittest.TestCase):
    """BugzillaREST backend tests using a cache"""

    def setUp(self):
        self.tmp_path = tempfile.mkdtemp(prefix='perceval_')

    def tearDown(self):
        shutil.rmtree(self.tmp_path)

    @httpretty.activate
    def test_fetch_from_cache(self):
        """Test whether the cache works"""

        http_requests = setup_http_server()

        # First, we fetch the topics from the server, storing them
        # in a cache
        cache = Cache(self.tmp_path)
        bg = BugzillaREST(BUGZILLA_SERVER_URL, max_bugs=2,
                          cache=cache)

        bugs = [bug for bug in bg.fetch()]
        self.assertEqual(len(http_requests), 12)

        # Now, we get the topics from the cache.
        # The contents should be the same and there won't be
        # any new request to the server
        cached_bugs = [bug for bug in bg.fetch_from_cache()]
        self.assertEqual(len(cached_bugs), len(bugs))

        self.assertEqual(len(cached_bugs), 3)

        self.assertEqual(bugs[0]['data']['id'], 1273442)
        self.assertEqual(len(bugs[0]['data']['comments']), 7)
        self.assertEqual(len(bugs[0]['data']['history']), 6)
        self.assertEqual(len(bugs[0]['data']['attachments']), 1)
        self.assertEqual(bugs[0]['origin'], BUGZILLA_SERVER_URL)
        self.assertEqual(bugs[0]['uuid'], '68494ad0072ed9e09cecb8235649a38c443326db')
        self.assertEqual(bugs[0]['updated_on'], 1465257689.0)

        self.assertEqual(bugs[1]['data']['id'], 1273439)
        self.assertEqual(len(bugs[1]['data']['comments']), 0)
        self.assertEqual(len(bugs[1]['data']['history']), 0)
        self.assertEqual(len(bugs[1]['data']['attachments']), 0)
        self.assertEqual(bugs[1]['origin'], BUGZILLA_SERVER_URL)
        self.assertEqual(bugs[1]['uuid'], 'd306162de06bc759f9bd9227fe3fd5f08aeb0dde')
        self.assertEqual(bugs[1]['updated_on'], 1465257715.0)

        self.assertEqual(bugs[2]['data']['id'], 947945)
        self.assertEqual(len(bugs[2]['data']['comments']), 0)
        self.assertEqual(len(bugs[2]['data']['history']), 0)
        self.assertEqual(len(bugs[2]['data']['attachments']), 0)
        self.assertEqual(bugs[2]['origin'], BUGZILLA_SERVER_URL)
        self.assertEqual(bugs[2]['uuid'], '33edda925351c3310fc3e12d7f18a365c365f6bd')
        self.assertEqual(bugs[2]['updated_on'], 1465257743.0)

        # No more requests were sent
        self.assertEqual(len(http_requests), 12)

    def test_fetch_from_empty_cache(self):
        """Test if there are not any bugs returned when the cache is empty"""

        cache = Cache(self.tmp_path)
        bg = BugzillaREST(BUGZILLA_SERVER_URL, cache=cache)
        cached_bugs = [bug for bug in bg.fetch_from_cache()]
        self.assertEqual(len(cached_bugs), 0)

    def test_fetch_from_non_set_cache(self):
        """Test if a error is raised when the cache was not set"""

        bg = BugzillaREST(BUGZILLA_SERVER_URL)

        with self.assertRaises(CacheError):
            _ = [bug for bug in bg.fetch_from_cache()]


class TestBugzillaRESTClient(unittest.TestCase):
    """Bugzilla REST API client tests

    These tests not check the body of the response, only if the call
    was well formed and if a response was obtained. Due to this, take
    into account that the body returned on each request might not
    match with the parameters from the request.
    """
    @httpretty.activate
    def test_init(self):
        """Test initialization"""

        client = BugzillaRESTClient(BUGZILLA_SERVER_URL)
        self.assertEqual(client.base_url, BUGZILLA_SERVER_URL)
        self.assertEqual(client.api_token, None)

    @httpretty.activate
    def test_init_auth(self):
        """Test initialization with authentication"""

        # Set up a mock HTTP server
        httpretty.register_uri(httpretty.GET,
                               BUGZILLA_LOGIN_URL,
                               body='{"token": "786-OLaWfBisMY", "id": "786"}',
                               status=200)

        client = BugzillaRESTClient(BUGZILLA_SERVER_URL,
                                    user='jsmith@example.com',
                                    password='1234')

        self.assertEqual(client.api_token, '786-OLaWfBisMY')

        # Check request params
        expected = {
                    'login' : ['jsmith@example.com'],
                    'password' : ['1234'],
                   }

        req = httpretty.last_request()

        self.assertEqual(req.method, 'GET')
        self.assertRegex(req.path, '/rest/login')
        self.assertEqual(req.querystring, expected)

    @httpretty.activate
    def test_invalid_auth(self):
        """Test whether it fails when the authentication goes wrong"""

        # Set up a mock HTTP server
        httpretty.register_uri(httpretty.GET,
                               BUGZILLA_LOGIN_URL,
                               body="401 Client Error: Authorization Required",
                               status=401)

        with self.assertRaises(BackendError):
            _ = BugzillaRESTClient(BUGZILLA_SERVER_URL,
                                   user='jsmith@example.com',
                                   password='1234')

    @httpretty.activate
    def test_auth_token_call(self):
        """Test whether the API token is included on the calls when it was set"""

        # Set up a mock HTTP server
        body = read_file('data/bugzilla_rest_bugs.json')

        # Set up a mock HTTP server
        httpretty.register_uri(httpretty.GET,
                               BUGZILLA_LOGIN_URL,
                               body='{"token": "786-OLaWfBisMY", "id": "786"}',
                               status=200)

        httpretty.register_uri(httpretty.GET,
                               BUGZILLA_BUGS_URL,
                               body=body, status=200)

        # Test API token login
        client = BugzillaRESTClient(BUGZILLA_SERVER_URL,
                                    user='jsmith@example.com',
                                    password='1234')

        self.assertEqual(client.api_token, '786-OLaWfBisMY')

        # Check whether it is included on the calls
        _ = client.bugs()

        # Check request params
        expected = {
                     'last_change_time' : ['1970-01-01T00:00:00Z'],
                     'limit' : ['500'],
                     'order' : ['changeddate'],
                     'include_fields' : ['_all'],
                     'token' :  ['786-OLaWfBisMY']
                   }

        req = httpretty.last_request()
        self.assertDictEqual(req.querystring, expected)

        # Test API token initialization
        client = BugzillaRESTClient(BUGZILLA_SERVER_URL,
                                    api_token='ABCD')
        _ = client.bugs()

        expected = {
                    'last_change_time' : ['1970-01-01T00:00:00Z'],
                    'limit' : ['500'],
                    'order' : ['changeddate'],
                    'include_fields' : ['_all'],
                    'token' :  ['ABCD']
                   }

        req = httpretty.last_request()
        self.assertDictEqual(req.querystring, expected)

    @httpretty.activate
    def test_bugs(self):
        """Test bugs API call"""

        # Set up a mock HTTP server
        body = read_file('data/bugzilla_rest_bugs.json')
        httpretty.register_uri(httpretty.GET,
                               BUGZILLA_BUGS_URL,
                               body=body, status=200)


        # Call API
        client = BugzillaRESTClient(BUGZILLA_SERVER_URL)
        response = client.bugs()

        self.assertEqual(response, body)

        # Check request params
        expected = {
                     'last_change_time' : ['1970-01-01T00:00:00Z'],
                     'limit' : ['500'],
                     'order' : ['changeddate'],
                     'include_fields' : ['_all']
                   }

        req = httpretty.last_request()

        self.assertEqual(req.method, 'GET')
        self.assertRegex(req.path, '/rest/bug')
        self.assertDictEqual(req.querystring, expected)

        # Call API with parameters
        from_date = datetime.datetime(2016, 6, 7, 0, 0, 0)

        client = BugzillaRESTClient(BUGZILLA_SERVER_URL)
        response = client.bugs(from_date=from_date, offset=100, max_bugs=5)

        self.assertEqual(response, body)

        expected = {
                    'last_change_time' : ['2016-06-07T00:00:00Z'],
                    'offset' : ['100'],
                    'limit' : ['5'],
                    'order' : ['changeddate'],
                    'include_fields' : ['_all']
                   }

        req = httpretty.last_request()

        self.assertEqual(req.method, 'GET')
        self.assertRegex(req.path, '/rest/bug')
        self.assertDictEqual(req.querystring, expected)

    @httpretty.activate
    def test_comments(self):
        """Test comments API call"""

        # Set up a mock HTTP server
        body = read_file('data/bugzilla_rest_bug_comments.json')
        httpretty.register_uri(httpretty.GET,
                               BUGZILLA_BUGS_COMMENTS_1273442_URL,
                               body=body, status=200)


        # Call API
        client = BugzillaRESTClient(BUGZILLA_SERVER_URL)
        response = client.comments('1273442')

        self.assertEqual(response, body)

        # Check request params
        expected = {}

        req = httpretty.last_request()

        self.assertEqual(req.method, 'GET')
        self.assertRegex(req.path, '/rest/bug/1273442/comment')
        self.assertDictEqual(req.querystring, expected)

    @httpretty.activate
    def test_history(self):
        """Test history API call"""

        # Set up a mock HTTP server
        body = read_file('data/bugzilla_rest_bug_history.json')
        httpretty.register_uri(httpretty.GET,
                               BUGZILLA_BUGS_HISTORY_1273442_URL,
                               body=body, status=200)


        # Call API
        client = BugzillaRESTClient(BUGZILLA_SERVER_URL)
        response = client.history('1273442')

        self.assertEqual(response, body)

        # Check request params
        expected = {}

        req = httpretty.last_request()

        self.assertEqual(req.method, 'GET')
        self.assertRegex(req.path, '/rest/bug/1273442/history')
        self.assertDictEqual(req.querystring, expected)

    @httpretty.activate
    def test_attachments(self):
        """Test attachments API call"""

        # Set up a mock HTTP server
        body = read_file('data/bugzilla_rest_bug_attachments.json')
        httpretty.register_uri(httpretty.GET,
                               BUGZILLA_BUGS_ATTACHMENTS_1273442_URL,
                               body=body, status=200)

        # Call API
        client = BugzillaRESTClient(BUGZILLA_SERVER_URL)
        response = client.attachments('1273442')

        self.assertEqual(response, body)

        # Check request params
        expected = {
            'exclude_fields' : ['data']
        }

        req = httpretty.last_request()

        self.assertEqual(req.method, 'GET')
        self.assertRegex(req.path, '/rest/bug/1273442/attachment')
        self.assertDictEqual(req.querystring, expected)


if __name__ == "__main__":
    unittest.main(warnings='ignore')
