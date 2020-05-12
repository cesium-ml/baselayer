/* Handle incoming websocket messages */

import { SHOW_NOTIFICATION, showNotification } from './components/Notifications';

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
    dispatch(showNotification(note, type));
  }
};


const messageHandler = new MessageHandler();
messageHandler.add(notificationHandler);

export default messageHandler;
