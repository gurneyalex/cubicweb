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
"""entity classes user and group entities"""

__docformat__ = "restructuredtext en"

from logilab.common.decorators import cached

from cubicweb import Unauthorized
from cubicweb.entities import AnyEntity, fetch_config

class CWGroup(AnyEntity):
    __regid__ = 'CWGroup'
    fetch_attrs, cw_fetch_order = fetch_config(['name'])
    cw_fetch_unrelated_order = cw_fetch_order

    def dc_long_title(self):
        name = self.name
        trname = self._cw._(name)
        if trname != name:
            return '%s (%s)' % (name, trname)
        return name

    @cached
    def num_users(self):
        """return the number of users in this group"""
        return self._cw.execute('Any COUNT(U) WHERE U in_group G, G eid %(g)s',
                                {'g': self.eid})[0][0]


class CWUser(AnyEntity):
    __regid__ = 'CWUser'
    fetch_attrs, cw_fetch_order = fetch_config(['login', 'firstname', 'surname'])
    cw_fetch_unrelated_order = cw_fetch_order

    # used by repository to check if  the user can log in or not
    AUTHENTICABLE_STATES = ('activated',)

    # low level utilities #####################################################
    def __init__(self, *args, **kwargs):
        groups = kwargs.pop('groups', None)
        properties = kwargs.pop('properties', None)
        super(CWUser, self).__init__(*args, **kwargs)
        if groups is not None:
            self._groups = groups
        if properties is not None:
            self._properties = properties

    @property
    def groups(self):
        try:
            return self._groups
        except AttributeError:
            self._groups = set(g.name for g in self.in_group)
            return self._groups

    @property
    def properties(self):
        try:
            return self._properties
        except AttributeError:
            self._properties = dict((p.pkey, p.value) for p in self.reverse_for_user)
            return self._properties

    def prefered_language(self, language=None):
        """return language used by this user, if explicitly defined (eg not
        using http negociation)
        """
        language = language or self.property_value('ui.language')
        vreg = self._cw.vreg
        try:
            vreg.config.translations[language]
        except KeyError:
            language = vreg.property_value('ui.language')
            assert language in vreg.config.translations[language], language
        return language

    def property_value(self, key):
        try:
            # properties stored on the user aren't correctly typed
            # (e.g. all values are unicode string)
            return self._cw.vreg.typed_value(key, self.properties[key])
        except KeyError:
            pass
        except ValueError:
            self.warning('incorrect value for eproperty %s of user %s',
                         key, self.login)
        return self._cw.vreg.property_value(key)

    def set_property(self, pkey, value):
        value = unicode(value)
        try:
            prop = self._cw.execute(
                'CWProperty X WHERE X pkey %(k)s, X for_user U, U eid %(u)s',
                {'k': pkey, 'u': self.eid}).get_entity(0, 0)
        except Exception:
            kwargs = dict(pkey=unicode(pkey), value=value)
            if self.is_in_group('managers'):
                kwargs['for_user'] = self
            self._cw.create_entity('CWProperty', **kwargs)
        else:
            prop.cw_set(value=value)

    def matching_groups(self, groups):
        """return the number of the given group(s) in which the user is

        :type groups: str or iterable(str)
        :param groups: a group name or an iterable on group names
        """
        if isinstance(groups, basestring):
            groups = frozenset((groups,))
        elif isinstance(groups, (tuple, list)):
            groups = frozenset(groups)
        return len(groups & self.groups) # XXX return the resulting set instead of its size

    def is_in_group(self, group):
        """convience / shortcut method to test if the user belongs to `group`
        """
        return group in self.groups

    def is_anonymous(self):
        """ checks if user is an anonymous user"""
        #FIXME on the web-side anonymous user is detected according
        # to config['anonymous-user'], we don't have this info on
        # the server side.
        return self.groups == frozenset(('guests', ))

    def owns(self, eid):
        try:
            return self._cw.execute(
                'Any X WHERE X eid %(x)s, X owned_by U, U eid %(u)s',
                {'x': eid, 'u': self.eid})
        except Unauthorized:
            return False
    owns = cached(owns, keyarg=1)

    # presentation utilities ##################################################

    def name(self):
        """construct a name using firstname / surname or login if not defined"""

        if self.firstname and self.surname:
            return self._cw._('%(firstname)s %(surname)s') % {
                'firstname': self.firstname, 'surname' : self.surname}
        if self.firstname:
            return self.firstname
        return self.login

    def dc_title(self):
        return self.login

    dc_long_title = name

    def __call__(self, *args, **kwargs):
        """ugly hack for compatibility betweeb dbapi and repo api

        In the dbapi, Connection and Session have a ``user`` method to
        generated a user for a request In the repo api, Connection and Session
        have a user attribute inherited from SessionRequestBase prototype. This
        ugly hack allows to not break user of the user method.

        XXX Deprecate me ASAP"""
        return self

from logilab.common.deprecation import class_renamed
EUser = class_renamed('EUser', CWUser)
EGroup = class_renamed('EGroup', CWGroup)
