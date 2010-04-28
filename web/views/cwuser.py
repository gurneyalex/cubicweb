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
# logilab-common is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for more
# details.
#
# You should have received a copy of the GNU Lesser General Public License along
# with CubicWeb.  If not, see <http://www.gnu.org/licenses/>.
"""Specific views for users

"""
__docformat__ = "restructuredtext en"

from logilab.mtconverter import xml_escape

from cubicweb.selectors import one_line_rset, implements, match_user_groups
from cubicweb.view import EntityView
from cubicweb.web import action, uicfg

_pvs = uicfg.primaryview_section
_pvs.tag_attribute(('CWUser', 'login'), 'hidden')
_pvs.tag_attribute(('CWGroup', 'name'), 'hidden')
_pvs.tag_subject_of(('CWGroup', 'read_permission', '*'), 'relations')
_pvs.tag_subject_of(('CWGroup', 'add_permission', '*'), 'relations')
_pvs.tag_subject_of(('CWGroup', 'delete_permission', '*'), 'relations')
_pvs.tag_subject_of(('CWGroup', 'update_permission', '*'), 'relations')
_pvs.tag_object_of(('*', 'in_group', 'CWGroup'), 'relations')
_pvs.tag_object_of(('*', 'require_group', 'CWGroup'), 'relations')

class UserPreferencesEntityAction(action.Action):
    __regid__ = 'prefs'
    __select__ = (one_line_rset() & implements('CWUser') &
                  match_user_groups('owners', 'managers'))

    title = _('preferences')
    category = 'mainactions'

    def url(self):
        login = self.cw_rset.get_entity(self.cw_row or 0, self.cw_col or 0).login
        return self._cw.build_url('cwuser/%s'%login, vid='propertiesform')


class FoafView(EntityView):
    __regid__ = 'foaf'
    __select__ = implements('CWUser')

    title = _('foaf')
    templatable = False
    content_type = 'text/xml'

    def call(self):
        self.w(u'''<?xml version="1.0" encoding="%s"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3org/2000/01/rdf-schema#"
         xmlns:foaf="http://xmlns.com/foaf/0.1/"> '''% self._cw.encoding)
        for i in xrange(self.cw_rset.rowcount):
            self.cell_call(i, 0)
        self.w(u'</rdf:RDF>\n')

    def cell_call(self, row, col):
        entity = self.cw_rset.complete_entity(row, col)
        self.w(u'''<foaf:PersonalProfileDocument rdf:about="">
                      <foaf:maker rdf:resource="%s"/>
                      <foaf:primaryTopic rdf:resource="%s"/>
                   </foaf:PersonalProfileDocument>''' % (entity.absolute_url(), entity.absolute_url()))
        self.w(u'<foaf:Person rdf:ID="%s">\n' % entity.eid)
        self.w(u'<foaf:name>%s</foaf:name>\n' % xml_escape(entity.dc_long_title()))
        if entity.surname:
            self.w(u'<foaf:family_name>%s</foaf:family_name>\n'
                   % xml_escape(entity.surname))
        if entity.firstname:
            self.w(u'<foaf:givenname>%s</foaf:givenname>\n'
                   % xml_escape(entity.firstname))
        emailaddr = entity.get_email()
        if emailaddr:
            self.w(u'<foaf:mbox>%s</foaf:mbox>\n' % xml_escape(emailaddr))
        self.w(u'</foaf:Person>\n')
