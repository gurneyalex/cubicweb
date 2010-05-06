# -*- coding: utf-8 -*-
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
"""unit/functional tests for cubicweb.server.hook

"""

from logilab.common.testlib import TestCase, unittest_main, mock_object


from cubicweb.devtools import TestServerConfiguration
from cubicweb.devtools.testlib import CubicWebTC
from cubicweb.selectors import implements
from cubicweb.server import hook
from cubicweb.hooks import integrity, syncschema


def clean_session_ops(func):
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        finally:
            self.session.pending_operations[:] = []
    return wrapper

class OperationsTC(CubicWebTC):

    def setUp(self):
        CubicWebTC.setUp(self)
        self.hm = self.repo.hm

    @clean_session_ops
    def test_late_operation(self):
        session = self.session
        l1 = hook.LateOperation(session)
        l2 = hook.LateOperation(session)
        l3 = hook.Operation(session)
        self.assertEquals(session.pending_operations, [l3, l1, l2])

    @clean_session_ops
    def test_single_last_operation(self):
        session = self.session
        l0 = hook.SingleLastOperation(session)
        l1 = hook.LateOperation(session)
        l2 = hook.LateOperation(session)
        l3 = hook.Operation(session)
        self.assertEquals(session.pending_operations, [l3, l1, l2, l0])
        l4 = hook.SingleLastOperation(session)
        self.assertEquals(session.pending_operations, [l3, l1, l2, l4])

    @clean_session_ops
    def test_global_operation_order(self):
        session = self.session
        op1 = integrity._DelayedDeleteOp(session)
        op2 = syncschema.MemSchemaRDefDel(session)
        # equivalent operation generated by op2 but replace it here by op3 so we
        # can check the result...
        op3 = syncschema.MemSchemaNotifyChanges(session)
        op4 = integrity._DelayedDeleteOp(session)
        op5 = integrity._CheckORelationOp(session)
        self.assertEquals(session.pending_operations, [op1, op2, op4, op5, op3])


class HookCalled(Exception): pass

config = TestServerConfiguration('data')
config.bootstrap_cubes()
schema = config.load_schema()

def teardown_module(*args):
    global config, schema
    del config, schema

class AddAnyHook(hook.Hook):
    __regid__ = 'addany'
    category = 'cat1'
    events = ('before_add_entity',)
    def __call__(self):
        raise HookCalled()


class HooksRegistryTC(TestCase):

    def setUp(self):
        """ called before each test from this class """
        self.vreg = mock_object(config=config, schema=schema)
        self.o = hook.HooksRegistry(self.vreg)

    def test_register_bad_hook1(self):
        class _Hook(hook.Hook):
            events = ('before_add_entiti',)
        ex = self.assertRaises(Exception, self.o.register, _Hook)
        self.assertEquals(str(ex), 'bad event before_add_entiti on %s._Hook' % __name__)

    def test_register_bad_hook2(self):
        class _Hook(hook.Hook):
            events = None
        ex = self.assertRaises(Exception, self.o.register, _Hook)
        self.assertEquals(str(ex), 'bad .events attribute None on %s._Hook' % __name__)

    def test_register_bad_hook3(self):
        class _Hook(hook.Hook):
            events = 'before_add_entity'
        ex = self.assertRaises(Exception, self.o.register, _Hook)
        self.assertEquals(str(ex), 'bad event b on %s._Hook' % __name__)

    def test_call_hook(self):
        self.o.register(AddAnyHook)
        dis = set()
        cw = mock_object(vreg=self.vreg,
                         set_read_security=lambda *a,**k: None,
                         set_write_security=lambda *a,**k: None,
                         is_hook_activated=lambda x, cls: cls.category not in dis)
        self.assertRaises(HookCalled,
                          self.o.call_hooks, 'before_add_entity', cw)
        dis.add('cat1')
        self.o.call_hooks('before_add_entity', cw) # disabled hooks category, not called
        dis.remove('cat1')
        self.assertRaises(HookCalled,
                          self.o.call_hooks, 'before_add_entity', cw)
        self.o.unregister(AddAnyHook)
        self.o.call_hooks('before_add_entity', cw) # nothing to call


class SystemHooksTC(CubicWebTC):

    def test_startup_shutdown(self):
        import hooks # cubicweb/server/test/data/hooks.py
        self.assertEquals(hooks.CALLED_EVENTS['server_startup'], True)
        # don't actually call repository.shutdown !
        self.repo.hm.call_hooks('server_shutdown', repo=self.repo)
        self.assertEquals(hooks.CALLED_EVENTS['server_shutdown'], True)

    def test_session_open_close(self):
        import hooks # cubicweb/server/test/data/hooks.py
        cnx = self.login('anon')
        self.assertEquals(hooks.CALLED_EVENTS['session_open'], 'anon')
        cnx.close()
        self.assertEquals(hooks.CALLED_EVENTS['session_close'], 'anon')


# class RelationHookTC(TestCase):
#     """testcase for relation hooks grouping"""
#     def setUp(self):
#         """ called before each test from this class """
#         self.o = HooksManager(schema)
#         self.called = []

#     def test_before_add_relation(self):
#         """make sure before_xxx_relation hooks are called directly"""
#         self.o.register(self._before_relation_hook,
#                              'before_add_relation', 'concerne')
#         self.assertEquals(self.called, [])
#         self.o.call_hooks('before_add_relation', 'concerne', 'USER',
#                           1, 'concerne', 2)
#         self.assertEquals(self.called, [(1, 'concerne', 2)])

#     def test_after_add_relation(self):
#         """make sure after_xxx_relation hooks are deferred"""
#         self.o.register(self._after_relation_hook,
#                              'after_add_relation', 'concerne')
#         self.assertEquals(self.called, [])
#         self.o.call_hooks('after_add_relation', 'concerne', 'USER',
#                           1, 'concerne', 2)
#         self.o.call_hooks('after_add_relation', 'concerne', 'USER',
#                           3, 'concerne', 4)
#         self.assertEquals(self.called, [(1, 'concerne', 2), (3, 'concerne', 4)])

#     def test_before_delete_relation(self):
#         """make sure before_xxx_relation hooks are called directly"""
#         self.o.register(self._before_relation_hook,
#                              'before_delete_relation', 'concerne')
#         self.assertEquals(self.called, [])
#         self.o.call_hooks('before_delete_relation', 'concerne', 'USER',
#                           1, 'concerne', 2)
#         self.assertEquals(self.called, [(1, 'concerne', 2)])

#     def test_after_delete_relation(self):
#         """make sure after_xxx_relation hooks are deferred"""
#         self.o.register(self._after_relation_hook,
#                         'after_delete_relation', 'concerne')
#         self.o.call_hooks('after_delete_relation', 'concerne', 'USER',
#                           1, 'concerne', 2)
#         self.o.call_hooks('after_delete_relation', 'concerne', 'USER',
#                           3, 'concerne', 4)
#         self.assertEquals(self.called, [(1, 'concerne', 2), (3, 'concerne', 4)])


#     def _before_relation_hook(self, pool, subject, r_type, object):
#         self.called.append((subject, r_type, object))

#     def _after_relation_hook(self, pool, subject, r_type, object):
#         self.called.append((subject, r_type, object))


if __name__ == '__main__':
    unittest_main()
