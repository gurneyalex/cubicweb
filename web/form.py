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
"""abstract form classes for CubicWeb web client

"""
__docformat__ = "restructuredtext en"

from warnings import warn

from logilab.common.decorators import iclassmethod
from logilab.common.deprecation import deprecated

from cubicweb.appobject import AppObject
from cubicweb.view import NOINDEX, NOFOLLOW
from cubicweb.web import httpcache, formfields, controller, formwidgets as fwdgs

class FormViewMixIn(object):
    """abstract form view mix-in"""
    category = 'form'
    http_cache_manager = httpcache.NoHTTPCacheManager
    add_to_breadcrumbs = False

    def html_headers(self):
        """return a list of html headers (eg something to be inserted between
        <head> and </head> of the returned page

        by default forms are neither indexed nor followed
        """
        return [NOINDEX, NOFOLLOW]

    def linkable(self):
        """override since forms are usually linked by an action,
        so we don't want them to be listed by appli.possible_views
        """
        return False


###############################################################################

class metafieldsform(type):
    """metaclass for FieldsForm to retrieve fields defined as class attributes
    and put them into a single ordered list: '_fields_'.
    """
    def __new__(mcs, name, bases, classdict):
        allfields = []
        for base in bases:
            if hasattr(base, '_fields_'):
                allfields += base._fields_
        clsfields = (item for item in classdict.items()
                     if isinstance(item[1], formfields.Field))
        for fieldname, field in sorted(clsfields, key=lambda x: x[1].creation_rank):
            if not field.name:
                field.set_name(fieldname)
            allfields.append(field)
        classdict['_fields_'] = allfields
        return super(metafieldsform, mcs).__new__(mcs, name, bases, classdict)


class FieldNotFound(Exception):
    """raised by field_by_name when a field with the given name has not been
    found
    """

class Form(AppObject):
    __metaclass__ = metafieldsform
    __registry__ = 'forms'

    internal_fields = ('__errorurl',) + controller.NAV_FORM_PARAMETERS

    parent_form = None
    force_session_key = None
    domid = 'form'
    copy_nav_params = False

    def __init__(self, req, rset=None, row=None, col=None,
                 submitmsg=None, mainform=True, **kwargs):
        super(Form, self).__init__(req, rset=rset, row=row, col=col)
        self.fields = list(self.__class__._fields_)
        if mainform:
            self.add_hidden(u'__form_id', kwargs.pop('formvid', self.__regid__))
        for key, val in kwargs.iteritems():
            if key in controller.NAV_FORM_PARAMETERS:
                self.add_hidden(key, val)
            elif key == 'redirect_path':
                self.add_hidden(u'__redirectpath', val)
            elif hasattr(self.__class__, key) and not key[0] == '_':
                setattr(self, key, val)
            else:
                self.cw_extra_kwargs[key] = val
            # skip other parameters, usually given for selection
            # (else write a custom class to handle them)
        if mainform:
            self.add_hidden(u'__errorurl', self.session_key())
            self.add_hidden(u'__domid', self.domid)
            self.restore_previous_post(self.session_key())
        # XXX why do we need two different variables (mainform and copy_nav_params ?)
        if self.copy_nav_params:
            for param in controller.NAV_FORM_PARAMETERS:
                if not param in kwargs:
                    value = req.form.get(param)
                    if value:
                        self.add_hidden(param, value)
        if submitmsg is not None:
            self.add_hidden(u'__message', submitmsg)

    @property
    def root_form(self):
        """return the root form"""
        if self.parent_form is None:
            return self
        return self.parent_form.root_form

    @property
    def form_valerror(self):
        """the validation error exception if any"""
        if self.parent_form is None:
            return self._form_valerror
        return self.parent_form.form_valerror

    @property
    def form_previous_values(self):
        """previously posted values (on validation error)"""
        if self.parent_form is None:
            return self._form_previous_values
        return self.parent_form.form_previous_values

    @iclassmethod
    def _fieldsattr(cls_or_self):
        if isinstance(cls_or_self, type):
            fields = cls_or_self._fields_
        else:
            fields = cls_or_self.fields
        return fields

    @iclassmethod
    def field_by_name(cls_or_self, name, role=None):
        """Return field with the given name and role.

        Raise :exc:`FieldNotFound` if the field can't be found.
        """
        for field in cls_or_self._fieldsattr():
            if field.name == name and field.role == role:
                return field
        raise FieldNotFound(name, role)

    @iclassmethod
    def fields_by_name(cls_or_self, name, role=None):
        """Return a list of fields with the given name and role."""
        return [field for field in cls_or_self._fieldsattr()
                if field.name == name and field.role == role]

    @iclassmethod
    def remove_field(cls_or_self, field):
        """Remove the given field."""
        cls_or_self._fieldsattr().remove(field)

    @iclassmethod
    def append_field(cls_or_self, field):
        """Append the given field."""
        cls_or_self._fieldsattr().append(field)

    @iclassmethod
    def insert_field_before(cls_or_self, field, name, role=None):
        """Insert the given field before the field of given name and role."""
        bfield = cls_or_self.field_by_name(name, role)
        fields = cls_or_self._fieldsattr()
        fields.insert(fields.index(bfield), field)

    @iclassmethod
    def insert_field_after(cls_or_self, field, name, role=None):
        """Insert the given field after the field of given name and role."""
        afield = cls_or_self.field_by_name(name, role)
        fields = cls_or_self._fieldsattr()
        fields.insert(fields.index(afield)+1, field)

    @iclassmethod
    def add_hidden(cls_or_self, name, value=None, **kwargs):
        """Append an hidden field to the form. `name`, `value` and extra keyword
        arguments will be given to the field constructor. The inserted field is
        returned.
        """
        kwargs.setdefault('ignore_req_params', True)
        kwargs.setdefault('widget', fwdgs.HiddenInput)
        field = formfields.StringField(name=name, value=value, **kwargs)
        if 'id' in kwargs:
            # by default, hidden input don't set id attribute. If one is
            # explicitly specified, ensure it will be set
            field.widget.setdomid = True
        cls_or_self.append_field(field)
        return field

    def session_key(self):
        """return the key that may be used to store / retreive data about a
        previous post which failed because of a validation error
        """
        if self.force_session_key is None:
            return '%s#%s' % (self._cw.url(), self.domid)
        return self.force_session_key

    def restore_previous_post(self, sessionkey):
        # get validation session data which may have been previously set.
        # deleting validation errors here breaks form reloading (errors are
        # no more available), they have to be deleted by application's publish
        # method on successful commit
        if hasattr(self, '_form_previous_values'):
            # XXX behaviour changed in 3.6.1, warn
            warn('[3.6.1] restore_previous_post already called, remove this call',
                 DeprecationWarning, stacklevel=2)
            return
        forminfo = self._cw.get_session_data(sessionkey, pop=True)
        if forminfo:
            self._form_previous_values = forminfo['values']
            self._form_valerror = forminfo['error']
            # if some validation error occured on entity creation, we have to
            # get the original variable name from its attributed eid
            foreid = self.form_valerror.entity
            for var, eid in forminfo['eidmap'].items():
                if foreid == eid:
                    self.form_valerror.eid = var
                    break
            else:
                self.form_valerror.eid = foreid
        else:
            self._form_previous_values = {}
            self._form_valerror = None

    def field_error(self, field):
        """return field's error if specified in current validation exception"""
        if self.form_valerror:
            if field.eidparam and self.edited_entity.eid != self.form_valerror.eid:
                return None
            try:
                return self.form_valerror.errors.pop(field.role_name())
            except KeyError:
                if field.role and field.name in self.form_valerror:
                    warn('%s: errors key of attribute/relation should be suffixed by "-<role>"'
                         % self.form_valerror.__class__, DeprecationWarning)
                    return self.form_valerror.errors.pop(field.name)
        return None

    def remaining_errors(self):
        return sorted(self.form_valerror.errors.items())

    @deprecated('[3.6] use form.field_error and/or new renderer.render_error method')
    def form_field_error(self, field):
        """return validation error for widget's field, if any"""
        err = self.field_error(field)
        if err:
            return u'<span class="error">%s</span>' % err
        return u''

