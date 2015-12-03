# coding: utf-8
# copyright 2003-2015 LOGILAB S.A. (Paris, FRANCE), all rights reserved.
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
"""unittest for cubicweb.dataimport.pgstore"""

import datetime as DT

from logilab.common.testlib import TestCase, unittest_main

from cubicweb.dataimport import pgstore
from cubicweb.devtools import testlib


class CreateCopyFromBufferTC(TestCase):

    # test converters

    def test_convert_none(self):
        cnvt = pgstore._copyfrom_buffer_convert_None
        self.assertEqual('NULL', cnvt(None))

    def test_convert_number(self):
        cnvt = pgstore._copyfrom_buffer_convert_number
        self.assertEqual('42', cnvt(42))
        self.assertEqual('42', cnvt(42L))
        self.assertEqual('42.42', cnvt(42.42))

    def test_convert_string(self):
        cnvt = pgstore._copyfrom_buffer_convert_string
        # simple
        self.assertEqual('babar', cnvt('babar'))
        # unicode
        self.assertEqual('\xc3\xa9l\xc3\xa9phant', cnvt(u'éléphant'))
        self.assertEqual('\xe9l\xe9phant', cnvt(u'éléphant', encoding='latin1'))
        # escaping
        self.assertEqual('babar\\tceleste\\n', cnvt('babar\tceleste\n'))
        self.assertEqual(r'C:\\new\tC:\\test', cnvt('C:\\new\tC:\\test'))

    def test_convert_date(self):
        cnvt = pgstore._copyfrom_buffer_convert_date
        self.assertEqual('0666-01-13', cnvt(DT.date(666, 1, 13)))

    def test_convert_time(self):
        cnvt = pgstore._copyfrom_buffer_convert_time
        self.assertEqual('06:06:06.000100', cnvt(DT.time(6, 6, 6, 100)))

    def test_convert_datetime(self):
        cnvt = pgstore._copyfrom_buffer_convert_datetime
        self.assertEqual('0666-06-13 06:06:06.000000', cnvt(DT.datetime(666, 6, 13, 6, 6, 6)))

    # test buffer
    def test_create_copyfrom_buffer_tuple(self):
        data = ((42, 42L, 42.42, u'éléphant', DT.date(666, 1, 13), DT.time(6, 6, 6),
                 DT.datetime(666, 6, 13, 6, 6, 6)),
                (6, 6L, 6.6, u'babar', DT.date(2014, 1, 14), DT.time(4, 2, 1),
                 DT.datetime(2014, 1, 1, 0, 0, 0)))
        results = pgstore._create_copyfrom_buffer(data)
        # all columns
        expected = '''42\t42\t42.42\téléphant\t0666-01-13\t06:06:06.000000\t0666-06-13 06:06:06.000000
6\t6\t6.6\tbabar\t2014-01-14\t04:02:01.000000\t2014-01-01 00:00:00.000000'''
        self.assertMultiLineEqual(expected, results.getvalue())
        # selected columns
        results = pgstore._create_copyfrom_buffer(data, columns=(1, 3, 6))
        expected = '''42\téléphant\t0666-06-13 06:06:06.000000
6\tbabar\t2014-01-01 00:00:00.000000'''
        self.assertMultiLineEqual(expected, results.getvalue())

    def test_create_copyfrom_buffer_dict(self):
        data = (dict(integer=42, double=42.42, text=u'éléphant',
                     date=DT.datetime(666, 6, 13, 6, 6, 6)),
                dict(integer=6, double=6.6, text=u'babar',
                     date=DT.datetime(2014, 1, 1, 0, 0, 0)))
        results = pgstore._create_copyfrom_buffer(data, ('integer', 'text'))
        expected = '''42\téléphant\n6\tbabar'''
        self.assertMultiLineEqual(expected, results.getvalue())


class SQLGenObjectStoreTC(testlib.CubicWebTC):

    def test_prepare_insert_entity(self):
        with self.admin_access.repo_cnx() as cnx:
            store = pgstore.SQLGenObjectStore(cnx)
            eid = store.prepare_insert_entity('CWUser', login=u'toto',
                                              upassword=u'pwd')
            self.assertIsNotNone(eid)


if __name__ == '__main__':
    unittest_main()
