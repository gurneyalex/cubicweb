from cubicweb.devtools.qunit import QUnitTestCase, unittest_main

from os import path as osp


class JScript(QUnitTestCase):

    all_js_tests = (
        ("jstests/test_datetime.js",(
            "../data/cubicweb.js",
            "../data/cubicweb.compat.js",)),
        ("jstests/test_htmlhelpers.js", (
            "../data/cubicweb.js",
            "../data/cubicweb.compat.js",
            "../data/cubicweb.python.js",
            "../data/cubicweb.htmlhelpers.js")),
        ("jstests/test_ajax.js",(
            "../data/cubicweb.python.js",
            "../data/cubicweb.js",
            "../data/cubicweb.compat.js",
            "../data/cubicweb.htmlhelpers.js",
            "../data/cubicweb.ajax.js",
            ),(
            "jstests/ajax_url0.html",
            "jstests/ajax_url1.html",
            "jstests/ajax_url2.html",
            "jstests/ajaxresult.json",
            ))
    )


if __name__ == '__main__':
    unittest_main()
