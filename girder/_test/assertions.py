import json

from girder._test.utils import getResponseBody


def assertStatus(response, code):
    """
    Call this to assert that a given HTTP status code was returned.

    :param response: The response object.
    :param code: The status code.
    :type code: int or str
    """
    code = str(code)

    if not response.output_status.startswith(code.encode()):
        msg = 'Response status was %s, not %s.' % (response.output_status,
                                                   code)

        if hasattr(response, 'json'):
            msg += ' Response body was:\n%s' % json.dumps(
                response.json, sort_keys=True, indent=4,
                separators=(',', ': '))
        else:
            msg += 'Response body was:\n%s' % getResponseBody(response)

        assert response.output_status.startswith(code.encode()), msg


def assertStatusOk(response):
    return assertStatus(response, 200)
