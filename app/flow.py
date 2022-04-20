import zmq

from ..log import make_log
from .env import load_env
from .json_util import to_json

env, cfg = load_env()
log = make_log("flow")


class Flow:
    """Send messages through websocket to frontend"""

    def __init__(self, socket_path=cfg["ports.websocket_path_in"]):
        self._socket_path = socket_path
        self._ctx = zmq.Context.instance()
        self._bus = self._ctx.socket(zmq.PUSH)
        self._bus.connect(self._socket_path)

    def push(self, user_id, action_type, payload={}):
        """Push action to specified user over websocket.

        Parameters
        ----------
        user_id : int or str
            User to push websocket message to.  If '*', target all users.
        action_type : str
            Action label for the message; a string identifier used by
            the frontend to distinguish between different types of
            messages.  Example: `cesium/RELOAD_FRONTPAGE`.
        payload : dict
            Payload forwarded to the frontend.  This may contain small
            pieces of data.  Larger result sets should be fetched via
            an API call.

        """
        log(f"Pushing action {action_type} to user {user_id}")
        message = [
            str(user_id),
            to_json(
                {"user_id": user_id, "actionType": action_type, "payload": payload}
            ),
        ]
        self._bus.send_multipart([m.encode("utf-8") for m in message])
