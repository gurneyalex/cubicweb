/*
 *  :organization: Logilab
 *  :copyright: 2003-2009 LOGILAB S.A. (Paris, FRANCE), all rights reserved.
 *  :contact: http://www.logilab.fr/ -- mailto:contact@logilab.fr
 */

CubicWeb.require('python.js');
CubicWeb.require('htmlhelpers.js');
CubicWeb.require('ajax.js');


//============= Eproperty form functions =====================================//

/* called on Eproperty key selection:
 * - get the selected value
 * - get a widget according to the key by a sync query to the server
 * - fill associated div with the returned html
 *
 * @param varname the name of the variable as used in the original creation form
 * @param tabindex the tabindex that should be set on the widget
 */
function setPropValueWidget(varname, tabindex) {
    var key = firstSelected(document.getElementById('pkey:'+varname));
    if (key) {
	var args = {fname: 'prop_widget', pageid: pageid,
     		    arg: map(jQuery.toJSON, [key, varname, tabindex])};
	jqNode('div:value:'+varname).loadxhtml(JSON_BASE_URL, args, 'post');
    }
}


// *** EDITION FUNCTIONS ****************************************** //

/*
 * this function is called when an AJAX form was generated to
 * make sure tabindex remains consistent
 */
function reorderTabindex(start) {
    var form = getNode('entityForm');
    var inputTypes = ['INPUT', 'SELECT', 'TEXTAREA'];
    var tabindex = (start==null)?15:start;
    nodeWalkDepthFirst(form, function(elem) {
        var tagName = elem.tagName.toUpperCase();
	if (inputTypes.contains(tagName)) {
	    if (getNodeAttribute(elem, 'tabindex') != null) {
		tabindex += 1;
		elem.setAttribute('tabindex', tabindex);
	    }
	    return null;
	}
	return filter(isElementNode, elem.childNodes);
    });
}


function showMatchingSelect(selectedValue, eid) {
    if (selectedValue) {
	divId = 'div' + selectedValue + '_' + eid;
	var divNode = jQuery('#' + divId);
	if (!divNode.length) {
	    var args = {vid: 'unrelateddivs', relation: selectedValue,
			rql: rql_for_eid(eid), '__notemplate': 1,
			callback: function() {_showMatchingSelect(eid, jQuery('#' + divId))}};
	    jQuery('#unrelatedDivs_' + eid).loadxhtml(baseuri() + 'view', args, 'post', 'append');
	} else {
	    _showMatchingSelect(eid, divNode);
	}
    } else {
	_showMatchingSelect(eid, null);
    }
}


// @param divNode is a jQuery selection
function _showMatchingSelect(eid, divNode) {
    // hide all divs, and then show the matching one
    // (would actually be better to directly hide the displayed one)
    jQuery('#unrelatedDivs_' + eid).children().hide();
    // divNode not found means 'no relation selected' (i.e. first blank item)
    if (divNode && divNode.length) {
	divNode.show();
    }
}

// this function builds a Handle to cancel pending insertion
function buildPendingInsertHandle(elementId, element_name, selectNodeId, eid) {
   jscall = "javascript: cancelPendingInsert('" + [elementId, element_name, selectNodeId, eid].join("', '") + "')";
   return A({'class' : 'handle', 'href' : jscall,
	     'title' : _("cancel this insert")}, '[x]');
}

function buildEntityLine(relationName, selectedOptionNode, comboId, eid) {
   // textContent doesn't seem to work on selectedOptionNode
   var content = selectedOptionNode.firstChild.nodeValue;
   var handle = buildPendingInsertHandle(selectedOptionNode.id, 'tr', comboId, eid);
   var link = A({'href' : 'view?rql=' + selectedOptionNode.value,
	  	 'class' : 'editionPending', 'id' : 'a' + selectedOptionNode.id},
		content);
   var tr = TR({'id' : 'tr' + selectedOptionNode.id}, [ TH(null, relationName),
							TD(null, [handle, link])
						      ]);
   try {
      var separator = getNode('relationSelectorRow_' + eid);
      //dump('relationSelectorRow_' + eid) XXX warn dump is not implemented in konqueror (at least)
      // XXX Warning: separator.parentNode is not (always ?) the
      // table itself, but an intermediate node (TableSectionElement)
      var tableBody = separator.parentNode;
      tableBody.insertBefore(tr, separator);
   } catch(ex) {
      log("got exception(2)!" + ex);
   }
}

function buildEntityCell(relationName, selectedOptionNode, comboId, eid) {
    var handle = buildPendingInsertHandle(selectedOptionNode.id, 'div_insert_', comboId, eid);
    var link = A({'href' : 'view?rql=' + selectedOptionNode.value,
		  'class' : 'editionPending', 'id' : 'a' + selectedOptionNode.id},
		 content);
    var div = DIV({'id' : 'div_insert_' + selectedOptionNode.id}, [handle, link]);
    try {
	var td = jQuery('#cell'+ relationName +'_'+eid);
	td.appendChild(div);
    } catch(ex) {
	alert("got exception(3)!" + ex);
    }
}

function addPendingInsert(optionNode, eid, cell, relname) {
    var value = getNodeAttribute(optionNode, 'value');
    if (!value) {
	// occurs when the first element in the box is selected (which is not
	// an entity but the combobox title)
        return;
    }
    // 2nd special case
    if (value.indexOf('http') == 0) {
	document.location = value;
	return;
    }
    // add hidden parameter
    var entityForm = jQuery('#entityForm');
    var oid = optionNode.id.substring(2); // option id is prefixed by "id"
    remoteExec('add_pending_inserts', [oid.split(':')]);
    var selectNode = optionNode.parentNode;
    // remove option node
    selectNode.removeChild(optionNode);
    // add line in table
    if (cell) {
      // new relation as a cell in multiple edit
      // var relation_name = relationSelected.getAttribute('value');
      // relation_name = relation_name.slice(0, relation_name.lastIndexOf('_'));
      buildEntityCell(relname, optionNode, selectNode.id, eid);
    }
    else {
	var relationSelector = getNode('relationSelector_'+eid);
	var relationSelected = relationSelector.options[relationSelector.selectedIndex];
	// new relation as a line in simple edit
	buildEntityLine(relationSelected.text, optionNode, selectNode.id, eid);
    }
}

function cancelPendingInsert(elementId, element_name, comboId, eid) {
    // remove matching insert element
    var entityView = jqNode('a' + elementId).text();
    jqNode(element_name + elementId).remove();
    if (comboId) {
	// re-insert option in combobox if it was taken from there
	var selectNode = getNode(comboId);
        // XXX what on object relation
	if (selectNode){
	   var options = selectNode.options;
	   var node_id = elementId.substring(0, elementId.indexOf(':'));
	   options[options.length] = OPTION({'id' : elementId, 'value' : node_id}, entityView);
	}
    }
    elementId = elementId.substring(2, elementId.length);
    remoteExec('remove_pending_insert', elementId.split(':'));
}

// this function builds a Handle to cancel pending insertion
function buildPendingDeleteHandle(elementId, eid) {
  var jscall = "javascript: addPendingDelete('" + elementId + ', ' + eid + "');";
  return A({'href' : jscall, 'class' : 'pendingDeleteHandle',
    'title' : _("delete this relation")}, '[x]');
}

// @param nodeId eid_from:r_type:eid_to
function addPendingDelete(nodeId, eid) {
    var d = asyncRemoteExec('add_pending_delete', nodeId.split(':'));
    d.addCallback(function () {
	// and strike entity view
	jqNode('span' + nodeId).addClass('pendingDelete');
	// replace handle text
	jqNode('handle' + nodeId).text('+');
    });
}

// @param nodeId eid_from:r_type:eid_to
function cancelPendingDelete(nodeId, eid) {
    var d = asyncRemoteExec('remove_pending_delete', nodeId.split(':'));
    d.addCallback(function () {
	// reset link's CSS class
	jqNode('span' + nodeId).removeClass('pendingDelete');
	// replace handle text
	jqNode('handle' + nodeId).text('x');
    });
}

// @param nodeId eid_from:r_type:eid_to
function togglePendingDelete(nodeId, eid) {
    // node found means we should cancel deletion
    if ( hasElementClass(getNode('span' + nodeId), 'pendingDelete') ) {
	cancelPendingDelete(nodeId, eid);
    } else {
	addPendingDelete(nodeId, eid);
    }
}


function selectForAssociation(tripletIdsString, originalEid) {
    var tripletlist = map(function (x) { return x.split(':'); },
			  tripletIdsString.split('-'));
    var d = asyncRemoteExec('add_pending_inserts', tripletlist);
    d.addCallback(function () {
	var args = {vid: 'edition', __mode: 'normal',
		    rql: rql_for_eid(originalEid)};
	document.location = 'view?' + asURL(args);
    });

}


function updateInlinedEntitiesCounters(rtype) {
    jQuery('#inline' + rtype + 'slot span.icounter').each(function (i) {
	this.innerHTML = i+1;
    });
}


/*
 * makes an AJAX request to get an inline-creation view's content
 * @param peid : the parent entity eid
 * @param ttype : the target (inlined) entity type
 * @param rtype : the relation type between both entities
 */
function addInlineCreationForm(peid, ttype, rtype, role) {
    var d = asyncRemoteExec('inline_creation_form', peid, ttype, rtype, role);
    d.addCallback(function (response) {
	var linknode = getNode('add' + rtype + ':' + peid + 'link');
        var dom = getDomFromResponse(response);
	var form = jQuery(dom);
	form.css('display', 'none');
	form.insertBefore(linknode.parentNode).slideDown('fast');
	updateInlinedEntitiesCounters(rtype);
	reorderTabindex();
	form.trigger('inlinedform-added');
        postAjaxLoad(dom);
    });
    d.addErrback(function (xxx) {
	log('xxx =', xxx);
    });
}

/*
 * removes the part of the form used to edit an inlined entity
 */
function removeInlineForm(peid, rtype, eid) {
    jqNode(['div', peid, rtype, eid].join('-')).slideUp('fast', function() {
	$(this).remove();
	updateInlinedEntitiesCounters(rtype);
    });
}

/*
 * alternatively adds or removes the hidden input that make the
 * edition of the relation `rtype` possible between `peid` and `eid`
 * @param peid : the parent entity eid
 * @param rtype : the relation type between both entities
 * @param eid : the inlined entity eid
 */
function removeInlinedEntity(peid, rtype, eid) {
    var nodeid = ['rel', peid, rtype, eid].join('-');
    var node = jqNode(nodeid);
    if (node && node.length) {
	node.remove();
	var divid = ['div', peid, rtype, eid].join('-');
	jqNode(divid).fadeTo('fast', 0.5);
	var noticeid = ['notice', peid, rtype, eid].join('-');
	jqNode(noticeid).fadeIn('fast');
    }
}

function restoreInlinedEntity(peid, rtype, eid) {
    var nodeid = ['rel', peid, rtype, eid].join('-');
    var divid = ['div', peid, rtype, eid].join('-');
    var noticeid = ['notice', peid, rtype, eid].join('-');
    var node = jqNode(nodeid);
    if (!(node && node.length)) {
	node = INPUT({type: 'hidden', id: nodeid,
		      name: rtype+':'+peid, value: eid});
	jqNode(['fs', peid, rtype, eid].join('-')).append(node);
	jqNode(divid).fadeTo('fast', 1);
	jqNode(noticeid).hide();
    }
}

function _clearPreviousErrors(formid) {
    jQuery('#' + formid + ' span.error').remove();
}

function _displayValidationerrors(formid, eid, errors) {
    var globalerrors = [];
    var firsterrfield = null;
    for (fieldname in errors) {
	var errmsg = errors[fieldname];
	var fieldid = fieldname + ':' + eid;
	var field = jqNode(fieldname + ':' + eid);
	if (field && getNodeAttribute(field, 'type') != 'hidden') {
	    if ( !firsterrfield ) {
		firsterrfield = 'err-' + fieldid;
	    }
	    addElementClass(field, 'error');
	    var span = SPAN({'id': 'err-' + fieldid, 'class': "error"}, errmsg);
	    field.before(span);
	} else {
	    firsterrfield = formid;
	    globalerrors.push(fieldname + ': ' + errmsg);
	}
    }
    if (globalerrors.length) {
	if (globalerrors.length == 1) {
	    var innernode = SPAN(null, globalerrors[0]);
	} else {
	    var innernode = UL(null, map(LI, globalerrors));
	}
	// insert DIV and innernode before the form
	var div = DIV({'class' : "errorMessage"});
	div.appendChild(innernode);
	jQuery('#' + formid).before(div);
    }
    return firsterrfield || formid;
}


function handleFormValidationResponse(formid, onsuccess, onfailure, result) {
    // Success
    if (result[0]) {
	if (onsuccess) {
	    return onsuccess(result[1], formid);
	} else {
	    document.location.href = result[1];
	    return ;
	}
    }
    unfreezeFormButtons(formid);
    // Failures
    _clearPreviousErrors(formid);
    var descr = result[1];
    // Unknown structure
    if ( !isArrayLike(descr) || descr.length != 2 ) {
	log('got strange error :', descr);
	updateMessage(descr);
	return ;
    }
    _displayValidationerrors(formid, descr[0], descr[1]);
    updateMessage(_("please correct errors below"));
    document.location.hash = '#header';
    if (onfailure){
	onfailure(formid);
    }
    return false;
}


/* unfreeze form buttons when the validation process is over*/
function unfreezeFormButtons(formid) {
    jQuery('#progress').hide();
    jQuery('#' + formid + ' input.validateButton').removeAttr('disabled');
    return true;
}

/* disable form buttons while the validation is being done */
function freezeFormButtons(formid) {
    jQuery('#progress').show();
    jQuery('#' + formid + ' input.validateButton').attr('disabled', 'disabled');
    return true;
}

/* used by additional submit buttons to remember which button was clicked */
function postForm(bname, bvalue, formid) {
    var form = getNode(formid);
    if (bname) {
	form.appendChild(INPUT({type: 'hidden', name: bname, value: bvalue}));
    }
    var onsubmit = form.onsubmit;
    if (!onsubmit || (onsubmit && onsubmit())) {
	form.submit();
    }
}


/* called on load to set target and iframeso object.
 * NOTE: this is a hack to make the XHTML compliant.
 * NOTE2: `object` nodes might be a potential replacement for iframes
 * NOTE3: there is a XHTML module allowing iframe elements but there
 *        is still the problem of the form's `target` attribute
 */
function setFormsTarget() {
    jQuery('form.entityForm').each(function () {
	var form = jQuery(this);
	var target = form.attr('cubicweb:target');
	if (target) {
	    form.attr('target', target);
	    /* do not use display: none because some browsers ignore iframe
             * with no display */
	    form.append(IFRAME({name: target, id: target,
				src: 'javascript: void(0)',
				width: '0px', height: '0px'}));
	}
    });
}

$(document).ready(setFormsTarget);


/*
 * called on traditionnal form submission : the idea is to try
 * to post the form. If the post is successful, `validateForm` redirects
 * to the appropriate URL. Otherwise, the validation errors are displayed
 * around the corresponding input fields.
 */
function validateForm(formid, action, onsuccess, onfailure) {
    try {
	var zipped = formContents(formid);
	var d = asyncRemoteExec('validate_form', action, zipped[0], zipped[1]);
    } catch (ex) {
	log('got exception', ex);
	return false;
    }
    function _callback(result, req) {
	handleFormValidationResponse(formid, onsuccess, onfailure, result);
    }
    d.addCallback(_callback);
    return false;
}


/*
 * called by reledit forms to submit changes
 * @param formid : the dom id of the form used
 * @param rtype : the attribute being edited
 * @param eid : the eid of the entity being edited
 * @param reload: boolean to reload page if true (when changing URL dependant data)
 */
function inlineValidateAttributeForm(formid, rtype, eid, divid, reload, default_value) {
    try {
	var form = getNode(formid);
	if (typeof FCKeditorAPI != "undefined") {
	    for ( var name in FCKeditorAPI.__Instances ) {
		var oEditor = FCKeditorAPI.__Instances[name] ;
		if ( oEditor.GetParentForm() == form ) {
		    oEditor.UpdateLinkedField();
		}
	    }
	}
	var zipped = formContents(form);
	var d = asyncRemoteExec('edit_field', 'apply', zipped[0], zipped[1],
                                rtype, eid, default_value);
    } catch (ex) {
	log('got exception', ex);
	return false;
    }
    d.addCallback(function (result, req) {
        handleFormValidationResponse(formid, noop, result);
	if (reload) {
	    document.location.href = result[1];
	} else {
	    var fieldview = getNode(divid);
	    // XXX using innerHTML is very fragile and won't work if
	    // we mix XHTML and HTML
	    fieldview.innerHTML = result[2];
	    // switch inline form off only if no error
	    if (result[0]) {
		// hide global error messages
		jQuery('div.errorMessage').remove();
		jQuery('#appMsg').hide();
		cancelInlineEdit(eid, rtype, divid);
	    }
	}
	return false;
    });
    return false;
}

function inlineValidateRelationForm(formid, rtype, role, eid, divid, vid, default_value) {
    try {
	var form = getNode(formid);
        var relname = rtype + ':' + eid;
        var newtarget = jQuery('[name=' + relname + ']').val();
	var zipped = formContents(form);
	var d = asyncRemoteExec('edit_relation', 'apply', zipped[0], zipped[1], rtype, role,
                                eid, vid, default_value);
    } catch (ex) {
	log('got exception', ex);
	return false;
    }
    d.addCallback(function (result, req) {
        handleFormValidationResponse(formid, noop, result);
	var fieldview = getNode(divid);
        fieldview.innerHTML = result[2];
	// switch inline form off only if no error
	if (result[0]) {
          // hide global error messages
	  jQuery('div.errorMessage').remove();
	  jQuery('#appMsg').hide();
          var inputname = 'edit' + role[0] + '-' + relname;
          jQuery('input[name=' + inputname + ']').val(newtarget);
	  cancelInlineEdit(eid, rtype, divid);
	}
        return false;
    });
  return false;
}


/**** inline edition ****/
function showInlineEditionForm(eid, rtype, divid) {
    jQuery('#' + divid).hide();
    jQuery('#' + divid + '-form').show();
}

function cancelInlineEdit(eid, rtype, divid) {
    jQuery('#' + divid).show();
    jQuery('#' + divid + '-form').hide();
}

CubicWeb.provide('edition.js');
