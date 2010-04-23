"""schema definition related entities

:organization: Logilab
:copyright: 2001-2010 LOGILAB S.A. (Paris, FRANCE), license is LGPL v2.
:contact: http://www.logilab.fr/ -- mailto:contact@logilab.fr
:license: GNU Lesser General Public License, v2.1 - http://www.gnu.org/licenses
"""
__docformat__ = "restructuredtext en"

from logilab.common.decorators import cached

from yams.schema import role_name

from cubicweb import ValidationError
from cubicweb.schema import ERQLExpression, RRQLExpression

from cubicweb.entities import AnyEntity, fetch_config


class CWEType(AnyEntity):
    __regid__ = 'CWEType'
    fetch_attrs, fetch_order = fetch_config(['name'])

    def dc_title(self):
        return u'%s (%s)' % (self.name, self._cw._(self.name))

    def dc_long_title(self):
        stereotypes = []
        _ = self._cw._
        if self.final:
            stereotypes.append(_('final'))
        if stereotypes:
            return u'%s <<%s>>' % (self.dc_title(), ', '.join(stereotypes))
        return self.dc_title()

    def db_key_name(self):
        """XXX goa specific"""
        return self.get('name')


class CWRType(AnyEntity):
    __regid__ = 'CWRType'
    fetch_attrs, fetch_order = fetch_config(['name'])

    def dc_title(self):
        return u'%s (%s)' % (self.name, self._cw._(self.name))

    def dc_long_title(self):
        stereotypes = []
        _ = self._cw._
        if self.symmetric:
            stereotypes.append(_('symmetric'))
        if self.inlined:
            stereotypes.append(_('inlined'))
        if self.final:
            stereotypes.append(_('final'))
        if stereotypes:
            return u'%s <<%s>>' % (self.dc_title(), ', '.join(stereotypes))
        return self.dc_title()

    def check_inlined_allowed(self):
        """check inlining is possible, raise ValidationError if not possible
        """
        # don't use the persistent schema, we may miss cardinality changes
        # in the same transaction
        for rdef in self.reverse_relation_type:
            card = rdef.cardinality[0]
            if not card in '?1':
                qname = role_name('inlined', 'subject')
                rtype = self.name
                stype = rdef.stype
                otype = rdef.otype
                msg = self._cw._("can't set inlined=%(inlined)s, "
                                 "%(stype)s %(rtype)s %(otype)s "
                                 "has cardinality=%(card)s")
                raise ValidationError(self.eid, {qname: msg % locals()})

    def db_key_name(self):
        """XXX goa specific"""
        return self.get('name')


class CWRelation(AnyEntity):
    __regid__ = 'CWRelation'
    fetch_attrs = fetch_config(['cardinality'])[0]

    def dc_title(self):
        return u'%s %s %s' % (
            self.from_entity[0].name,
            self.relation_type[0].name,
            self.to_entity[0].name)

    def dc_long_title(self):
        card = self.cardinality
        scard, ocard = u'', u''
        if card[0] != '1':
            scard = '[%s]' % card[0]
        if card[1] != '1':
            ocard = '[%s]' % card[1]
        return u'%s %s%s%s %s' % (
            self.from_entity[0].name,
            scard, self.relation_type[0].name, ocard,
            self.to_entity[0].name)

    def after_deletion_path(self):
        """return (path, parameters) which should be used as redirect
        information when this entity is being deleted
        """
        if self.relation_type:
            return self.relation_type[0].rest_path(), {}
        return super(CWRelation, self).after_deletion_path()

    @property
    def rtype(self):
        return self.relation_type[0]

    @property
    def stype(self):
        return self.from_entity[0]

    @property
    def otype(self):
        return self.to_entity[0]


class CWAttribute(CWRelation):
    __regid__ = 'CWAttribute'

    def dc_long_title(self):
        card = self.cardinality
        scard = u''
        if card[0] == '1':
            scard = '+'
        return u'%s %s%s %s' % (
            self.from_entity[0].name,
            scard, self.relation_type[0].name,
            self.to_entity[0].name)


class CWConstraint(AnyEntity):
    __regid__ = 'CWConstraint'
    fetch_attrs, fetch_order = fetch_config(['value'])

    def dc_title(self):
        return '%s(%s)' % (self.cstrtype[0].name, self.value or u'')

    def after_deletion_path(self):
        """return (path, parameters) which should be used as redirect
        information when this entity is being deleted
        """
        if self.reverse_constrained_by:
            return self.reverse_constrained_by[0].rest_path(), {}
        return super(CWConstraint, self).after_deletion_path()

    @property
    def type(self):
        return self.cstrtype[0].name


class RQLExpression(AnyEntity):
    __regid__ = 'RQLExpression'
    fetch_attrs, fetch_order = fetch_config(['exprtype', 'mainvars', 'expression'])

    def dc_title(self):
        return '%s(%s)' % (self.exprtype, self.expression or u'')

    @property
    def expression_of(self):
        for rel in ('read_permission', 'add_permission', 'delete_permission',
                    'update_permission', 'condition'):
            values = getattr(self, 'reverse_%s' % rel)
            if values:
                return values[0]

    @cached
    def _rqlexpr(self):
        if self.exprtype == 'ERQLExpression':
            return ERQLExpression(self.expression, self.mainvars, self.eid)
        #if self.exprtype == 'RRQLExpression':
        return RRQLExpression(self.expression, self.mainvars, self.eid)

    def check_expression(self, *args, **kwargs):
        return self._rqlexpr().check(*args, **kwargs)

    def after_deletion_path(self):
        """return (path, parameters) which should be used as redirect
        information when this entity is being deleted
        """
        if self.expression_of:
            return self.expression_of.rest_path(), {}
        return super(RQLExpression, self).after_deletion_path()


class CWPermission(AnyEntity):
    __regid__ = 'CWPermission'
    fetch_attrs, fetch_order = fetch_config(['name', 'label'])

    def dc_title(self):
        if self.label:
            return '%s (%s)' % (self._cw._(self.name), self.label)
        return self._cw._(self.name)

    def after_deletion_path(self):
        """return (path, parameters) which should be used as redirect
        information when this entity is being deleted
        """
        permissionof = getattr(self, 'reverse_require_permission', ())
        if len(permissionof) == 1:
            return permissionof[0].rest_path(), {}
        return super(CWPermission, self).after_deletion_path()
