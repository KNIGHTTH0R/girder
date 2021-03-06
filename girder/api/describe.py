#!/usr/bin/env python
# -*- coding: utf-8 -*-

###############################################################################
#  Copyright Kitware Inc.
#
#  Licensed under the Apache License, Version 2.0 ( the "License" );
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
###############################################################################

import bson.json_util
import dateutil.parser
try:
    from inspect import signature, Parameter
except ImportError:
    from funcsigs import signature, Parameter
import inspect
import jsonschema
import os
import six
import cherrypy

from girder import constants, events, logprint
from girder.api.rest import getCurrentUser, RestException, getBodyJson
from girder.constants import CoreEventHandler, SettingKey
from girder.models.setting import Setting
from girder.utility import config, toBool
from girder.utility.model_importer import ModelImporter
from girder.utility.webroot import WebrootBase
from . import docs, access
from .rest import Resource, getApiUrl, getUrlParts

"""
Whenever we add new return values or new options we should increment the
maintenance value. Whenever we add new endpoints, we should increment the minor
version. If we break backward compatibility in any way, we should increment the
major version.  This value is derived from the version number given in
the top level package.json.
"""
API_VERSION = constants.VERSION['apiVersion']

SWAGGER_VERSION = '2.0'


class Description(object):
    """
    This class provides convenient chainable semantics to allow api route
    handlers to describe themselves to the documentation. A route handler
    function can apply the :py:class:`girder.api.describe.describeRoute`
    decorator to itself (called with an instance of this class) in order to
    describe itself.
    """

    # Data Type map from common name or type to (type, format)
    # See Data Type spec:
    #   https://github.com/OAI/OpenAPI-Specification/blob/
    #   0122c22e7fb93b571740dd3c6e141c65563a18be/versions/2.0.md#data-types
    _dataTypeMap = {
        # Primitives
        'integer': ('integer', 'int32'),
        'long': ('integer', 'int64'),
        'number': ('number', None),
        'float': ('number', 'float'),
        'double': ('number', 'double'),
        'string': ('string', None),
        'byte': ('string', 'byte'),
        'binary': ('string', 'binary'),
        'boolean': ('boolean', None),
        'date': ('string', 'date'),
        'dateTime': ('string', 'date-time'),
        'password': ('string', 'password'),
        'file': ('file', None)
    }

    def __init__(self, summary):
        self._summary = summary
        self._params = []
        self._responses = {}
        self._consumes = []
        self._produces = []
        self._responseClass = None
        self._responseClassArray = False
        self._notes = None
        self._deprecated = False
        self.hasPagingParams = False
        self.modelParams = {}
        self.jsonParams = {}

    def asDict(self):
        """
        Returns this description object as an appropriately formatted dict
        """

        # Responses Object spec:
        # The Responses Object MUST contain at least one response code, and it
        # SHOULD be the response for a successful operation call.
        if '200' not in self._responses:
            self._responses['200'] = {
                'description': 'Success'
            }
        if self._responseClass is not None:
            schema = {
                '$ref': '#/definitions/%s' % self._responseClass
            }
            if self._responseClassArray:
                schema = {
                    'type': 'array',
                    'items': schema
                }
            self._responses['200']['schema'] = schema

        resp = {
            'summary': self._summary,
            'responses': self._responses
        }

        if self._params:
            resp['parameters'] = self._params

        if self._notes is not None:
            resp['description'] = self._notes

        if self._consumes:
            resp['consumes'] = self._consumes

        if self._produces:
            resp['produces'] = self._produces

        if self._deprecated:
            resp['deprecated'] = True

        return resp

    def responseClass(self, obj, array=False):
        self._responseClass = obj
        self._responseClassArray = array
        return self

    def _validateParamInfo(self, dataType, paramType, name):
        """
        Helper to convert and validate the dataType and paramType.
        Prints warnings if invalid values were passed.
        """
        # Legacy data type conversions
        if dataType == 'int':
            dataType = 'integer'

        # Parameter Object spec:
        # If type is "file", then the swagger "consumes" field MUST be either
        # "multipart/form-data", "application/x-www-form-urlencoded" or both
        # and the parameter MUST be in "formData".
        if dataType == 'file':
            paramType = 'formData'

        # Get type and format from common name
        dataTypeFormat = None
        if dataType in self._dataTypeMap:
            dataType, dataTypeFormat = self._dataTypeMap[dataType]
        # If we are dealing with the body then the dataType might be defined
        # by a schema added using addModel(...), we don't know for sure as we
        # don't know the resource name here to look it up.
        elif paramType != 'body':
            logprint.warning(
                'WARNING: Invalid dataType "%s" specified for parameter names "%s"' %
                (dataType, name))

        # Parameter Object spec:
        # Since the parameter is not located at the request body, it is limited
        # to simple types (that is, not an object).
        if paramType != 'body' and dataType not in (
                'string', 'number', 'integer', 'long', 'boolean', 'array', 'file', 'float',
                'double', 'date', 'dateTime'):
            logprint.warning(
                'WARNING: Invalid dataType "%s" specified for parameter "%s"' % (dataType, name))

        if paramType == 'form':
            paramType = 'formData'

        return dataType, dataTypeFormat, paramType

    def param(self, name, description, paramType='query', dataType='string',
              required=True, enum=None, default=None, strip=False, lower=False, upper=False):
        """
        This helper will build a parameter declaration for you. It has the most
        common options as defaults, so you won't have to repeat yourself as much
        when declaring the APIs.

        Note that we could expose more parameters from the Parameter Object
        spec, for example: format, allowEmptyValue, minimum, maximum, pattern,
        uniqueItems.

        :param name: name of the parameter used in the REST query.
        :param description: explanation of the parameter.
        :param paramType: how is the parameter sent.  One of 'query', 'path',
                          'body', 'header', or 'formData'.
        :param dataType: the data type expected in the parameter. This is one
                         of 'integer', 'long', 'float', 'double', 'string',
                         'byte', 'binary', 'boolean', 'date', 'dateTime',
                         'password', or 'file'.
        :param required: True if the request will fail if this parameter is not
                         present, False if the parameter is optional.
        :param enum: a fixed list of possible values for the field.
        :type enum: `list`
        :param strip: For string types, set this to True if the string should be
            stripped of white space.
        :type strip: bool
        :param lower: For string types, set this to True if the string should be
            converted to lowercase.
        :type lower: bool
        :param upper: For string types, set this to True if the string should be
            converted to uppercase.
        :type upper: bool
        """
        dataType, format, paramType = self._validateParamInfo(dataType, paramType, name)

        param = {
            'name': name,
            'description': description,
            'in': paramType,
            'required': required
        }

        if dataType == 'string':
            param['_strip'] = strip
            param['_lower'] = lower
            param['_upper'] = upper

        if paramType == 'body':
            param['schema'] = {
                '$ref': '#/definitions/%s' % dataType
            }
        else:
            param['type'] = dataType

        if format is not None:
            param['format'] = format

        if enum:
            param['enum'] = enum

        if default is not None:
            param['default'] = default

        self._params.append(param)
        return self

    def modelParam(self, name, description=None, model=None, destName=None, paramType='path',
                   plugin='_core', level=None, required=True, force=False, exc=True,
                   requiredFlags=None, **kwargs):
        """
        This should be used in lieu of ``param`` if the parameter is a model ID
        and the model should be loaded and passed into the route handler. For example,
        if you have a route like ``GET /item/:id``, you could do:

        >>> from girder.models.item import Item
        >>> modelParam('id', model=Item, level=AccessType.READ)

        Which would cause the ``id`` parameter in the path to be mapped to an
        item model parameter named ``item``, and ensure that the calling user
        has at least ``READ`` access on that item. For parameters passed in
        the query string or form data, for example a request like
        ``POST /item?folderId=...``, you must specify the ``paramType``.

        >>> modelParam('folderId', 'The ID of the parent folder.', model=Folder,
        ...            level=AccessType.WRITE, paramType='query')

        Note that in the above example, ``model`` is omitted; in this case, the
        model is inferred to be ``'folder'`` from the parameter name ``'folderId'``.

        :param name: The name passed in via the request, e.g. 'id'.
        :type name: str
        :param description: The description of the parameter. If not passed, defaults
            to "The ID of the <model>."
        :type description: str
        :param destName: The kwarg name after model loading, e.g. 'folder'. Defaults
            to the value of the model parameter.
        :type destName: str
        :param paramType: how is the parameter sent.  One of 'query', 'path',
            'body', 'header', or 'formData'.
        :param model: The model class to use for loading, or a name, e.g. 'folder'. If not passed,
            defaults to stripping the last two characters from the name, such that e.g. 'folderId'
            would make the model become 'folder'.
        :type model: class or str
        :param plugin: Plugin name, if loading a plugin model. Only used when the ``model``
            param is a string rather than a class.
        :type plugin: str
        :param level: Access level, if this is an access controlled model.
        :type level: AccessType
        :param required: Whether this parameter is required.
        :type required: bool
        :param force: Force loading of the model (skip access check).
        :type force: bool
        :param exc: Whether an exception should be raised for a nonexistent resource.
        :type exc: bool
        :param requiredFlags: Access flags that are required on the object being loaded.
        :type requiredFlags: str or list/set/tuple of str or None
        """
        if model is None:
            model = name[:-2]  # strip off "Id"

        if inspect.isclass(model):
            modelInst = model()
            modelName = modelInst.name
        else:
            modelName = model
            modelInst = ModelImporter.model(model, plugin)

        if description is None:
            description = 'The ID of the %s.' % modelName

        self.param(name=name, description=description, paramType=paramType, required=required)

        self.modelParams[name] = {
            'destName': destName or modelName,
            'level': level,
            'force': force,
            'model': modelInst,
            'exc': exc,
            'required': required,
            'requiredFlags': requiredFlags,
            'kwargs': kwargs
        }

        return self

    def jsonParam(self, name, description, paramType='query', dataType='string', required=True,
                  default=None, requireObject=False, requireArray=False, schema=None):
        """
        Specifies a parameter that should be processed as JSON.

        :param requireObject: Whether the value must be a JSON object / Python dict.
        :type requireObject: bool
        :param requireArray: Whether the value must be a JSON array / Python list.
        :type requireArray: bool
        :param schema: A JSON schema that will be used to validate the parameter value. If
            this is passed, it overrides any ``requireObject`` or ``requireArray`` values
            that were passed.
        :type schema: dict
        """
        if default:
            default = bson.json_util.dumps(default)

        self.param(
            name=name, description=description, paramType=paramType, dataType=dataType,
            required=required, default=default)

        self.jsonParams[name] = {
            'requireObject': requireObject,
            'requireArray': requireArray,
            'schema': schema
        }

        return self

    def pagingParams(self, defaultSort, defaultSortDir=1, defaultLimit=50):
        """
        Adds the limit, offset, sort, and sortdir parameter documentation to
        this route handler.

        :param defaultSort: The default field used to sort the result set.
        :type defaultSort: str
        :param defaultSortDir: Sort order: -1 or 1 (desc or asc)
        :type defaultSortDir: int
        :param defaultLimit: The default page size.
        :type defaultLimit: int
        """
        self.param(
            'limit', 'Result set size limit.', default=defaultLimit, required=False, dataType='int')
        self.param('offset', 'Offset into result set.', default=0, required=False, dataType='int')

        if defaultSort is not None:
            self.param(
                'sort', 'Field to sort the result set by.', default=defaultSort, required=False,
                strip=True)
            self.param(
                'sortdir', 'Sort order: 1 for ascending, -1 for descending.',
                required=False, dataType='integer', enum=(1, -1), default=defaultSortDir)

        self.hasPagingParams = True
        return self

    def consumes(self, value):
        self._consumes.append(value)
        return self

    def produces(self, value):
        if isinstance(value, (list, tuple)):
            self._produces.extend(value)
        else:
            self._produces.append(value)
        return self

    def notes(self, notes):
        self._notes = notes
        return self

    def errorResponse(self, reason='A parameter was invalid.', code=400):
        """
        This helper will build an errorResponse declaration for you. Many
        endpoints will be able to use the default parameter values for one of
        their responses.

        :param reason: The reason or list of reasons why the error occurred.
        :type reason: `str, list, or tuple`
        :param code: HTTP status code.
        :type code: int
        """
        code = str(code)

        # Combine list of reasons into a single string.
        # swagger-ui renders the description using Markdown.
        if not isinstance(reason, six.string_types):
            reason = '\n\n'.join(reason)

        if code in self._responses:
            self._responses[code]['description'] += '\n\n' + reason
        else:
            self._responses[code] = {
                'description': reason
            }

        return self

    def deprecated(self):
        """
        Mark the route as deprecated.
        """
        self._deprecated = True
        return self

    @property
    def params(self):
        return self._params


class ApiDocs(WebrootBase):
    """
    This serves up the Swagger page.
    """
    def __init__(self, templatePath=None):
        if not templatePath:
            templatePath = os.path.join(constants.PACKAGE_DIR,
                                        'api', 'api_docs.mako')
        super(ApiDocs, self).__init__(templatePath)

        curConfig = config.getConfig()
        mode = curConfig['server'].get('mode', '')

        self.vars = {
            'apiRoot': '',
            'staticRoot': '',
            'brandName': Setting().get(SettingKey.BRAND_NAME),
            'mode': mode
        }

        events.bind('model.setting.save.after', CoreEventHandler.WEBROOT_SETTING_CHANGE,
                    self._onSettingSave)
        events.bind('model.setting.remove', CoreEventHandler.WEBROOT_SETTING_CHANGE,
                    self._onSettingRemove)

    def _onSettingSave(self, event):
        settingDoc = event.info
        if settingDoc['key'] == SettingKey.BRAND_NAME:
            self.updateHtmlVars({'brandName': settingDoc['value']})

    def _onSettingRemove(self, event):
        settingDoc = event.info
        if settingDoc['key'] == SettingKey.BRAND_NAME:
            self.updateHtmlVars({'brandName': Setting().getDefault(SettingKey.BRAND_NAME)})


class Describe(Resource):
    def __init__(self):
        super(Describe, self).__init__()
        self.route('GET', (), self.listResources, nodoc=True)

    @access.public
    def listResources(self, params):
        # Paths Object
        paths = {}

        # Definitions Object
        definitions = dict(**docs.models[None])

        # List of Tag Objects
        tags = []

        for resource in sorted(six.viewkeys(docs.routes)):
            # Update Definitions Object
            if resource in docs.models:
                for name, model in six.viewitems(docs.models[resource]):
                    definitions[name] = model

            # Tag Object
            tags.append({
                'name': resource
            })

            for route, methods in six.viewitems(docs.routes[resource]):
                # Path Item Object
                pathItem = {}
                for method, operation in six.viewitems(methods):
                    # Operation Object
                    pathItem[method.lower()] = operation

                paths[route] = pathItem

        apiUrl = getApiUrl(preferReferer=True)
        urlParts = getUrlParts(apiUrl)
        host = urlParts.netloc
        basePath = urlParts.path

        return {
            'swagger': SWAGGER_VERSION,
            'info': {
                'title': 'Girder REST API',
                'version': API_VERSION
            },
            'host': host,
            'basePath': basePath,
            'tags': tags,
            'paths': paths,
            'definitions': definitions
        }


class describeRoute(object):  # noqa: class name
    def __init__(self, description):
        """
        This returns a decorator to set the API documentation on a route
        handler. Pass the Description object (or None) that you want to use to
        describe this route. It should be used like the following example:

            @describeRoute(
                Description('Do something')
               .param('foo', 'Some parameter', ...)
            )
            def routeHandler(...)

        :param description: The description for the route.
        :type description: :py:class:`girder.api.describe.Description` or None
        """
        self.description = description

    def __call__(self, fun):
        fun.description = self.description
        return fun


class autoDescribeRoute(describeRoute):  # noqa: class name
    def __init__(self, description, hide=False):
        """
        Like describeRoute, but this decorator also controls behavior of the
        underlying method. It handles parameter validation and transformation
        based on the Description object passed.

        :param description: The description object.
        :type description: Description
        :param hide: Set to True if this route should not appear in the swagger listing.
        :type hide: bool
        """
        super(autoDescribeRoute, self).__init__(description=description)
        self.hide = hide

    def _passArg(self, fun, kwargs, name, val):
        """
        This helper passes the arguments to the underlying function if the function
        has an argument with the given name. Otherwise, it adds it into the "params"
        argument, which is a dictionary containing other parameters.

        :param fun: The wrapped route handler function
        :type fun: callable
        :param name: The name of the argument to set
        :type name: str
        :param kwargs: The arguments to be passed down to the function.
        :type kwargs: dict
        :param val: The value of the argument to set
        """
        if name in self._funNamedArgs or self._funHasKwargs:
            kwargs[name] = val
            kwargs['params'].pop(name, None)
        else:
            kwargs['params'][name] = val

    def _mungeKwargs(self, kwargs, fun):
        """
        Performs final modifications to the kwargs passed into the wrapped function.
        Combines the sort/sortdir params appropriately for consumption by the model
        layer, and only passes the "params" catch-all dict if there is a corresponding
        kwarg for it in the wrapped function.
        """
        if self.description.hasPagingParams and 'sort' in kwargs:
            sortdir = kwargs.pop('sortdir', None) or kwargs['params'].pop('sortdir', None)
            kwargs['sort'] = [(kwargs['sort'], sortdir)]

        if 'params' not in self._funNamedArgs and not self._funHasKwargs:
            kwargs.pop('params', None)

    def _inspectFunSignature(self, fun):
        self._funNamedArgs = set()
        self._funHasKwargs = False
        for funParam in six.viewvalues(signature(fun).parameters):
            if funParam.kind in {Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY}:
                # POSITIONAL_OR_KEYWORD are basic positional parameters
                # KEYWORD_ONLY are named parameters that appear after a * in Python 3
                self._funNamedArgs.add(funParam.name)
            elif funParam.kind == Parameter.VAR_KEYWORD:
                # VAR_KEYWORD is the **kwargs parameter
                self._funHasKwargs = True

    def __call__(self, fun):
        self._inspectFunSignature(fun)

        @six.wraps(fun)
        def wrapped(*args, **kwargs):
            """
            Transform any passed params according to the spec, or
            fill in default values for any params not passed.
            """
            # Combine path params with form/query params into a single lookup table
            params = {k: v for k, v in six.viewitems(kwargs) if k != 'params'}
            params.update(kwargs.get('params', {}))

            for descParam in self.description.params:
                # We need either a type or a schema ( for message body )
                if 'type' not in descParam and 'schema' not in descParam:
                    continue
                name = descParam['name']
                if name in params:
                    if name in self.description.jsonParams:
                        info = self.description.jsonParams[name]
                        val = self._loadJson(name, info, params[name])
                        self._passArg(fun, kwargs, name, val)
                    elif name in self.description.modelParams:
                        info = self.description.modelParams[name]
                        kwargs.pop(name, None)  # Remove from path params
                        val = self._loadModel(name, info, params[name])
                        self._passArg(fun, kwargs, info['destName'], val)
                    else:
                        val = self._validateParam(name, descParam, params[name])
                        self._passArg(fun, kwargs, name, val)
                elif descParam['in'] == 'body':
                    if name in self.description.jsonParams:
                        info = self.description.jsonParams[name].copy()
                        info['required'] = descParam['required']
                        val = self._loadJsonBody(name, info)
                        self._passArg(fun, kwargs, name, val)
                    else:
                        self._passArg(fun, kwargs, name, cherrypy.request.body)
                elif 'default' in descParam:
                    self._passArg(fun, kwargs, name, descParam['default'])
                elif descParam['required']:
                    raise RestException('Parameter "%s" is required.' % name)
                else:
                    # If required=False but no default is specified, use None
                    if name in self.description.modelParams:
                        info = self.description.modelParams[name]
                        kwargs.pop(name, None)  # Remove from path params
                        self._passArg(fun, kwargs, info['destName'], None)
                    else:
                        self._passArg(fun, kwargs, name, None)

            self._mungeKwargs(kwargs, fun)

            return fun(*args, **kwargs)

        if self.hide:
            wrapped.description = None
        else:
            wrapped.description = self.description
        return wrapped

    def _validateJsonType(self, name, info, val):
        if info.get('schema') is not None:
            try:
                jsonschema.validate(val, info['schema'])
            except jsonschema.ValidationError as e:
                raise RestException('Invalid JSON object for parameter %s: %s' % (
                    name, e.message))
        elif info['requireObject'] and not isinstance(val, dict):
            raise RestException('Parameter %s must be a JSON object.' % name)
        elif info['requireArray'] and not isinstance(val, list):
            raise RestException('Parameter %s must be a JSON array.' % name)

    def _loadJsonBody(self, name, info):
        val = None
        if cherrypy.request.body.length == 0 and info['required']:
            raise RestException('JSON parameter %s must be passed in request body.' % name)
        elif cherrypy.request.body.length > 0:
            val = getBodyJson()
            self._validateJsonType(name, info, val)

        return val

    def _loadJson(self, name, info, value):
        try:
            val = bson.json_util.loads(value)
        except ValueError:
            raise RestException('Parameter %s must be valid JSON.' % name)

        self._validateJsonType(name, info, val)

        return val

    def _loadModel(self, name, info, id):
        model = info['model']

        if info['force']:
            doc = model.load(id, force=True, **info['kwargs'])
        elif info['level'] is not None:
            doc = model.load(id=id, level=info['level'], user=getCurrentUser(), **info['kwargs'])
        else:
            doc = model.load(id, **info['kwargs'])

        if doc is None and info['exc']:
            raise RestException('Invalid %s id (%s).' % (model.name, str(id)))

        if info['requiredFlags']:
            model.requireAccessFlags(doc, user=getCurrentUser(), flags=info['requiredFlags'])

        return doc

    def _handleString(self, name, descParam, value):
        if descParam['_strip']:
            value = value.strip()
        if descParam['_lower']:
            value = value.lower()
        if descParam['_upper']:
            value = value.upper()

        format = descParam.get('format')
        if format in ('date', 'date-time'):
            try:
                value = dateutil.parser.parse(value)
            except ValueError:
                raise RestException('Invalid date format for parameter %s: %s.' % (name, value))

            if format == 'date':
                value = value.date()

        return value

    def _handleInt(self, name, descParam, value):
        try:
            return int(value)
        except ValueError:
            raise RestException('Invalid value for integer parameter %s: %s.' % (name, value))

    def _handleNumber(self, name, descParam, value):
        try:
            return float(value)
        except ValueError:
            raise RestException('Invalid value for numeric parameter %s: %s.' % (name, value))

    def _validateParam(self, name, descParam, value):
        """
        Validates and transforms a single parameter that was passed. Raises
        RestException if the passed value is invalid.

        :param name: The name of the param.
        :type name: str
        :param descParam: The formal parameter in the Description.
        :type descParam: dict
        :param value: The value passed in for this param for the current request.
        :returns: The value transformed
        """
        type = descParam.get('type')

        # Coerce to the correct data type
        if type == 'string':
            value = self._handleString(name, descParam, value)
        elif type == 'boolean':
            value = toBool(value)
        elif type == 'integer':
            value = self._handleInt(name, descParam, value)
        elif type == 'number':
            value = self._handleNumber(name, descParam, value)

        # Enum validation (should be afer type coercion)
        if 'enum' in descParam and value not in descParam['enum']:
            raise RestException('Invalid value for %s: "%s". Allowed values: %s.' % (
                name, value, ', '.join(str(v) for v in descParam['enum'])))

        return value
