# copyright 2003-2012 LOGILAB S.A. (Paris, FRANCE), all rights reserved.
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
"""cubicweb.server.sources.ldapusers unit and functional tests"""
from __future__ import with_statement

import os
import shutil
import time
from os.path import join, exists
import subprocess

from logilab.common.testlib import TestCase, unittest_main, mock_object, Tags

from cubicweb import AuthenticationError
from cubicweb.devtools.testlib import CubicWebTC
from cubicweb.devtools.repotest import RQLGeneratorTC
from cubicweb.devtools.httptest import get_available_port
from cubicweb.devtools import get_test_db_handler

from cubicweb.server.sources.ldapuser import GlobTrFunc, UnknownEid, RQL2LDAPFilter

CONFIG = u'user-base-dn=ou=People,dc=cubicweb,dc=test'
URL = None

def create_slapd_configuration(cls):
    global URL
    config = cls.config
    basedir = join(config.apphome, "ldapdb")
    slapdconf = join(config.apphome, "slapd.conf")
    confin = file(join(config.apphome, "slapd.conf.in")).read()
    confstream = file(slapdconf, 'w')
    confstream.write(confin % {'apphome': config.apphome})
    confstream.close()
    if exists(basedir):
        shutil.rmtree(basedir)
    os.makedirs(basedir)
    # fill ldap server with some data
    ldiffile = join(config.apphome, "ldap_test.ldif")
    config.info('Initing ldap database')
    cmdline = "/usr/sbin/slapadd -f %s -l %s -c" % (slapdconf, ldiffile)
    subprocess.call(cmdline, shell=True)

    #ldapuri = 'ldapi://' + join(basedir, "ldapi").replace('/', '%2f')
    port = get_available_port(xrange(9000, 9100))
    host = 'localhost:%s' % port
    ldapuri = 'ldap://%s' % host
    cmdline = ["/usr/sbin/slapd", "-f",  slapdconf,  "-h",  ldapuri, "-d", "0"]
    config.info('Starting slapd:', ' '.join(cmdline))
    cls.slapd_process = subprocess.Popen(cmdline)
    time.sleep(0.2)
    if cls.slapd_process.poll() is None:
        config.info('slapd started with pid %s' % cls.slapd_process.pid)
    else:
        raise EnvironmentError('Cannot start slapd with cmdline="%s" (from directory "%s")' %
                               (" ".join(cmdline), os.getcwd()))
    URL = u'ldap://%s' % host

def terminate_slapd(cls):
    config = cls.config
    if cls.slapd_process and cls.slapd_process.returncode is None:
        config.info('terminating slapd')
        if hasattr(cls.slapd_process, 'terminate'):
            cls.slapd_process.terminate()
        else:
            import os, signal
            os.kill(cls.slapd_process.pid, signal.SIGTERM)
        cls.slapd_process.wait()
        config.info('DONE')

class LDAPTestBase(CubicWebTC):
    loglevel = 'ERROR'

    @classmethod
    def setUpClass(cls):
        from cubicweb.cwctl import init_cmdline_log_threshold
        init_cmdline_log_threshold(cls.config, cls.loglevel)
        create_slapd_configuration(cls)

    @classmethod
    def tearDownClass(cls):
        terminate_slapd(cls)

class DeleteStuffFromLDAPFeedSourceTC(LDAPTestBase):
    test_db_id = 'ldap-feed'

    @classmethod
    def pre_setup_database(cls, session, config):
        session.create_entity('CWSource', name=u'ldapuser', type=u'ldapfeed', parser=u'ldapfeed',
                              url=URL, config=CONFIG)
        session.commit()
        isession = session.repo.internal_session(safe=True)
        lfsource = isession.repo.sources_by_uri['ldapuser']
        stats = lfsource.pull_data(isession, force=True, raise_on_error=True)

    def _pull(self):
        with self.session.repo.internal_session() as isession:
            lfsource = isession.repo.sources_by_uri['ldapuser']
            stats = lfsource.pull_data(isession, force=True, raise_on_error=True)
            isession.commit()

    def test_delete(self):
        """ delete syt, pull, check deactivation, repull,
        readd syt, pull, check activation
        """
        uri = self.repo.sources_by_uri['ldapuser'].urls[0]
        deletecmd = ("ldapdelete -H %s 'uid=syt,ou=People,dc=cubicweb,dc=test' "
                     "-v -x -D cn=admin,dc=cubicweb,dc=test -w'cw'" % uri)
        os.system(deletecmd)
        self._pull()
        self.assertRaises(AuthenticationError, self.repo.connect, 'syt', password='syt')
        self.assertEqual(self.execute('Any N WHERE U login "syt", '
                                      'U in_state S, S name N').rows[0][0],
                         'deactivated')
        # check that it doesn't choke
        self._pull()
        # reset the fscking ldap thing
        self.tearDownClass()
        self.setUpClass()
        self._pull()
        # still deactivated, but a warning has been emitted ...
        self.assertEqual(self.execute('Any N WHERE U login "syt", '
                                      'U in_state S, S name N').rows[0][0],
                         'deactivated')
        # test reactivating the user isn't enough to authenticate, as the native source
        # refuse to authenticate user from other sources
        os.system(deletecmd)
        self._pull()
        user = self.execute('CWUser U WHERE U login "syt"').get_entity(0, 0)
        user.cw_adapt_to('IWorkflowable').fire_transition('activate')
        self.commit()
        self.assertRaises(AuthenticationError, self.repo.connect, 'syt', password='syt')

class LDAPFeedSourceTC(LDAPTestBase):
    test_db_id = 'ldap-feed'

    @classmethod
    def pre_setup_database(cls, session, config):
        session.create_entity('CWSource', name=u'ldapuser', type=u'ldapfeed', parser=u'ldapfeed',
                              url=URL, config=CONFIG)
        session.commit()
        isession = session.repo.internal_session(safe=True)
        lfsource = isession.repo.sources_by_uri['ldapuser']
        stats = lfsource.pull_data(isession, force=True, raise_on_error=True)

    def setUp(self):
        super(LDAPFeedSourceTC, self).setUp()
        # ldap source url in the database may use a different port as the one
        # just attributed
        lfsource = self.repo.sources_by_uri['ldapuser']
        lfsource.urls = [URL]

    def assertMetadata(self, entity):
        self.assertTrue(entity.creation_date)
        self.assertTrue(entity.modification_date)

    def test_authenticate(self):
        source = self.repo.sources_by_uri['ldapuser']
        self.session.set_cnxset()
        # ensure we won't be logged against
        self.assertRaises(AuthenticationError,
                          source.authenticate, self.session, 'toto', 'toto')
        self.assertTrue(source.authenticate(self.session, 'syt', 'syt'))
        self.assertTrue(self.repo.connect('syt', password='syt'))

    def test_base(self):
        # check a known one
        rset = self.sexecute('CWUser X WHERE X login %(login)s', {'login': 'syt'})
        e = rset.get_entity(0, 0)
        self.assertEqual(e.login, 'syt')
        e.complete()
        self.assertMetadata(e)
        self.assertEqual(e.firstname, None)
        self.assertEqual(e.surname, None)
        self.assertEqual(e.in_group[0].name, 'users')
        self.assertEqual(e.owned_by[0].login, 'syt')
        self.assertEqual(e.created_by, ())
        self.assertEqual(e.primary_email[0].address, 'Sylvain Thenault')
        # email content should be indexed on the user
        rset = self.sexecute('CWUser X WHERE X has_text "thenault"')
        self.assertEqual(rset.rows, [[e.eid]])

    def test_copy_to_system_source(self):
        source = self.repo.sources_by_uri['ldapuser']
        eid = self.sexecute('CWUser X WHERE X login %(login)s', {'login': 'syt'})[0][0]
        self.sexecute('SET X cw_source S WHERE X eid %(x)s, S name "system"', {'x': eid})
        self.commit()
        source.reset_caches()
        rset = self.sexecute('CWUser X WHERE X login %(login)s', {'login': 'syt'})
        self.assertEqual(len(rset), 1)
        e = rset.get_entity(0, 0)
        self.assertEqual(e.eid, eid)
        self.assertEqual(e.cw_metainformation(), {'source': {'type': u'native',
                                                             'uri': u'system',
                                                             'use-cwuri-as-url': False},
                                                  'type': 'CWUser',
                                                  'extid': None})
        self.assertEqual(e.cw_source[0].name, 'system')
        self.assertTrue(e.creation_date)
        self.assertTrue(e.modification_date)
        source.pull_data(self.session)
        rset = self.sexecute('CWUser X WHERE X login %(login)s', {'login': 'syt'})
        self.assertEqual(len(rset), 1)
        # test some password has been set
        cu = self.session.system_sql('SELECT cw_upassword FROM cw_CWUser WHERE cw_eid=%s' % rset[0][0])
        value = str(cu.fetchall()[0][0])
        self.assertEqual(value, '{SSHA}v/8xJQP3uoaTBZz1T7Y0B3qOxRN1cj7D')
        self.assertTrue(self.repo.system_source.authenticate(
                self.session, 'syt', password='syt'))


class LDAPUserSourceTC(LDAPFeedSourceTC):
    test_db_id = 'ldap-user'
    tags = CubicWebTC.tags | Tags(('ldap'))

    @classmethod
    def pre_setup_database(cls, session, config):
        session.create_entity('CWSource', name=u'ldapuser', type=u'ldapuser',
                              url=URL, config=CONFIG)
        session.commit()
        # XXX keep it there
        session.execute('CWUser U')

    def assertMetadata(self, entity):
        self.assertEqual(entity.creation_date, None)
        self.assertEqual(entity.modification_date, None)

    def test_synchronize(self):
        source = self.repo.sources_by_uri['ldapuser']
        source.synchronize()

    def test_base(self):
        # check a known one
        rset = self.sexecute('CWUser X WHERE X login %(login)s', {'login': 'syt'})
        e = rset.get_entity(0, 0)
        self.assertEqual(e.login, 'syt')
        e.complete()
        self.assertMetadata(e)
        self.assertEqual(e.firstname, None)
        self.assertEqual(e.surname, None)
        self.assertEqual(e.in_group[0].name, 'users')
        self.assertEqual(e.owned_by[0].login, 'syt')
        self.assertEqual(e.created_by, ())
        self.assertEqual(e.primary_email[0].address, 'Sylvain Thenault')
        # email content should be indexed on the user
        rset = self.sexecute('CWUser X WHERE X has_text "thenault"')
        self.assertEqual(rset.rows, [[e.eid]])

    def test_not(self):
        eid = self.sexecute('CWUser X WHERE X login %(login)s', {'login': 'syt'})[0][0]
        rset = self.sexecute('CWUser X WHERE NOT X eid %s' % eid)
        self.assert_(rset)
        self.assert_(not eid in (r[0] for r in rset))

    def test_multiple(self):
        seid = self.sexecute('CWUser X WHERE X login %(login)s', {'login': 'syt'})[0][0]
        aeid = self.sexecute('CWUser X WHERE X login %(login)s', {'login': 'adim'})[0][0]
        rset = self.sexecute('CWUser X, Y WHERE X login %(syt)s, Y login %(adim)s',
                            {'syt': 'syt', 'adim': 'adim'})
        self.assertEqual(rset.rows, [[seid, aeid]])
        rset = self.sexecute('Any X,Y,L WHERE X login L, X login %(syt)s, Y login %(adim)s',
                            {'syt': 'syt', 'adim': 'adim'})
        self.assertEqual(rset.rows, [[seid, aeid, 'syt']])

    def test_in(self):
        seid = self.sexecute('CWUser X WHERE X login %(login)s', {'login': 'syt'})[0][0]
        aeid = self.sexecute('CWUser X WHERE X login %(login)s', {'login': 'adim'})[0][0]
        rset = self.sexecute('Any X,L ORDERBY L WHERE X login IN("%s", "%s"), X login L' % ('syt', 'adim'))
        self.assertEqual(rset.rows, [[aeid, 'adim'], [seid, 'syt']])

    def test_relations(self):
        eid = self.sexecute('CWUser X WHERE X login %(login)s', {'login': 'syt'})[0][0]
        rset = self.sexecute('Any X,E WHERE X is CWUser, X login L, X primary_email E')
        self.assert_(eid in (r[0] for r in rset))
        rset = self.sexecute('Any X,L,E WHERE X is CWUser, X login L, X primary_email E')
        self.assert_('syt' in (r[1] for r in rset))

    def test_count(self):
        nbusers = self.sexecute('Any COUNT(X) WHERE X is CWUser')[0][0]
        # just check this is a possible number
        self.assert_(nbusers > 1, nbusers)
        self.assert_(nbusers < 30, nbusers)

    def test_upper(self):
        eid = self.sexecute('CWUser X WHERE X login %(login)s', {'login': 'syt'})[0][0]
        rset = self.sexecute('Any UPPER(L) WHERE X eid %s, X login L' % eid)
        self.assertEqual(rset[0][0], 'syt'.upper())

    def test_unknown_attr(self):
        eid = self.sexecute('CWUser X WHERE X login %(login)s', {'login': 'syt'})[0][0]
        rset = self.sexecute('Any L,C,M WHERE X eid %s, X login L, '
                            'X creation_date C, X modification_date M' % eid)
        self.assertEqual(rset[0][0], 'syt')
        self.assertEqual(rset[0][1], None)
        self.assertEqual(rset[0][2], None)

    def test_sort(self):
        logins = [l for l, in self.sexecute('Any L ORDERBY L WHERE X login L')]
        self.assertEqual(logins, sorted(logins))

    def test_lower_sort(self):
        logins = [l for l, in self.sexecute('Any L ORDERBY lower(L) WHERE X login L')]
        self.assertEqual(logins, sorted(logins))

    def test_or(self):
        rset = self.sexecute('DISTINCT Any X WHERE X login %(login)s OR (X in_group G, G name "managers")',
                            {'login': 'syt'})
        self.assertEqual(len(rset), 2, rset.rows) # syt + admin

    def test_nonregr_set_owned_by(self):
        # test that when a user coming from ldap is triggering a transition
        # the related TrInfo has correct owner information
        self.sexecute('SET X in_group G WHERE X login %(syt)s, G name "managers"', {'syt': 'syt'})
        self.commit()
        syt = self.sexecute('CWUser X WHERE X login %(login)s', {'login': 'syt'}).get_entity(0, 0)
        self.assertEqual([g.name for g in syt.in_group], ['managers', 'users'])
        cnx = self.login('syt', password='syt')
        cu = cnx.cursor()
        adim = cu.execute('CWUser X WHERE X login %(login)s', {'login': 'adim'}).get_entity(0, 0)
        iworkflowable = adim.cw_adapt_to('IWorkflowable')
        iworkflowable.fire_transition('deactivate')
        try:
            cnx.commit()
            adim.cw_clear_all_caches()
            self.assertEqual(adim.in_state[0].name, 'deactivated')
            trinfo = iworkflowable.latest_trinfo()
            self.assertEqual(trinfo.owned_by[0].login, 'syt')
            # select from_state to skip the user's creation TrInfo
            rset = self.sexecute('Any U ORDERBY D DESC WHERE WF wf_info_for X,'
                                'WF creation_date D, WF from_state FS,'
                                'WF owned_by U?, X eid %(x)s',
                                {'x': adim.eid})
            self.assertEqual(rset.rows, [[syt.eid]])
        finally:
            # restore db state
            self.restore_connection()
            adim = self.sexecute('CWUser X WHERE X login %(login)s', {'login': 'adim'}).get_entity(0, 0)
            adim.cw_adapt_to('IWorkflowable').fire_transition('activate')
            self.sexecute('DELETE X in_group G WHERE X login %(syt)s, G name "managers"', {'syt': 'syt'})

    def test_same_column_names(self):
        self.sexecute('Any X, Y WHERE X copain Y, X login "comme", Y login "cochon"')

    def test_multiple_entities_from_different_sources(self):
        req = self.request()
        self.create_user(req, 'cochon')
        self.assertTrue(self.sexecute('Any X,Y WHERE X login %(syt)s, Y login "cochon"', {'syt': 'syt'}))

    def test_exists1(self):
        self.session.set_cnxset()
        self.session.create_entity('CWGroup', name=u'bougloup1')
        self.session.create_entity('CWGroup', name=u'bougloup2')
        self.sexecute('SET U in_group G WHERE G name ~= "bougloup%", U login "admin"')
        self.sexecute('SET U in_group G WHERE G name = "bougloup1", U login %(syt)s', {'syt': 'syt'})
        rset = self.sexecute('Any L,SN ORDERBY L WHERE X in_state S, '
                             'S name SN, X login L, EXISTS(X in_group G, G name ~= "bougloup%")')
        self.assertEqual(rset.rows, [['admin', 'activated'], ['syt', 'activated']])

    def test_exists2(self):
        req = self.request()
        self.create_user(req, 'comme')
        self.create_user(req, 'cochon')
        self.sexecute('SET X copain Y WHERE X login "comme", Y login "cochon"')
        rset = self.sexecute('Any GN ORDERBY GN WHERE X in_group G, G name GN, '
                             '(G name "managers" OR EXISTS(X copain T, T login in ("comme", "cochon")))')
        self.assertEqual(rset.rows, [['managers'], ['users']])

    def test_exists3(self):
        req = self.request()
        self.create_user(req, 'comme')
        self.create_user(req, 'cochon')
        self.sexecute('SET X copain Y WHERE X login "comme", Y login "cochon"')
        self.assertTrue(self.sexecute('Any X, Y WHERE X copain Y, X login "comme", Y login "cochon"'))
        self.sexecute('SET X copain Y WHERE X login %(syt)s, Y login "cochon"', {'syt': 'syt'})
        self.assertTrue(self.sexecute('Any X, Y WHERE X copain Y, X login %(syt)s, Y login "cochon"', {'syt': 'syt'}))
        rset = self.sexecute('Any GN,L WHERE X in_group G, X login L, G name GN, G name "managers" '
                             'OR EXISTS(X copain T, T login in ("comme", "cochon"))')
        self.assertEqual(sorted(rset.rows), [['managers', 'admin'], ['users', 'comme'], ['users', 'syt']])

    def test_exists4(self):
        req = self.request()
        self.create_user(req, 'comme')
        self.create_user(req, 'cochon', groups=('users', 'guests'))
        self.create_user(req, 'billy')
        self.sexecute('SET X copain Y WHERE X login "comme", Y login "cochon"')
        self.sexecute('SET X copain Y WHERE X login "cochon", Y login "cochon"')
        self.sexecute('SET X copain Y WHERE X login "comme", Y login "billy"')
        self.sexecute('SET X copain Y WHERE X login %(syt)s, Y login "billy"', {'syt': 'syt'})
        # search for group name, login where
        #   CWUser copain with "comme" or "cochon" AND same login as the copain
        # OR
        #   CWUser in_state activated AND not copain with billy
        #
        # SO we expect everybody but "comme" and "syt"
        rset= self.sexecute('Any GN,L WHERE X in_group G, X login L, G name GN, '
                           'EXISTS(X copain T, T login L, T login in ("comme", "cochon")) OR '
                           'EXISTS(X in_state S, S name "activated", NOT X copain T2, T2 login "billy")')
        all = self.sexecute('Any GN, L WHERE X in_group G, X login L, G name GN')
        all.rows.remove(['users', 'comme'])
        all.rows.remove(['users', 'syt'])
        self.assertEqual(sorted(rset.rows), sorted(all.rows))

    def test_exists5(self):
        req = self.request()
        self.create_user(req, 'comme')
        self.create_user(req, 'cochon', groups=('users', 'guests'))
        self.create_user(req, 'billy')
        self.sexecute('SET X copain Y WHERE X login "comme", Y login "cochon"')
        self.sexecute('SET X copain Y WHERE X login "cochon", Y login "cochon"')
        self.sexecute('SET X copain Y WHERE X login "comme", Y login "billy"')
        self.sexecute('SET X copain Y WHERE X login %(syt)s, Y login "cochon"', {'syt': 'syt'})
        rset= self.sexecute('Any L WHERE X login L, '
                           'EXISTS(X copain T, T login in ("comme", "cochon")) AND '
                           'NOT EXISTS(X copain T2, T2 login "billy")')
        self.assertEqual(sorted(rset.rows), [['cochon'], ['syt']])
        rset= self.sexecute('Any GN,L WHERE X in_group G, X login L, G name GN, '
                           'EXISTS(X copain T, T login in ("comme", "cochon")) AND '
                           'NOT EXISTS(X copain T2, T2 login "billy")')
        self.assertEqual(sorted(rset.rows), [['guests', 'cochon'],
                                              ['users', 'cochon'],
                                              ['users', 'syt']])

    def test_cd_restriction(self):
        rset = self.sexecute('CWUser X WHERE X creation_date > "2009-02-01"')
        # admin/anon but no ldap user since it doesn't support creation_date
        self.assertEqual(sorted(e.login for e in rset.entities()),
                          ['admin', 'anon'])

    def test_union(self):
        afeids = self.sexecute('State X')
        ueids = self.sexecute('CWUser X')
        rset = self.sexecute('(Any X WHERE X is State) UNION (Any X WHERE X is CWUser)')
        self.assertEqual(sorted(r[0] for r in rset.rows),
                          sorted(r[0] for r in afeids + ueids))

    def _init_security_test(self):
        req = self.request()
        self.create_user(req, 'iaminguestsgrouponly', groups=('guests',))
        cnx = self.login('iaminguestsgrouponly')
        return cnx.cursor()

    def test_security1(self):
        cu = self._init_security_test()
        rset = cu.execute('CWUser X WHERE X login %(login)s', {'login': 'syt'})
        self.assertEqual(rset.rows, [])
        rset = cu.execute('Any X WHERE X login "iaminguestsgrouponly"')
        self.assertEqual(len(rset.rows), 1)

    def test_security2(self):
        cu = self._init_security_test()
        rset = cu.execute('Any X WHERE X has_text %(syt)s', {'syt': 'syt'})
        self.assertEqual(rset.rows, [])
        rset = cu.execute('Any X WHERE X has_text "iaminguestsgrouponly"')
        self.assertEqual(len(rset.rows), 1)

    def test_security3(self):
        cu = self._init_security_test()
        rset = cu.execute('Any F WHERE X has_text %(syt)s, X firstname F', {'syt': 'syt'})
        self.assertEqual(rset.rows, [])
        rset = cu.execute('Any F WHERE X has_text "iaminguestsgrouponly", X firstname F')
        self.assertEqual(rset.rows, [[None]])

    def test_nonregr1(self):
        self.sexecute('Any X,AA ORDERBY AA DESC WHERE E eid %(x)s, E owned_by X, '
                     'X modification_date AA',
                     {'x': self.session.user.eid})

    def test_nonregr2(self):
        self.sexecute('Any X,L,AA WHERE E eid %(x)s, E owned_by X, '
                     'X login L, X modification_date AA',
                     {'x': self.session.user.eid})

    def test_nonregr3(self):
        self.sexecute('Any X,AA ORDERBY AA DESC WHERE E eid %(x)s, '
                     'X modification_date AA',
                     {'x': self.session.user.eid})

    def test_nonregr4(self):
        emaileid = self.sexecute('INSERT EmailAddress X: X address "toto@logilab.org"')[0][0]
        self.sexecute('Any X,AA WHERE X use_email Y, Y eid %(x)s, X modification_date AA',
                     {'x': emaileid})

    def test_nonregr5(self):
        # original jpl query:
        # Any X, NOW - CD, P WHERE P is Project, U interested_in P, U is CWUser,
        # U login "sthenault", X concerns P, X creation_date CD ORDERBY CD DESC LIMIT 5
        rql = ('Any X, NOW - CD, P ORDERBY CD DESC LIMIT 5 WHERE P bookmarked_by U, '
               'U login "%s", P is X, X creation_date CD') % self.session.user.login
        self.sexecute(rql, )#{'x': })

    def test_nonregr6(self):
        self.sexecute('Any B,U,UL GROUPBY B,U,UL WHERE B created_by U?, B is File '
                     'WITH U,UL BEING (Any U,UL WHERE ME eid %(x)s, (EXISTS(U identity ME) '
                     'OR (EXISTS(U in_group G, G name IN("managers", "staff")))) '
                     'OR (EXISTS(U in_group H, ME in_group H, NOT H name "users")), U login UL, U is CWUser)',
                     {'x': self.session.user.eid})

class GlobTrFuncTC(TestCase):

    def test_count(self):
        trfunc = GlobTrFunc('count', 0)
        res = trfunc.apply([[1], [2], [3], [4]])
        self.assertEqual(res, [[4]])
        trfunc = GlobTrFunc('count', 1)
        res = trfunc.apply([[1, 2], [2, 4], [3, 6], [1, 5]])
        self.assertEqual(res, [[1, 2], [2, 1], [3, 1]])

    def test_sum(self):
        trfunc = GlobTrFunc('sum', 0)
        res = trfunc.apply([[1], [2], [3], [4]])
        self.assertEqual(res, [[10]])
        trfunc = GlobTrFunc('sum', 1)
        res = trfunc.apply([[1, 2], [2, 4], [3, 6], [1, 5]])
        self.assertEqual(res, [[1, 7], [2, 4], [3, 6]])

    def test_min(self):
        trfunc = GlobTrFunc('min', 0)
        res = trfunc.apply([[1], [2], [3], [4]])
        self.assertEqual(res, [[1]])
        trfunc = GlobTrFunc('min', 1)
        res = trfunc.apply([[1, 2], [2, 4], [3, 6], [1, 5]])
        self.assertEqual(res, [[1, 2], [2, 4], [3, 6]])

    def test_max(self):
        trfunc = GlobTrFunc('max', 0)
        res = trfunc.apply([[1], [2], [3], [4]])
        self.assertEqual(res, [[4]])
        trfunc = GlobTrFunc('max', 1)
        res = trfunc.apply([[1, 2], [2, 4], [3, 6], [1, 5]])
        self.assertEqual(res, [[1, 5], [2, 4], [3, 6]])


class RQL2LDAPFilterTC(RQLGeneratorTC):

    tags = RQLGeneratorTC.tags | Tags(('ldap'))

    @property
    def schema(self):
        """return the application schema"""
        return self._schema

    def setUp(self):
        self.handler = get_test_db_handler(LDAPUserSourceTC.config)
        self.handler.build_db_cache('ldap-user', LDAPUserSourceTC.pre_setup_database)
        self.handler.restore_database('ldap-user')
        self._repo = repo = self.handler.get_repo()
        self._schema = repo.schema
        super(RQL2LDAPFilterTC, self).setUp()
        ldapsource = repo.sources[-1]
        self.cnxset = repo._get_cnxset()
        session = mock_object(cnxset=self.cnxset)
        self.o = RQL2LDAPFilter(ldapsource, session)
        self.ldapclasses = ''.join(ldapsource.base_filters)

    def tearDown(self):
        self._repo.turn_repo_off()
        super(RQL2LDAPFilterTC, self).tearDown()

    def test_base(self):
        rqlst = self._prepare('CWUser X WHERE X login "toto"').children[0]
        self.assertEqual(self.o.generate(rqlst, 'X')[1],
                          '(&%s(uid=toto))' % self.ldapclasses)

    def test_kwargs(self):
        rqlst = self._prepare('CWUser X WHERE X login %(x)s').children[0]
        self.o._args = {'x': "toto"}
        self.assertEqual(self.o.generate(rqlst, 'X')[1],
                          '(&%s(uid=toto))' % self.ldapclasses)

    def test_get_attr(self):
        rqlst = self._prepare('Any X WHERE E firstname X, E eid 12').children[0]
        self.assertRaises(UnknownEid, self.o.generate, rqlst, 'E')


if __name__ == '__main__':
    unittest_main()
