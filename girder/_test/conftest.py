import cherrypy
import pytest

from girder.models import _dbClients, getDbConnection
from girder._test.utils import request
from girder.utility import model_importer
from girder.utility.server import setup as setupServer


def pytest_addoption(parser):
    parser.addoption('--mongo-uri', action='store', default='mongodb://localhost:27017',
                     help='The base URI to the MongoDB instance to use for database connections.')
    parser.addoption('--drop-db', action='store', default='post', choices=('pre', 'post', 'never'),
                     help='When to destroy testing databases.')


@pytest.fixture
def db(request):
    """
    Require a Mongo test database.

    Provides a Mongo test database named after the requesting test function. Mongo databases are
    created/destroyed based on the URI provided with the --mongo-uri option and tear-down
    semantics are handled by the --drop-db option.
    """
    dbUri = request.config.getoption('--mongo-uri')
    dbName = 'girder_test_%s' % request.node.name
    dropDb = request.config.getoption('--drop-db')
    connection = getDbConnection(uri='%s/%s' % (dbUri, dbName), quiet=False)

    # Force getDbConnection from models to return our connection
    _dbClients[(None, None)] = connection

    if dropDb == 'pre':
        connection.drop_database(dbName)
        model_importer.reinitializeAll()

    yield connection

    if dropDb == 'post':
        connection.drop_database(dbName)


@pytest.fixture(scope='session')
def model():
    """
    Shortcut for providing a model_importer.ModelImporter.model function.

    This is to reduce the boilerplate in loading models.
    """
    from girder.utility.model_importer import ModelImporter
    return ModelImporter.model


@pytest.fixture
def server(db):
    """
    Require a CherryPy embedded server.

    Provides a started CherryPy embedded server with a request method for performing
    local requests against it.
    """
    # The event daemon cannot be restarted since it is a threading.Thread object, however
    # all references to girder.events.daemon are a singular global daemon due to its side
    # effect on import. We have to hack around this by creating a unique event daemon
    # each time we startup the server and assigning it to the global.
    import girder.events
    girder.events.daemon = girder.events.AsyncEventsThread()

    server = setupServer(test=True)
    server.request = request

    cherrypy.server.unsubscribe()
    cherrypy.config.update({'environment': 'embedded',
                            'log.screen': False})
    cherrypy.engine.start()

    yield server

    cherrypy.engine.unsubscribe('start', girder.events.daemon.start)
    cherrypy.engine.unsubscribe('stop', girder.events.daemon.stop)
    cherrypy.engine.stop()
    cherrypy.engine.exit()


@pytest.fixture
def admin(db, model):
    yield model('user').createUser(email='admin@email.com', login='admin', firstName='Admin',
                                   lastName='Admin', password='password', admin=True)


@pytest.fixture
def user(db, model):
    yield model('user').createUser(email='user@email.com', login='user', firstName='user',
                                   lastName='user', password='password', admin=False)
