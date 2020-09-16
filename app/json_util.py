from datetime import datetime, date
import simplejson as json
import six
from sqlalchemy.orm.base import object_mapper
from sqlalchemy.orm.exc import UnmappedInstanceError
from sqlalchemy_utils import PhoneNumber
from arrow.arrow import Arrow


data_types = {
    int: 'int',
    float: 'float',
    bool: 'bool',
    dict: 'dict',
    str: 'str',
    list: 'list',
}


class Encoder(json.JSONEncoder):
    """Extends json.JSONEncoder with additional capabilities/configurations."""

    def default(self, o):
        if isinstance(o, (datetime, Arrow, date)):
            return o.isoformat()

        elif isinstance(o, bytes):
            return o.decode('utf-8')

        elif hasattr(o, '__table__'):  # SQLAlchemy model
            return o.to_dict()

        elif o is int:
            return 'int'

        elif o is float:
            return 'float'

        elif type(o).__name__ == 'ndarray':  # avoid numpy import
            return o.tolist()

        elif type(o).__name__ == 'DataFrame':  # avoid pandas import
            o.columns = o.columns.droplevel('channel')  # flatten MultiIndex
            return o.to_dict(orient='index')

        elif isinstance(o, PhoneNumber):
            return o.e164

        elif type(o) is type and o in data_types:
            return data_types[o]

        return json.JSONEncoder.default(self, o)


def to_json(obj):
    return json.dumps(obj, cls=Encoder, indent=2, ignore_nan=True)
