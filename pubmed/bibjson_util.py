import simplejson, StringIO

def get_records(tar, with_index=False, types=('Article',)):
    for tar_info in tar:
        if tar_info.name.endswith('.json'):
            json = tar.extractfile(tar_info)
            json = simplejson.load(json)
            if with_index:
                index = {}
                for record in json['recordList']:
                    if record:
                        index[record['id']] = record
            else:
                index = None
            for record in json['recordList']:
                if record and record['type'] in types:
                    yield index, record

def get_datasets(tar, types=('Article', 'Journal')):
    for tar_info in tar:
        if tar_info.name.endswith('.json'):
            json = tar.extractfile(tar_info)
            json = simplejson.load(json)
            if any(r['type'] in types for r in json['recordList']):
                yield tar_info, json

def get_json_files(tar):
    for tar_info in tar:
        if tar_info.name.endswith('.json'):
            json = tar.extractfile(tar_info)
            yield tar_info, StringIO.StringIO(json.read())

def write_dataset(tar, tar_info, json):
    data = StringIO.StringIO()
    data.write(simplejson.dumps(json))
    data.seek(0)
    tar_info.size = data.len
    tar.addfile(tar_info, data)
    tar.members = []
