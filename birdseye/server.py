from __future__ import print_function, division, absolute_import

import json
from itertools import chain

from future import standard_library
from littleutils import DecentJSONEncoder, withattrs, select_keys

standard_library.install_aliases()
import sys

from flask import Flask, request
from flask.templating import render_template
from flask_humanize import Humanize
from werkzeug.routing import PathConverter

from birdseye.db import Call, Function, Session
from birdseye.utils import all_file_paths, short_path, IPYTHON_FILE_PATH

app = Flask('birdseye')
Humanize(app)


class FileConverter(PathConverter):
    regex = '.*?'


app.url_map.converters['file'] = FileConverter


@app.route('/')
def index():
    files = all_file_paths()
    files = zip(files, [short_path(f, files) for f in files])
    return render_template('index.html',
                           files=files)


@app.route('/file/<file:path>')
def file_view(path):
    return render_template('file.html',
                           funcs=sorted(Session().query(Function.name).filter_by(file=path).distinct()),
                           is_ipython=path == IPYTHON_FILE_PATH,
                           full_path=path,
                           short_path=short_path(path))


@app.route('/file/<file:path>/function/<func_name>')
def func_view(path, func_name):
    session = Session()
    query = (session.query(*(Call.basic_columns + Function.basic_columns))
                 .join(Function)
                 .filter_by(file=path, name=func_name)
                 .order_by(Call.start_time.desc())[:200])
    if query:
        func = query[0]
        print(func.body_hash)
        calls = [withattrs(Call(), **row._asdict()) for row in query]
    else:
        func = session.query(Function).filter_by(file=path, name=func_name)[0]
        calls = None

    return render_template('function.html',
                           func=func,
                           calls=calls)


@app.route('/call/<call_id>')
def call_view(call_id):
    call = Session().query(Call).filter_by(id=call_id).one()
    func = call.function
    return render_template('call.html',
                           call=call,
                           func=func)


@app.route('/kill', methods=['POST'])
def kill():
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()
    return 'Server shutting down...'


@app.route('/api/call/<call_id>')
def api_call_view(call_id):
    call = Session().query(Call).filter_by(id=call_id).one()
    func = call.function
    return DecentJSONEncoder().encode(dict(
        call=dict(data=call.parsed_data, **Call.basic_dict(call)),
        function=dict(data=func.parsed_data, **Function.basic_dict(func))))


@app.route('/api/calls_by_body_hash/<body_hash>')
def calls_by_body_hash(body_hash):
    query = (Session().query(*Call.basic_columns + (Function.data,))
                 .join(Function)
                 .filter_by(body_hash=body_hash)[:200])

    calls = [Call.basic_dict(withattrs(Call(), **row._asdict()))
             for row in query]

    function_data_set = {row.data for row in query}
    ranges = set()
    for function_data in function_data_set:
        node_ranges = json.loads(function_data)['node_ranges']
        for group in node_ranges:
            for node in group['nodes']:
                ranges.add((node['start'], node['end']))

    ranges = [dict(start=start, end=end) for start, end in ranges]

    return DecentJSONEncoder().encode(dict(calls=calls, ranges=ranges))


@app.route('/api/body_hashes_present/', methods=['POST'])
def body_hashes_present():
    hashes = request.json
    query = (Session().query(Function.body_hash)
             .filter(Function.body_hash.in_(hashes))
             .distinct())

    return DecentJSONEncoder().encode(chain.from_iterable(query))


def main():
    try:
        port = int(sys.argv[1])
    except IndexError:
        port = 7777

    app.run(debug=True, port=port)


if __name__ == '__main__':
    main()
