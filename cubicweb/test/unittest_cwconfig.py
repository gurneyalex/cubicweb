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
"""cubicweb.cwconfig unit tests"""

import contextlib
import compileall
import functools
import sys
import os
import pkgutil
from os.path import dirname, join, abspath
from pkg_resources import EntryPoint, Distribution
import unittest

from mock import patch
from six import PY3

from logilab.common.modutils import cleanup_sys_modules
from logilab.common.changelog import Version

from cubicweb.devtools import ApptestConfiguration
from cubicweb.devtools.testlib import BaseTestCase, TemporaryDirectory
from cubicweb.cwconfig import (
    CubicWebConfiguration, _find_prefix, _expand_modname)


def unabsolutize(path):
    parts = path.split(os.sep)
    for i, part in reversed(tuple(enumerate(parts))):
        if part.startswith('cubicweb_'):
            return os.sep.join([part[len('cubicweb_'):]] + parts[i+1:])
        if part.startswith('cubicweb') or part == 'legacy_cubes':
            return os.sep.join(parts[i+1:])
    raise Exception('duh? %s' % path)


def templibdir(func):
    """create a temporary directory and insert it in sys.path"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with TemporaryDirectory() as libdir:
            sys.path.insert(0, libdir)
            try:
                args = args + (libdir,)
                return func(*args, **kwargs)
            finally:
                sys.path.remove(libdir)
    return wrapper


def create_filepath(filepath):
    filedir = dirname(filepath)
    if not os.path.exists(filedir):
        os.makedirs(filedir)
    with open(filepath, 'a'):
        pass


@contextlib.contextmanager
def temp_config(appid, instance_dir, cubes_dir, cubes):
    """context manager that create a config object with specified appid,
    instance_dir, cubes_dir and cubes"""
    cls = CubicWebConfiguration
    old = (cls._INSTANCES_DIR, cls.CUBES_DIR, cls.CUBES_PATH,
           sys.path[:], sys.meta_path[:])
    old_modules = set(sys.modules)
    try:
        cls._INSTANCES_DIR, cls.CUBES_DIR, cls.CUBES_PATH = (
            instance_dir, cubes_dir, [])
        config = cls(appid)
        config._cubes = cubes
        config.adjust_sys_path()
        yield config
    finally:
        (cls._INSTANCES_DIR, cls.CUBES_DIR, cls.CUBES_PATH,
         sys.path[:], sys.meta_path[:]) = old
        for module in set(sys.modules) - old_modules:
            del sys.modules[module]


class CubicWebConfigurationTC(BaseTestCase):

    @classmethod
    def setUpClass(cls):
        sys.path.append(cls.datapath('libpython'))

    @classmethod
    def tearDownClass(cls):
        sys.path.remove(cls.datapath('libpython'))

    def setUp(self):
        self.config = ApptestConfiguration('data', __file__)
        self.config._cubes = ('email', 'file')

    def tearDown(self):
        ApptestConfiguration.CUBES_PATH = []

    def iter_entry_points(group, name):
        """Mock pkg_resources.iter_entry_points to yield EntryPoint from
        packages found in test/data/libpython even though these are not
        installed.
        """
        libpython = CubicWebConfigurationTC.datapath('libpython')
        prefix = 'cubicweb_'
        for pkgname in os.listdir(libpython):
            if not pkgname.startswith(prefix):
                continue
            location = join(libpython, pkgname)
            yield EntryPoint(pkgname[len(prefix):], pkgname,
                             dist=Distribution(location))

    @patch('pkg_resources.iter_entry_points', side_effect=iter_entry_points)
    def test_available_cubes(self, mock_iter_entry_points):
        expected_cubes = [
            'card', 'comment', 'cubicweb_comment', 'cubicweb_email', 'file',
            'cubicweb_file', 'cubicweb_forge', 'localperms',
            'cubicweb_mycube', 'tag',
        ]
        self._test_available_cubes(expected_cubes)
        mock_iter_entry_points.assert_called_once_with(
            group='cubicweb.cubes', name=None)

    def _test_available_cubes(self, expected_cubes):
        self.assertEqual(self.config.available_cubes(), expected_cubes)

    def test_reorder_cubes(self):
        # forge depends on email and file and comment
        # email depends on file
        self.assertEqual(self.config.reorder_cubes(['file', 'email', 'forge']),
                          ('forge', 'email', 'file'))
        self.assertEqual(self.config.reorder_cubes(['email', 'file', 'forge']),
                          ('forge', 'email', 'file'))
        self.assertEqual(self.config.reorder_cubes(['email', 'forge', 'file']),
                          ('forge', 'email', 'file'))
        self.assertEqual(self.config.reorder_cubes(['file', 'forge', 'email']),
                          ('forge', 'email', 'file'))
        self.assertEqual(self.config.reorder_cubes(['forge', 'file', 'email']),
                          ('forge', 'email', 'file'))
        self.assertEqual(self.config.reorder_cubes(('forge', 'email', 'file')),
                          ('forge', 'email', 'file'))

    def test_reorder_cubes_recommends(self):
        from cubicweb_comment import __pkginfo__ as comment_pkginfo
        self._test_reorder_cubes_recommends(comment_pkginfo)

    def _test_reorder_cubes_recommends(self, comment_pkginfo):
        comment_pkginfo.__recommends_cubes__ = {'file': None}
        try:
            # email recommends comment
            # comment recommends file
            self.assertEqual(self.config.reorder_cubes(('forge', 'email', 'file', 'comment')),
                              ('forge', 'email', 'comment', 'file'))
            self.assertEqual(self.config.reorder_cubes(('forge', 'email', 'comment', 'file')),
                              ('forge', 'email', 'comment', 'file'))
            self.assertEqual(self.config.reorder_cubes(('forge', 'comment', 'email', 'file')),
                              ('forge', 'email', 'comment', 'file'))
            self.assertEqual(self.config.reorder_cubes(('comment', 'forge', 'email', 'file')),
                              ('forge', 'email', 'comment', 'file'))
        finally:
            comment_pkginfo.__recommends_cubes__ = {}

    def test_expand_cubes(self):
        self.assertEqual(self.config.expand_cubes(('email', 'comment')),
                          ['email', 'comment', 'file'])


    def test_init_cubes_ignore_pyramid_cube(self):
        warning_msg = 'cubicweb-pyramid got integrated into CubicWeb'
        with self.assertLogs('cubicweb.configuration', level='WARNING') as cm:
            self.config.init_cubes(['pyramid', 'card'])
        self.assertIn(warning_msg, cm.output[0])
        self.assertNotIn('pyramid', self.config._cubes)

class CubicWebConfigurationWithLegacyCubesTC(CubicWebConfigurationTC):

    @classmethod
    def setUpClass(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        self.custom_cubes_dir = self.datapath('legacy_cubes')
        cleanup_sys_modules([self.custom_cubes_dir, ApptestConfiguration.CUBES_DIR])
        super(CubicWebConfigurationWithLegacyCubesTC, self).setUp()
        self.config.__class__.CUBES_PATH = [self.custom_cubes_dir]
        self.config.adjust_sys_path()

    def tearDown(self):
        ApptestConfiguration.CUBES_PATH = []

    def test_available_cubes(self):
        expected_cubes = sorted(set([
            # local cubes
            'comment', 'email', 'file', 'forge', 'mycube',
            # test dependencies
            'card', 'file', 'localperms', 'tag',
        ]))
        self._test_available_cubes(expected_cubes)

    def test_reorder_cubes_recommends(self):
        from cubes.comment import __pkginfo__ as comment_pkginfo
        self._test_reorder_cubes_recommends(comment_pkginfo)

    def test_cubes_path(self):
        # make sure we don't import the email cube, but the stdlib email package
        import email
        self.assertNotEqual(dirname(email.__file__), self.config.CUBES_DIR)
        self.config.__class__.CUBES_PATH = [self.custom_cubes_dir]
        self.assertEqual(self.config.cubes_search_path(),
                          [self.custom_cubes_dir, self.config.CUBES_DIR])
        self.config.__class__.CUBES_PATH = [self.custom_cubes_dir,
                                            self.config.CUBES_DIR, 'unexistant']
        # filter out unexistant and duplicates
        self.assertEqual(self.config.cubes_search_path(),
                          [self.custom_cubes_dir,
                           self.config.CUBES_DIR])
        self.assertIn('mycube', self.config.available_cubes())
        # test cubes python path
        self.config.adjust_sys_path()
        import cubes
        self.assertEqual(cubes.__path__, self.config.cubes_search_path())
        # this import should succeed once path is adjusted
        from cubes import mycube
        self.assertEqual(mycube.__path__, [join(self.custom_cubes_dir, 'mycube')])
        # file cube should be overriden by the one found in data/cubes
        if sys.modules.pop('cubes.file', None) and PY3:
            del cubes.file
        from cubes import file
        self.assertEqual(file.__path__, [join(self.custom_cubes_dir, 'file')])

    def test_config_value_from_environment(self):
        self.assertIsNone(self.config['base-url'])
        os.environ['CW_BASE_URL'] = 'https://www.cubicweb.org'
        try:
            self.assertEqual(self.config['base-url'],
                             'https://www.cubicweb.org')
        finally:
            del os.environ['CW_BASE_URL']


class FindPrefixTC(unittest.TestCase):

    def make_dirs(self, basedir, *args):
        path = join(basedir, *args)
        if not os.path.exists(path):
            os.makedirs(path)
        return path

    def make_file(self, basedir, *args):
        self.make_dirs(basedir, *args[:-1])
        file_path = join(basedir, *args)
        with open(file_path, 'w') as f:
            f.write('""" None """')
        return file_path

    def test_samedir(self):
        with TemporaryDirectory() as prefix:
            self.make_dirs(prefix, 'share', 'cubicweb')
            self.assertEqual(_find_prefix(prefix), prefix)

    def test_samedir_filepath(self):
        with TemporaryDirectory() as prefix:
            self.make_dirs(prefix, 'share', 'cubicweb')
            file_path = self.make_file(prefix, 'bob.py')
            self.assertEqual(_find_prefix(file_path), prefix)

    def test_dir_inside_prefix(self):
        with TemporaryDirectory() as prefix:
            self.make_dirs(prefix, 'share', 'cubicweb')
            dir_path = self.make_dirs(prefix, 'bob')
            self.assertEqual(_find_prefix(dir_path), prefix)

    def test_file_in_dir_inside_prefix(self):
        with TemporaryDirectory() as prefix:
            self.make_dirs(prefix, 'share', 'cubicweb')
            file_path = self.make_file(prefix, 'bob', 'toto.py')
            self.assertEqual(_find_prefix(file_path), prefix)

    def test_file_in_deeper_dir_inside_prefix(self):
        with TemporaryDirectory() as prefix:
            self.make_dirs(prefix, 'share', 'cubicweb')
            file_path = self.make_file(prefix, 'bob', 'pyves', 'alain',
                                       'adim', 'syt', 'toto.py')
            self.assertEqual(_find_prefix(file_path), prefix)

    def test_multiple_candidate_prefix(self):
        with TemporaryDirectory() as tempdir:
            self.make_dirs(tempdir, 'share', 'cubicweb')
            prefix = self.make_dirs(tempdir, 'bob')
            self.make_dirs(prefix, 'share', 'cubicweb')
            file_path = self.make_file(prefix, 'pyves', 'alain',
                                       'adim', 'syt', 'toto.py')
            self.assertEqual(_find_prefix(file_path), prefix)

    def test_sister_candidate_prefix(self):
        with TemporaryDirectory() as prefix:
            self.make_dirs(prefix, 'share', 'cubicweb')
            self.make_dirs(prefix, 'bob', 'share', 'cubicweb')
            file_path = self.make_file(prefix, 'bell', 'toto.py')
            self.assertEqual(_find_prefix(file_path), prefix)

    def test_multiple_parent_candidate_prefix(self):
        with TemporaryDirectory() as tempdir:
            self.make_dirs(tempdir, 'share', 'cubicweb')
            prefix = self.make_dirs(tempdir, 'share', 'cubicweb', 'bob')
            self.make_dirs(tempdir, 'share', 'cubicweb', 'bob', 'share',
                           'cubicweb')
            file_path = self.make_file(tempdir, 'share', 'cubicweb', 'bob',
                                       'pyves', 'alain', 'adim', 'syt',
                                       'toto.py')
            self.assertEqual(_find_prefix(file_path), prefix)

    def test_upper_candidate_prefix(self):
        with TemporaryDirectory() as prefix:
            self.make_dirs(prefix, 'share', 'cubicweb')
            self.make_dirs(prefix, 'bell', 'bob',  'share', 'cubicweb')
            file_path = self.make_file(prefix, 'bell', 'toto.py')
            self.assertEqual(_find_prefix(file_path), prefix)

    def test_no_prefix(self):
        with TemporaryDirectory() as prefix:
            self.assertEqual(_find_prefix(prefix), sys.prefix)

    def test_virtualenv(self):
        venv = os.environ.get('VIRTUAL_ENV')
        try:
            with TemporaryDirectory() as prefix:
                os.environ['VIRTUAL_ENV'] = prefix
                self.make_dirs(prefix, 'share', 'cubicweb')
                self.assertEqual(_find_prefix(), prefix)
        finally:
            if venv:
                os.environ['VIRTUAL_ENV'] = venv


class ModnamesTC(unittest.TestCase):

    @templibdir
    def test_expand_modnames(self, libdir):
        tempdir = join(libdir, 'lib')
        filepaths = [
            join(tempdir, '__init__.py'),
            join(tempdir, 'a.py'),
            join(tempdir, 'b.py'),
            join(tempdir, 'c.py'),
            join(tempdir, 'b', '__init__.py'),
            join(tempdir, 'b', 'a.py'),
            join(tempdir, 'b', 'c.py'),
            join(tempdir, 'b', 'd', '__init__.py'),
            join(tempdir, 'e', 'e.py'),
        ]
        for filepath in filepaths:
            create_filepath(filepath)
        # not importable
        self.assertEqual(list(_expand_modname('isnotimportable')), [])
        # not a python package
        self.assertEqual(list(_expand_modname('lib.e')), [])
        self.assertEqual(list(_expand_modname('lib.a')), [
            ('lib.a', join(tempdir, 'a.py')),
        ])
        # lib.b.d (subpackage) not to be imported
        self.assertEqual(list(_expand_modname('lib.b')), [
            ('lib.b', join(tempdir, 'b', '__init__.py')),
            ('lib.b.a', join(tempdir, 'b', 'a.py')),
            ('lib.b.c', join(tempdir, 'b', 'c.py')),
        ])
        self.assertEqual(list(_expand_modname('lib')), [
            ('lib', join(tempdir, '__init__.py')),
            ('lib.a', join(tempdir, 'a.py')),
            ('lib.c', join(tempdir, 'c.py')),
        ])
        for source in (
            join(tempdir, 'c.py'),
            join(tempdir, 'b', 'c.py'),
        ):
            if not PY3:
                # ensure pyc file exists.
                # Doesn't required for PY3 since it create __pycache__
                # directory and will not import if source file doesn't
                # exists.
                compileall.compile_file(source, force=True)
                self.assertTrue(os.path.exists(source + 'c'))
            # remove source file
            os.remove(source)
        self.assertEqual(list(_expand_modname('lib.c')), [])
        self.assertEqual(list(_expand_modname('lib.b')), [
            ('lib.b', join(tempdir, 'b', '__init__.py')),
            ('lib.b.a', join(tempdir, 'b', 'a.py')),
        ])
        self.assertEqual(list(_expand_modname('lib')), [
            ('lib', join(tempdir, '__init__.py')),
            ('lib.a', join(tempdir, 'a.py')),
        ])

    @templibdir
    def test_schema_modnames(self, libdir):
        for filepath in (
            join(libdir, 'schema.py'),
            join(libdir, 'cubicweb_foo', '__init__.py'),
            join(libdir, 'cubicweb_foo', 'schema', '__init__.py'),
            join(libdir, 'cubicweb_foo', 'schema', 'a.py'),
            join(libdir, 'cubicweb_foo', 'schema', 'b.py'),
            join(libdir, 'cubes', '__init__.py'),
            join(libdir, 'cubes', 'bar', '__init__.py'),
            join(libdir, 'cubes', 'bar', 'schema.py'),
            join(libdir, '_instance_dir', 'data1', 'schema.py'),
            join(libdir, '_instance_dir', 'data2', 'noschema.py'),
        ):
            create_filepath(filepath)
        expected = [
            ('cubicweb', 'cubicweb.schemas.bootstrap'),
            ('cubicweb', 'cubicweb.schemas.base'),
            ('cubicweb', 'cubicweb.schemas.workflow'),
            ('cubicweb', 'cubicweb.schemas.Bookmark'),
            ('bar', 'cubes.bar.schema'),
            ('foo', 'cubes.foo.schema'),
            ('foo', 'cubes.foo.schema.a'),
            ('foo', 'cubes.foo.schema.b'),
        ]
        # app has schema file
        instance_dir, cubes_dir = (
            join(libdir, '_instance_dir'), join(libdir, 'cubes'))
        with temp_config('data1', instance_dir, cubes_dir,
                         ('foo', 'bar')) as config:
            self.assertEqual(pkgutil.find_loader('schema').get_filename(),
                             join(libdir, '_instance_dir',
                                  'data1', 'schema.py'))
            self.assertEqual(config.schema_modnames(),
                             expected + [('data', 'schema')])
        # app doesn't have schema file
        with temp_config('data2', instance_dir, cubes_dir,
                         ('foo', 'bar')) as config:
            self.assertEqual(pkgutil.find_loader('schema').get_filename(),
                             join(libdir, 'schema.py'))
            self.assertEqual(config.schema_modnames(), expected)

    @templibdir
    def test_appobjects_modnames(self, libdir):
        for filepath in (
            join(libdir, 'entities.py'),
            join(libdir, 'cubicweb_foo', '__init__.py'),
            join(libdir, 'cubicweb_foo', 'entities', '__init__.py'),
            join(libdir, 'cubicweb_foo', 'entities', 'a.py'),
            join(libdir, 'cubicweb_foo', 'hooks.py'),
            join(libdir, 'cubes', '__init__.py'),
            join(libdir, 'cubes', 'bar', '__init__.py'),
            join(libdir, 'cubes', 'bar', 'hooks.py'),
            join(libdir, '_instance_dir', 'data1', 'entities.py'),
            join(libdir, '_instance_dir', 'data2', 'hooks.py'),
        ):
            create_filepath(filepath)
        instance_dir, cubes_dir = (
            join(libdir, '_instance_dir'), join(libdir, 'cubes'))
        expected = [
            'cubicweb.entities',
            'cubicweb.entities.adapters',
            'cubicweb.entities.authobjs',
            'cubicweb.entities.lib',
            'cubicweb.entities.schemaobjs',
            'cubicweb.entities.sources',
            'cubicweb.entities.wfobjs',
            'cubes.bar.hooks',
            'cubes.foo.entities',
            'cubes.foo.entities.a',
            'cubes.foo.hooks',
        ]
        # data1 has entities
        with temp_config('data1', instance_dir, cubes_dir,
                         ('foo', 'bar')) as config:
            config.cube_appobject_path = set(['entities', 'hooks'])
            self.assertEqual(config.appobjects_modnames(),
                             expected + ['entities'])
        # data2 has hooks
        with temp_config('data2', instance_dir, cubes_dir,
                         ('foo', 'bar')) as config:
            config.cube_appobject_path = set(['entities', 'hooks'])
            self.assertEqual(config.appobjects_modnames(),
                             expected + ['hooks'])


if __name__ == '__main__':
    unittest.main()
