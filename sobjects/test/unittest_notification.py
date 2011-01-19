# -*- coding: iso-8859-1 -*-
# copyright 2003-2010 LOGILAB S.A. (Paris, FRANCE), all rights reserved.
# contact http://www.logilab.fr/ -- mailto:contact@logilab.fr
#
# This file is part of CubicWeb.
#
# CubicWeb is free software: you can redistribute it and/or modify it under the
# terms of the GNU Lesser General Public License as published by the Free
# Software Foundation, either version 2.1 of the License, or (at your option)
# any later version.
#
# CubicWeb is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for more
# details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with CubicWeb.  If not, see <http://www.gnu.org/licenses/>.
"""

"""
from socket import gethostname

from logilab.common.testlib import unittest_main, TestCase
from cubicweb.devtools.testlib import CubicWebTC, MAILBOX

from cubicweb.mail import construct_message_id, parse_message_id

class MessageIdTC(TestCase):
    def test_base(self):
        msgid1 = construct_message_id('testapp', 21)
        msgid2 = construct_message_id('testapp', 21)
        self.failIfEqual(msgid1, msgid2)
        self.failIf('&' in msgid1)
        self.failIf('=' in msgid1)
        self.failIf('/' in msgid1)
        self.failIf('+' in msgid1)
        values = parse_message_id(msgid1, 'testapp')
        self.failUnless(values)
        # parse_message_id should work with or without surrounding <>
        self.failUnlessEqual(values, parse_message_id(msgid1[1:-1], 'testapp'))
        self.failUnlessEqual(values['eid'], '21')
        self.failUnless('timestamp' in values)
        self.failUnlessEqual(parse_message_id(msgid1[1:-1], 'anotherapp'), None)

    def test_notimestamp(self):
        msgid1 = construct_message_id('testapp', 21, False)
        msgid2 = construct_message_id('testapp', 21, False)
        values = parse_message_id(msgid1, 'testapp')
        self.failUnlessEqual(values, {'eid': '21'})

    def test_parse_message_doesnt_raise(self):
        self.failUnlessEqual(parse_message_id('oijioj@bla.bla', 'tesapp'), None)
        self.failUnlessEqual(parse_message_id('oijioj@bla', 'tesapp'), None)
        self.failUnlessEqual(parse_message_id('oijioj', 'tesapp'), None)


    def test_nonregr_empty_message_id(self):
        for eid in (1, 12, 123, 1234):
            msgid1 = construct_message_id('testapp', eid, 12)
            self.assertNotEqual(msgid1, '<@testapp.%s>' % gethostname())


class RecipientsFinderTC(CubicWebTC):
    def test(self):
        urset = self.execute('CWUser X WHERE X login "admin"')
        self.execute('INSERT EmailAddress X: X address "admin@logilab.fr", U primary_email X '
                     'WHERE U eid %(x)s', {'x': urset[0][0]})
        self.execute('INSERT CWProperty X: X pkey "ui.language", X value "fr", X for_user U '
                     'WHERE U eid %(x)s', {'x': urset[0][0]})
        self.commit() # commit so that admin get its properties updated
        finder = self.vreg['components'].select('recipients_finder',
                                                self.request(), rset=urset)
        self.set_option('default-recipients-mode', 'none')
        self.assertEqual(finder.recipients(), [])
        self.set_option('default-recipients-mode', 'users')
        self.assertEqual(finder.recipients(), [(u'admin@logilab.fr', 'fr')])
        self.set_option('default-recipients-mode', 'default-dest-addrs')
        self.set_option('default-dest-addrs', 'abcd@logilab.fr, efgh@logilab.fr')
        self.assertEqual(finder.recipients(), [('abcd@logilab.fr', 'en'), ('efgh@logilab.fr', 'en')])


class StatusChangeViewsTC(CubicWebTC):

    def test_status_change_view(self):
        req = self.request()
        u = self.create_user('toto', req=req)
        u.cw_adapt_to('IWorkflowable').fire_transition('deactivate', comment=u'yeah')
        self.failIf(MAILBOX)
        self.commit()
        self.assertEqual(len(MAILBOX), 1)
        email = MAILBOX[0]
        self.assertEqual(email.content,
                          '''
admin changed status from <activated> to <deactivated> for entity
'toto'

yeah

url: http://testing.fr/cubicweb/cwuser/toto
''')
        self.assertEqual(email.subject, 'status changed cwuser #%s (admin)' % u.eid)

if __name__ == '__main__':
    unittest_main()
