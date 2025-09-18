/* Handle incoming websocket messages */

import {
  SHOW_NOTIFICATION,
  showNotification,
} from "./components/Notifications.jsx";

class MessageHandler {
  /* You have to run `init` before the messageHandler can be used */
  #handlers = [];
  #dispatch = null;
  #getState = null;

  init(dispatch, getState) {
    this.#dispatch = dispatch;
    this.#getState = getState;
  }

  add(handler) {
    this.#handlers.push(handler);
  }

  handle(actionType, payload) {
    // Execute all registered handlers on the incoming message
    this.#handlers.forEach((handler) => {
      handler(actionType, payload, this.#dispatch, this.#getState);
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
