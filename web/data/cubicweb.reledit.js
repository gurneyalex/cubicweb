cw.reledit = new Namespace('cw.reledit');


jQuery.extend(cw.reledit, {

    /* Unhides the part of reledit div containing the form
     * hides other parts
     */
    showInlineEditionForm: function (divid) {
        jQuery('#' + divid).hide();
        jQuery('#' + divid + '-value').hide();
        jQuery('#' + divid + '-form').show();
      },

    /* Hides and removes edition parts, incl. messages
     * show initial widget state
     */
    cleanupAfterCancel: function (divid) {
        jQuery('#appMsg').hide();
        jQuery('div.errorMessage').remove();
        jQuery('#' + divid).show();
        jQuery('#' + divid + '-value').show();
        jQuery('#' + divid + '-form').hide();
    },

    /* callback used on form validation success
     * refreshes the whole page or just the edited reledit zone
     * @param results: [status, ...]
     * @param formid: the dom id of the reledit form
     * @param cbargs: ...
     */
     onSuccess: function (results, formid, cbargs) {
        var params = {fname: 'reledit_form'};
        jQuery('#' + formid + ' input:hidden').each(function (elt) {
            var name = jQuery(this).attr('name');
            if (name && name.startswith('__reledit|')) {
                params[name.split('|')[1]] = this.value;
            }
        });
        var reload = cw.evalJSON(params.reload);
        if (reload || (params.formid == 'deleteconf')) {
            if (typeof reload == 'string') {
                /* Sometimes we want to reload but the reledit thing
                 * updated a key attribute which was a component of the
                 * url
                 */
                document.location.href = reload;
                return;
            }
            else {
                document.location.reload();
                return;
            }
        }
        jQuery('#'+params.divid+'-reledit').parent().loadxhtml(JSON_BASE_URL, params, 'post');
    },

    /* called by reledit forms to submit changes
     * @param formid : the dom id of the form used
     * @param rtype : the attribute being edited
     * @param eid : the eid of the entity being edited
     * @param reload: boolean to reload page if true (when changing URL dependant data)
     * @param default_value : value if the field is empty
     */
    loadInlineEditionForm: function(formid, eid, rtype, role, divid, reload, vid, default_value) {
        var args = {fname: 'reledit_form', rtype: rtype, role: role,
                    pageid: pageid,
                    eid: eid, divid: divid, formid: formid,
                    reload: reload, vid: vid, default_value: default_value,
                    callback: function () {cw.reledit.showInlineEditionForm(divid);}};
       jQuery('#'+divid+'-reledit').parent().loadxhtml(JSON_BASE_URL, args, 'post');
    }
});
