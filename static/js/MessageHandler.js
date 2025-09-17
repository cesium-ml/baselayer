/* Handle incoming websocket messages */

import {
  SHOW_NOTIFICATION,
  showNotification,
} from "./components/Notifications.jsx";

class MessageHandler {
  /* You have to run `init` before the messageHandler can be used */

  constructor() {
    this._handlers = [];
    this._dispatch = null;
    this._getState = null;
  }

  init(dispatch, getState) {
    this._dispatch = dispatch;
    this._getState = getState;
  }

  add(handler) {
    this._handlers.push(handler);
  }

  handle(actionType, payload) {
    // Execute all registered handlers on the incoming message
    this._handlers.forEach((handler) => {
      handler(actionType, payload, this._dispatch, this._getState);
    });
  }
}

const notificationHandler = (actionType, payload, dispatch) => {
  if (actionType === SHOW_NOTIFICATION) {
    const { note, type } = payload;
    let { duration } = payload;
    // if the duration is missing or invalid (negative or too large), use the default
    if (!duration || duration <= 0 || duration >= 30000) {
      duration = 3000;
    }
    dispatch(showNotification(note, type, duration));
  }
};

const messageHandler = new MessageHandler();
messageHandler.add(notificationHandler);

export default messageHandler;
