cw.utils.movedToNamespace(['log', 'jqNode', 'getNode', 'evalJSON', 'urlEncode',
                           'swapDOM'], cw);
cw.utils.movedToNamespace(['nodeWalkDepthFirst', 'formContents', 'isArray',
                           'isString', 'isArrayLike', 'sliceList',
                           'toISOTimestamp'], cw.utils);


if ($.noop === undefined) {
    function noop() {}
} else {
    noop = cw.utils.deprecatedFunction(
        '[3.9] noop() is deprecated, use $.noop() instead (XXX requires jQuery 1.4)',
        $.noop);
}

// ========== ARRAY EXTENSIONS ========== ///
Array.prototype.contains = cw.utils.deprecatedFunction(
    '[3.9] array.contains(elt) is deprecated, use $.inArray(elt, array) instead',
    function(element) {
        return jQuery.inArray(element, this) != - 1;
    }
);

// ========== END OF ARRAY EXTENSIONS ========== ///
forEach = cw.utils.deprecatedFunction(
    '[3.9] forEach() is deprecated, use $.each() instead',
    function(array, func) {
        return $.each(array, func);
    }
);

/**
 * .. function:: cw.utils.deprecatedFunction(msg, function)
 *
 * jQUery flattens arrays returned by the mapping function:
 * >>> y = ['a:b:c', 'd:e']
 * >>> jQuery.map(y, function(y) { return y.split(':');})
 * ["a", "b", "c", "d", "e"]
 *  // where one would expect:
 *  [ ["a", "b", "c"], ["d", "e"] ]
 *  XXX why not the same argument order as $.map and forEach ?
 */
map = cw.utils.deprecatedFunction(
    '[3.9] map() is deprecated, use $.map instead',
    function(func, array) {
        var result = [];
        for (var i = 0, length = array.length; i < length; i++) {
            result.push(func(array[i]));
        }
        return result;
    }
);

findValue = cw.utils.deprecatedFunction(
    '[3.9] findValue(array, elt) is deprecated, use $.inArray(elt, array) instead',
    function(array, element) {
        return jQuery.inArray(element, array);
    }
);

filter = cw.utils.deprecatedFunction(
    '[3.9] filter(func, array) is deprecated, use $.grep(array, f) instead',
    function(func, array) {
        return $.grep(array, func);
    }
);

addElementClass = cw.utils.deprecatedFunction(
    '[3.9] addElementClass(node, cls) is depcreated, use $(node).addClass(cls) instead',
    function(node, klass) {
        $(node).addClass(klass);
    }
);

removeElementClass = cw.utils.deprecatedFunction(
    '[3.9] removeElementClass(node, cls) is depcreated, use $(node).removeClass(cls) instead',
    function(node, klass) {
        $(node).removeClass(klass);
    }
);

hasElementClass = cw.utils.deprecatedFunction(
    '[3.9] hasElementClass(node, cls) is depcreated, use $.className.has(node, cls)',
    function(node, klass) {
        return $.className.has(node, klass);
    }
);

getNodeAttribute = cw.utils.deprecatedFunction(
    '[3.9] getNodeAttribute(node, attr) is deprecated, use $(node).attr(attr)',
    function(node, attribute) {
        return $(node).attr(attribute);
    }
);

getNode = cw.utils.deprecatedFunction(
    '[3.9] getNode(nodeid) is deprecated, use $(#nodeid) instead',
    function(node) {
        if (typeof node == 'string') {
            return document.getElementById(node);
        }
        return node;
    }
);

/**
 * .. function:: Deferred
 *
 * dummy ultra minimalist implementation on deferred for jQuery
 */
function Deferred() {
    this.__init__(this);
}

jQuery.extend(Deferred.prototype, {
    __init__: function() {
        this._onSuccess = [];
        this._onFailure = [];
        this._req = null;
        this._result = null;
        this._error = null;
    },

    addCallback: function(callback) {
        if (this._req.readyState == 4) {
            if (this._result) {
                var args = [this._result, this._req];
                jQuery.merge(args, cw.utils.sliceList(arguments, 1));
                callback.apply(null, args);
            }
        }
        else {
            this._onSuccess.push([callback, cw.utils.sliceList(arguments, 1)]);
        }
        return this;
    },

    addErrback: function(callback) {
        if (this._req.readyState == 4) {
            if (this._error) {
                callback.apply(null, [this._error, this._req]);
            }
        }
        else {
            this._onFailure.push([callback, cw.utils.sliceList(arguments, 1)]);
        }
        return this;
    },

    success: function(result) {
        this._result = result;
        try {
            for (var i = 0; i < this._onSuccess.length; i++) {
                var callback = this._onSuccess[i][0];
                var args = [result, this._req];
                jQuery.merge(args, this._onSuccess[i][1]);
                callback.apply(null, args);
            }
        } catch(error) {
            this.error(this.xhr, null, error);
        }
    },

    error: function(xhr, status, error) {
        this._error = error;
        for (var i = 0; i < this._onFailure.length; i++) {
            var callback = this._onFailure[i][0];
            var args = [error, this._req];
            jQuery.merge(args, this._onFailure[i][1]);
            callback.apply(null, args);
        }
    }

});

/**
 * The only known usage of KEYS is in the tag cube. Once cubicweb-tag 1.7.0 is out,
 * this current definition can be removed.
 */
var KEYS = {
    KEY_ESC: 27,
    KEY_ENTER: 13
};

// XXX avoid crashes / backward compat
CubicWeb = {
    require: function(module) {},
    provide: function(module) {}
};

jQuery(document).ready(function() {
    jQuery(CubicWeb).trigger('server-response', [false, document]);
});

// XXX as of 2010-04-07, no known cube uses this
jQuery(CubicWeb).bind('ajax-loaded', function() {
    log('[3.7] "ajax-loaded" event is deprecated, use "server-response" instead');
    jQuery(CubicWeb).trigger('server-response', [false, document]);
});

CubicWeb.provide('python.js');
