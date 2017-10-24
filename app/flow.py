import zmq
from .json_util import to_json


class Flow(object):
    """Send messages through websocket to frontend

    """
    def __init__(self, socket_path='ipc:///tmp/message_flow_in'):
        self._socket_path = socket_path
        self._ctx = zmq.Context.instance()
        self._bus = self._ctx.socket(zmq.PUSH)
        self._bus.connect(self._socket_path)

    def push(self, username, action_type, payload={}):
        """Push action to specified user over websocket.

        Parameters
        ----------
        username : str
            Username to push websocket message to.  If '*', target all users.
        action_type : str
            Action label for the message; a string identifier used by
            the frontend to distinguish between different types of
            messages.  Example: `cesium/RELOAD_FRONTPAGE`.
        payload : dict
            Payload forwarded to the frontend.  This may contain small
            pieces of data.  Larger result sets should be fetched via
            an API call.

        """
        print('[Flow] Pushing action {} to {}'.format(action_type, username))
        message = [username,
                   to_json({'username': username,
                            'action': action_type,
                            'payload': payload})]
        self._bus.send_multipart([m.encode('utf-8') for m in message])
