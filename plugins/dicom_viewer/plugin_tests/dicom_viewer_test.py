from tests import base
import os
import time


def setUpModule():
    base.enabledPlugins.append('dicom_viewer')
    base.startServer()
    global removeUniqueMetadata
    from girder.plugins.dicom_viewer import removeUniqueMetadata


def tearDownModule():
    base.stopServer()


class DicomViewerTest(base.TestCase):

    def setUp(self):
        base.TestCase.setUp(self)

        self.users = [self.model('user').createUser(
            'usr%s' % num, 'passwd', 'tst', 'usr', 'u%s@u.com' % num)
            for num in [0, 1]]

    def testRemoveUniqueMetadata(self):
        dicomMeta = {
            'key1': 'value1',
            'key2': 'value2',
            'key3': 'value3',
            'key4': 35,
            'key5': 54,
            'key6': 'commonVal',
            'uniqueKey1': 'commonVal'
        }
        additionalMeta = {
            'key1': 'value1',
            'key2': 'value2',
            'key3': 'value3',
            'key4': 35,
            'key5': 54,
            'key6': 'uniqueVal',
            'uniqueKey2': 'commonVal',

        }
        commonMeta = {
            'key1': 'value1',
            'key2': 'value2',
            'key3': 'value3',
            'key4': 35,
            'key5': 54
        }
        self.assertEqual(removeUniqueMetadata(dicomMeta, additionalMeta), commonMeta)

    def testDicomViewer(self):
        admin, user = self.users

        # create a collection, folder, and item
        collection = self.model('collection').createCollection(
            'collection', admin, public=True)
        folder = self.model('folder').createFolder(
            collection, 'folder', parentType='collection', public=True)
        item = self.model('item').createItem('item', admin, folder)

        # test initial values
        path = '/item/%s/files' % item.get('_id')
        resp = self.request(path=path, user=admin)
        self.assertStatusOk(resp)
        self.assertEqual(resp.json, [])

        path = os.path.join(os.path.split(__file__)[0], 'test.dcm')
        with open(path, 'rb') as fp:
            self.model('upload').uploadFromFile(
                fp, 25640, 'test.dcm', 'item', item, admin)

        path = os.path.join(os.path.split(__file__)[0], 'not-dicom.dcm')
        with open(path, 'rb') as fp:
            self.model('upload').uploadFromFile(
                fp, 7590, 'not-dicom.dcm', 'item', item, admin)

        # test dicom endpoint
        start = time.time()
        while True:
            try:
                path = '/item/%s/parseDicom' % item.get('_id')
                resp = self.request(path=path, user=admin, method='POST')
                break
            except AssertionError:
                if time.time() - start > 15:
                    raise
                time.sleep(0.5)

        self.assertStatusOk(resp)

        # one dicom file found
        path = '/item/%s/files' % item.get('_id')
        resp = self.request(path=path, user=admin)
        files = resp.json
        self.assertEqual(len(files), 2)

        # # dicom tags present
        # file = files[0]
        # dicom = file['dicom']
        # self.assertEqual(bool(dicom), True)

        # # dicom tags correct
        # self.assertEqual(dicom['Rows'], 80)
        # self.assertEqual(dicom['Columns'], 150)

        # test filters
        # path = '/item/%s/dicom' % item.get('_id')
        # resp = self.request(path=path, user=admin, params=dict(filters='Rows'))
        # self.assertStatusOk(resp)
        # dicom = resp.json[0]['dicom']
        # self.assertEqual(dicom['Rows'], 80)
        # self.assertEqual(dicom.get('Columns'), None)

        # # test non-admin force
        # path = '/item/%s/dicom' % item.get('_id')
        # resp = self.request(path=path, user=user, params=dict(force=True))
        # self.assertStatus(resp, 403)
