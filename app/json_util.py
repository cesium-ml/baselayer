from datetime import date, datetime

import simplejson as json
from arrow.arrow import Arrow
from sqlalchemy_utils import PhoneNumber

data_types = {
    int: "int",
    float: "float",
    bool: "bool",
    dict: "dict",
    str: "str",
    list: "list",
}

import asyncio

class Encoder(json.JSONEncoder):
    """Extends json.JSONEncoder with additional capabilities/configurations."""

    def default(self, o):
        if isinstance(o, (datetime, Arrow, date)):
            return o.isoformat()

        elif isinstance(o, bytes):
            return o.decode("utf-8")

        # TODO: how do we handle that when to_dict is async???
        # elif hasattr(o, "__table__"):  # SQLAlchemy model
        #     return asyncio.run(o.to_dict())
        # instead we throw an error for now
        elif hasattr(o, "__table__"):  # SQLAlchemy model
            raise NotImplementedError("sync to_dict not implemented yet")

        elif o is int:
            return "int"

        elif o is float:
            return "float"

        elif type(o).__name__ == "ndarray":  # avoid numpy import
            return o.tolist()

        elif type(o).__name__ == "DataFrame":  # avoid pandas import
            o.columns = o.columns.droplevel("channel")  # flatten MultiIndex
            return o.to_dict(orient="index")

        elif isinstance(o, PhoneNumber):
            return o.e164

        elif o.__class__.__name__ == "ObjectId":
            return str(o)

        elif type(o) is type and o in data_types:
            return data_types[o]

        return json.JSONEncoder.default(self, o)


async def to_json(obj, **kwargs):
    indent = kwargs.pop("indent", 2)
    return json.dumps(obj, cls=Encoder, indent=indent, ignore_nan=True, **kwargs)
