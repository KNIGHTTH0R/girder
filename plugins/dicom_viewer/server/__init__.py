from dicom.sequence import Sequence
from dicom.valuerep import PersonName3
from girder import events
from girder.api import access
from girder.api.describe import Description, autoDescribeRoute
from girder.api.rest import Resource
from girder.constants import AccessType
from girder.utility.model_importer import ModelImporter
import dicom
import six


class DicomItem(Resource):

    @access.user
    @autoDescribeRoute(
        Description('Get and store common DICOM metadata, if any, for all files in the item.')
        .modelParam('id', 'The item ID',
                    model='item', level=AccessType.WRITE, paramType='path')
        .errorResponse('ID was invalid.')
        .errorResponse('Read permission denied on the item.', 403)
    )
    def makeDicomItem(self, item):
        """
        Try to convert an existing item into a "DICOM item", which contains a
        "dicomMeta" field with DICOM metadata that is common to all DICOM files.
        """
        metadataReference = None
        dicomFiles = []

        for file in ModelImporter.model('item').childFiles(item):
            dicomMeta = parse_file(file)
            if dicomMeta is None:
                continue
            dicomFiles.append(_extractFileData(file, dicomMeta))
            if metadataReference is None:
                metadataReference = dicomMeta
            else:
                metadataReference = removeUniqueMetadata(metadataReference, dicomMeta)

        if len(dicomFiles) is not 0:
            # Sort the dicom files
            dicomFiles = sorted(dicomFiles,key=_sort_key)
            # Store in the item
            item['dicom'] = {}
            item['dicom']['meta'] = metadataReference
            item['dicom']['files'] = dicomFiles
            # Save the item
            ModelImporter.model('item').save(item)


def _extractFileData(file, dicom):
    '''
    Extract the usefull data to be stored in the `item['dicom']['files']`.
    In this way it become simpler to sort them and store them.
    '''
    return {
        '_id': file.get('_id'),
        'name': file.get('name'),
        'SeriesNumber': dicom.get('SeriesNumber'),
        'InstanceNumber': dicom.get('InstanceNumber'),
        'SliceLocation': dicom.get('SliceLocation')
    }


def _sort_key(f):
    '''
    These properties are used to sort the files into the item
    '''
    return (
        f.get('name'),
        f.get('SeriesNumber'),
        f.get('InstanceNumber'),
        f.get('SliceLocation')
    )


def removeUniqueMetadata(dicomMeta, additionalMeta):
    '''
    Return only the common data between the two inputs.
    Only work if all the data element are hashable,
    this means not have any dict or list as properties
    '''
    return dict(
        set(
            (
                k,
                tuple(v) if isinstance(v, list) else v
            )
            for k, v in six.viewitems(dicomMeta)
        ) &
        set(
            (
                k,
                tuple(v) if isinstance(v, list) else v
            )
            for k, v in six.viewitems(additionalMeta)
        )
    )


def coerce(x):
    if isinstance(x, Sequence):
        return None
    if isinstance(x, list):
        return [coerce(y) for y in x]
    if isinstance(x, PersonName3):
        return x.encode('utf-8')
    try:
        six.text_type(x)
        return x
    except Exception:
        return None


def parse_file(f):
    data = {}
    try:
        # download file and try to parse dicom
        with ModelImporter.model('file').open(f) as fp:
            ds = dicom.read_file(
                fp,
                # some dicom files don't have a valid header
                # force=True,
                # don't read huge fields, esp. if this isn't even really dicom
                defer_size=1024,
                # don't read image data, just metadata
                stop_before_pixels=True)
            # does this look like a dicom file?
            if (len(ds.dir()), len(ds.items())) == (0, 1):
                return data
            # human-readable keys
            for key in ds.dir():
                value = coerce(ds.data_element(key).value)
                if value is not None:
                    data[key] = value
            # hex keys
            for key, value in ds.items():
                key = 'x%04x%04x' % (key.group, key.element)
                value = coerce(value.value)
                if value is not None:
                    data[key] = value
    except dicom.errors.InvalidDicomError:
        # if this error occurs, probably not a dicom file
        return None
    return data


def handler(event):
    """
    Whenever an additional file is uploaded to a "DICOM item", remove any
    DICOM metadata that is no longer common to all DICOM files in the item.
    """
    file = event.info['file']
    fileMetadata = parse_file(file)
    if fileMetadata is None:
        return
    item = ModelImporter.model('item').load(file['itemId'], force=True)
    if 'dicom' in item:
        item['dicom']['meta'] = removeUniqueMetadata(item['dicom']['meta'], fileMetadata)
    else:
        # In this case the uploaded file is the first of the item
        item['dicom'] = {}
        item['dicom']['meta'] = fileMetadata
        item['dicom']['files'] = _extractFileData(file, fileMetadata)
    ModelImporter.model('item').save(item)


def load(info):
    ModelImporter.model('item').exposeFields(level=AccessType.READ, fields={'dicom'})
    events.bind('data.process', 'dicom_viewer', handler)
    dicomItem = DicomItem()
    info['apiRoot'].item.route(
        'POST', (':id', 'parseDicom'), dicomItem.makeDicomItem)
